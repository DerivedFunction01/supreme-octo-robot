"""Independent leg verdicts: every declared leg of a
package executes and verdicts, even when an earlier leg
is red.

The runner's original composition was fail-fast within
a package (the retired check files' semantics): the
first red leg aborted the package, and every later leg
went unverdicted. The 2026-11-15 composed re-gate
showed the cost in the formation's own log — attention's
ruff-format failure ended its package block, so its
ruff-lint and suite legs never ran and the attention
tail stack stood unverdicted behind a formatting
finding; the platform suite verdicted only because the
formation carries a diagnostic patch (leg 1D) that
re-runs it under a leg filter.

These tests pin the cured composition over fixture
packages: a failing early leg (a command leg; and, in
the re-gate's own shape, a failing ruff-format leg)
still runs and verdicts every later leg, including a
suite leg after the failing static leg; the package
verdict is the conjunction; the printed per-leg verdict
lines — the lines the formation greps — appear for
every leg; and a leg filter still only narrows the
selection.
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gate import runner


def _scratch_package():
    """A fixture package root: one passing suite module
    under tests/, an empty var/ state dir (the isolation
    leg's watched subpath, in the attention form)."""
    root = Path(tempfile.mkdtemp(prefix="gate-legverdicts-"))
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "__init__.py").write_text(
        "", encoding="utf-8")
    (root / "tests" / "test_fixture.py").write_text(
        "import unittest\n\n\n"
        "class FixtureTests(unittest.TestCase):\n"
        "    def test_passes(self):\n"
        "        self.assertTrue(True)\n",
        encoding="utf-8")
    (root / "var").mkdir()
    return root


def _package(root, legs):
    return runner.Package(
        name="fixture", root=root,
        decl={"package": "fixture", "python": "system",
              "legs": legs},
        source=root / "gate.json")


def _run(pkg):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = runner.run_package(pkg, repo_root=pkg.root)
    return result, out.getvalue()


def _command(name, code):
    return {"leg": "command", "name": name,
            "argv": ["{python}", "-c",
                     f"import sys; sys.exit({code})"]}


SUITE_LEG = {"leg": "unittest", "name": "fixture suite",
             "start": "tests", "top": "."}


class IndependentVerdictTests(unittest.TestCase):
    def test_failing_early_leg_leaves_no_leg_unverdicted(self):
        root = _scratch_package()
        pkg = _package(root, [
            _command("early failure", 3),
            dict(SUITE_LEG),
            _command("late pass", 0),
        ])
        result, output = _run(pkg)
        self.assertEqual(
            [o.name for o in result.outcomes],
            ["early failure", "fixture suite", "late pass"])
        self.assertEqual(
            [o.ok for o in result.outcomes],
            [False, True, True])
        self.assertFalse(result.ok)
        self.assertEqual(result.skipped, [])
        # The verdict lines the formation greps exist for
        # every leg, red or green.
        for line in ("-- FAIL: early failure",
                     "-- PASS: fixture suite",
                     "-- PASS: late pass"):
            self.assertIn(line, output)

    def test_suite_leg_verdicts_after_a_failing_static_leg(self):
        # The re-gate's leg-4 shape: ruff format red, then
        # ruff lint and the (isolation-wrapped) suite must
        # still execute and verdict. The ruff legs are
        # stubbed at the component seam — the composition
        # is what is pinned; the components have their own
        # tests.
        root = _scratch_package()
        pkg = _package(root, [
            {"leg": "ruff-format", "name": "ruff format",
             "targets": ["mod.py"]},
            {"leg": "ruff-lint", "name": "ruff lint",
             "targets": ["mod.py"]},
            {"leg": "isolation-unittest",
             "name": "fixture test suite",
             "start": "tests", "top": ".",
             "state": {"subpaths": ["var"],
                       "exclude_first": ["venv"]}},
        ])
        calls = []

        def fake_format(root_, targets, python, fix=False):
            calls.append("ruff format")
            return 1

        def fake_lint(root_, targets, python, fix=False):
            calls.append("ruff lint")
            return 0

        with mock.patch.object(
                runner.staticlegs, "ruff_format", fake_format), \
                mock.patch.object(
                    runner.staticlegs, "ruff_lint", fake_lint):
            result, output = _run(pkg)
        self.assertEqual(calls, ["ruff format", "ruff lint"])
        self.assertEqual(
            [o.name for o in result.outcomes],
            ["ruff format", "ruff lint", "fixture test suite"])
        self.assertEqual(
            [o.ok for o in result.outcomes],
            [False, True, True])
        self.assertFalse(result.ok)
        for line in ("-- FAIL: ruff format",
                     "-- PASS: ruff lint",
                     "-- PASS: fixture test suite"):
            self.assertIn(line, output)

    def test_green_package_verdicts_every_leg(self):
        root = _scratch_package()
        pkg = _package(root, [
            _command("first pass", 0),
            _command("second pass", 0),
        ])
        result, _output = _run(pkg)
        self.assertEqual(
            [o.ok for o in result.outcomes], [True, True])
        self.assertTrue(result.ok)

    def test_leg_filter_still_only_narrows_the_selection(self):
        root = _scratch_package()
        pkg = _package(root, [
            _command("early failure", 3),
            dict(SUITE_LEG),
            _command("late pass", 0),
        ])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = runner.run_package(
                pkg, repo_root=root, legs_filter=["unittest"])
        self.assertEqual(
            [o.name for o in result.outcomes], ["fixture suite"])
        self.assertEqual(
            sorted(result.skipped), ["early failure", "late pass"])
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
