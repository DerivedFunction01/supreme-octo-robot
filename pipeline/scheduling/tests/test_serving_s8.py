"""The S8 pipeline-side serving (contract 09, pipeline-serving
section): the classification axis, the entry config blocks and
their guarded save, the acked-pings window (G5), and the job
detail projections — each against fixture stores only."""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.request

from server import registry
from server.entries import configblocks
from server.firing.engine import Engine
from server.serving import api
from server.serving import classification as classification_mod
from server.serving import http as http_mod
from tests.helpers import (T0, Clock, agent_yaml, make_home, scripted_yaml,
                           seed_specimen_knob_entry, seed_tracked_fleet,
                           write_body, write_entry)

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KNOB_BLOCK = (
    "config:\n"
    "  version: 1\n"
    "  knobs:\n"
    "    low_gb:\n"
    "      label: Low tier\n"
    "      type: integer\n"
    "      unit: GB\n"
    "      value: 50\n"
    "      min: 1\n"
    "      max: 500\n"
    "    crit_gb:\n"
    "      label: Critical tier\n"
    "      type: integer\n"
    "      unit: GB\n"
    "      value: 45\n"
    "      min: 1\n"
    "      max: 500\n"
    "  constraints:\n"
    "    crit_below_low:\n"
    "      kind: lt\n"
    "      left: crit_gb\n"
    "      right: low_gb\n"
    "      message: The critical tier must sit below the low tier.\n"
)


class ClassificationTests(unittest.TestCase):
    def test_fleet_table_shape(self):
        table = classification_mod._FLEET
        self.assertEqual(len(table), 23)
        audiences = [v[0] for v in table.values()]
        self.assertEqual(audiences.count("operator"), 3)
        self.assertEqual(audiences.count("builtin"), 20)
        families = [v[1] for v in table.values() if v[1]]
        self.assertEqual(len(families), 11)
        for audience, family, open_in in table.values():
            if family:
                self.assertEqual(audience, "builtin")
                self.assertIsNotNone(open_in)
            else:
                self.assertIsNone(open_in)

    def test_representative_rows_and_fallback(self):
        self.assertEqual(
            classification_mod.classify("storage-watch"),
            {"audience": "builtin", "family": None, "open_in": None})
        self.assertEqual(
            classification_mod.classify("colab-store-prune"),
            {"audience": "builtin", "family": "venue", "open_in": "runner"})
        self.assertEqual(
            classification_mod.classify("bridge-drain"),
            {"audience": "builtin", "family": "dispatch",
             "open_in": "dispatch"})
        self.assertEqual(
            classification_mod.classify("memory-index-watchdog"),
            {"audience": "operator", "family": None, "open_in": None})
        # an unlisted id is the operator's own until classified
        self.assertEqual(
            classification_mod.classify("some-future-job"),
            {"audience": "operator", "family": None, "open_in": None})


class ServingBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.values, self.sources = make_home(self.tmp)
        self.clock = Clock(T0)

    def engine(self):
        return Engine(self.values, now_fn=self.clock, inline=True)


class JobViewClassificationTests(ServingBase):
    def test_job_view_carries_the_axis(self):
        write_entry(self.tmp, "storage-watch",
                    scripted_yaml("storage-watch", "/bin/true"))
        engine = self.engine()
        view = api.job_view(engine, engine.entries["storage-watch"],
                            self.clock())
        self.assertEqual(view["audience"], "builtin")
        self.assertIsNone(view["family"])
        self.assertIsNone(view["open_in"])
        detail = api.job_detail(engine, "storage-watch", self.clock())
        self.assertEqual(detail["audience"], "builtin")


class ConfigRegistryTests(ServingBase):
    def _load(self, extra):
        write_entry(self.tmp, "job-cfg",
                    scripted_yaml("job-cfg", "/bin/true", extra=extra))
        return registry.load_dir(os.path.join(self.tmp, "jobs"),
                                 self.values["home"])

    def test_well_formed_block_loads(self):
        entries, errors = self._load(KNOB_BLOCK)
        self.assertEqual(errors, [])
        self.assertIn("job-cfg", entries)

    def test_out_of_range_value_at_rest_rejected(self):
        bad = KNOB_BLOCK.replace("value: 50", "value: 900")
        _entries, errors = self._load(bad)
        self.assertTrue(any("config knob low_gb" in e for e in errors),
                        errors)

    def test_constraint_violated_at_rest_rejected(self):
        bad = KNOB_BLOCK.replace("value: 45", "value: 60")
        _entries, errors = self._load(bad)
        self.assertTrue(any("violated" in e for e in errors), errors)

    def test_unknown_constraint_knob_rejected(self):
        bad = KNOB_BLOCK.replace("left: crit_gb", "left: nope")
        _entries, errors = self._load(bad)
        self.assertTrue(any("unknown knob" in e for e in errors), errors)

    def test_missing_version_stamp_rejected(self):
        bad = KNOB_BLOCK.replace("  version: 1\n", "")
        _entries, errors = self._load(bad)
        self.assertTrue(any("version" in e for e in errors), errors)

    def test_unknown_knob_field_rejected(self):
        bad = KNOB_BLOCK.replace("      unit: GB\n      value: 50",
                                 "      unit: GB\n      bogus: 1\n      value: 50")
        _entries, errors = self._load(bad)
        self.assertTrue(any("unknown or missing fields" in e
                            for e in errors), errors)


class ConfigServingTests(ServingBase):
    def setUp(self):
        super().setUp()
        write_entry(self.tmp, "job-cfg",
                    scripted_yaml("job-cfg", "/bin/true", extra=KNOB_BLOCK))
        write_entry(self.tmp, "job-plain",
                    scripted_yaml("job-plain", "/bin/true"))
        self.engine = self.engine()

    def test_detail_serves_the_config_view(self):
        detail = api.job_detail(self.engine, "job-cfg", self.clock())
        cfg = detail["detail"]["config"]
        self.assertEqual(cfg["version"], 1)
        self.assertEqual([k["key"] for k in cfg["knobs"]],
                         ["low_gb", "crit_gb"])
        self.assertEqual(cfg["knobs"][0],
                         {"key": "low_gb", "label": "Low tier",
                          "type": "integer", "unit": "GB", "value": 50,
                          "min": 1, "max": 500})
        self.assertEqual(cfg["constraints"],
                         [{"kind": "lt", "left": "crit_gb",
                           "right": "low_gb",
                           "message": "The critical tier must sit below "
                                      "the low tier."}])

    def test_knobless_entry_serves_null(self):
        detail = api.job_detail(self.engine, "job-plain", self.clock())
        self.assertIsNone(detail["detail"]["config"])

    def _ops(self):
        return self.engine.ledger.query(kinds=["op"])

    def _file_bytes(self, job_id="job-cfg"):
        with open(os.path.join(self.tmp, "jobs", f"{job_id}.yaml"),
                  "rb") as fh:
            return fh.read()

    def test_save_applies_bumps_and_ledgers(self):
        code, payload = configblocks.save_config(
            self.engine, "job-cfg", 1, {"low_gb": 60}, "scheduler-app")
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["config"]["knobs"][0]["value"], 60)
        # the record on disk moved, and the engine serves it
        entries, errors = registry.load_dir(
            os.path.join(self.tmp, "jobs"), self.values["home"])
        self.assertEqual(errors, [])
        self.assertEqual(entries["job-cfg"].get("config")["version"], 2)
        detail = api.job_detail(self.engine, "job-cfg", self.clock())
        self.assertEqual(detail["detail"]["config"]["version"], 2)
        # one ledgered op event per changed knob
        ops = self._ops()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["op"], "config")
        self.assertEqual(ops[0]["knob"], "low_gb")
        self.assertEqual(ops[0]["old"], 50)
        self.assertEqual(ops[0]["new"], 60)
        self.assertEqual(ops[0]["caller"], "scheduler-app")
        self.assertEqual(ops[0]["status"], "ok")

    def test_save_preserves_the_rest_of_the_entry(self):
        before = self._file_bytes().decode("utf-8")
        code, _payload = configblocks.save_config(
            self.engine, "job-cfg", 1, {"low_gb": 60}, "scheduler-app")
        self.assertEqual(code, 200)
        after = self._file_bytes().decode("utf-8")
        strip = lambda text: "\n".join(  # noqa: E731
            line for line in text.split("\n")
            if not line.startswith(("config:", "  ", "    ", "      ")))
        self.assertEqual(strip(before), strip(after))

    def test_stale_version_refused_no_match(self):
        before = self._file_bytes()
        code, payload = configblocks.save_config(
            self.engine, "job-cfg", 7, {"low_gb": 60}, "scheduler-app")
        self.assertEqual(code, 409)
        self.assertEqual(payload["error"], "no_match")
        self.assertEqual(self._file_bytes(), before)
        self.assertEqual(self._ops(), [])

    def test_out_of_range_refused_whole(self):
        before = self._file_bytes()
        code, payload = configblocks.save_config(
            self.engine, "job-cfg", 1, {"low_gb": 60, "crit_gb": 9999},
            "scheduler-app")
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "bad_request")
        self.assertIn("between 1 and 500", payload["detail"])
        # the valid knob in the same save was NOT applied
        self.assertEqual(self._file_bytes(), before)
        self.assertEqual(self._ops(), [])

    def test_constraint_violation_refused(self):
        code, payload = configblocks.save_config(
            self.engine, "job-cfg", 1, {"crit_gb": 55}, "scheduler-app")
        self.assertEqual(code, 400)
        self.assertEqual(payload["detail"],
                         "The critical tier must sit below the low tier.")

    def test_unknown_knob_and_fraction_refused(self):
        code, payload = configblocks.save_config(
            self.engine, "job-cfg", 1, {"nope": 3}, "scheduler-app")
        self.assertEqual((code, payload["error"]), (400, "bad_request"))
        code, payload = configblocks.save_config(
            self.engine, "job-cfg", 1, {"low_gb": 55.5}, "scheduler-app")
        self.assertEqual(code, 400)
        self.assertIn("whole number", payload["detail"])

    def test_no_change_save_moves_nothing(self):
        before = self._file_bytes()
        code, payload = configblocks.save_config(
            self.engine, "job-cfg", 1, {"low_gb": 50}, "scheduler-app")
        self.assertEqual(code, 200)
        self.assertEqual(payload["version"], 1)
        self.assertEqual(self._file_bytes(), before)
        self.assertEqual(self._ops(), [])

    def test_unknown_job_and_knobless_job(self):
        code, payload = configblocks.save_config(
            self.engine, "job-nope", 1, {"low_gb": 60}, "scheduler-app")
        self.assertEqual((code, payload["error"]), (404, "not_found"))
        code, payload = configblocks.save_config(
            self.engine, "job-plain", 1, {"low_gb": 60}, "scheduler-app")
        self.assertEqual(code, 400)
        self.assertIn("carries no editable config", payload["detail"])


class PingsRecentTests(ServingBase):
    def setUp(self):
        super().setUp()
        write_body(self.tmp, "job-b")
        write_entry(self.tmp, "job-b", agent_yaml("job-b"))
        self.engine = self.engine()

    def _ping(self):
        self.engine.outbox.add_or_coalesce(
            "job-b", self.clock(), "agent-due",
            body_ref="bodies/job-b.md", now=self.clock())
        return self.engine.outbox.pending()[-1]

    def test_empty_window_is_empty(self):
        data = api.pings_recent(self.engine, self.clock())
        self.assertEqual(data["pings"], [])

    def test_acked_window_newest_first_pending_excluded(self):
        first = self._ping()
        self.engine.outbox.ack(first["id"])
        second = self._ping()
        self.engine.outbox.ack(second["id"])
        self._ping()  # left pending — never in the window
        data = api.pings_recent(self.engine, self.clock())
        self.assertEqual([p["id"] for p in data["pings"]],
                         [second["id"], first["id"]])
        self.assertTrue(all(p["state"] == "acked" for p in data["pings"]))
        self.assertTrue(all("acked_at" in p for p in data["pings"]))


class DetailProjectionTests(ServingBase):
    def test_projections_served_where_carried(self):
        extra = (
            "status: suspended\n"
            "suspend_reason: held for the test\n"
            "suspended_on: 2026-11-08\n"
            "self_removal: 'the test removes this entry itself'\n"
            "catalog:\n"
            "  origin: hand\n"
            "  generality: deployment-specific\n"
            "  use_case: file-survival\n"
        )
        write_entry(self.tmp, "job-d",
                    scripted_yaml("job-d", "/bin/true", extra=extra))
        engine = self.engine()
        block = api.job_detail(engine, "job-d", self.clock())["detail"]
        self.assertEqual(block["suspended_on"], "2026-11-08")
        self.assertEqual(block["self_removal"],
                         "the test removes this entry itself")
        self.assertEqual(block["catalog"],
                         {"origin": "hand",
                          "generality": "deployment-specific",
                          "use_case": "file-survival"})

    def test_projections_null_where_absent(self):
        write_entry(self.tmp, "job-plain",
                    scripted_yaml("job-plain", "/bin/true"))
        engine = self.engine()
        block = api.job_detail(engine, "job-plain", self.clock())["detail"]
        self.assertIsNone(block["suspended_on"])
        self.assertIsNone(block["self_removal"])
        self.assertIsNone(block["catalog"])
        self.assertIsNone(block["config"])


class HttpRouteTests(ServingBase):
    """The two new routes on the wire: GET /api/v1/pings/recent
    and POST /api/v1/jobs/<id>/config, against a fixture server
    on an ephemeral port."""

    def setUp(self):
        super().setUp()
        write_body(self.tmp, "job-b")
        write_entry(self.tmp, "job-b", agent_yaml("job-b"))
        write_entry(self.tmp, "job-cfg",
                    scripted_yaml("job-cfg", "/bin/true", extra=KNOB_BLOCK))
        self.engine = self.engine()
        self.server = http_mod.make_server(
            self.engine, self.values, self.sources,
            host="127.0.0.1", port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _call(self, method, path, body=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method=method,
            data=json.dumps(body).encode("utf-8") if body is not None
            else None,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_recent_route_serves_the_acked_window(self):
        self.engine.outbox.add_or_coalesce(
            "job-b", self.clock(), "agent-due",
            body_ref="bodies/job-b.md", now=self.clock())
        ping = self.engine.outbox.pending()[0]
        self.engine.outbox.ack(ping["id"])
        code, payload = self._call("GET", "/api/v1/pings/recent")
        self.assertEqual(code, 200)
        self.assertEqual([p["id"] for p in payload["pings"]], [ping["id"]])

    def test_config_route_round_trip_and_stale_refusal(self):
        code, payload = self._call(
            "POST", "/api/v1/jobs/job-cfg/config",
            {"version": 1, "values": {"low_gb": 60}})
        self.assertEqual(code, 200)
        self.assertEqual(payload["version"], 2)
        code, payload = self._call("GET", "/api/v1/jobs/job-cfg")
        self.assertEqual(code, 200)
        self.assertEqual(payload["detail"]["config"]["version"], 2)
        self.assertEqual(
            payload["detail"]["config"]["knobs"][0]["value"], 60)
        code, payload = self._call(
            "POST", "/api/v1/jobs/job-cfg/config",
            {"version": 1, "values": {"low_gb": 70}})
        self.assertEqual(code, 409)
        self.assertEqual(payload["error"], "no_match")


LIVENESS_FIXTURE = (
    "id: venue-liveness-fixture-session\n"
    "title: 'Liveness check - fixture session'\n"
    "kind: scripted\n"
    "status: active\n"
    "cadence:\n"
    "  type: interval\n"
    "  every: 15m\n"
    "owner: none\n"
    "owner_reason: 'Machine-written fixture: the lease record is "
    "the record of truth and this entry is its derived schedule.'\n"
    "run:\n"
    "  argv:\n"
    "    - python3\n"
    "    - ${REPO}/ops/liveness_check.py\n"
    "    - fixture-session\n"
    "timeout_secs: 120\n"
    "report:\n"
    "  when: on_failure\n"
    "  ok_exit_codes:\n"
    "    - 0\n"
    "escalate_body: bodies/venue-liveness.md\n"
    "state_paths:\n"
    "  - ${WS}/venue/var/liveness-fixture-session.json\n"
    "classification: 'fixed command; local file reads only; when "
    "it speaks is fully determined by its state file and the "
    "exit code'\n"
    "lifetime: until_complete\n"
    "self_removal: 'the lease core deletes this entry in the "
    "same call that deletes the lease record'\n"
)


class LandedRegistryTests(unittest.TestCase):
    """The landed fleet itself, seeded into a fixture home:
    the registry loads but for the one agent-admission
    refusal the census found, every entry classifies, and the
    knob-bearing entries serve the blocks contract 09's
    amendment evidenced (the tracked storage watch, and a
    seeded specimen standing for the overlay's instance
    entry of the same shape). The fleet expectation derives from
    the tracked set (git's index) — provisioned per-deployment
    entries are untracked and never enter, and the bodies the
    entries reference are instance data, stubbed by the seed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tracked_ids = seed_tracked_fleet(self.tmp, PKG_ROOT)
        self.entries, self.errors = registry.load_dir(
            os.path.join(self.tmp, "jobs"), self.tmp)

    def test_registry_loads_clean(self):
        # The tracked fleet loads clean: the one refusal
        # the agent-admission census found
        # (declaration-reconcile, an agent job with no
        # designated executing surface) is resolved by
        # retiring that entry to its Muse cron twin, so
        # no tracked entry stands refused and every
        # tracked entry stands loaded.
        self.assertEqual(self.errors, [])
        self.assertEqual(sorted(self.entries), self.tracked_ids)

    def test_every_entry_classifies(self):
        for job_id in self.entries:
            axis = classification_mod.classify(job_id)
            self.assertIn(axis["audience"], ("operator", "builtin"))

    def test_storage_watch_block(self):
        view = configblocks.view_of(self.entries["storage-watch"])
        self.assertEqual(view["version"], 3)
        by_key = {k["key"]: k for k in view["knobs"]}
        self.assertEqual(by_key["home_low_free_gb"]["value"], 50)
        self.assertEqual(by_key["home_low_free_gb"]["label"],
                         "Low tier — home free space below")
        self.assertEqual(by_key["home_critical_free_gb"]["value"], 45)
        self.assertEqual(view["constraints"][0]["kind"], "lt")

    def test_specimen_knob_block(self):
        # The knob-bearing shape's second specimen: the
        # deployment's own knob-bearing instance entry
        # lives in the untracked overlay, so the fixture
        # home gains the specimen entry (same block shape,
        # generic values) and the view is read from it.
        seed_specimen_knob_entry(self.tmp)
        entries, errors = registry.load_dir(
            os.path.join(self.tmp, "jobs"), self.tmp)
        self.assertEqual(errors, [])
        view = configblocks.view_of(entries["specimen-knob-watchdog"])
        by_key = {k["key"]: k for k in view["knobs"]}
        self.assertEqual(by_key["topic_file_max_bytes"]["value"], 40000)
        self.assertEqual(by_key["topic_per_file_bytes"]["value"], 12000)
        self.assertEqual(view["constraints"], [])

    def test_fleet_carries_the_projected_data(self):
        catalog = self.entries["file-registry-check"].get("catalog")
        self.assertEqual(
            {k: catalog[k] for k in ("origin", "generality", "use_case")},
            {"origin": "hand", "generality": "deployment-specific",
             "use_case": "file-survival"})

    def test_liveness_entry_projects_self_removal(self):
        # Liveness entries are machine-written per live lease —
        # provisioned, never tracked — so the projection is
        # pinned on a seeded fixture entry of the same form:
        # load must carry its self_removal through.
        with tempfile.TemporaryDirectory() as tmp:
            make_home(tmp)
            write_entry(tmp, "venue-liveness-fixture-session",
                        LIVENESS_FIXTURE)
            write_body(tmp, "venue-liveness")
            entries, errors = registry.load_dir(
                os.path.join(tmp, "jobs"), tmp)
            self.assertEqual(errors, [])
            entry = entries["venue-liveness-fixture-session"]
            self.assertEqual(entry.get("lifetime"), "until_complete")
            self.assertTrue(entry.get("self_removal"))


if __name__ == "__main__":
    unittest.main()
