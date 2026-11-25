import os
import tempfile
import unittest

from ops.watches import local_test_watch as watch

WS = "ws"
REPO = "ws/programme-b-wt-addressunit"


class LedgerConsultCase(unittest.TestCase):
    """The ledger consult: an ops-route-covered first sighting
    records OPS-ROUTE and raises nothing; the consult itself
    matches strictly against a scratch ledger."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = watch.STATE
        watch.STATE = os.path.join(self.tmp, "state.json")
        self.old_disp = watch.DISPOSITIONS
        watch.DISPOSITIONS = os.path.join(self.tmp, "dispositions.json")

    def tearDown(self):
        watch.STATE = self.old
        watch.DISPOSITIONS = self.old_disp

    def procs(self):
        return [(["vitest", "run", "src/a.test.ts"], REPO)]

    def test_covered_sighting_is_ops_route_and_opens_nothing(self):
        lookup = lambda finding, at: {"op_id": 7, "caller": "workhorse", "ts": "T0"}
        code, lines = watch.run("/proc", WS, procs=self.procs(),
                                load="1", at="T1", live_count=0,
                                ledger_lookup=lookup)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("LOCAL-EXEC OPS-ROUTE", lines[0])
        self.assertIn("op=7", lines[0])
        record = watch.defects.load_dispositions(watch.DISPOSITIONS)
        self.assertEqual(record.get("dispositions") or {}, {})

    def test_uncovered_sighting_still_warns(self):
        code, lines = watch.run("/proc", WS, procs=self.procs(),
                                load="1", at="T1", live_count=0,
                                ledger_lookup=lambda f, at: None)
        self.assertEqual(len(lines), 1)
        self.assertIn("LOCAL-TEST vitest", lines[0])

    def _scratch_db(self, rows):
        import json as _json
        import sqlite3
        # One file per call: two scratch ledgers, two distinct DBs.
        fd, db = tempfile.mkstemp(dir=self.tmp, suffix=".db")
        os.close(fd)
        con = sqlite3.connect(db)
        con.executescript("CREATE TABLE events (id INTEGER, ts TEXT, "
                          "ts_epoch REAL, kind TEXT, job_id TEXT, "
                          "status TEXT, record TEXT)")
        for op_id, epoch, target in rows:
            con.execute("INSERT INTO events VALUES (?, ?, ?, 'op', "
                        "NULL, 'ok', ?)",
                        (op_id, "2026-11-21T15:55:12+00:00", epoch,
                         _json.dumps({"caller": "workhorse", "target": target})))
        con.commit()
        con.close()
        return db

    def test_ledger_match_is_strict(self):
        from ops.watches import local_test_ledger as ledger_mod
        at = "2026-11-21T15:56:00+00:00"
        import datetime as _dt
        epoch = _dt.datetime(2026, 11, 21, 15, 55, 12,
                             tzinfo=_dt.timezone.utc).timestamp()
        finding = {"argv": ["python3",
                             "/ws/repo/ops/watches/nightly_leg.py"],
                   "cwd": "/ws/repo"}
        db = self._scratch_db([(11, epoch, "cd /ws/repo && python3 "
                                             "/ws/repo/ops/watches/"
                                             "nightly_leg.py")])
        hit = ledger_mod.covered_by_op(finding, at, db_path=db)
        self.assertEqual(hit["op_id"], 11)
        db2 = self._scratch_db([(12, epoch, "cd /ws/repo && python3 "
                                              "check.py")])
        self.assertIsNone(ledger_mod.covered_by_op(finding, at, db_path=db2))
        self.assertIsNone(ledger_mod.covered_by_op(
            finding, at, db_path=os.path.join(self.tmp, "absent.db")))
        self.assertEqual(ledger_mod.op_citation(11, db_path=db)["caller"],
                         "workhorse")
        self.assertIsNone(ledger_mod.op_citation(99, db_path=db))

    def test_adhoc_op_target_does_not_cover(self):
        # An op whose target is an ad-hoc repo-root command is
        # ledgered agent work, not the automation surface:
        # the strict token match alone must not cover it.
        from ops.watches import local_test_ledger as ledger_mod
        at = "2026-11-21T15:56:00+00:00"
        import datetime as _dt
        epoch = _dt.datetime(2026, 11, 21, 15, 55, 12,
                             tzinfo=_dt.timezone.utc).timestamp()
        finding = {"argv": ["python3", "/ws/repo/run_full_gate.py"],
                   "cwd": "/ws/repo"}
        db = self._scratch_db([(11, epoch, "cd /ws/repo && python3 "
                                             "/ws/repo/run_full_gate.py")])
        self.assertIsNone(ledger_mod.covered_by_op(finding, at,
                                                   db_path=db))

    def test_sched_exec_gate_repro_is_not_covered(self):
        # The swallowed-gate miss, pinned: a check.py gate routed
        # through sched exec (bash -c wrapper, the verbatim
        # command as the op target, a programme-slug caller)
        # matched the old consult on every token and was
        # swallowed as ops-route — no disposition, no item.
        # It must now take the defect path end to end.
        from ops.watches import local_test_ledger as ledger_mod
        at = "2026-11-24T17:00:00+00:00"
        import datetime as _dt
        epoch = _dt.datetime(2026, 11, 24, 16, 59, 0,
                             tzinfo=_dt.timezone.utc).timestamp()
        argv = ["var/venv/bin/python", "check.py", "backend/apps",
                "--workers", "2"]
        cwd = "/ws/usmc-pay-monitor-v2"
        target = ("bash -c cd /ws/usmc-pay-monitor-v2 && "
                  "TMPDIR=/ws/usmc-pay-monitor-v2/var/tmp-gate "
                  "var/venv/bin/python check.py backend/apps "
                  "--workers 2")
        db = self._scratch_db([(21, epoch, target)])
        finding = {"argv": argv, "cwd": cwd}
        self.assertIsNone(ledger_mod.covered_by_op(finding, at,
                                                   db_path=db))
        lookup = lambda f, a: ledger_mod.covered_by_op(f, a,
                                                       db_path=db)
        code, lines = watch.run(
            "/proc", "/ws", procs=[(argv, cwd)], load="22.0",
            at=at, live_count=1,
            routes={"threads": {}, "service_patterns": [],
                    "main": None},
            ledger_lookup=lookup)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("LOCAL-EXEC WARNING", lines[0])
        self.assertIn("check.py", lines[0])
        record = watch.defects.load_dispositions(watch.DISPOSITIONS)
        self.assertEqual(len(record.get("dispositions") or {}), 1)


if __name__ == "__main__":
    unittest.main()
