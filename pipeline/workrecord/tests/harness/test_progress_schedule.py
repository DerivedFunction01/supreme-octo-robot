"""Retired progress schedules (supervision plan Step
6): the scheduler-registry entry rendering is gone —
arming a todo writes its attention armed row, and the
tick's armed rows are the check now. What remains here
is the removal path: every todo write deletes any
lingering wb-progress entry, `wb progress
--sync-entries` deletes them all, and the doctor flags
any entry still standing. `wb progress-check` renders
the stall verdict as an exit code, unchanged. The todo
file stays the record of truth.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent))

from lib.writes import bundles as bundle_mod  # noqa: E402
from evaluation import doctor  # noqa: E402
from lib.progress import schedule as ps  # noqa: E402
from lib.discovery.manifest import Manifest  # noqa: E402
from lib.discovery.sweep import Project  # noqa: E402

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
TODO_ID = "long-work"
ENTRY_ID = ps.entry_id("fixture-proj", TODO_ID)


def entry_text(todo_id=TODO_ID, slug="fixture-proj"):
    """A minimal wb-progress entry in the retired
    format — hand-written, since render_entry is gone;
    enough for parse_entry_todo_id and the doctor."""
    return (
        f"id: wb-progress-{slug}-{todo_id}\n"
        "kind: scripted\n"
        "run:\n"
        "  argv:\n"
        "    - ${WS}/workbench-viewer/wb\n"
        "    - --root\n"
        f"    - ${{WS}}/{slug}\n"
        "    - progress-check\n"
        f"    - {todo_id}\n")


def armed_todo(**over):
    todo = {
        "id": TODO_ID,
        "title": "Long work",
        "status": "doing",
        "bundle": "2026-11-01-work",
        "archived": False,
        "path": "2026-11-01-work/todos/t-a.md",
        "progress_check": "30m",
        "progress_armed": "2026-11-01T11:30:00+00:00",
        "body": "",
    }
    todo.update(over)
    return todo


class SeamCase(unittest.TestCase):
    """A tmp workspace + tmp jobs dir under the env
    seams (WB_WORKSPACE_ROOT / WB_SCHEDULER_JOBS_DIR),
    with one fixture project inside the workspace."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.ws = base / "ws"
        self.jobs = base / "jobs"
        self.jobs.mkdir(parents=True)
        self.proj = self.ws / "fixture-proj"
        self.plans = self.proj / ".plans"
        self.plans.mkdir(parents=True)
        (self.proj / "workbench.yaml").write_text(
            "name: Fixture Proj\nslug: fixture-proj\n"
            "plans: .plans\n", encoding="utf-8")
        (self.ws / "workbench-viewer").mkdir()
        patcher = mock.patch.dict(os.environ, {
            "WB_SCHEDULER_JOBS_DIR": str(self.jobs),
            "WB_WORKSPACE_ROOT": str(self.ws),
            "WB_VIEWER_ROOT": str(self.ws
                                  / "workbench-viewer")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def project(self):
        manifest = Manifest(
            root=self.proj, name="Fixture Proj",
            slug="fixture-proj", registry=None,
            plans=self.plans, mockups=None, archive=None,
            declared={})
        return Project(manifest)

    def entry_path(self, eid=ENTRY_ID):
        return self.jobs / f"{eid}.yaml"

    def make_armed(self, **kw):
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-01")
        return bundle_mod.create_todo(
            self.plans, "work", "Long task",
            status="doing", progress="30m", **kw)


class TestRetired(unittest.TestCase):
    def test_render_path_is_gone(self):
        # The rendering is retired, not deprecated: no
        # entry is ever written again, so the render
        # entry point and its constants are removed
        # outright rather than left as dead surface.
        self.assertFalse(hasattr(ps, "render_entry"))
        self.assertFalse(hasattr(ps, "CHECK_TIMEOUT_SECS"))
        self.assertFalse(hasattr(ps, "scheduled_ids"))

    def test_parse_entry_todo_id_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / f"{ENTRY_ID}.yaml"
            path.write_text(entry_text(), encoding="utf-8")
            self.assertEqual(
                ps.parse_entry_todo_id(path), TODO_ID)

    def test_parse_entry_todo_id_rejects_other_files(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "other.yaml"
            path.write_text("id: other\ntitle: 'x'\n",
                            encoding="utf-8")
            self.assertIsNone(ps.parse_entry_todo_id(path))


class TestSync(SeamCase):
    def test_armed_todo_writes_nothing(self):
        out = ps.sync_todo(self.plans, armed_todo())
        self.assertEqual(out["action"], "unchanged")
        self.assertFalse(self.entry_path().exists())

    def test_stale_entry_is_removed_on_any_write(self):
        self.entry_path().write_text(
            entry_text(), encoding="utf-8")
        out = ps.sync_todo(self.plans, armed_todo())
        self.assertEqual(out["action"], "removed")
        self.assertFalse(self.entry_path().exists())

    def test_blocked_and_archived_carry_no_entry(self):
        for over in ({"status": "blocked"},
                     {"archived": True}):
            out = ps.sync_todo(
                self.plans, armed_todo(**over))
            self.assertEqual(out["action"], "unchanged")
            self.assertFalse(self.entry_path().exists())

    def test_no_jobs_dir_skips(self):
        with mock.patch.dict(
                os.environ,
                {"WB_SCHEDULER_JOBS_DIR": "/nonexistent/x"}):
            self.assertIsNone(ps.jobs_dir())
            out = ps.sync_todo(self.plans, armed_todo())
        self.assertEqual(out["action"], "skipped")

    def test_project_outside_workspace_skips(self):
        # Outside the (seam) workspace AND the entry
        # would land in the real registry: refused.
        outside = Path(self.tmp.name) / "elsewhere"
        (outside / ".plans").mkdir(parents=True)
        (outside / "workbench.yaml").write_text(
            "name: X\n", encoding="utf-8")
        live = ps._live_jobs_dir()
        before = set(live.glob("*.yaml"))
        with mock.patch.dict(
                os.environ,
                {"WB_SCHEDULER_JOBS_DIR": str(live)}):
            out = ps.sync_todo(outside / ".plans",
                               armed_todo())
        self.assertEqual(out["action"], "skipped")
        self.assertEqual(set(live.glob("*.yaml")), before)


class TestWriters(SeamCase):
    def test_create_and_terminal_moves_write_no_entry(self):
        # The retirement: arming writes the attention
        # armed row, never a scheduler entry — the
        # writer's progress_entry action is unchanged
        # and no entry file appears at any move.
        todo = self.make_armed()
        self.assertEqual(
            todo["progress_entry"]["action"], "unchanged")
        eid = ps.entry_id("fixture-proj", todo["id"])
        self.assertFalse(self.entry_path(eid).exists())
        out = bundle_mod.set_todo_status(
            self.plans, todo["id"], "done")
        self.assertEqual(
            out["progress_entry"]["action"], "unchanged")
        self.assertFalse(self.entry_path(eid).exists())

    def test_stale_entry_is_removed_by_a_todo_write(self):
        todo = self.make_armed()
        eid = ps.entry_id("fixture-proj", todo["id"])
        self.entry_path(eid).write_text(
            entry_text(todo["id"]), encoding="utf-8")
        out = bundle_mod.set_todo_status(
            self.plans, todo["id"], "done")
        self.assertEqual(
            out["progress_entry"]["action"], "removed")
        self.assertFalse(self.entry_path(eid).exists())

    def test_blocked_move_removes_a_stale_entry(self):
        todo = self.make_armed()
        eid = ps.entry_id("fixture-proj", todo["id"])
        self.entry_path(eid).write_text(
            entry_text(todo["id"]), encoding="utf-8")
        bundle_mod.set_todo_status(
            self.plans, todo["id"], "blocked")
        self.assertFalse(self.entry_path(eid).exists())

    def test_unarmed_todo_writes_no_entry(self):
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-01")
        todo = bundle_mod.create_todo(
            self.plans, "work", "Plain task")
        self.assertEqual(
            todo["progress_entry"]["action"], "unchanged")
        self.assertEqual(list(self.jobs.glob("*.yaml")),
                         [])

    def test_doing_move_without_flag_writes_no_entry(self):
        # End to end through the writer (2026-11-03):
        # no --progress anywhere, and the doing move
        # still arms the todo (15m) — but the arm now
        # writes the attention row, not a scheduler
        # entry.
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-01")
        todo = bundle_mod.create_todo(
            self.plans, "work", "Long task")
        moved = bundle_mod.set_todo_status(
            self.plans, todo["id"], "doing")
        self.assertEqual(moved["progress_check"], "15m")
        self.assertEqual(
            moved["progress_entry"]["action"], "unchanged")
        eid = ps.entry_id("fixture-proj", todo["id"])
        self.assertFalse(self.entry_path(eid).exists())
        out = bundle_mod.set_todo_status(
            self.plans, todo["id"], "done")
        self.assertEqual(
            out["progress_entry"]["action"], "unchanged")
        self.assertFalse(self.entry_path(eid).exists())

    def test_opt_out_todo_never_writes_entry(self):
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-01")
        todo = bundle_mod.create_todo(
            self.plans, "work", "Unwatched task",
            no_progress=True)
        moved = bundle_mod.set_todo_status(
            self.plans, todo["id"], "doing")
        self.assertEqual(moved["progress_check"], "off")
        self.assertFalse(ps.is_armed(moved))
        self.assertEqual(list(self.jobs.glob("*.yaml")),
                         [])


class TestCheck(SeamCase):
    def test_fresh_armed_is_on_track(self):
        todo = self.make_armed(
            armed_at="2026-11-01T11:30:00+00:00")
        code, line = ps.check_todo(
            self.plans, todo["id"], now=NOW)
        self.assertEqual(code, 0)
        self.assertIn("on track", line)

    def test_stale_armed_exits_3_with_stall_line(self):
        todo = self.make_armed(
            armed_at="2026-11-01T08:00:00+00:00")
        code, line = ps.check_todo(
            self.plans, todo["id"], now=NOW)
        self.assertEqual(code, 3)
        self.assertIn("STALLED", line)
        self.assertIn(todo["id"], line)

    def test_opt_out_gap_reads_opted_out_not_stalled(self):
        # The Edgar greenfield Step 3 shape (2026-11-16)
        # as a fixture: an opted-out todo, deliberately
        # held, with historical conforming checkpoints
        # on file. The check once derived a verdict from
        # those lines alone and read the gap past the
        # last one as STALLED (exit 3) — a recorded hold
        # escalated as a stall, repeatedly. The opt-out
        # exempts the todo from measurement: the verdict
        # names the opt-out at any read time, and the
        # checkpoint lines — conforming or decoy — are
        # not consulted at all. The body keeps the
        # refresh-repo-finalization lines (conforming
        # checkpoints to 05:05:28Z, plus the two 05:47
        # decoys) that the old derivation read as
        # 2 missed checks at 05:50Z.
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-16")
        body = "\n\n".join([
            "progress-checkpoint: "
            "2026-11-16T04:37:04Z — reconciliation complete",
            "progress-checkpoint: "
            "2026-11-16T04:43:16Z — v4 formation commissioned",
            "progress-checkpoint: "
            "2026-11-16T05:05:28Z — cure layer recovered",
            "progress-checkpoint: at "
            "2026-11-16T05:47:00Z the lane noted — "
            "stamp out of position",
            "a prose note quoting progress-checkpoint: "
            "2026-11-16T05:47:00Z — example only",
        ])
        todo = bundle_mod.create_todo(
            self.plans, "work", "Repo finalization",
            name="refresh-repo-finalization",
            no_progress=True, body=body,
            created="2026-11-16", updated="2026-11-16")
        bundle_mod.set_todo_status(
            self.plans, todo["id"], "doing")
        at_gap = datetime(2026, 11, 16, 5, 50,
                          tzinfo=timezone.utc)
        code, line = ps.check_todo(
            self.plans, todo["id"], now=at_gap)
        self.assertEqual(code, 0)
        self.assertIn("progress_check off", line)
        self.assertIn("opted out", line)
        self.assertNotIn("STALLED", line)
        self.assertNotIn("on track", line)
        within = datetime(2026, 11, 16, 5, 20,
                          tzinfo=timezone.utc)
        code, line = ps.check_todo(
            self.plans, todo["id"], now=within)
        self.assertEqual(code, 0)
        self.assertIn("progress_check off", line)
        self.assertIn("opted out", line)

    def test_done_flip_checkpoint_is_not_a_stall(self):
        # The refresh-step-6-verdict-v2 zombie stall
        # (2026-11-16) as a fixture: a todo whose last
        # conforming checkpoint is its done flip at
        # 04:46:05Z, read at T + 3 cadences. The watch
        # pinged the real todo STALLED in two consecutive
        # passes on the flip's age alone. The check names
        # the stop instead; the doing twin with identical
        # stamps still reads STALLED — the cure does not
        # blunt the true read.
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-16")
        body = "\n\n".join([
            "progress-checkpoint: "
            "2026-11-16T04:15:25Z — directed build complete",
            "progress-checkpoint: "
            "2026-11-16T04:46:05Z — verdict delivered; "
            "closing",
        ])
        at = datetime(2026, 11, 16, 5, 31, 5,
                      tzinfo=timezone.utc)
        done = bundle_mod.create_todo(
            self.plans, "work", "Verdict v2",
            name="verdict-done", status="doing",
            progress="15m",
            armed_at="2026-11-16T01:56:37+00:00",
            body=body, created="2026-11-16",
            updated="2026-11-16")
        # The flip lands by direct file edit, keeping
        # the cadence on file: the writers disarm on a
        # done flip, but the parser admits the shape and
        # external edits are a first-class write path —
        # the derivation is the last line of defense.
        path = self.plans / done["path"]
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "status: doing", "status: done"),
            encoding="utf-8")
        code, line = ps.check_todo(
            self.plans, done["id"], now=at)
        self.assertEqual(code, 0)
        self.assertIn("done — schedule stopped", line)
        self.assertNotIn("STALLED", line)
        doing = bundle_mod.create_todo(
            self.plans, "work", "Verdict twin",
            name="verdict-doing", progress="15m",
            armed_at="2026-11-16T01:56:37+00:00",
            body=body, created="2026-11-16",
            updated="2026-11-16")
        bundle_mod.set_todo_status(
            self.plans, doing["id"], "doing")
        code, line = ps.check_todo(
            self.plans, doing["id"], now=at)
        self.assertEqual(code, 3)
        self.assertIn("STALLED", line)
        self.assertIn("3 missed checks", line)

    def test_done_opt_out_reads_stopped_not_stalled(self):
        # A done opt-out's check line: the stop status
        # is named before the opt-out — finished work
        # reads as finished, never as a stall.
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-16")
        body = ("progress-checkpoint: "
                "2026-11-16T04:46:05Z — verdict delivered; "
                "closing")
        todo = bundle_mod.create_todo(
            self.plans, "work", "Verdict manual",
            name="verdict-manual", status="doing",
            no_progress=True,
            body=body, created="2026-11-16",
            updated="2026-11-16")
        path = self.plans / todo["path"]
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "status: doing", "status: done"),
            encoding="utf-8")
        at = datetime(2026, 11, 16, 5, 31, 5,
                      tzinfo=timezone.utc)
        code, line = ps.check_todo(
            self.plans, todo["id"], now=at)
        self.assertEqual(code, 0)
        self.assertIn("done — schedule stopped", line)
        self.assertNotIn("STALLED", line)

    def test_opt_out_without_checkpoints_reads_opted_out(self):
        # No checkpoints on file changes nothing: the
        # opt-out is itself the verdict — the check does
        # not fall back to a no-verdict line for want of
        # lines it no longer derives from.
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-16")
        todo = bundle_mod.create_todo(
            self.plans, "work", "Unstamped manual task",
            no_progress=True,
            created="2026-11-16", updated="2026-11-16")
        bundle_mod.set_todo_status(
            self.plans, todo["id"], "doing")
        code, line = ps.check_todo(
            self.plans, todo["id"], now=NOW)
        self.assertEqual(code, 0)
        self.assertIn("progress_check off", line)
        self.assertIn("opted out", line)
        self.assertNotIn("on track", line)
        self.assertNotIn("STALLED", line)

    def test_invalid_cadence_no_verdict(self):
        todo = self.make_armed()
        path = self.plans / todo["path"]
        text = path.read_text(encoding="utf-8")
        text = text.replace("progress_check: 30m",
                            "progress_check: whenever")
        path.write_text(text, encoding="utf-8")
        code, line = ps.check_todo(
            self.plans, todo["id"], now=NOW)
        self.assertEqual(code, 0)
        self.assertIn("invalid progress_check", line)
        self.assertNotIn("on track", line)

    def test_unknown_and_disarmed_are_quiet_zero(self):
        code, line = ps.check_todo(
            self.plans, TODO_ID, now=NOW)
        self.assertEqual(code, 0)
        self.assertIn("not found", line)
        todo = self.make_armed()
        bundle_mod.set_todo_status(
            self.plans, todo["id"], "done")
        code, line = ps.check_todo(
            self.plans, todo["id"], now=NOW)
        self.assertEqual(code, 0)
        self.assertIn("not armed", line)


class TestSyncAll(SeamCase):
    def test_sync_all_removes_every_entry(self):
        # The retirement sweep: every wb-progress entry
        # stands in the registry, armed todo or not, and
        # the sweep deletes them all — nothing is ever
        # written.
        todo = self.make_armed()
        eid = ps.entry_id("fixture-proj", todo["id"])
        self.entry_path(eid).write_text(
            entry_text(todo["id"]), encoding="utf-8")
        ghost_id = ps.entry_id(
            "fixture-proj", "ghost-task")
        self.entry_path(ghost_id).write_text(
            entry_text("ghost-task"), encoding="utf-8")
        out = ps.sync_all([self.project()])
        self.assertEqual(out["written"], [])
        self.assertIn(eid, out["removed"])
        self.assertIn(ghost_id, out["removed"])
        self.assertFalse(self.entry_path(eid).exists())
        self.assertFalse(self.entry_path(ghost_id)
                         .exists())

    def test_sync_all_with_no_entries_is_a_no_op(self):
        self.make_armed()
        out = ps.sync_all([self.project()])
        self.assertEqual(out, {"written": [],
                               "removed": [],
                               "kept": 0})


class TestDoctor(SeamCase):
    def findings(self):
        return doctor.progress_entry_findings(
            [self.project()])

    def test_missing_entry_is_silent(self):
        # An armed todo with no entry is the retired
        # state, not drift: nothing is rendered any
        # more, so absence convicts nothing.
        self.make_armed()
        self.assertEqual(self.findings(), [])

    def test_lingering_entry_is_flagged(self):
        # Any wb-progress entry still standing is
        # drift, whatever its todo's state — the
        # rendering is retired and the tick's armed
        # rows are the check now.
        todo = self.make_armed()
        self.entry_path(ps.entry_id(
            "fixture-proj", todo["id"])).write_text(
            entry_text(todo["id"]), encoding="utf-8")
        found = self.findings()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["check"],
                         "todo-progress-entry-lingering")
        self.assertEqual(found[0]["project"],
                         "fixture-proj")

    def test_lingering_ghost_entry_is_flagged(self):
        # The todo is gone but its entry stands: still
        # a lingering entry, not a distinct class.
        ghost_id = ps.entry_id(
            "fixture-proj", "ghost-task")
        self.entry_path(ghost_id).write_text(
            entry_text("ghost-task"), encoding="utf-8")
        found = self.findings()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["check"],
                         "todo-progress-entry-lingering")

    def test_other_projects_entries_are_out_of_scope(self):
        # A partial sweep must not call another
        # project's entries lingering (regression: the
        # first doctor wiring flagged every unswept
        # project's live entries, breaking the
        # clean-fixture doctor tests).
        other_id = ps.entry_id(
            "other-proj", "other-task")
        self.entry_path(other_id).write_text(
            entry_text("other-task", slug="other-proj"),
            encoding="utf-8")
        self.assertEqual(self.findings(), [])

    def test_unattributable_entry_is_silent(self):
        # A wb-progress file whose argv does not parse
        # as one of ours is not the doctor's to judge —
        # the scheduler's own validation quarantines
        # malformed entries.
        path = self.entry_path(ps.entry_id(
            "fixture-proj", "unreadable"))
        path.write_text("id: wb-progress-fixture-proj"
                        "-unreadable\ntitle: 'x'\n",
                        encoding="utf-8")
        self.assertEqual(self.findings(), [])

    def test_no_registry_is_silent(self):
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-01")
        bundle_mod.create_todo(
            self.plans, "work", "Armed elsewhere",
            status="doing", progress="30m")
        with mock.patch.dict(
                os.environ,
                {"WB_SCHEDULER_JOBS_DIR":
                 str(self.ws / "no-scheduler-here")}):
            # A bogus override dir reads as no registry.
            self.assertIsNone(ps.jobs_dir())
            self.assertEqual(self.findings(), [])


class TestTempGuard(unittest.TestCase):
    """The leak guard: a scratch (temp-root) project's
    sync never touches the LIVE jobs dir. The 2026-11-08
    incident: a suite arming fixture todos with no jobs
    seam rendered ${WS}/tmp-gate/... entries into the
    live registry; the fixture dirs died with their runs
    and the entries crashed every cycle. The retirement
    keeps the guard: the sync is removal-only, and the
    removal itself is refused outside the seam."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.proj = base / "fixture-proj"
        self.plans = self.proj / ".plans"
        self.plans.mkdir(parents=True)
        (self.proj / "workbench.yaml").write_text(
            "name: Fixture Proj\nplans: .plans\n",
            encoding="utf-8")
        self.live_jobs = base / "live-jobs"
        self.live_jobs.mkdir()
        self.scratch_jobs = base / "scratch-jobs"
        self.scratch_jobs.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _todo(self):
        return {"id": TODO_ID, "title": "Long task",
                "status": "doing", "progress_check": "30m",
                "progress_armed": "2026-11-01T11:30:00+00:00",
                "archived": False}

    def test_sync_into_live_jobs_dir_is_refused(self):
        # The incident's exact shape: the jobs dir IS
        # this machine's real registry (resolved from
        # the module's own location), the project is a
        # temp fixture.
        live = ps._live_jobs_dir()
        before = set(live.glob("*.yaml"))
        env = {"WB_SCHEDULER_JOBS_DIR": str(live)}
        with mock.patch.dict(os.environ, env):
            out = ps.sync_todo(self.plans, self._todo())
        self.assertEqual(out["action"], "skipped")
        self.assertEqual(set(live.glob("*.yaml")), before)

    def test_sync_into_scratch_jobs_dir_removes_only(self):
        # A scratch project against a scratch jobs dir
        # passes the guards — and the sync is
        # removal-only: it deletes a lingering entry
        # and writes nothing.
        env = {"WB_SCHEDULER_JOBS_DIR":
               str(self.scratch_jobs)}
        with mock.patch.dict(os.environ, env):
            out = ps.sync_todo(self.plans, self._todo())
        self.assertEqual(out["action"], "unchanged")
        path = (self.scratch_jobs
                / f"{ENTRY_ID}.yaml")
        self.assertFalse(path.exists())
        path.write_text(entry_text(), encoding="utf-8")
        with mock.patch.dict(os.environ, env):
            out = ps.sync_todo(self.plans, self._todo())
        self.assertEqual(out["action"], "removed")
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
