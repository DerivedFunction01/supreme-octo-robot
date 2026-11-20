"""Drain leg tests (supervision plan Step 4): the
continuation pass's drain leg hands each active
programme's drain declaration fields to the workbench
per project and reports a drain that raised or
archived; a workbench that cannot serve a project
skips it without failing the pass. The workbench
client is faked at the port — no live store, no live
workbench, and the leg itself writes no sends and no
progress checkpoints (the checkpoint stays the lane's
act; the detector's acts are workbench-side).
"""

import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import store as store_mod  # noqa: E402
from attention.infra import wb_client  # noqa: E402
from attention.services.measure import continuation  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)

PROGRAMME = {
    "slug": "fixture-programme",
    "label": "Fixture programme",
    "handles": ["@lane"],
    "wb_projects": ["proj-a", "proj-b"],
    "drain_tail": ["Consolidation", "Doc updates",
                   "Performance pass"],
    "drain_bundles": ["2026-11-18-fixture-plan"],
    "contract_path": "/fixture/.plans/"
                     "2026-11-18-fixture-plan/contract.md",
    "worktree_roots": ["/fixture/ws/repo-*"],
}


def _state(*programmes):
    state = store_mod.empty_state()
    state["programmes"] = list(programmes)
    return state


def _settings(tmp):
    return Settings(data_path=None,
                    run_records_dir=Path(tmp) / "records")


class DrainLegTests(unittest.TestCase):

    def test_pass_hands_declarations_per_project(self):
        calls = []

        def fake_run_drain(url, project, declarations, timeout):
            calls.append((project, declarations))
            return {"drain": [{
                "programme": "fixture-programme",
                "raised": ["t-1"], "archived": []}]}

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(
                    wb_client, "run_drain", fake_run_drain):
            changed = continuation.run_drain_pass(
                _state(PROGRAMME), _settings(tmp), NOW)
        self.assertTrue(changed)
        self.assertEqual(
            [project for project, _ in calls],
            ["proj-a", "proj-b"])
        for _, declarations in calls:
            self.assertEqual(len(declarations), 1)
            decl = declarations[0]
            # The seam: exactly the drain fields ride.
            self.assertEqual(
                decl["drain_tail"], PROGRAMME["drain_tail"])
            self.assertEqual(
                decl["drain_bundles"],
                PROGRAMME["drain_bundles"])
            self.assertEqual(
                decl["contract_path"],
                PROGRAMME["contract_path"])
            self.assertEqual(
                decl["worktree_roots"],
                PROGRAMME["worktree_roots"])

    def test_registry_tail_binds_over_the_store_row(self):
        # The Step 1 supervision registry is the tail
        # set's home: a programme the registry declares
        # hands over its registry tail — steampowernj's
        # baked-in tech-debt item included — whatever
        # the store row itself carries.
        programme = dict(PROGRAMME, slug="steampowernj",
                         drain_tail=["Store row tail"])
        seen = []

        def fake_run_drain(url, project, declarations, timeout):
            seen.extend(declarations)
            return {"drain": []}

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(
                    wb_client, "run_drain", fake_run_drain):
            continuation.run_drain_pass(
                _state(programme), _settings(tmp), NOW)
        self.assertTrue(seen)
        titles = [
            entry.get("title") if isinstance(entry, dict)
            else entry
            for entry in seen[0]["drain_tail"]]
        self.assertIn("Tech-debt paydown", titles)
        self.assertNotIn("Store row tail", titles)

    def test_quiet_drain_changes_nothing(self):
        def fake_run_drain(url, project, declarations, timeout):
            return {"drain": [{
                "programme": "fixture-programme",
                "raised": [], "archived": []}]}

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(
                    wb_client, "run_drain", fake_run_drain):
            changed = continuation.run_drain_pass(
                _state(PROGRAMME), _settings(tmp), NOW)
        self.assertFalse(changed)

    def test_unavailable_workbench_skips_the_project(self):
        def fake_run_drain(url, project, declarations, timeout):
            raise wb_client.WbUnavailable("down")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(
                    wb_client, "run_drain", fake_run_drain):
            changed = continuation.run_drain_pass(
                _state(PROGRAMME), _settings(tmp), NOW)
        self.assertFalse(changed)

    def test_retired_programme_is_not_drained(self):
        calls = []

        def fake_run_drain(url, project, declarations, timeout):
            calls.append(project)
            return {"drain": []}

        retired = dict(PROGRAMME, retired=True)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(
                    wb_client, "run_drain", fake_run_drain):
            continuation.run_drain_pass(
                _state(retired), _settings(tmp), NOW)
        self.assertEqual(calls, [])

    def test_run_pass_includes_the_drain_leg(self):
        calls = []

        def fake_run_drain(url, project, declarations, timeout):
            calls.append(project)
            return {"drain": [{
                "programme": "fixture-programme",
                "raised": [], "archived": [{"tree": "wt-1"}]}]}

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(
                    wb_client, "run_drain", fake_run_drain):
            state = _state(PROGRAMME)
            changed = continuation.run_pass(
                state, _settings(tmp), NOW)
        self.assertTrue(changed)
        self.assertEqual(calls, ["proj-a", "proj-b"])
        # The leg writes no sends: the drain's acts are
        # workbench-side, and no lane checkpoint exists
        # anywhere in the state the pass touched.
        self.assertEqual(state.get("sends") or [], [])


if __name__ == "__main__":
    unittest.main()
