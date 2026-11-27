"""Timing-ledger Step 3 (wb timing-ledger plan):
mint-time carrying.

The wb-step grammar gains position= — the step's
fan-out position (serial / branch / fan-in,
grammar.FANOUT_POSITIONS) — validated by plan-check
in the same enforced form as est: a well-formed value
passes, a malformed one is refused. The mint
(`wb todo new --step N`, lib create_todo) reads the
bundle plan's block for step N and writes its est=
and position= into the minted todo's front-matter,
immutable from the mint; an explicit caller figure
wins and the block fills only what the caller left
open. The activation move (set_todo_status) records
the acting worktree when the caller supplies it —
front-matter stamp plus the move's transition line —
with editor identity (actor) and worktree carried as
independent fields. All state lives in tmp dirs.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
WB_ROOT = HERE.parents[2]
sys.path.insert(0, str(WB_ROOT))

from lib.plans import bundles as parser  # noqa: E402
from lib.plans import plan_check  # noqa: E402
from lib.plans.parser import (FANOUT_POSITIONS,  # noqa: E402
                              extract_step_blocks)
from lib.writes import bundles as bundle_mod  # noqa: E402
from lib.writes import transitions as tr  # noqa: E402

WB = WB_ROOT / "wb"
PY = sys.executable

PLAN = """# Fixture plan

Status: adopted
Feature: timing-fixture

## Steps

### Step 1 — Serial groundwork

Lay the ground.

<!-- wb-step
step=1
todos=groundwork
requires=
est=30m
position=serial
serial=the ground everything stands on
-->

files: lib/a.py
verify: fixture
done when: grounded
est: 30m

### Step 2 — Branch work

Run the branch.

<!-- wb-step
step=2
todos=branch-work
requires=groundwork
est=45m
position=branch
fanout=two lanes over one worktree
-->

files: lib/b.py
verify: fixture
done when: branched
est: 45m
"""

BAD_POSITION_PLAN = PLAN.replace(
    "position=branch", "position=sideways")


def plan_with(position_line):
    """The one-step plan text plan-check reads, with
    the given position= line in its block (or none)."""
    block = ("<!-- wb-step\nstep=1\ntodos=only-step\n"
             "requires=\nest=5m\nfanout=one lane\n")
    if position_line is not None:
        block += position_line + "\n"
    block += "-->\n"
    return ("# One step\n\nStatus: draft\n\n## Steps\n\n"
            "### Step 1 — Only step\n\nWork.\n\n"
            + block
            + "files: lib/a.py\nverify: fixture\n"
              "done when: done\nest: 5m\n")


class TestPositionGrammar(unittest.TestCase):
    def test_block_reader_surfaces_position(self):
        blocks = extract_step_blocks(PLAN)
        by_step = {b["step"]: b for b in blocks}
        self.assertEqual(by_step[1]["position"], "serial")
        self.assertEqual(by_step[2]["position"], "branch")
        self.assertIsNone(
            extract_step_blocks(plan_with(None))[0]
            ["position"])

    def test_one_value_set_two_surfaces(self):
        # The grammar's set and the writer's are the
        # same tuple — one home, both consumers.
        self.assertEqual(FANOUT_POSITIONS,
                         bundle_mod.FANOUT_POSITIONS)
        self.assertEqual(FANOUT_POSITIONS,
                         ("serial", "branch", "fan-in"))


class TestPlanCheckPosition(unittest.TestCase):
    def findings(self, text):
        return plan_check.check_plan(text)["findings"]

    def test_well_formed_position_passes(self):
        self.assertEqual(
            [], self.findings(plan_with("position=branch")))

    def test_every_position_value_passes(self):
        for value in FANOUT_POSITIONS:
            self.assertEqual(
                [], self.findings(
                    plan_with(f"position={value}")),
                value)

    def test_malformed_position_is_refused(self):
        findings = self.findings(
            plan_with("position=sideways"))
        self.assertEqual(1, len(findings))
        self.assertIn("position='sideways'", findings[0])
        self.assertIn("serial, branch, fan-in",
                      findings[0])

    def test_undeclared_position_is_no_finding(self):
        # The field is additive, like the front-matter
        # it feeds: absence is carried as absence.
        self.assertEqual([], self.findings(plan_with(None)))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plans = Path(self.tmp.name) / ".plans"
        self.plans.mkdir(parents=True)
        bundle_mod.create_bundle(
            self.plans, "work", plan=True,
            today="2026-11-27")
        self.bundle_dir = bundle_mod.find_bundle_dir(
            self.plans, "work")

    def write_plan(self, text=PLAN):
        (self.bundle_dir / "plan.md").write_text(
            text, encoding="utf-8")

    def create(self, title="Branch work", **kw):
        kw.setdefault("created", "2026-11-27")
        kw.setdefault("updated", "2026-11-27")
        return bundle_mod.create_todo(
            self.plans, "work", title, **kw)

    def read_back(self, result):
        text = Path(result["file"]).read_text(
            encoding="utf-8")
        return parser.parse_todo(text), text


class TestMintCarrying(Fixture):
    def test_step_mint_carries_block_est_and_position(self):
        self.write_plan()
        result = self.create(step=2)
        self.assertEqual(result["est"], "45m")
        self.assertEqual(result["fanout_position"],
                         "branch")
        parsed, text = self.read_back(result)
        # Read back through parse_todo: the figures are
        # the file's front-matter, not the verb's echo.
        self.assertEqual(parsed["est"], "45m")
        self.assertEqual(parsed["fanout_position"],
                         "branch")
        self.assertIn("est: 45m", text)
        self.assertIn("fanout_position: branch", text)

    def test_serial_step_carries_serial(self):
        self.write_plan()
        result = self.create("Groundwork", step=1)
        self.assertEqual(result["est"], "30m")
        self.assertEqual(result["fanout_position"],
                         "serial")

    def test_explicit_figure_wins_block_fills_the_rest(self):
        self.write_plan()
        result = self.create(step=2, est="1h")
        self.assertEqual(result["est"], "1h")
        self.assertEqual(result["fanout_position"],
                         "branch")

    def test_step_with_no_block_mints_as_before(self):
        self.write_plan()
        result = self.create("Unblocked work", step=7)
        self.assertIsNone(result["est"])
        self.assertIsNone(result["fanout_position"])
        _, text = self.read_back(result)
        self.assertNotIn("fanout_position:", text)

    def test_no_step_reads_no_block(self):
        self.write_plan()
        result = self.create("Plain work")
        self.assertIsNone(result["est"])
        self.assertIsNone(result["fanout_position"])

    def test_malformed_block_position_is_refused(self):
        self.write_plan(BAD_POSITION_PLAN)
        with self.assertRaises(bundle_mod.BundleError):
            self.create(step=2)


class TestActivationWorktree(Fixture):
    def test_doing_move_records_the_worktree(self):
        result = self.create()
        todo_id = result["id"]
        moved = bundle_mod.set_todo_status(
            self.plans, todo_id, "doing",
            worktree="wt-lane-a", actor="editor-1",
            today="2026-11-27")
        self.assertEqual(moved["worktree"], "wt-lane-a")
        parsed, text = self.read_back(moved)
        self.assertEqual(parsed["worktree"], "wt-lane-a")
        records = tr.transitions_in(text)
        move = records[-1]
        self.assertEqual(move["verb"], "set-status")
        self.assertEqual(move["new"], "doing")
        # Editor identity and worktree are independent
        # fields on the same line: the actor is the
        # editor, the worktree the tree it ran in.
        self.assertEqual(move["actor"], "editor-1")
        self.assertEqual(move["worktree"], "wt-lane-a")

    def test_move_without_worktree_leaves_both_untouched(self):
        result = self.create()
        todo_id = result["id"]
        bundle_mod.set_todo_status(
            self.plans, todo_id, "doing",
            worktree="wt-lane-a", today="2026-11-27")
        moved = bundle_mod.set_todo_status(
            self.plans, todo_id, "done",
            today="2026-11-27")
        parsed, text = self.read_back(moved)
        # The stamp rides through a move that names no
        # worktree; the move's own line carries none.
        self.assertEqual(parsed["worktree"], "wt-lane-a")
        self.assertNotIn("worktree",
                         tr.transitions_in(text)[-1])

    def test_later_activation_replaces_the_stamp(self):
        result = self.create()
        todo_id = result["id"]
        bundle_mod.set_todo_status(
            self.plans, todo_id, "doing",
            worktree="wt-lane-a", today="2026-11-27")
        moved = bundle_mod.set_todo_status(
            self.plans, todo_id, "blocked",
            worktree="wt-lane-b", today="2026-11-27")
        parsed, _ = self.read_back(moved)
        self.assertEqual(parsed["worktree"], "wt-lane-b")


class TestMintCli(unittest.TestCase):
    """The verb itself: `wb todo new --step N` over a
    fixture project, and `wb todo set --worktree`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir(parents=True)
        (self.root / "workbench.yaml").write_text(
            "name: Fixture\nregistry: workbench/registry.db\n"
            "plans: .plans\n")

    def wb(self, *argv, expect=0):
        r = subprocess.run(
            [PY, str(WB), "--root", str(self.root), *argv],
            capture_output=True, text=True)
        if expect is not None:
            self.assertEqual(
                r.returncode, expect,
                f"wb {argv} -> {r.returncode}\n{r.stdout}\n"
                f"{r.stderr}")
        return r

    def test_step_mint_and_activation_over_cli(self):
        r = self.wb("bundle", "new", "demo", "--plan")
        bundle = json.loads(r.stdout)["id"]
        plan_files = list(
            (self.root / ".plans").glob("*/plan.md"))
        self.assertEqual(1, len(plan_files))
        plan_files[0].write_text(PLAN, encoding="utf-8")
        r = self.wb("todo", "new", bundle, "Branch work",
                    "--step", "2")
        todo = json.loads(r.stdout)
        self.assertEqual(todo["est"], "45m")
        self.assertEqual(todo["fanout_position"],
                         "branch")
        parsed = parser.parse_todo(
            Path(todo["file"]).read_text(encoding="utf-8"))
        self.assertEqual(parsed["est"], "45m")
        self.assertEqual(parsed["fanout_position"],
                         "branch")
        r = self.wb("todo", "set", todo["id"], "doing",
                    "--worktree", "wt-cli")
        moved = json.loads(r.stdout)
        self.assertEqual(moved["worktree"], "wt-cli")
        text = Path(todo["file"]).read_text(
            encoding="utf-8")
        self.assertEqual(
            tr.transitions_in(text)[-1]["worktree"],
            "wt-cli")


if __name__ == "__main__":
    unittest.main()
