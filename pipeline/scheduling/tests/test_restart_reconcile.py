import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "restart_reconcile",
    os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))),
        "ops", "server-care", "restart_reconcile.py"))
restart_reconcile = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(restart_reconcile)

UTC = timezone.utc
NOW = datetime(2026, 11, 12, 17, 0, 0, tzinfo=UTC)
BOOT_TIME = datetime(2026, 11, 12, 15, 36, 0, tzinfo=UTC)
BOOT_A = "aaaaaaaa-0000-0000-0000-000000000000"
BOOT_B = "bbbbbbbb-0000-0000-0000-000000000000"
CHAT = "chat-00000000-aaaa"


class FakeOutbox:
    def __init__(self):
        self.planted = []

    def add_or_coalesce(self, job_id, due, kind, body_ref=None,
                        detail=None, now=None):
        self.planted.append({
            "job_id": job_id, "kind": kind,
            "body_ref": body_ref, "detail": detail})
        return {"id": "ping-x"}, True


def record(run_id, caller="prog-main", state="polling",
           evidence=None, started=None):
    return {
        "run_id": run_id, "job": "job-" + run_id, "caller": caller,
        "session": "sess-1", "state": state,
        "started_at": (started or NOW - timedelta(hours=3)).isoformat(),
        "last_evidence_at": (evidence or NOW).isoformat(),
    }


class Env:
    """A seeded fake workspace: runs dir, state path, owners."""

    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        self.runs = os.path.join(root, "runs")
        os.makedirs(self.runs)
        self.state = os.path.join(root, "reconcile.json")
        self.owners = os.path.join(root, "owners.yaml")
        with open(self.owners, "w", encoding="utf-8") as fh:
            fh.write(
                "owners:\n  prog-main:\n    chat: \"%s\"\n"
                "namespaces:\n  prog:\n    chat: \"chat-prefix\"\n"
                "prefixes:\n  prog-:\n    chat: \"chat-dash\"\n"
                % CHAT)
        self.outbox = FakeOutbox()

    def put(self, rec):
        with open(os.path.join(self.runs, rec["run_id"] + ".json"),
                  "w", encoding="utf-8") as fh:
            json.dump(rec, fh)

    def seed_boot(self, boot_id):
        with open(self.state, "w", encoding="utf-8") as fh:
            json.dump({"boot_id": boot_id, "reported": {}}, fh)

    def run(self, boot_id=BOOT_A, boot_time=BOOT_TIME, now=NOW):
        return restart_reconcile.run(
            runs_dir=self.runs, state_path=self.state,
            owners_path=self.owners, state_dir=self.tmp.name,
            boot_id=boot_id, boot_time=boot_time, now=now,
            outbox=self.outbox,
            ledger_db=os.path.join(self.tmp.name, "no-ledger.db"))


class RestartLegTests(unittest.TestCase):
    def test_first_run_adopts_boot_and_stays_silent_on_fresh(self):
        env = Env(self)
        env.put(record("r1", evidence=NOW - timedelta(minutes=5)))
        lines = env.run()
        self.assertEqual(lines, [])
        self.assertEqual(env.outbox.planted, [])

    def test_restart_reports_pre_boot_evidence_once(self):
        env = Env(self)
        env.seed_boot(BOOT_A)
        env.put(record("r1", evidence=BOOT_TIME - timedelta(minutes=2)))
        # fresh, post-boot evidence: a live collector — neither leg
        env.put(record("r2", evidence=NOW - timedelta(minutes=5)))
        # post-boot but long-frozen evidence: the stuck leg's catch
        env.put(record("r3", evidence=BOOT_TIME + timedelta(minutes=10)))
        lines = env.run(boot_id=BOOT_B)
        self.assertTrue(any(l.startswith("RECONCILE") for l in lines))
        self.assertEqual(len(env.outbox.planted), 1)
        detail = env.outbox.planted[0]["detail"]
        self.assertEqual(detail["target_chat"], CHAT)
        legs = {i["run_id"]: i["leg"] for i in detail["items"]}
        self.assertEqual(legs, {"r1": "restart", "r3": "stuck"})
        # second pass on the same boot: deduped by episode
        env.outbox.planted.clear()
        self.assertEqual(env.run(boot_id=BOOT_B), [])
        self.assertEqual(env.outbox.planted, [])

    def test_terminal_record_closes_its_episode(self):
        env = Env(self)
        env.seed_boot(BOOT_A)
        env.put(record("r1", evidence=BOOT_TIME - timedelta(minutes=2)))
        env.run(boot_id=BOOT_B)
        env.put(record("r1", state="complete",
                       evidence=BOOT_TIME - timedelta(minutes=2)))
        self.assertEqual(env.run(boot_id=BOOT_B), [])
        state = restart_reconcile.load_state(env.state)
        self.assertNotIn("r1", state["reported"])


class StuckLegTests(unittest.TestCase):
    def test_stale_evidence_reports_without_a_restart(self):
        env = Env(self)
        env.seed_boot(BOOT_A)
        env.put(record("r1", evidence=NOW - timedelta(minutes=45)))
        lines = env.run()
        self.assertTrue(any("ORPHANS" in l for l in lines))
        detail = env.outbox.planted[0]["detail"]
        self.assertEqual(detail["items"][0]["leg"], "stuck")
        # and not again on the next pass
        env.outbox.planted.clear()
        self.assertEqual(env.run(), [])

    def test_stuck_record_rereports_under_a_new_boot(self):
        env = Env(self)
        env.seed_boot(BOOT_A)
        env.put(record("r1", evidence=NOW - timedelta(hours=2)))
        env.run()
        env.outbox.planted.clear()
        later = NOW + timedelta(hours=2)
        lines = env.run(boot_id=BOOT_B,
                        boot_time=NOW + timedelta(hours=1), now=later)
        self.assertTrue(any(l.startswith("RECONCILE") for l in lines))
        detail = env.outbox.planted[0]["detail"]
        self.assertEqual(detail["items"][0]["leg"], "restart")


class OwnerResolutionTests(unittest.TestCase):
    def test_prefix_match_and_unresolved_reporting(self):
        env = Env(self)
        env.seed_boot(BOOT_A)
        env.put(record("r1", caller="prog:lane-7",
                       evidence=NOW - timedelta(hours=2)))
        env.put(record("r2", caller="stranger",
                       evidence=NOW - timedelta(hours=2)))
        lines = env.run()
        planted_chats = {
            p["detail"]["target_chat"] for p in env.outbox.planted}
        self.assertEqual(planted_chats, {"chat-prefix"})
        self.assertTrue(any(
            l.startswith("UNRESOLVED") and "r2" in l for l in lines))

    def test_bare_caller_resolves_by_its_namespace_name(self):
        # A colon-less caller named for its namespace (the
        # specimen-caller shape: orphan records carry the bare
        # caller, the owners file keys it under namespaces)
        # resolves by its full name, not UNRESOLVED.
        env = Env(self)
        env.seed_boot(BOOT_A)
        env.put(record("r1", caller="prog",
                       evidence=NOW - timedelta(hours=2)))
        lines = env.run()
        planted_chats = {
            p["detail"]["target_chat"] for p in env.outbox.planted}
        self.assertEqual(planted_chats, {"chat-prefix"})
        self.assertFalse(any(
            l.startswith("UNRESOLVED") for l in lines))

    def test_dash_prefix_and_collector_at_keying(self):
        env = Env(self)
        env.seed_boot(BOOT_A)
        # dash-family caller resolves through the prefixes map
        env.put(record("r1", caller="prog-lane-9",
                       evidence=NOW - timedelta(hours=2)))
        # collector_at is the heartbeat when present: stale
        # evidence with a fresh collector stamp is attended
        fresh = record("r2", evidence=NOW - timedelta(hours=2))
        fresh["collector_at"] = (NOW - timedelta(minutes=4)).isoformat()
        env.put(fresh)
        # and the converse: fresh evidence, stale collector
        stale = record("r3", evidence=NOW - timedelta(minutes=4))
        stale["collector_at"] = (NOW - timedelta(hours=2)).isoformat()
        env.put(stale)
        lines = env.run()
        self.assertTrue(any("ORPHANS" in l for l in lines))
        by_chat = {}
        for plant in env.outbox.planted:
            by_chat[plant["detail"]["target_chat"]] = [
                i["run_id"] for i in plant["detail"]["items"]]
        self.assertEqual(by_chat.get("chat-dash"), ["r1"])
        self.assertEqual(by_chat.get(CHAT), ["r3"])

    def test_absent_evidence_keys_on_started_at(self):
        # Pre-cure records can carry no last_evidence_at at
        # all (a detached launch whose confirmation read
        # never succeeded); the fallback is started_at, the
        # cure's own initialization semantics.
        env = Env(self)
        env.seed_boot(BOOT_A)
        rec = record("r1", evidence=NOW - timedelta(hours=2))
        del rec["last_evidence_at"]
        rec["started_at"] = (NOW - timedelta(hours=2)).isoformat()
        env.put(rec)
        lines = env.run()
        self.assertTrue(any("ORPHANS" in l for l in lines))
        detail = env.outbox.planted[0]["detail"]
        self.assertEqual(detail["items"][0]["run_id"], "r1")

    def test_unreadable_records_are_counted_not_fatal(self):
        env = Env(self)
        env.seed_boot(BOOT_A)
        with open(os.path.join(env.runs, "broken.json"),
                  "w", encoding="utf-8") as fh:
            fh.write("{not json")
        env.put(record("r1", evidence=NOW - timedelta(hours=2)))
        lines = env.run()
        self.assertIn("unreadable=1", lines[0])


def fired(ledger, job_id, due, started, timeout_secs=3600,
          kind="run_started"):
    """One ledger event for a fire, ts-stamped at `started`
    (the _insert seam the ledger suite itself uses)."""
    rec = {"ts": started.isoformat(), "kind": kind,
           "job_id": job_id, "due": due.isoformat()}
    if kind == "run_started":
        rec["timeout_secs"] = timeout_secs
    if kind == "run":
        rec["status"] = "ok"
    ledger._insert(rec)


class FiredEnv:
    """A seeded fake workspace for the fired population: an
    empty runs dir, a real ledger, owners keyed by job id."""

    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        self.runs = os.path.join(root, "runs")
        os.makedirs(self.runs)
        self.state = os.path.join(root, "reconcile.json")
        self.owners = os.path.join(root, "owners.yaml")
        with open(self.owners, "w", encoding="utf-8") as fh:
            fh.write('owners:\n  daily-job:\n'
                     '    chat: "chat-fired"\n')
        self.ledger_dir = os.path.join(root, "ledger")
        self.ledger = restart_reconcile.Ledger(self.ledger_dir)
        self.outbox = FakeOutbox()

    def seed_boot(self, boot_id):
        with open(self.state, "w", encoding="utf-8") as fh:
            json.dump({"boot_id": boot_id, "reported": {}}, fh)

    def run(self, boot_id=BOOT_A, boot_time=BOOT_TIME, now=NOW):
        return restart_reconcile.run(
            runs_dir=self.runs, state_path=self.state,
            owners_path=self.owners, state_dir=self.tmp.name,
            boot_id=boot_id, boot_time=boot_time, now=now,
            outbox=self.outbox,
            ledger_db=os.path.join(self.ledger_dir, "scheduler.db"),
            ledger=self.ledger)

    def interrupted(self):
        return [r for r in self.ledger.read_all()
                if r["kind"] == "interrupted"]


DUE = datetime(2026, 11, 12, 15, 20, 0, tzinfo=UTC)


class FiredLegTests(unittest.TestCase):
    def test_boot_change_marks_frozen_fire_interrupted(self):
        # (a) a fire started before the boot, never completed:
        # the restart leg marks it interrupted, the boot cause
        # on the record, and one ping surfaces it the same pass.
        env = FiredEnv(self)
        env.seed_boot(BOOT_A)
        fired(env.ledger, "daily-job", DUE,
              BOOT_TIME - timedelta(minutes=10))
        lines = env.run(boot_id=BOOT_B)
        self.assertTrue(any("fired=1" in l for l in lines))
        marks = env.interrupted()
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["job_id"], "daily-job")
        self.assertEqual(marks[0]["due"], DUE.isoformat())
        self.assertEqual(marks[0]["leg"], "restart")
        self.assertIn(BOOT_B, marks[0]["cause"])
        self.assertEqual(len(env.outbox.planted), 1)
        detail = env.outbox.planted[0]["detail"]
        self.assertEqual(detail["target_chat"], "chat-fired")
        item = detail["items"][0]
        self.assertEqual(item["state"], "interrupted")
        self.assertEqual(item["due"], DUE.isoformat())
        self.assertIn(BOOT_B, item["cause"])
        # the mark closes the pair for every later pass
        open_records, closed = restart_reconcile.scan_fired(
            os.path.join(env.ledger_dir, "scheduler.db"))
        self.assertEqual(open_records, [])
        self.assertIn(("daily-job", DUE.isoformat()), closed)

    def test_within_budget_fire_is_untouched(self):
        # (b) a fire inside its timeout budget, same boot:
        # no mark, no ping, no output.
        env = FiredEnv(self)
        env.seed_boot(BOOT_A)
        fired(env.ledger, "daily-job", DUE,
              NOW - timedelta(minutes=5))
        self.assertEqual(env.run(), [])
        self.assertEqual(env.interrupted(), [])
        self.assertEqual(env.outbox.planted, [])

    def test_completed_fire_never_moves(self):
        # (c) a fire whose completion landed is terminal: a
        # boot change does not mark or report it.
        env = FiredEnv(self)
        env.seed_boot(BOOT_A)
        started = BOOT_TIME - timedelta(minutes=10)
        fired(env.ledger, "daily-job", DUE, started)
        fired(env.ledger, "daily-job", DUE,
              started + timedelta(minutes=2), kind="run")
        self.assertEqual(env.run(boot_id=BOOT_B), [])
        self.assertEqual(env.interrupted(), [])
        self.assertEqual(env.outbox.planted, [])

    def test_second_sweep_posts_no_second_ping(self):
        # (d) the same episode re-swept: no second ping, and
        # the mark itself is never written twice.
        env = FiredEnv(self)
        env.seed_boot(BOOT_A)
        fired(env.ledger, "daily-job", DUE,
              BOOT_TIME - timedelta(minutes=10))
        env.run(boot_id=BOOT_B)
        self.assertEqual(env.run(boot_id=BOOT_B), [])
        self.assertEqual(len(env.outbox.planted), 1)
        self.assertEqual(len(env.interrupted()), 1)

    def test_budget_leg_marks_without_a_restart(self):
        # No boot change: a fire past its timeout budget plus
        # the staleness bound, with no completion, is marked
        # under the budget leg.
        env = FiredEnv(self)
        env.seed_boot(BOOT_A)
        fired(env.ledger, "daily-job", DUE,
              NOW - timedelta(hours=3), timeout_secs=120)
        lines = env.run()
        self.assertTrue(any("fired=1" in l for l in lines))
        marks = env.interrupted()
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["leg"], "budget")
        self.assertIn("past budget", marks[0]["cause"])


if __name__ == "__main__":
    unittest.main()
