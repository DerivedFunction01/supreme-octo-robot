"""wb plan-check: the plan-syntax gate over one plan
file (coding_plan skill — a plan is unfinished until
`wb plan-check` passes on it). One fixture plan per
refusal class under tests/fixtures/plan-check/, each
convicting exactly its class; the passing fixture
asserts the frontier output at the lib level and,
through the CLI, the exit codes (0 pass with the
frontier, 3 refused with findings, 2 unreadable).
The headline fixtures pin the estimate-discipline
extension: a stated plan total over the computed
critical path refuses (the serial-sum-with-fanout
plan is the specimen), a stated total at or under
it passes, and a pass prints the critical path.
The formation fixtures pin the wall-clock class: a
declared worktree or branch per row and a gate per
item refuse, while the same bound stated as a
prohibition in the Rulings passes.
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

    def test_per_row_formation_refused(self):
        findings = self.assert_refused(
            "per-row-formation.md", "per-row formation",
            "per formation group")
        # Both declaration surfaces convict: the step
        # body's "worktree per row" and the fan-out
        # value "per-row worktrees".
        joined = "\n".join(findings)
        self.assertIn("worktree per", joined)
        self.assertIn("per-row worktree", joined)

    def test_per_item_gate_refused(self):
        self.assert_refused("per-item-gate.md",
                            "per-item gate",
                            "queue trigger")

    def test_bound_stated_in_rulings_passes(self):
        # The bound stated as a prohibition, and a
        # per-family fan-out, make no finding.
        self.assertEqual(
            [], findings_of("bound-stated-in-rulings.md"))


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


class Headline(unittest.TestCase):
    """The headline rule (supervision rules, estimates
    passage): a plan's stated total is its wall-clock
    — the critical path over the in-plan requires
    graph at each step's est= — never the serial sum.
    A stated total over the critical path refuses;
    at or under it, and no stated total at all, pass.
    The critical path itself is computed and reported
    either way."""

    def test_stated_total_over_critical_path_refused(self):
        findings = findings_of("stated-total-over.md")
        joined = "\n".join(findings)
        self.assertIn("headline", joined)
        # The finding names the stated figure, the
        # computed critical path, and the chain.
        self.assertIn("2h", joined)
        self.assertIn("40m", joined)
        self.assertIn("st-alpha (30m)", joined)
        self.assertIn("st-join (10m)", joined)

    def test_serial_sum_with_fanout_is_the_specimen(self):
        # Stated 70m is exactly the serial sum
        # (30 + 30 + 10) while steps 1-2 declare a
        # fan-out: the wall-clock is 40m, so the
        # headline refuses.
        findings = findings_of("stated-total-serial-sum.md")
        joined = "\n".join(findings)
        self.assertIn("headline", joined)
        self.assertIn("70m", joined)
        self.assertIn("40m", joined)
        self.assertIn("serial sum", joined)

    def test_stated_total_at_critical_path_passes(self):
        result = plan_check.check_plan_file(
            FIXTURES / "stated-total-within.md")
        self.assertEqual(result["findings"], [])
        critical = result["critical_path"]
        self.assertEqual(critical["minutes"], 40)
        self.assertEqual(
            [e["step"] for e in critical["chain"]], [1, 3])

    def test_stated_total_under_critical_path_passes(self):
        text = (FIXTURES / "stated-total-within.md") \
            .read_text(encoding="utf-8") \
            .replace("Total: 40m", "Total: 30m")
        result = plan_check.check_plan(text)
        self.assertEqual(result["findings"], [])

    def test_no_stated_total_passes_and_reports_path(self):
        # The passing fixture states no total: no
        # headline finding, and the critical path is
        # still computed — 10m -> 20m down the
        # pp-alpha chain, 30m against a 35m serial sum.
        result = plan_check.check_plan_file(
            FIXTURES / "passing-plan.md")
        self.assertEqual(result["findings"], [])
        critical = result["critical_path"]
        self.assertEqual(critical["minutes"], 30)
        self.assertEqual(critical["serial_sum"], 35)
        self.assertEqual(
            [e["todos"] for e in critical["chain"]],
            [["pp-alpha"], ["pp-beta"]])

    def test_unparseable_stated_total_makes_no_finding(self):
        text = (FIXTURES / "passing-plan.md") \
            .read_text(encoding="utf-8") \
            .replace("Status: draft",
                     "Status: draft\nTotal: about a day")
        result = plan_check.check_plan(text)
        self.assertEqual(result["findings"], [])


class HeadlineCli(unittest.TestCase):
    def wb(self, *argv):
        return subprocess.run(
            [PY, str(WB), *argv], capture_output=True,
            text=True)

    def test_pass_prints_critical_path_exit_0(self):
        r = self.wb("plan-check",
                    str(FIXTURES / "stated-total-within.md"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("critical path (wall-clock): 40m",
                      r.stdout)
        self.assertIn("tw-alpha (30m)", r.stdout)
        self.assertIn("tw-join (10m)", r.stdout)

    def test_headline_refusal_exit_3(self):
        r = self.wb("plan-check",
                    str(FIXTURES / "stated-total-over.md"))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("headline", r.stdout)
        self.assertIn("plan refused", r.stdout)


if __name__ == "__main__":
    unittest.main()
