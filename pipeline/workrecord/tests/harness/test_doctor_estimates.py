"""wb doctor plan-estimate family: the estimate
grammar's refusals over fixture plan trees, the
clean form, and the as-is (pre-amendment) discard.
The family derives from the same lib functions the
feeds use, so the fixtures plant the shapes those
functions read (the harness doctor fixtures in
test_doctor.py, imported here)."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent))

from evaluation import doctor  # noqa: E402
from tests.harness.test_doctor import (  # noqa: E402
    make_project, write)


class TestPlanEstimateChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plans = self.root / ".plans"
        self.plans.mkdir(parents=True)
        self.project = make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self):
        return doctor.plan_todo_findings(self.project)

    def as_is_project(self):
        return make_project(
            self.root, declared={"registration": "as-is"})

    # -- plan-estimate (the estimate grammar)

    ESTIMATE_PLAN = (
        "# Estimated plan\n\n"
        "Status: draft\n\n"
        "## Steps\n\n"
        "### Step 1 — Small edit\n\n"
        "<!-- wb-step\nstep=1\ntodos=small-edit\n"
        "requires=\nest=15m\n"
        "fanout=single lane\n-->\n\n"
        "A plain edit.\n\n"
        "est: 15m\n\n"
        "### Step 2 — Debugging session\n\n"
        "<!-- wb-step\nstep=2\ntodos=debug-session\n"
        "requires=small-edit\nest=45m\n"
        "fanout=single lane\n-->\n\n"
        "A debugging step, under the hour.\n\n"
        "est: 45m\n\n"
        "### Step 3 — Novel derivation\n\n"
        "<!-- wb-step\nstep=3\ntodos=derivation\n"
        "requires=debug-session\nest=2h\n"
        "fanout=single lane\n-->\n\n"
        "Why 2h: a hard algorithmic complexity floor "
        "governs the derivation; why not lower: the "
        "floor is intrinsic to the problem.\n\n"
        "est: 2h\n")

    def estimate_checks(self):
        return [(f["check"], f["subject"])
                for f in self.findings()
                if f["check"] == "plan-estimate"]

    def test_estimate_clean_plan(self):
        write(self.plans / "2026-01-23-estimated.md",
              self.ESTIMATE_PLAN)
        self.assertEqual(self.findings(), [])

    def test_estimate_step_without_est(self):
        write(self.plans / "2026-01-23-nostep.md",
              self.ESTIMATE_PLAN.replace(
                  "est=45m\n", ""))
        self.assertEqual(
            self.estimate_checks(),
            [("plan-estimate",
              "2026-01-23-nostep.md step 2")])

    def test_estimate_step_without_block(self):
        write(self.plans / "2026-01-23-noblock.md",
              self.ESTIMATE_PLAN.replace(
                  "<!-- wb-step\nstep=1\n"
                  "todos=small-edit\nrequires=\n"
                  "est=15m\n"
                  "fanout=single lane\n-->\n", ""))
        self.assertEqual(
            self.estimate_checks(),
            [("plan-estimate",
              "2026-01-23-noblock.md step 1")])

    def test_estimate_overrun_names_no_class(self):
        write(self.plans / "2026-01-23-unclassed.md",
              self.ESTIMATE_PLAN.replace(
                  "Why 2h: a hard algorithmic complexity "
                  "floor governs the derivation; why not "
                  "lower: the floor is intrinsic to the "
                  "problem.",
                  "Why 2h: the derivation is long; why "
                  "not lower: it cannot be shortened."))
        found = [f for f in self.findings()
                 if f["check"] == "plan-estimate"]
        self.assertEqual(len(found), 1)
        self.assertIn("names no long-duration class",
                      found[0]["detail"])

    def test_estimate_overrun_at_thirty_boundary(self):
        # The threshold is thirty minutes: step 2's 45m
        # estimate, justified in prose naming no class,
        # is an unclassed overrun — under the old hour
        # threshold it would have read clean.
        write(self.plans / "2026-01-23-boundary.md",
              self.ESTIMATE_PLAN.replace(
                  "A debugging step, under the hour.",
                  "A long session of plain edits."))
        found = [f for f in self.findings()
                 if f["check"] == "plan-estimate"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["subject"],
                         "2026-01-23-boundary.md step 2")
        self.assertIn("names no long-duration class",
                      found[0]["detail"])

    def test_estimate_overrun_without_justification(self):
        write(self.plans / "2026-01-23-bare.md",
              self.ESTIMATE_PLAN.replace(
                  "Why 2h: a hard algorithmic complexity "
                  "floor governs the derivation; why not "
                  "lower: the floor is intrinsic to the "
                  "problem.", ""))
        found = [f for f in self.findings()
                 if f["check"] == "plan-estimate"]
        self.assertEqual(len(found), 1)
        self.assertIn("no justification",
                      found[0]["detail"])

    def test_estimate_unparseable_value(self):
        write(self.plans / "2026-01-23-vague.md",
              self.ESTIMATE_PLAN.replace(
                  "est=15m", "est=soon"))
        found = [f for f in self.findings()
                 if f["check"] == "plan-estimate"]
        self.assertEqual(len(found), 1)
        self.assertIn("carries no duration",
                      found[0]["detail"])

    def test_estimate_as_is_discarded(self):
        # A pre-amendment corpus (registration: as-is)
        # is flagged by the computation, not failed by
        # it: a plan with no estimate discipline at all
        # posts no plan-estimate findings.
        write(self.plans / "2026-01-23-legacy.md",
              "# Legacy\n\nStatus: draft\n\n"
              "## Steps\n\n### Step 1 — Old form\n\n"
              "Prose only, no step block.\n")
        self.assertEqual(
            doctor.plan_todo_findings(self.as_is_project()),
            [])



if __name__ == "__main__":
    unittest.main()
