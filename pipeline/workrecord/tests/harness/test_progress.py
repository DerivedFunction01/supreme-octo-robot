"""Progress derivation tests (progress-schedules plan,
step 2): lib/progress.py reads the arming fields the
writers plant (lib/writes/bundles.py) and the checkpoint lines
in todo bodies, and derives missed checks + the stall
verdict at read time — plus the `wb progress` JSON the
platform driver consumes."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from lib.plans import bundles as bundle_parser  # noqa: E402
from lib.writes import bundles as bundle_mod  # noqa: E402
from lib import progress  # noqa: E402

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def armed_todo(**over):
    todo = {
        "id": "t-01K8Q00000000000000000000A",
        "title": "Long work",
        "status": "doing",
        "bundle": "2026-10-30-work",
        "archived": False,
        "path": "2026-10-30-work/todos/t-a.md",
        "progress_check": "30m",
        "progress_armed": "2026-10-30T11:30:00+00:00",
        "body": "",
    }
    todo.update(over)
    return todo


class TestTodoProgress(unittest.TestCase):
    def test_unarmed_todo_has_no_block(self):
        todo = armed_todo(progress_check=None,
                          progress_armed=None)
        self.assertIsNone(progress.todo_progress(
            todo, now=NOW))

    def test_freshly_armed_is_not_stalled(self):
        block = progress.todo_progress(armed_todo(),
                                       now=NOW)
        self.assertEqual(block["missed_checks"], 1)
        self.assertFalse(block["stalled"])
        self.assertEqual(block["interval_seconds"], 1800.0)
        self.assertEqual(block["last_activity"],
                         "2026-10-30T11:30:00+00:00")
        self.assertIsNone(block["last_checkpoint"])

    def test_two_missed_checks_is_stalled(self):
        block = progress.todo_progress(
            armed_todo(
                progress_armed="2026-10-30T10:00:00+00:00"),
            now=NOW)
        self.assertEqual(block["missed_checks"], 4)
        self.assertTrue(block["stalled"])

    def test_exactly_two_intervals_is_stalled(self):
        block = progress.todo_progress(
            armed_todo(
                progress_armed="2026-10-30T11:00:00+00:00"),
            now=NOW)
        self.assertEqual(block["missed_checks"], 2)
        self.assertTrue(block["stalled"])

    def test_done_todo_is_never_stalled(self):
        # The zombie-stall cure: the
        # derivation reads status before age. A done
        # todo's missed count stays the factual age of
        # its record, but the verdict never fires — its
        # last checkpoint being its done flip is its
        # history, not a stall (refresh-step-6-verdict-v2,
        # pinged STALLED in two watch passes after it
        # flipped done).
        block = progress.todo_progress(
            armed_todo(
                status="done",
                progress_armed="2026-10-30T10:00:00+00:00"),
            now=NOW)
        self.assertEqual(block["missed_checks"], 4)
        self.assertFalse(block["stalled"])

    def test_blocked_todo_is_never_stalled(self):
        block = progress.todo_progress(
            armed_todo(
                status="blocked",
                progress_armed="2026-10-30T10:00:00+00:00"),
            now=NOW)
        self.assertEqual(block["missed_checks"], 4)
        self.assertFalse(block["stalled"])

    def test_archived_todo_is_never_stalled(self):
        block = progress.todo_progress(
            armed_todo(
                archived=True,
                progress_armed="2026-10-30T10:00:00+00:00"),
            now=NOW)
        self.assertEqual(block["missed_checks"], 4)
        self.assertFalse(block["stalled"])

    def test_checkpoint_resets_activity(self):
        body = ("Working.\n\n"
                "progress-checkpoint: "
                "2026-10-30T11:50:00+00:00 — halfway.\n")
        block = progress.todo_progress(
            armed_todo(
                progress_armed="2026-10-30T08:00:00+00:00",
                body=body),
            now=NOW)
        self.assertEqual(block["last_checkpoint"],
                         "2026-10-30T11:50:00+00:00")
        self.assertEqual(block["last_activity"],
                         "2026-10-30T11:50:00+00:00")
        self.assertEqual(block["missed_checks"], 0)
        self.assertFalse(block["stalled"])

    def test_newest_checkpoint_wins_and_bad_lines_skip(self):
        body = ("progress-checkpoint: "
                "2026-10-30T11:10:00+00:00 — first.\n"
                "progress-checkpoint: not-a-time — junk.\n"
                "progress-checkpoint: "
                "2026-10-30T11:40:00+00:00 — second.\n")
        block = progress.todo_progress(
            armed_todo(body=body), now=NOW)
        self.assertEqual(block["last_checkpoint"],
                         "2026-10-30T11:40:00+00:00")

    def test_hour_cadence_interval(self):
        block = progress.todo_progress(
            armed_todo(progress_check="2h",
                       progress_armed=
                       "2026-10-30T09:00:00+00:00"),
            now=NOW)
        self.assertEqual(block["interval_seconds"], 7200.0)
        self.assertEqual(block["missed_checks"], 1)
        self.assertFalse(block["stalled"])

    def test_invalid_cadence_is_not_armed(self):
        # Cured semantics: an unparseable
        # cadence is not arming — the same predicate
        # schedule.is_armed uses. The old block (interval
        # None, missed None, never stalled) was the
        # vacuous-verdict shape behind the
        # refresh-repo-finalization divergence.
        self.assertIsNone(progress.todo_progress(
            armed_todo(progress_check="whenever"), now=NOW))

    def test_opt_out_is_not_armed(self):
        self.assertIsNone(progress.todo_progress(
            armed_todo(progress_check="off",
                       progress_armed=None), now=NOW))


class TestProjectProgress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plans = Path(self.tmp.name) / ".plans"
        self.plans.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_lists_only_armed_across_bundles(self):
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-10-30")
        bundle_mod.create_todo(
            self.plans, "work", "Armed one", status="doing",
            progress="30m",
            armed_at="2026-10-30T09:00:00+00:00",
            created="2026-10-30", updated="2026-10-30")
        bundle_mod.create_todo(
            self.plans, "work", "Quiet one",
            created="2026-10-30", updated="2026-10-30")
        report = progress.project_progress(self.plans,
                                           now=NOW)
        self.assertEqual(report["summary"],
                         {"armed": 1, "stalled": 1})
        self.assertEqual(
            [b["title"] for b in report["armed"]],
            ["Armed one"])
        self.assertEqual(report["armed"][0]["bundle"],
                         "2026-10-30-work")

    def test_done_armed_todo_does_not_count_as_stalled(
            self):
        # The served measure's summary counts verdicts,
        # and a done todo carries none: two armed todos
        # past the threshold, one doing and one done,
        # read armed 2 / stalled 1.
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-10-30")
        bundle_mod.create_todo(
            self.plans, "work", "Still working",
            status="doing", progress="30m",
            armed_at="2026-10-30T09:00:00+00:00",
            created="2026-10-30", updated="2026-10-30")
        finished = bundle_mod.create_todo(
            self.plans, "work", "Finished",
            status="doing", progress="30m",
            armed_at="2026-10-30T09:00:00+00:00",
            created="2026-10-30", updated="2026-10-30")
        # The done-with-cadence shape arrives by direct
        # file edit (the writers disarm on the flip:
        # create refuses to arm a done todo and
        # set_todo_status strips the cadence) — the
        # parser admits it, so the derivation must rule
        # on it. Flip the status in the file itself.
        path = self.plans / finished["path"]
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "status: doing", "status: done"),
            encoding="utf-8")
        report = progress.project_progress(self.plans,
                                           now=NOW)
        self.assertEqual(report["summary"],
                         {"armed": 2, "stalled": 1})
        by_title = {b["title"]: b
                    for b in report["armed"]}
        self.assertTrue(
            by_title["Still working"]["stalled"])
        self.assertFalse(by_title["Finished"]["stalled"])

    def test_opted_out_todo_never_enters_the_measure(self):
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-10-30")
        bundle_mod.create_todo(
            self.plans, "work", "Manual one",
            status="doing", no_progress=True,
            body="progress-checkpoint: "
                 "2026-10-30T08:00:00+00:00 — manual",
            created="2026-10-30", updated="2026-10-30")
        report = progress.project_progress(self.plans,
                                           now=NOW)
        self.assertEqual(report["armed"], [])
        self.assertEqual(report["summary"],
                         {"armed": 0, "stalled": 0})


class TestMeasureFreshness(unittest.TestCase):
    """The stale-measure cure: a served
    measure carries its freshness block, and
    measure_freshness re-rules it against the cited
    todo files. The incident's shape: a measure drawn
    at 23:00Z over a lane whose records then advanced
    to 01:12Z must rule VOID when a consumer re-checks
    it at 04:45Z; the same measure over records that
    did not advance rules CURRENT."""

    AS_OF = datetime(2026, 10, 30, 23, 0,
                     tzinfo=timezone.utc)
    ARMED_AT = "2026-10-30T22:30:00+00:00"
    FIRST_CHECKPOINT = "2026-10-30T22:45:00+00:00"
    ADVANCED_CHECKPOINT = "2026-10-31T01:12:00+00:00"
    RECHECK = datetime(2026, 10, 31, 4, 45,
                       tzinfo=timezone.utc)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plans = Path(self.tmp.name) / ".plans"
        self.plans.mkdir(parents=True)
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-10-30")
        bundle_mod.create_todo(
            self.plans, "work", "Measured lane",
            status="doing", progress="15m",
            armed_at=self.ARMED_AT,
            created="2026-10-30", updated="2026-10-30")
        todo = bundle_parser.list_todos(self.plans)[0]
        self.todo_path = self.plans / todo["path"]
        self._append_checkpoint(self.FIRST_CHECKPOINT,
                                when=self.FIRST_CHECKPOINT)

    def tearDown(self):
        self.tmp.cleanup()

    def _append_checkpoint(self, stamp, *, when):
        text = self.todo_path.read_text(encoding="utf-8")
        text += f"\nprogress-checkpoint: {stamp} — advanced\n"
        self.todo_path.write_text(text, encoding="utf-8")
        ts = datetime.fromisoformat(when).timestamp()
        os.utime(self.todo_path, (ts, ts))

    def _measure(self):
        return progress.project_progress(self.plans,
                                         now=self.AS_OF)

    def test_served_measure_carries_current_freshness(self):
        report = self._measure()
        fresh = report["freshness"]
        self.assertEqual(fresh["verdict"], "current")
        self.assertEqual(fresh["as_of"],
                         "2026-10-30T23:00:00+00:00")
        self.assertEqual(fresh["cited_newest_activity"],
                         self.FIRST_CHECKPOINT)
        self.assertEqual(fresh["bound_seconds"], 900)

    def test_records_advanced_past_one_cadence_is_void(self):
        report = self._measure()
        self._append_checkpoint(self.ADVANCED_CHECKPOINT,
                                when=self.ADVANCED_CHECKPOINT)
        fresh = progress.measure_freshness(
            report, self.plans, now=self.RECHECK)
        self.assertEqual(fresh["verdict"], "void")
        self.assertEqual(fresh["cited_newest_activity"],
                         self.ADVANCED_CHECKPOINT)
        self.assertEqual(fresh["advanced_seconds"], 7920)
        self.assertIn("re-measure", fresh["reason"])

    def test_records_unadvanced_stays_current(self):
        report = self._measure()
        fresh = progress.measure_freshness(
            report, self.plans, now=self.RECHECK)
        self.assertEqual(fresh["verdict"], "current")
        self.assertEqual(fresh["cited_newest_activity"],
                         self.FIRST_CHECKPOINT)

    def test_advance_within_one_cadence_stays_current(self):
        report = self._measure()
        self._append_checkpoint(
            "2026-10-30T23:10:00+00:00",
            when="2026-10-30T23:10:00+00:00")
        fresh = progress.measure_freshness(
            report, self.plans, now=self.RECHECK)
        self.assertEqual(fresh["verdict"], "current")

    def test_cited_record_gone_is_void(self):
        report = self._measure()
        self.todo_path.unlink()
        fresh = progress.measure_freshness(
            report, self.plans, now=self.RECHECK)
        self.assertEqual(fresh["verdict"], "void")
        self.assertIn("gone", fresh["reason"])

    def test_measure_without_as_of_is_void(self):
        fresh = progress.measure_freshness(
            {"armed": []}, self.plans, now=self.RECHECK)
        self.assertEqual(fresh["verdict"], "void")
        self.assertEqual(fresh["bound_seconds"],
                         progress.DEFAULT_CADENCE_SECONDS)


class TestProgressCli(unittest.TestCase):
    def test_wb_progress_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            proj = ws / "proj"
            (proj / ".plans").mkdir(parents=True)
            (proj / "workbench.yaml").write_text(
                "name: Proj\nslug: proj\n"
                "registry: workbench/registry.db\n"
                "plans: .plans\n", encoding="utf-8")
            bundle_mod.create_bundle(proj / ".plans",
                                     "work",
                                     today="2026-10-30")
            armed_at = datetime.now(
                timezone.utc).isoformat()
            todo = bundle_mod.create_todo(
                proj / ".plans", "work", "Armed one",
                status="doing", progress="30m",
                armed_at=armed_at)
            r = subprocess.run(
                [sys.executable, str(REPO / "wb"),
                 "progress", "--root", str(ws)],
                capture_output=True, text=True, cwd=REPO)
            self.assertEqual(r.returncode, 0, r.stderr)
            payload = json.loads(r.stdout)
            self.assertEqual(len(payload["projects"]), 1)
            project = payload["projects"][0]
            self.assertEqual(project["slug"], "proj")
            self.assertEqual(project["summary"]["armed"], 1)
            self.assertEqual(project["armed"][0]["id"],
                             todo["id"])
            self.assertFalse(project["armed"][0]["stalled"])


if __name__ == "__main__":
    unittest.main()
