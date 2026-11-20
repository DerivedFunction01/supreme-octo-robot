import os
import tempfile
import unittest

from server import registry
from server.firing import executor
from server.firing.engine import Engine, LockError
from tests.helpers import (T0, Clock, agent_yaml, make_home, scripted_yaml,
                           write_body, write_entry, write_script)


class EngineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.values, self.sources = make_home(self.tmp)
        self.clock = Clock(T0)
        self.state = os.path.join(self.tmp, "state")

    def engine(self, inline=True):
        return Engine(self.values, now_fn=self.clock, inline=inline)

    def marker_script(self, name, code=""):
        marker = os.path.join(self.tmp, f"{name}.marker")
        script = write_script(self.tmp, f"{name}.py",
                              f"open({marker!r}, 'a').write('x')\n{code}")
        return script, marker

    @staticmethod
    def count(path):
        if not os.path.exists(path):
            return 0
        with open(path, encoding="utf-8") as fh:
            return len(fh.read())

    def ledger(self, engine, kind=None, job_id=None):
        recs = engine.ledger.read_all()
        if kind:
            recs = [r for r in recs if r["kind"] == kind]
        if job_id:
            recs = [r for r in recs if r.get("job_id") == job_id]
        return recs


class EngineTests(EngineCase):
    def test_ec1_catchup_collapses_to_one_run(self):
        script, marker = self.marker_script("a")
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", script))
        engine = self.engine()
        self.clock.advance(minutes=32)  # six grid points pass unrun
        engine.tick()
        self.assertEqual(self.count(marker), 1)
        catchups = self.ledger(engine, "catchup", "job-a")
        self.assertEqual(len(catchups), 1)
        self.assertGreaterEqual(catchups[0]["collapsed"], 5)

    def test_ec4_restart_never_refires(self):
        script, marker = self.marker_script("a")
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", script))
        engine = self.engine()
        self.clock.advance(minutes=6)
        engine.tick()
        self.assertEqual(self.count(marker), 1)
        engine2 = self.engine()  # same state dir: a fresh process
        engine2.tick()
        self.assertEqual(self.count(marker), 1)

    def test_ec5_timeout_isolated(self):
        slow = write_script(self.tmp, "slow.py", "import time\ntime.sleep(10)\n")
        script_b, marker_b = self.marker_script("b")
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", slow, timeout=1))
        write_entry(self.tmp, "job-b", scripted_yaml("job-b", script_b))
        engine = self.engine()
        self.clock.advance(minutes=6)
        engine.tick()
        runs = {r["job_id"]: r for r in self.ledger(engine, "run")}
        self.assertEqual(runs["job-a"]["status"], "timeout")
        self.assertEqual(runs["job-b"]["status"], "ok")
        self.assertEqual(self.count(marker_b), 1)

    def test_ec7_fail_pattern(self):
        script = write_script(self.tmp, "fp.py", "print('verify-failed on item 3')\n")
        text = scripted_yaml("job-a", script, extra_report="  fail_patterns:\n    - verify-failed\n")
        write_entry(self.tmp, "job-a", text)
        engine = self.engine()
        self.clock.advance(minutes=6)
        engine.tick()
        runs = self.ledger(engine, "run", "job-a")
        self.assertEqual(runs[0]["status"], "failure")
        self.assertEqual(runs[0]["matched_pattern"], "verify-failed")
        pings = engine.outbox.pending()
        self.assertEqual(len(pings), 1)
        self.assertEqual(pings[0]["kind"], "escalation")

    def test_ec8_spawn_error_escalates(self):
        text = (
            "id: job-a\ntitle: Test job-a\nkind: scripted\n"
            "cadence:\n  type: interval\n  every: 5m\n"
            "owner: goal:test-goal\n"
            "run:\n  argv:\n    - nonexistent-binary-xyz\n"
            "timeout_secs: 10\nreport:\n  when: on_failure\n  ok_exit_codes:\n    - 0\n"
            "state_paths: []\nclassification: test fixture\n"
        )
        write_entry(self.tmp, "job-a", text)
        engine = self.engine()
        self.clock.advance(minutes=6)
        engine.tick()
        runs = self.ledger(engine, "run", "job-a")
        self.assertEqual(runs[0]["status"], "spawn_error")
        self.assertEqual(engine.outbox.pending()[0]["kind"], "escalation")

    def test_agent_due_ping_coalesces(self):
        write_body(self.tmp, "agent-a")
        write_entry(self.tmp, "agent-a", agent_yaml("agent-a"))
        engine = self.engine()
        self.clock.advance(minutes=6)
        engine.tick()
        self.clock.advance(minutes=12)
        engine.tick()
        pings = engine.outbox.pending()
        self.assertEqual(len(pings), 1)
        self.assertEqual(pings[0]["kind"], "agent-due")
        self.assertEqual(pings[0]["body_ref"], "bodies/agent-a.md")
        self.assertGreaterEqual(pings[0]["coalesced_count"], 2)

    def test_ec16_deleted_entry_voids_pings(self):
        write_body(self.tmp, "agent-a")
        path = write_entry(self.tmp, "agent-a", agent_yaml("agent-a"))
        engine = self.engine()
        self.clock.advance(minutes=6)
        engine.tick()
        self.assertEqual(len(engine.outbox.pending()), 1)
        os.unlink(path)
        engine.tick()
        self.assertEqual(engine.outbox.pending(), [])
        kinds = [r["kind"] for r in engine.ledger.read_all()]
        self.assertIn("ping_voided", kinds)

    def test_ec9_bad_entry_quarantined_last_good_runs(self):
        script, marker = self.marker_script("a")
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", script))
        engine = self.engine()
        write_entry(self.tmp, "job-broken", "id: job-broken\nkind: banana\n")
        self.clock.advance(minutes=6)
        engine.tick()
        self.assertTrue(engine.registry_errors)
        self.assertEqual(engine.health_data()["status"], "registry_error")
        self.assertEqual(self.count(marker), 1)  # last-good registry kept firing
        registry_pings = [p for p in engine.outbox.pending() if p["job_id"] == "scheduler-registry"]
        self.assertEqual(len(registry_pings), 1)

    def test_ec10_corrupt_state_fails_safe(self):
        with open(os.path.join(self.state, "next_due.json"), "w", encoding="utf-8") as fh:
            fh.write("{broken json")
        script, marker = self.marker_script("a")
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", script))
        engine = self.engine()
        self.assertIsNotNone(engine.state_error)
        engine.tick()
        self.assertEqual(self.count(marker), 0)
        self.assertEqual(engine.health_data()["status"], "state_error")

    def test_ec11_single_instance_lock(self):
        engine = self.engine()
        engine.acquire_lock()
        try:
            other = self.engine()
            with self.assertRaises(LockError):
                other.acquire_lock()
        finally:
            engine.release_lock()
        other = self.engine()
        other.acquire_lock()
        other.release_lock()

    def test_stale_lock_takeover_writes_exact_pid(self):
        # Regression: the takeover branch opened the lock
        # file without O_TRUNC, so a shorter pid written
        # over a longer stale (dead) pid left trailing
        # digits — the file then named a pid that never
        # existed (live specimen: lock read 182105 while
        # the server ran as 1821). The file must end up
        # holding exactly the acquirer's pid.
        import subprocess
        dead = subprocess.Popen(["true"])
        dead.wait()
        stale = str(dead.pid)
        mine = str(os.getpid())
        while len(stale) <= len(mine):
            stale += "9"
        lock_path = os.path.join(self.state, "server.lock")
        with open(lock_path, "w", encoding="utf-8") as fh:
            fh.write(stale)
        engine = self.engine()
        engine.acquire_lock()
        try:
            with open(lock_path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), mine)
        finally:
            engine.release_lock()

    def test_ec15_activation_after_proof_run_no_double_fire(self):
        script, marker = self.marker_script("a")
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", script))
        engine = self.engine()
        # the Step 5 proof run: executed by hand, immediately after
        # the live cron's run, before the entry goes active
        entry = engine.entries["job-a"]
        result = executor.run_entry(entry, T0, 65536)
        self.assertEqual(result.status, "ok")
        self.assertEqual(self.count(marker), 1)
        engine.tick()  # before the first grid point: no fire
        self.assertEqual(self.count(marker), 1)
        self.clock.advance(minutes=5)
        engine.tick()  # at the grid point: exactly one fire
        self.assertEqual(self.count(marker), 2)

    def test_entry_presence_is_admission_and_fires(self):
        # Contract 13 (amendment 3): the migration field family
        # does not exist in this format — an entry stands in the
        # registry only by being written through the one writer
        # path, so presence is admission: the entry seeds a due
        # and fires on its grid with no admission field at all.
        # (The pinned engine's migrated-only clause is
        # deliberately not carried.)
        script, marker = self.marker_script("a")
        text = scripted_yaml("job-a", script)
        write_entry(self.tmp, "job-a", text)
        engine = self.engine()
        self.assertIn("job-a", engine._next_due)
        self.clock.advance(minutes=30)
        engine.tick()
        self.assertGreaterEqual(self.count(marker), 1)

    def test_suspended_entry_never_fires(self):
        script, marker = self.marker_script("a")
        text = scripted_yaml("job-a", script).replace(
            "kind: scripted\n",
            "kind: scripted\nstatus: suspended\nsuspend_reason: test pause\nsuspended_on: 2026-10-31\n")
        write_entry(self.tmp, "job-a", text)
        engine = self.engine()
        self.clock.advance(minutes=30)
        engine.tick()
        self.assertEqual(self.count(marker), 0)

    def test_no_self_overlap_skips_point(self):
        script = write_script(self.tmp, "slow.py",
                              "import time\nopen(%r, 'a').write('x')\ntime.sleep(5)\n"
                              % os.path.join(self.tmp, "slow.marker"))
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", script, every="1m", timeout=30))
        engine = self.engine(inline=False)
        self.clock.advance(minutes=1)
        engine.tick()  # dispatches the long run in a thread
        self.clock.advance(minutes=2)
        engine.tick()  # next points fall while it is still running
        skips = self.ledger(engine, "skipped_overlap", "job-a")
        self.assertGreaterEqual(len(skips), 1)
        engine.wait_idle(timeout=15)
        self.assertEqual(self.count(os.path.join(self.tmp, "slow.marker")), 1)

    def test_report_always_pings(self):
        script, _marker = self.marker_script("a")
        text = scripted_yaml("job-a", script, report="  when: always\n")
        write_entry(self.tmp, "job-a", text)
        engine = self.engine()
        self.clock.advance(minutes=6)
        engine.tick()
        pings = engine.outbox.pending()
        self.assertEqual(len(pings), 1)
        self.assertEqual(pings[0]["kind"], "report")

    def test_on_output_quiet_then_reportable(self):
        quiet = write_script(self.tmp, "quiet.py", "print('nothing due')\n")
        loud = write_script(self.tmp, "loud.py", "print('re-drove entry X: ok')\n")
        extra = "  quiet_patterns:\n    - nothing due\n"
        write_entry(self.tmp, "job-q", scripted_yaml(
            "job-q", quiet, report="  when: on_output\n", extra_report=extra))
        write_entry(self.tmp, "job-l", scripted_yaml(
            "job-l", loud, report="  when: on_output\n", extra_report=extra))
        engine = self.engine()
        self.clock.advance(minutes=6)
        engine.tick()
        pings = engine.outbox.pending()
        self.assertEqual(len(pings), 1)
        self.assertEqual(pings[0]["job_id"], "job-l")
        self.assertEqual(pings[0]["kind"], "report")


class ExecutorTests(unittest.TestCase):
    def test_ec6_output_flood_tail_capped_not_killed(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = write_script(tmp, "flood.py", "print('x' * 300000)\n")
            entry = registry.validate(
                "job-a",
                registry.parse_yaml(scripted_yaml("job-a", script), where="job-a.yaml"),
                tmp, where="job-a.yaml")
            result = executor.run_entry(entry, T0, capture_cap=1024)
            self.assertEqual(result.status, "ok")
            self.assertLessEqual(len(result.stdout_tail), 1024)


if __name__ == "__main__":
    unittest.main()
