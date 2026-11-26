"""wb plan-check: the plan-syntax gate over one plan
file (coding_plan skill — a plan is unfinished until
`wb plan-check` passes on it). One fixture plan per
refusal class under tests/fixtures/plan-check/, each
convicting exactly its class; the passing fixture
asserts the frontier output at the lib level and,
through the CLI, the exit codes (0 pass with the
frontier, 3 refused with findings, 2 unreadable).
Fixtures are the tests' own — no live plan file is
ever an input.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO.parent))

WB = REPO / "wb"
PY = sys.executable
FIXTURES = REPO / "tests" / "fixtures" / "plan-check"

from lib.plans import plan_check  # noqa: E402


def findings_of(fixture):
    result = plan_check.check_plan_file(FIXTURES / fixture)
    return result["findings"]


class Refusals(unittest.TestCase):
    """Each refusal fixture yields findings, and its
    class's wording is among them."""

    def assert_refused(self, fixture, *needles):
        findings = findings_of(fixture)
        self.assertTrue(
            findings, f"{fixture}: expected findings, got none")
        joined = "\n".join(findings)
        for needle in needles:
            self.assertIn(needle, joined,
                          f"{fixture}: {needle!r} not in {joined!r}")
        return findings

    def test_prose_only_step(self):
        self.assert_refused("prose-only-step.md", "prose-only")

    def test_missing_requires_field(self):
        self.assert_refused("missing-requires.md",
                            "undeclared prerequisites",
                            "requires=")

    def test_dangling_edge(self):
        self.assert_refused("dangling-edge.md",
                            "never-minted-anywhere", "dangling")

    def test_requires_cycle(self):
        findings = self.assert_refused("cycle.md", "cycle")
        joined = "\n".join(findings)
        self.assertIn("cy-one", joined)
        self.assertIn("cy-two", joined)

    def test_fanout_serial_neither(self):
        self.assert_refused("fanout-serial-neither.md",
                            "neither fanout= nor serial=")

    def test_fanout_serial_both(self):
        self.assert_refused("fanout-serial-both.md",
                            "both fanout= and serial=")

    def test_missing_closing_lines(self):
        findings = self.assert_refused(
            "missing-closing-lines.md", "verify:")
        joined = "\n".join(findings)
        self.assertIn("est:", joined)

    def test_est_mismatch(self):
        self.assert_refused("est-mismatch.md",
                            "disagreement", "30m", "45m")

    def test_question_without_recommended(self):
        self.assert_refused("question-no-recommended.md",
                            "qr-home", "recommended")

    def test_missing_status(self):
        self.assert_refused("missing-status.md", "Status")


class Passing(unittest.TestCase):
    def test_passing_fixture_is_clean(self):
        result = plan_check.check_plan_file(
            FIXTURES / "passing-plan.md")
        self.assertEqual(result["findings"], [])

    def test_frontier_is_the_root_steps(self):
        result = plan_check.check_plan_file(
            FIXTURES / "passing-plan.md")
        frontier = [(e["step"], e["todos"], e["serial"])
                    for e in result["frontier"]]
        self.assertEqual(
            frontier,
            [(1, ["pp-alpha"], False),
             (3, ["pp-gamma"], False)])

    def test_sibling_plan_resolves_an_edge(self):
        # A prerequisite minted by a sibling plan in
        # the same .plans dir resolves — the skill's
        # "todo ids anywhere under the same goal".
        with tempfile.TemporaryDirectory() as tmp:
            plans = Path(tmp)
            (plans / "sibling.md").write_text(
                "# Sibling\n\nStatus: draft\n\n## Steps\n\n"
                "### Step 1 — Minting step\n\nWork.\n\n"
                "<!-- wb-step\nstep=1\ntodos=sib-one\n"
                "requires=\nest=5m\nfanout=one lane\n-->\n"
                "files: lib/a.py\n"
                "verify: python3 -m unittest tests.a\n"
                "done when: done\nest: 5m\n",
                encoding="utf-8")
            (plans / "dependent.md").write_text(
                "# Dependent\n\nStatus: draft\n\n## Steps\n\n"
                "### Step 1 — Dependent step\n\nWork.\n\n"
                "<!-- wb-step\nstep=1\ntodos=dep-one\n"
                "requires=sib-one\nest=5m\n"
                "fanout=one lane\n-->\n"
                "files: lib/b.py\n"
                "verify: python3 -m unittest tests.b\n"
                "done when: done\nest: 5m\n",
                encoding="utf-8")
            result = plan_check.check_plan_file(
                plans / "dependent.md")
            self.assertEqual(result["findings"], [])
            # The sibling prerequisite is no in-plan
            # blocker: the step arms at adoption.
            self.assertEqual(
                [e["step"] for e in result["frontier"]], [1])


class Cli(unittest.TestCase):
    def wb(self, *argv):
        return subprocess.run(
            [PY, str(WB), *argv], capture_output=True,
            text=True)

    def test_pass_prints_frontier_exit_0(self):
        r = self.wb("plan-check",
                    str(FIXTURES / "passing-plan.md"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("clean", r.stdout)
        self.assertIn("step 1 — pp-alpha", r.stdout)
        self.assertIn("step 3 — pp-gamma", r.stdout)
        self.assertNotIn("step 2", r.stdout)

    def test_refusal_exit_3_with_findings(self):
        r = self.wb("plan-check",
                    str(FIXTURES / "dangling-edge.md"))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("never-minted-anywhere", r.stdout)
        self.assertIn("plan refused", r.stdout)

    def test_missing_file_exit_2(self):
        r = self.wb("plan-check",
                    str(FIXTURES / "no-such-plan.md"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no such plan file", r.stdout)


if __name__ == "__main__":
    unittest.main()
