"""The rename driver (lib/writes/todo_rename.py) against a fake
project store: legacy ids become title-derived names,
references re-point, derived state follows the todo —
the scheduler entry is deleted under its old name and
never re-created (the rendering is retired), the
attention row moves with the todo — the old token
survives only as `legacy_id:` data, and a second pass
is a no-op. All state lives in tmp dirs behind the env
seams — no live store is touched.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
WB_ROOT = HERE.parents[2]
sys.path.insert(0, str(WB_ROOT))

from lib.writes import bundles as bundle_mod  # noqa: E402
from lib.writes import todo_rename  # noqa: E402
from lib.plans import bundles as parser  # noqa: E402
from lib.progress import attention as att  # noqa: E402
from lib.progress import schedule as ps  # noqa: E402

L1 = "t-01K8Q00000000000000000000A"
L2 = "t-01K8Q00000000000000000000B"
L3 = "t-01K8Q00000000000000000000C"
UNKNOWN = "t-01ZZZZZZZZZZZZZZZZZZZZZZZZ"


def todo_text(id_, title, status="todo", extra_fm="",
              body=""):
    return (f"---\nid: {id_}\ntitle: {title}\n"
            f"status: {status}\ncreated: 2026-11-01\n"
            f"updated: 2026-11-01\n{extra_fm}---\n"
            f"\n{body}\n")


class RenameCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.ws = base / "ws"
        self.proj = self.ws / "fixture-proj"
        self.plans = self.proj / ".plans"
        self.jobs = base / "jobs"
        self.armed = base / "armed"
        for d in (self.jobs, self.armed):
            d.mkdir(parents=True)
        (self.proj / "workbench.yaml").parent.mkdir(
            parents=True, exist_ok=True)
        (self.proj / "workbench.yaml").write_text(
            "name: Fixture Proj\nslug: fixture-proj\n"
            "plans: .plans\n", encoding="utf-8")
        bundle = self.plans / "2026-11-01-work"
        todos = bundle / "todos"
        todos.mkdir(parents=True)
        (bundle / "plan.md").write_text(
            f"# Plan\n\nSequence: {L1} first, then the "
            f"rest.\nHistorical note: {UNKNOWN} was "
            f"dropped.\n", encoding="utf-8")
        (todos / f"{L1}-long-work.md").write_text(
            todo_text(
                L1, "Long work", status="doing",
                extra_fm="progress_check: 30m\n"
                         "progress_armed: "
                         "2026-11-01T11:30:00+00:00\n",
                body=f"Kickoff done. The second half is "
                     f"{L2}."),
            encoding="utf-8")
        (todos / f"{L2}-long-work.md").write_text(
            todo_text(L2, "Long work",
                      body=f"See {L1} for the first half."),
            encoding="utf-8")
        (todos / f"{L3}-solo-task.md").write_text(
            todo_text(L3, "Solo task", body="Alone."),
            encoding="utf-8")
        (todos / "already-named.md").write_text(
            todo_text("already-named", "Already named",
                      body="Untouched."),
            encoding="utf-8")
        (self.ws / "workbench-viewer").mkdir(parents=True)
        self._env = {}
        for key, value in (
                ("WB_WORKSPACE_ROOT", str(self.ws)),
                ("WB_VIEWER_ROOT",
                 str(self.ws / "workbench-viewer")),
                ("WB_SCHEDULER_JOBS_DIR", str(self.jobs)),
                ("WB_ATTENTION_ARMED_DIR", str(self.armed))):
            self._env[key] = os.environ.get(key)
            os.environ[key] = value
        # Arm L1's derived state under its legacy name:
        # the attention row through the writers' own sync
        # path, the scheduler entry hand-written — the
        # rendering is retired, so no writer creates one.
        armed = [t for t in parser.list_todos(self.plans)
                 if t["id"] == L1][0]
        att.sync_todo(self.plans, armed)
        self.entry_file = self.jobs / (
            ps.entry_id("fixture-proj", L1) + ".yaml")
        self.entry_file.write_text(
            "id: " + ps.entry_id("fixture-proj", L1) + "\n"
            "kind: scripted\n"
            "run:\n"
            "  argv:\n"
            "    - ${WS}/workbench-viewer/wb\n"
            "    - --root\n"
            "    - ${WS}/fixture-proj\n"
            "    - progress-check\n"
            f"    - {L1}\n",
            encoding="utf-8")
        self.row_file = self.armed / (
            att.row_id("fixture-proj", L1) + ".json")
        self.assertTrue(self.entry_file.is_file())
        self.assertTrue(self.row_file.is_file())

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def rename(self, apply=True):
        return todo_rename.rename_todos(
            self.plans, apply=apply,
            jobs_directory=self.jobs,
            armed_directory=self.armed)


class TestDryRun(RenameCase):
    def test_dry_run_plans_and_writes_nothing(self):
        before = sorted(
            str(p.relative_to(self.plans))
            for p in self.plans.rglob("*"))
        report = self.rename(apply=False)
        self.assertFalse(report["applied"])
        self.assertEqual(report["todos_scanned"], 4)
        self.assertEqual(report["already_named"], 1)
        names = {r["legacy_id"]: r["name"]
                 for r in report["renamed"]}
        self.assertEqual(names, {L1: "long-work",
                                 L2: "long-work-2",
                                 L3: "solo-task"})
        self.assertGreaterEqual(
            report["references_repointed"], 3)
        after = sorted(
            str(p.relative_to(self.plans))
            for p in self.plans.rglob("*"))
        self.assertEqual(before, after)
        self.assertTrue(self.entry_file.is_file())


class TestApply(RenameCase):
    def test_rename_repoints_everything(self):
        report = self.rename()
        self.assertTrue(report["applied"])
        names = {r["legacy_id"]: r["name"]
                 for r in report["renamed"]}
        self.assertEqual(names, {L1: "long-work",
                                 L2: "long-work-2",
                                 L3: "solo-task"})
        # the shared title resolved by suffix, reported
        self.assertEqual(len(report["collisions"]), 1)
        self.assertEqual(report["collisions"][0]["name"],
                         "long-work-2")
        todos_dir = (self.plans / "2026-11-01-work"
                     / "todos")
        for name in ("long-work", "long-work-2",
                     "solo-task", "already-named"):
            self.assertTrue(
                (todos_dir / f"{name}.md").is_file(), name)
        for old in (L1, L2, L3):
            self.assertFalse(any(
                old in p.name
                for p in todos_dir.iterdir()))
        # records: slug id + legacy_id data; the already
        # named record is untouched by the pass
        by_id = {t["id"]: t
                 for t in parser.list_todos(self.plans)}
        self.assertEqual(by_id["long-work"]["legacy_id"], L1)
        self.assertEqual(by_id["long-work"]["id_form"],
                         "slug")
        self.assertTrue(by_id["long-work"]["valid"])
        self.assertIsNone(by_id["already-named"]["legacy_id"])
        # references re-pointed in plan + bodies
        plan_text = (self.plans / "2026-11-01-work"
                     / "plan.md").read_text()
        self.assertIn("long-work first", plan_text)
        self.assertIn(UNKNOWN, plan_text)
        body = by_id["long-work-2"]["body"]
        self.assertIn("long-work", body)
        self.assertNotIn(L1, body)
        # the old tokens survive ONLY on legacy_id lines
        for path in self.plans.rglob("*.md"):
            for line in path.read_text().split("\n"):
                if L1 in line or L2 in line or L3 in line:
                    self.assertTrue(
                        line.startswith("legacy_id:"), line)
        # the unknown token is named, left untouched
        self.assertIn(UNKNOWN,
                      report["unresolved_references"])
        # derived state: the old entry and row are gone;
        # the row moved to the new name, the entry was
        # NOT re-created — the rendering is retired.
        self.assertFalse(self.entry_file.exists())
        self.assertFalse(self.row_file.exists())
        new_entry = self.jobs / (
            "wb-progress-fixture-proj-long-work.yaml")
        new_row = self.armed / (
            "wb-armed-fixture-proj-long-work.json")
        self.assertFalse(new_entry.exists())
        self.assertTrue(new_row.is_file())
        row = json.loads(new_row.read_text())
        self.assertEqual(row["todo"], "long-work")
        self.assertEqual(report["entries_removed"],
                         [self.entry_file.stem])
        self.assertEqual(report["entries_written"], [])
        self.assertEqual(report["rows_written"],
                         [new_row.stem])
        # lookups resolve by the name only — the legacy
        # token is data now, never a lookup path
        with self.assertRaises(bundle_mod.BundleError):
            bundle_mod.set_todo_status(self.plans, L1, "done")
        moved = bundle_mod.set_todo_status(
            self.plans, "solo-task", "done")
        self.assertEqual(moved["status"], "done")

    def test_second_pass_is_a_no_op(self):
        self.rename()
        report = self.rename()
        self.assertEqual(report["renamed"], [])
        self.assertEqual(report["references_repointed"], 0)
        self.assertEqual(report["already_named"], 4)
        self.assertEqual(report["unresolved"], [])


class TestUnresolved(RenameCase):
    def test_duplicate_legacy_id_is_named_not_renamed(self):
        todos = self.plans / "2026-11-01-work" / "todos"
        (todos / "dupe.md").write_text(
            todo_text(L3, "Solo task clone"),
            encoding="utf-8")
        report = self.rename()
        paths = {u["path"] for u in report["unresolved"]}
        self.assertTrue(any("dupe" in p for p in paths))
        names = {r["legacy_id"] for r in report["renamed"]}
        self.assertNotIn(L3, names)


if __name__ == "__main__":
    unittest.main()
