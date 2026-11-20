"""Goal-record store tests (contract 11): the store and
its writer rules, the ping entry the record arms about
itself (validated through the pipeline scheduling
registry's own loader), the goal-check verdict, and the
served projection the feeds document carries.

Everything stands on fixture state: the store lives in a
temp dir and the jobs dir seam points at a temp registry,
so no test touches the live store or the live registry.
"""

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from lib.writes import goals as goals_mod

PIPELINE_ROOT = Path(__file__).resolve().parents[3]

CONTRACT = {
    "objective": "Exercise the goal-record store.",
    "complete_when": "the checks pass",
    "blocked_only_when": "a cited owner decision is "
                         "missing",
    "continuation": "continue without a tap",
}
T0 = "2026-10-25T12:00:00+00:00"


def _sched_registry():
    spec = importlib.util.spec_from_file_location(
        "sched_registry_for_goals",
        PIPELINE_ROOT / "scheduling" / "server"
        / "registry.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GoalCase(unittest.TestCase):
    """A temp store + temp jobs dir under the env seams."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.ws = base / "ws"
        self.jobs = base / "jobs"
        self.jobs.mkdir(parents=True)
        self.store_path = base / "state" / "goals.json"
        patcher = mock.patch.dict(os.environ, {
            "WB_SCHEDULER_JOBS_DIR": str(self.jobs),
            "WB_WORKSPACE_ROOT": str(self.ws),
            "WB_VIEWER_ROOT": str(self.ws / "workrecord")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.store = goals_mod.GoalStore(self.store_path)

    def create(self, slug="fixture-goal", **kw):
        kw.setdefault("now", T0)
        return self.store.create(
            slug, "alpha", "Fixture goal", CONTRACT, **kw)

    def entry_path(self, slug="fixture-goal"):
        return self.jobs / f"goal-ping-{slug}.yaml"


class TestStoreBasics(GoalCase):

    def test_create_round_trip(self):
        out = self.create()
        self.assertEqual(out["ping_sync"]["action"],
                         "written")
        record = self.store.get("fixture-goal")
        self.assertEqual(record["project"], "alpha")
        self.assertEqual(record["contract"], CONTRACT)
        self.assertEqual(record["ping"],
                         {"cadence_minutes": 15,
                          "armed": True})
        self.assertEqual(record["posts"], [])
        on_disk = json.loads(
            self.store_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [g["slug"] for g in on_disk["goals"]],
            ["fixture-goal"])
        self.assertTrue(self.entry_path().is_file())

    def test_create_disarmed_writes_no_entry(self):
        out = self.create(armed=False)
        self.assertEqual(out["ping_sync"]["action"],
                         "unchanged")
        self.assertFalse(self.entry_path().exists())

    def test_duplicate_refused(self):
        self.create()
        with self.assertRaises(goals_mod.GoalError):
            self.create()

    def test_bad_slug_refused(self):
        for slug in ("Fixture Goal", "UPPER", "-lead",
                     "has space", ""):
            with self.assertRaises(goals_mod.GoalError):
                self.store.create(slug, "alpha", "T",
                                  CONTRACT, now=T0)

    def test_incomplete_contract_refused(self):
        for bad in ({**CONTRACT, "complete_when": "  "},
                    {k: v for k, v in CONTRACT.items()
                     if k != "continuation"},
                    "not a dict"):
            with self.assertRaises(goals_mod.GoalError):
                self.store.create("other-goal", "alpha",
                                  "T", bad, now=T0)
        self.assertEqual(self.store.records(), [])

    def test_missing_store_reads_empty(self):
        self.assertEqual(self.store.records(), [])
        self.assertIsNone(self.store.get("nope"))

    def test_malformed_store_fails_closed(self):
        self.store_path.parent.mkdir(parents=True,
                                     exist_ok=True)
        self.store_path.write_text("{not json",
                                   encoding="utf-8")
        with self.assertRaises(goals_mod.GoalError):
            self.store.records()
        self.store_path.write_text('{"goals": {}}',
                                   encoding="utf-8")
        with self.assertRaises(goals_mod.GoalError):
            self.store.records()

    def test_update_record(self):
        self.create()
        out = self.store.update_record(
            "fixture-goal", title="Renamed goal")
        self.assertEqual(out["record"]["title"],
                         "Renamed goal")
        with self.assertRaises(goals_mod.GoalError):
            self.store.update_record(
                "fixture-goal",
                contract={**CONTRACT, "objective": ""})
        # The refused contract landed nowhere.
        self.assertEqual(
            self.store.get("fixture-goal")["contract"],
            CONTRACT)

    def test_unknown_goal_refused(self):
        with self.assertRaises(goals_mod.GoalError):
            self.store.post_status(
                "nope", {"handle": "main",
                         "status_code": "WORKING",
                         "summary": "x"})


class TestEntryForm(GoalCase):

    def test_entry_renders_contract14_form(self):
        self.create()
        text = self.entry_path().read_text(
            encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual(lines[0],
                         "id: goal-ping-fixture-goal")
        for needle in ("kind: scripted", "status: active",
                       "  type: interval", "  every: 15m",
                       "owner: goal:fixture-goal",
                       "timeout_secs: 120",
                       "  when: on_failure",
                       "lifetime: until_complete",
                       "- goal-check", "- fixture-goal"):
            self.assertIn(needle, text)
        # No admission field family (amendment 3), and no
        # machine source stamp: that form names a todo,
        # which a goal record has none of.
        self.assertNotIn("migrated", text)
        self.assertNotIn("source:", text)

    def test_entry_validates_in_pipeline_registry(self):
        self.create()
        registry = _sched_registry()
        entries, errors = registry.load_dir(
            str(self.jobs), str(Path(self.tmp.name)
                                / "sched-home"))
        self.assertEqual(errors, [])
        self.assertIn("goal-ping-fixture-goal", entries)
        entry = entries["goal-ping-fixture-goal"]
        self.assertEqual(entry.data["owner"],
                         "goal:fixture-goal")

    def test_cadence_change_rewrites_entry(self):
        self.create()
        out = self.store.set_ping("fixture-goal", True,
                                  cadence_minutes=30)
        self.assertEqual(out["ping_sync"]["action"],
                         "written")
        self.assertIn("every: 30m",
                      self.entry_path().read_text(
                          encoding="utf-8"))

    def test_disarm_removes_entry(self):
        self.create()
        out = self.store.set_ping("fixture-goal", False)
        self.assertEqual(out["ping_sync"]["action"],
                         "removed")
        self.assertFalse(self.entry_path().exists())

    def test_scratch_store_never_arms_live_registry(self):
        slug = "fixture-guard-goal"
        live = (goals_mod.REPO_ROOT.parent / "scheduling"
                / "jobs")
        leaked = live / f"goal-ping-{slug}.yaml"
        env = dict(os.environ)
        env.pop("WB_SCHEDULER_JOBS_DIR", None)
        try:
            with mock.patch.dict(os.environ, env,
                                 clear=True):
                out = self.store.create(
                    slug, "alpha", "Guard goal", CONTRACT,
                    now=T0)
            self.assertEqual(out["ping_sync"]["action"],
                             "skipped")
            self.assertFalse(leaked.exists())
        finally:
            if leaked.exists():
                leaked.unlink()


class TestWriterRules(GoalCase):

    def test_working_post_lands_with_refs(self):
        self.create()
        out = self.store.post_status(
            "fixture-goal",
            {"handle": "main", "status_code": "WORKING",
             "summary": "working",
             "refs": {"project": "alpha",
                      "plan": "2026-10-25-fixture-work",
                      "todo_ids": ["t-01K8Q000000000000"
                                   "000000A"]}},
            now="2026-10-25T12:05:00+00:00")
        post = out["record"]["posts"][-1]
        self.assertEqual(post["posted_at"],
                         "2026-10-25T12:05:00+00:00")
        self.assertEqual(post["refs"]["plan"],
                         "2026-10-25-fixture-work")

    def test_blocked_uncited_refused_both_codes(self):
        self.create()
        for code in ("BLOCKED-OWNER", "BLOCKED-HARD"):
            with self.assertRaises(goals_mod.GoalError):
                self.store.post_status(
                    "fixture-goal",
                    {"handle": "main", "status_code": code,
                     "summary": "blocked"})
        # Neither refusal reached the store.
        self.assertEqual(
            self.store.get("fixture-goal")["posts"], [])

    def test_blocked_citation_needs_thread_and_time(self):
        self.create()
        with self.assertRaises(goals_mod.GoalError):
            self.store.post_status(
                "fixture-goal",
                {"handle": "main",
                 "status_code": "BLOCKED-OWNER",
                 "summary": "blocked",
                 "basis_citation": {"thread": "main"}})

    def test_blocked_cited_accepted_and_stamped(self):
        self.create()
        out = self.store.post_status(
            "fixture-goal",
            {"handle": "main",
             "status_code": "BLOCKED-OWNER",
             "summary": "blocked",
             "basis_citation": {
                 "thread": "main",
                 "at": "2026-10-25T09:00:00+00:00"}},
            now="2026-10-25T12:05:00+00:00")
        post = out["record"]["posts"][-1]
        self.assertEqual(
            post["verification"],
            {"by": "main",
             "at": "2026-10-25T12:05:00+00:00"})
        # A supplied stamp is the verifier's own and is
        # preserved, not overwritten.
        out = self.store.post_status(
            "fixture-goal",
            {"handle": "main",
             "status_code": "BLOCKED-HARD",
             "summary": "still blocked",
             "basis_citation": {
                 "thread": "main",
                 "at": "2026-10-25T09:30:00+00:00"},
             "verification": {"by": "reviewer",
                              "at": "2026-10-25T10:00:00"
                                    "+00:00"}})
        self.assertEqual(
            out["record"]["posts"][-1]["verification"],
            {"by": "reviewer",
             "at": "2026-10-25T10:00:00+00:00"})

    def test_unknown_status_code_refused(self):
        self.create()
        with self.assertRaises(goals_mod.GoalError):
            self.store.post_status(
                "fixture-goal",
                {"handle": "main", "status_code": "MEH",
                 "summary": "x"})

    def test_terminal_post_clears_waiting_retires_ping(
            self):
        self.create()
        self.store.post_status(
            "fixture-goal",
            {"handle": "main", "status_code": "WORKING",
             "summary": "working",
             "owner_waiting": {
                 "label": "fixture decision",
                 "commissioned_at": T0}},
            now="2026-10-25T12:05:00+00:00")
        out = self.store.post_status(
            "fixture-goal",
            {"handle": "main", "status_code": "DONE",
             "summary": "done",
             "owner_waiting": {
                 "label": "fixture decision",
                 "commissioned_at": T0}},
            now="2026-10-25T12:10:00+00:00")
        record = out["record"]
        self.assertIsNone(
            record["posts"][-1]["owner_waiting"])
        self.assertFalse(record["ping"]["armed"])
        self.assertEqual(out["ping_sync"]["action"],
                         "removed")
        self.assertFalse(self.entry_path().exists())

    def test_rearm_after_terminal_refused(self):
        self.create()
        self.store.post_status(
            "fixture-goal",
            {"handle": "main", "status_code": "CLOSED",
             "summary": "closed"})
        with self.assertRaises(goals_mod.GoalError):
            self.store.set_ping("fixture-goal", True)

    def test_set_ping_round_trip(self):
        self.create(armed=False)
        out = self.store.set_ping("fixture-goal", True)
        self.assertEqual(out["ping_sync"]["action"],
                         "written")
        out = self.store.set_ping("fixture-goal", True)
        self.assertEqual(out["ping_sync"]["action"],
                         "unchanged")


class TestVerdict(GoalCase):

    def _at(self, minutes):
        return datetime(2026, 10, 25, 12, 0,
                        tzinfo=timezone.utc) \
            + timedelta(minutes=minutes)

    def test_on_track(self):
        self.create()
        code, line = goals_mod.check_goal(
            self.store, "fixture-goal", now=self._at(10))
        self.assertEqual(code, 0)
        self.assertIn("on track", line)

    def test_stalled_after_two_missed_intervals(self):
        self.create()
        code, line = goals_mod.check_goal(
            self.store, "fixture-goal", now=self._at(31))
        self.assertEqual(code, 3)
        self.assertTrue(line.startswith(
            "STALLED goal fixture-goal"))
        self.assertIn("2 missed checks", line)

    def test_post_refreshes_activity(self):
        self.create()
        self.store.post_status(
            "fixture-goal",
            {"handle": "main", "status_code": "WORKING",
             "summary": "still working"},
            now="2026-10-25T12:20:00+00:00")
        code, _ = goals_mod.check_goal(
            self.store, "fixture-goal", now=self._at(40))
        self.assertEqual(code, 0)

    def test_terminal_and_missing_verdicts(self):
        self.create()
        self.store.post_status(
            "fixture-goal",
            {"handle": "main", "status_code": "DONE",
             "summary": "done"})
        code, line = goals_mod.check_goal(
            self.store, "fixture-goal", now=self._at(500))
        self.assertEqual(code, 0)
        self.assertIn("ping retired", line)
        code, line = goals_mod.check_goal(
            self.store, "no-such-goal", now=self._at(0))
        self.assertEqual(code, 0)
        self.assertIn("not found", line)


class TestServeProjection(GoalCase):

    def test_serve_record_shape(self):
        self.create(short_objective="one clause")
        served = goals_mod.serve_record(
            self.store.get("fixture-goal"))
        self.assertEqual(served["slug"], "fixture-goal")
        self.assertEqual(served["shortObjective"],
                         "one clause")
        self.assertEqual(
            served["contract"],
            {"objective": CONTRACT["objective"],
             "completeWhen": CONTRACT["complete_when"],
             "blockedOnlyWhen":
                 CONTRACT["blocked_only_when"],
             "continuation": CONTRACT["continuation"]})
        self.assertEqual(
            served["ping"],
            {"entryId": "goal-ping-fixture-goal",
             "cadenceMinutes": 15, "armed": True})
        self.assertIsNone(served["lastPost"])

    def test_short_objective_absent_never_invented(self):
        self.create()
        served = goals_mod.serve_record(
            self.store.get("fixture-goal"))
        self.assertNotIn("shortObjective", served)

    def test_serve_blocked_post_carries_the_pair(self):
        self.create()
        self.store.post_status(
            "fixture-goal",
            {"handle": "main",
             "status_code": "BLOCKED-OWNER",
             "summary": "blocked",
             "basis_citation": {
                 "thread": "main",
                 "at": "2026-10-25T09:00:00+00:00"}},
            now="2026-10-25T12:05:00+00:00")
        last = goals_mod.serve_record(
            self.store.get("fixture-goal"))["lastPost"]
        self.assertEqual(last["status_code"],
                         "BLOCKED-OWNER")
        self.assertEqual(last["basis_citation"]["thread"],
                         "main")
        self.assertEqual(last["verification"]["by"],
                         "main")
        self.assertEqual(last["postedAt"],
                         "2026-10-25T12:05:00+00:00")
        self.assertNotIn("posted_at", last)


if __name__ == "__main__":
    unittest.main()
