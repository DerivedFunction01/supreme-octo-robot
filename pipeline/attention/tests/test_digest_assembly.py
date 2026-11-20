"""The persisted digest assembly's pins (perf lane L-B):
the stored payload is byte-identical to the per-request
build it replaces, at the same state and the same now;
every state key the digest can read moves the assembly's
fingerprint, and every writer in the battery invalidates
by landing in the state; a fresh assembly is not
recomputed, a stale or invalidated one is; and a
recompute never holds the request lock while it builds,
so a glance read proceeds during one.

Determinism: one pinned now, fake run records in a temp
dir, a push item naming a repo that does not exist (its
fact derives without git), fixture stores only — no
wall clock, no sleeping, no polling; thread coordination
rides events the fakes set.
"""

import copy
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention import server as server_mod  # noqa: E402
from attention.infra import sample_data, store as store_mod  # noqa: E402
from attention.infra.store import JsonFileStore, MemoryStore  # noqa: E402
from attention.services.dispatch import dispatch as dispatch_mod  # noqa: E402
from attention.services.reads import digest as digest_mod  # noqa: E402
from attention.services.reads import model  # noqa: E402
from attention.services.waits import facts as facts_mod  # noqa: E402
from attention.services.writes import ingest, writes  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone(timedelta(hours=-5)))


def _settings(tmp, **overrides):
    values = {
        "run_records_dir": Path(tmp) / "records",
        "digest_max_age_s": 60.0,
        "digest_poll_s": 0.02,
    }
    values.update(overrides)
    return Settings(**values)


def _fake_records(tmp):
    records = Path(tmp) / "records"
    records.mkdir(parents=True, exist_ok=True)
    (records / "20261116T170000Z-r1.json").write_text(
        json.dumps(
            {
                "id": "r1",
                "caller": "workhorse",
                "session": "flint-1",
                "state": "running",
                "started_at": "2026-11-16T16:30:00+00:00",
                "finished_at": None,
            }
        ),
        encoding="utf-8",
    )
    (records / "20261116T165500Z-r2.json").write_text(
        json.dumps(
            {
                "id": "r2",
                "caller": "edgar-lane",
                "session": "solar-2",
                "state": "finished",
                "started_at": "2026-11-16T16:00:00+00:00",
                "finished_at": "2026-11-16T16:20:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def _fixture_state():
    state = sample_data.sample_state(NOW)
    state["items"].append(
        {
            "id": "demo-ghost-push",
            "handle": "@xbrl",
            "kind": "push_needed",
            "title": "Push the ghost fix",
            "status_code": "BLOCKED-OWNER",
            "source_ref": "demo-ghost-push",
            "source_url": "",
            "clears_at_source": True,
            "due_at": None,
            "waiting_since": NOW - timedelta(hours=3),
            "need": "owner_actionable",
            "tier": "digest",
            "triage": "open",
            "snooze_return_at": None,
            "snooze_on_activity": False,
            "resume_note": None,
            "repo": "ghost-repo",
        }
    )
    state["digest_wb_snapshot"] = {
        "at": NOW.isoformat(),
        "parked": {
            "available": True,
            "reason": None,
            "skipped_projects": [],
            "plans": [
                {
                    "project": "edgar-sec",
                    "path": "2026-11-02-parked-plan.md",
                    "title": "Parked plan",
                }
            ],
        },
        "parked_counts": {"edgar-sec": 1},
        # The T-form collect_wb_facts writes: the store's
        # load decodes it back to a datetime, and the
        # snapshot reader normalizes both forms (the
        # WbFactsFromSnapshotTests below pin the shapes).
        "modified": {"edgar-sec": "2026-11-16T11:00:00-05:00"},
        "wb_topics": {},
    }
    state["capacity_snapshot"] = {
        "at": NOW,
        "sessions": [
            {"session": "flint-1", "shape": None, "high_mem": True},
            {"session": "solar-2", "shape": None, "high_mem": True},
        ],
        "session_runs": {"flint-1": 1, "solar-2": 0},
        "idle_since": {"solar-2": NOW - timedelta(minutes=45)},
        "specs": [],
    }
    return state


def _served_bytes(payload) -> str:
    """The mount's serialization, exactly: prepare with
    _jsonable, dump with plain json.dumps."""
    return json.dumps(server_mod._jsonable(payload))


class AssemblyEqualityTests(unittest.TestCase):
    def test_digest_payload_byte_identical_through_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            settings = _settings(tmp)
            facts = facts_mod.derive_push_facts(
                _fixture_state(), NOW, workspace=Path(tmp)
            )
            self.assertEqual(facts["demo-ghost-push"]["state"], "gone")
            old = digest_mod.build_digest(
                _fixture_state(), settings, NOW, copy.deepcopy(facts)
            )
            # The new path, end to end: assemble over a
            # store-loaded state, persist the record
            # through the real file store, load it back,
            # and serve what the route would serve.
            store = JsonFileStore(Path(tmp) / "state.json")
            store.save_state(_fixture_state())
            working = store.load_state()
            record = server_mod.assemble_digest(
                working, settings, NOW, push_facts=copy.deepcopy(facts)
            )
            working["digest_assembly"] = record
            store.save_state(working)
            served = store.load_state()["digest_assembly"]["payload"]
            self.assertEqual(_served_bytes(old), _served_bytes(served))

    def test_glance_byte_identical_with_stored_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            settings = _settings(tmp)
            live_facts = facts_mod.derive_push_facts(
                _fixture_state(), NOW, workspace=Path(tmp)
            )
            old = model.build_glance(
                _fixture_state(), settings, NOW, copy.deepcopy(live_facts)
            )
            record = server_mod.assemble_digest(
                _fixture_state(), settings, NOW, push_facts=copy.deepcopy(live_facts)
            )
            new = model.build_glance(
                _fixture_state(), settings, NOW, record["push_facts"]
            )
            self.assertEqual(_served_bytes(old), _served_bytes(new))


class WbFactsFromSnapshotTests(unittest.TestCase):
    """The snapshot reader's stamp shapes: collect writes
    T-form ISO strings, the store's load decodes T-form
    strings back to datetimes, and the reader takes both
    — plus the space-separated string form and the empty
    shapes. Before the cure, a round-tripped snapshot
    whose plans carried a parseable modified stamp raised
    TypeError in the reader (datetime.fromisoformat on a
    datetime), so the digest died on the first workbench
    plan modification the collector ever recorded."""

    STAMP = datetime(2026, 11, 16, 11, 0, tzinfo=timezone(timedelta(hours=-5)))

    def _state(self, modified, topics):
        return {
            "digest_wb_snapshot": {
                "at": NOW.isoformat(),
                "parked": {
                    "available": True,
                    "reason": None,
                    "skipped_projects": [],
                    "plans": [
                        {
                            "project": "edgar-sec",
                            "path": "2026-11-02-parked-plan.md",
                            "title": "Parked plan",
                        }
                    ],
                },
                "parked_counts": {"edgar-sec": 1},
                "modified": modified,
                "wb_topics": topics,
            }
        }

    def _topic(self, plan_modified):
        return {
            "edgar": {
                "todos_total": 5,
                "todos_done": 2,
                "plan_modified": plan_modified,
            }
        }

    def test_round_tripped_stamps_read_as_datetimes(self):
        state = self._state(
            {"edgar-sec": self.STAMP.isoformat()},
            self._topic(self.STAMP.isoformat()),
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonFileStore(Path(tmp) / "state.json")
            store.save_state(state)
            loaded = store.load_state()
        # The mechanism: the store's decode restored the
        # T-form strings to datetimes on load.
        self.assertIsInstance(
            loaded["digest_wb_snapshot"]["modified"]["edgar-sec"], datetime
        )
        parked, counts, modified, topics = digest_mod._wb_facts_from_snapshot(
            loaded, NOW
        )
        self.assertEqual(modified, {"edgar-sec": self.STAMP})
        self.assertEqual(topics["edgar"]["plan_modified"], self.STAMP)
        self.assertEqual(topics["edgar"]["todos_total"], 5)
        self.assertEqual(topics["edgar"]["todos_done"], 2)
        self.assertEqual(counts, {"edgar-sec": 1})
        self.assertEqual(parked["plans"][0]["age_days"], 14)

    def test_fresh_string_stamps_read_the_same(self):
        state = self._state(
            {"edgar-sec": self.STAMP.isoformat()},
            self._topic(self.STAMP.isoformat()),
        )
        _, _, modified, topics = digest_mod._wb_facts_from_snapshot(state, NOW)
        self.assertEqual(modified, {"edgar-sec": self.STAMP})
        self.assertEqual(topics["edgar"]["plan_modified"], self.STAMP)

    def test_space_separated_string_stamps_read_the_same(self):
        # The form that survives the store's decode as a
        # string (its separator at position 10 is not "T").
        space_form = "2026-11-16 11:00:00-05:00"
        state = self._state({"edgar-sec": space_form}, self._topic(space_form))
        _, _, modified, topics = digest_mod._wb_facts_from_snapshot(state, NOW)
        self.assertEqual(modified, {"edgar-sec": self.STAMP})
        self.assertEqual(topics["edgar"]["plan_modified"], self.STAMP)

    def test_empty_and_missing_shapes(self):
        state = self._state({}, self._topic(None))
        _, counts, modified, topics = digest_mod._wb_facts_from_snapshot(state, NOW)
        self.assertEqual(modified, {})
        self.assertEqual(counts, {"edgar-sec": 1})
        self.assertIsNone(topics["edgar"]["plan_modified"])
        state = self._state({}, self._topic(""))
        _, _, _, topics = digest_mod._wb_facts_from_snapshot(state, NOW)
        self.assertIsNone(topics["edgar"]["plan_modified"])
        bare = self._state({}, {})
        del bare["digest_wb_snapshot"]["modified"]
        del bare["digest_wb_snapshot"]["wb_topics"]
        _, _, modified, topics = digest_mod._wb_facts_from_snapshot(bare, NOW)
        self.assertEqual(modified, {})
        self.assertEqual(topics, {})


class FingerprintTests(unittest.TestCase):
    def test_every_state_key_but_the_assemblys_own_moves_it(self):
        state = _fixture_state()
        for key in store_mod.empty_state():
            state.setdefault(key, None)
        baseline = server_mod.digest_fingerprint(state)
        for key in sorted(state):
            mutated = copy.deepcopy(state)
            mutated[key] = {"__battery__": key}
            moved = server_mod.digest_fingerprint(mutated) != baseline
            if key in server_mod._ASSEMBLY_KEYS:
                self.assertFalse(moved, f"{key} must not move the fingerprint")
            else:
                self.assertTrue(moved, f"{key} must move the fingerprint")

    def test_writer_battery_invalidates(self):
        def send(state, send_id):
            state["sends"].append(
                {
                    "id": send_id,
                    "handle": "@xbrl",
                    "at": NOW,
                    "rule_id": None,
                    "wait_id": None,
                    "target": "main",
                    "template": "status",
                    "version": 1,
                    "attempt": 1,
                    "presence": "active",
                    "text": "battery",
                }
            )

        def tail(state):
            state["handler_status"]["@xbrl"] = {
                "status_code": "BLOCKED-OWNER",
                "summary": "Battery tail holder",
                "at": NOW - timedelta(hours=1),
                "owner_waiting": {
                    "label": "Battery deliverable",
                    "commissioned_at": NOW - timedelta(hours=2),
                },
                "tail": [
                    {
                        "kind": "followup",
                        "title": "Battery tail item",
                        "owner": "owner",
                        "at": NOW - timedelta(hours=1),
                    }
                ],
            }

        battery = [
            ("historical_status", None, lambda s: s["handler_status"].update(
                {"@xbrl": {"status_code": "WORKING",
                           "summary": "Battery status", "at": NOW,
                           "provenance": "commission"}}
            )),
            ("upsert_item", None, lambda s: ingest.upsert_item(
                s,
                {"handle": "@xbrl", "source_ref": "battery-1",
                 "kind": "defect", "title": "Battery item"},
                NOW,
            )),
            ("resolve_item", None, lambda s: ingest.resolve_item(
                s, "demo-wedge", {"resolution": "done"}
            )),
            ("post_wait", None, lambda s: ingest.post_wait(
                s,
                {"handle": "@panel", "wait_class": "lease_renewal",
                 "summary": "Battery wait"},
                NOW,
            )),
            ("promote_tail_items", tail, lambda s: ingest.promote_tail_items(s, NOW)),
            ("ingest_report_pings", None, lambda s: ingest.ingest_report_pings(
                s,
                [{"id": "ping-batt", "kind": "report",
                  "title": "Battery ping", "caller": "workhorse"}],
                NOW,
            )),
            ("set_presence", None, lambda s: writes.set_presence(
                s, {"mode": "away", "expires_at": None}
            )),
            ("set_digest_prefs", None, lambda s: writes.set_digest_prefs(
                s, {"window_time": "12:30", "window_enabled": False}
            )),
            ("add_rule", None, lambda s: writes.add_rule(
                s, {"id": "battery-rule", "match": {},
                    "action": {"type": "surface"}}
            )),
            ("add_status_code", None, lambda s: writes.add_status_code(
                s, {"code": "BATTERY", "short": "BAT", "label": "Battery",
                    "need": "owner_actionable"}
            )),
            ("add_item_kind", None, lambda s: writes.add_item_kind(
                s, {"kind": "battery_kind", "label": "Battery kind"}
            )),
            ("register_handler", None, lambda s: writes.register_handler(
                s, {"handle": "@battery", "label": "Battery lane"}
            )),
            ("upsert_programme", None, lambda s: writes.upsert_programme(
                s, {"slug": "battery", "label": "Battery programme"}
            )),
            ("mute_type", None, lambda s: writes.mute_type(
                s, "@xbrl", {"kind": "defect"}
            )),
            ("unmute_type", None, lambda s: writes.unmute_type(
                s, "@workbench-viewer", {"kind": "fyi"}
            )),
            ("record_dispatch_failure", lambda s: send(s, "s-x"),
             lambda s: writes.record_dispatch_failure(
                 s, {"send_id": "s-x", "consumer": "battery",
                     "reason": "boom"}, NOW
             )),
            ("record_verification", None, lambda s: writes.record_verification(
                s, {"handle": "@workbench-viewer", "verdict": "verified"}, NOW
            )),
            ("dispatch_claim", lambda s: send(s, "s-batt"),
             lambda s: dispatch_mod.claim(
                 s, "s-batt", {"consumer": "battery"},
                 _settings("."), NOW
             )),
            ("dispatch_ack", lambda s: (
                send(s, "s-batt"),
                dispatch_mod.claim(s, "s-batt", {"consumer": "battery"},
                                   _settings("."), NOW),
            ), lambda s: dispatch_mod.ack(
                s, "s-batt", {"consumer": "battery",
                              "delivery_ref": "msg-1"}, NOW
            )),
            ("dispatch_suppress", lambda s: send(s, "s-batt"),
             lambda s: dispatch_mod.suppress(
                 s, "s-batt", {"reason": "moot"}, NOW
             )),
        ]
        for name, setup, writer in battery:
            with self.subTest(writer=name):
                state = _fixture_state()
                if setup:
                    setup(state)
                before = server_mod.digest_fingerprint(state)
                writer(state)
                after = server_mod.digest_fingerprint(state)
                self.assertNotEqual(before, after, f"{name} did not invalidate")


class EpochStoreTests(unittest.TestCase):
    def test_saves_advance_the_epoch_loads_do_not(self):
        store = server_mod._EpochStore(MemoryStore(_fixture_state()))
        self.assertEqual(store.epoch, 0)
        store.load_state()
        self.assertEqual(store.epoch, 0)
        store.save_state(store.load_state())
        self.assertEqual(store.epoch, 1)
        store.save_state(store.load_state())
        self.assertEqual(store.epoch, 2)


class PassTests(unittest.TestCase):
    def _store(self):
        return server_mod._EpochStore(MemoryStore(_fixture_state()))

    def test_pass_lands_a_current_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            settings = _settings(tmp)
            store = self._store()
            lock = threading.Lock()
            self.assertTrue(server_mod._digest_pass(store, settings, lock, NOW))
            state = store.load_state()
            record = state["digest_assembly"]
            self.assertEqual(
                record["fingerprint"], server_mod.digest_fingerprint(state)
            )
            self.assertEqual(record["assembled_at"], NOW.isoformat())
            expected = digest_mod.build_digest(
                _fixture_state(),
                settings,
                NOW,
                facts_mod.derive_push_facts(_fixture_state(), NOW),
            )
            self.assertEqual(
                _served_bytes(expected), _served_bytes(record["payload"])
            )

    def test_fresh_assembly_is_not_recomputed_stale_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            settings = _settings(tmp)
            store = self._store()
            lock = threading.Lock()
            self.assertTrue(server_mod._digest_pass(store, settings, lock, NOW))
            young = NOW + timedelta(seconds=30)
            self.assertFalse(server_mod._digest_pass(store, settings, lock, young))
            stale = NOW + timedelta(seconds=61)
            self.assertTrue(server_mod._digest_pass(store, settings, lock, stale))
            record = store.load_state()["digest_assembly"]
            self.assertEqual(record["assembled_at"], stale.isoformat())

    def test_write_between_passes_recomputes_and_reflects(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            settings = _settings(tmp)
            store = self._store()
            lock = threading.Lock()
            self.assertTrue(server_mod._digest_pass(store, settings, lock, NOW))
            state = store.load_state()
            writes.set_digest_prefs(
                state, {"window_time": "12:30", "window_enabled": False}
            )
            store.save_state(state)
            self.assertTrue(server_mod._digest_pass(store, settings, lock, NOW))
            record = store.load_state()["digest_assembly"]
            self.assertEqual(
                record["payload"]["window"]["enabled_times"], ["07:30", "17:30"]
            )

    def test_recompute_never_holds_the_request_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            settings = _settings(tmp)
            store = self._store()
            lock = threading.Lock()
            computing = threading.Event()
            release = threading.Event()
            real_build = digest_mod.build_digest

            def blocking_build(state, settings_, now, facts=None):
                computing.set()
                release.wait()
                return real_build(state, settings_, NOW, facts or {})

            digest_mod.build_digest = blocking_build
            outcome = []
            try:
                worker = threading.Thread(
                    target=lambda: outcome.append(
                        server_mod._digest_pass(store, settings, lock, NOW)
                    ),
                    daemon=True,
                )
                worker.start()
                self.assertTrue(computing.wait(timeout=10))
                # The glance computation proceeds while the
                # digest build is in flight, and the request
                # lock is free to take — the build holds
                # neither.
                glance = model.build_glance(_fixture_state(), settings, NOW, {})
                self.assertEqual(glance["contract"], "api/1")
                self.assertTrue(lock.acquire(blocking=False))
                lock.release()
            finally:
                release.set()
                digest_mod.build_digest = real_build
            worker.join(timeout=10)
            self.assertEqual(outcome, [True])
            self.assertIsNotNone(store.load_state()["digest_assembly"])


class LoopTests(unittest.TestCase):
    def test_loop_assembles_on_start_and_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            settings = _settings(tmp)
            landed = threading.Event()
            invalidated = threading.Event()
            target = {"fingerprint": None}

            class ProbeStore(MemoryStore):
                def save_state(self, state):
                    super().save_state(state)
                    record = state.get("digest_assembly") or {}
                    if record.get("payload"):
                        landed.set()
                        if record["fingerprint"] == target["fingerprint"]:
                            invalidated.set()

            inner = ProbeStore(_fixture_state())
            store = server_mod._EpochStore(inner)
            lock = threading.Lock()
            stop = threading.Event()
            worker = threading.Thread(
                target=server_mod._digest_loop,
                args=(stop, store, settings, lock),
                daemon=True,
            )
            worker.start()
            try:
                self.assertTrue(landed.wait(timeout=10))
                state = store.load_state()
                writes.set_presence(state, {"mode": "away", "expires_at": None})
                target["fingerprint"] = server_mod.digest_fingerprint(state)
                store.save_state(state)
                self.assertTrue(invalidated.wait(timeout=10))
            finally:
                stop.set()
                worker.join(timeout=10)


class MountRouteTests(unittest.TestCase):
    def _serve(self, tmp, state):
        path = Path(tmp) / "state.json"
        JsonFileStore(path).save_state(state)
        settings = Settings(
            data_path=path,
            host="127.0.0.1",
            port=0,
            run_records_dir=Path(tmp) / "records",
        )
        store = server_mod.make_store(settings)
        mount, _workers = server_mod.build_mount(settings, store)
        listener = server_mod.serving.Listener(mount, "127.0.0.1", 0)
        thread = threading.Thread(target=listener.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(listener.shutdown)
        self.addCleanup(listener.server_close)
        return listener.server_address[1]

    def call(self, port, path):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_digest_route_serves_the_stored_payload_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            state = _fixture_state()
            marker = {"contract": "api/1", "marker": "stored-assembly"}
            state["digest_assembly"] = {
                "fingerprint": "pinned",
                "assembled_at": NOW.isoformat(),
                "push_facts": {},
                "payload": marker,
            }
            port = self._serve(tmp, state)
            status, payload = self.call(port, "/api/v1/digest")
            self.assertEqual(status, 200)
            self.assertEqual(payload, marker)
            status, payload = self.call(port, "/api/v1/glance")
            self.assertEqual(status, 200)
            self.assertEqual(payload["contract"], "api/1")

    def test_digest_route_falls_back_to_a_live_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            _fake_records(tmp)
            port = self._serve(tmp, _fixture_state())
            status, payload = self.call(port, "/api/v1/digest")
            self.assertEqual(status, 200)
            self.assertEqual(payload["contract"], "api/1")
            self.assertIn("sections", payload)
            self.assertIn("staffing", payload)


if __name__ == "__main__":
    unittest.main()
