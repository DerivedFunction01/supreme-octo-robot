"""Root portability coverage: the repo-scoped leg that
scans every tracked file no package's portability leg
covers.

Before this leg, a package's portability leg scanned only
its own root tree, so the tracked trees outside pipeline/
(apps/, contracts/, docs/, the root files) sat in no scan
root and no leg ever read them — absolute home paths
survived there through every gate, local and bare-clone.
These tests pin the coverage invariant over fixture git
trees: the root set and the package-covered sets are
disjoint, their union is the whole tracked tree, a
specimen in a root-level tree is flagged by the composed
invocation, and the denylist leg applies at the root with
the same auto semantics as a package leg.

Specimens are written into scratch trees at runtime: a
tracked test file carrying an abs-path literal or a
personal literal would itself be a finding under the
legs it pins.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gate import denylist_match, portability, runner

FIXTURES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures", "denylist")
FIXTURE_DENYLIST = os.path.join(FIXTURES, "denylist.txt")


def _fixture_literal():
    with open(FIXTURE_DENYLIST, encoding="utf-8") as fh:
        for line in denylist_match.parse_literals(fh):
            return line
    raise AssertionError("fixture denylist carries no literal")


def _scratch_repo():
    """A fixture git repo: package aa declares a
    portability leg, package bb does not; docs/, apps/
    and a root file sit outside pipeline/."""
    root = Path(tempfile.mkdtemp(prefix="gate-rootcov-"))
    files = {
        "pipeline/aa/gate.json": json.dumps({
            "package": "aa",
            "legs": [{"leg": "portability"}]}),
        "pipeline/aa/code.py": "x = 1\n",
        "pipeline/bb/gate.json": json.dumps({
            "package": "bb",
            "legs": [{"leg": "unittest"}]}),
        "pipeline/bb/code.py": "y = 1\n",
        "docs/note.md": "a clean note\n",
        "apps/app.ts": "export {};\n",
        "top.py": "z = 1\n",
    }
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def _run_root_leg(root, packages):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        outcome = runner.run_root_portability(root, packages)
    return outcome, out.getvalue()


class CoveragePartitionTests(unittest.TestCase):
    def test_root_set_is_the_tracked_tree_minus_portability_roots(self):
        root = _scratch_repo()
        packages = runner.load_packages(root)
        root_files = runner.root_coverage_files(root, packages)
        # aa declares a portability leg: its tree is covered
        # by its own leg and excluded here.
        self.assertNotIn("pipeline/aa/code.py", root_files)
        self.assertNotIn("pipeline/aa/gate.json", root_files)
        # bb declares none: the root leg is its only cover.
        self.assertIn("pipeline/bb/code.py", root_files)
        # The trees outside pipeline/ are the root leg's own.
        self.assertIn("docs/note.md", root_files)
        self.assertIn("apps/app.ts", root_files)
        self.assertIn("top.py", root_files)

    def test_partition_is_disjoint_and_complete(self):
        root = _scratch_repo()
        packages = runner.load_packages(root)
        root_files = set(runner.root_coverage_files(root, packages))
        all_files = set(portability._tracked_files(str(root)))
        covered = all_files - root_files
        self.assertFalse(root_files & covered)
        self.assertEqual(root_files | covered, all_files)
        self.assertTrue(
            all(f.startswith("pipeline/aa/") for f in covered))


class RootLegTests(unittest.TestCase):
    def test_specimen_in_a_root_tree_is_flagged(self):
        root = _scratch_repo()
        specimen = "/".join(["", "home", "someone", "workspace", "x"])
        (root / "docs" / "specimen.md").write_text(
            f"see {specimen} for details\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        packages = runner.load_packages(root)
        with mock.patch.dict(os.environ, {}, clear=True):
            outcome, output = _run_root_leg(root, packages)
        self.assertEqual(outcome.code, 1)
        self.assertFalse(outcome.ok)
        self.assertIn(
            "portability/abs-path: docs/specimen.md:1 "
            "(content withheld)", output)
        self.assertNotIn(specimen, output)

    def test_clean_root_coverage_passes(self):
        root = _scratch_repo()
        packages = runner.load_packages(root)
        with mock.patch.dict(os.environ, {}, clear=True):
            outcome, output = _run_root_leg(root, packages)
        self.assertEqual(outcome.code, 0)
        self.assertTrue(outcome.ok)
        self.assertIn("portability: ok", output)

    def test_denylist_leg_applies_at_the_root_auto(self):
        root = _scratch_repo()
        state = root / "state"
        state.mkdir()
        shutil.copy(FIXTURE_DENYLIST, state / "denylist.txt")
        (root / "docs" / "carrier.md").write_text(
            f"a note naming {_fixture_literal()}\n",
            encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        packages = runner.load_packages(root)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(
                portability.denylist_provisioned(str(root)))
            outcome, output = _run_root_leg(root, packages)
        self.assertEqual(outcome.code, 1)
        self.assertIn(
            "denylist/personal-literal: docs/carrier.md:1 "
            "(content withheld)", output)
        self.assertNotIn(_fixture_literal(), output)


class DeclarationTests(unittest.TestCase):
    def test_run_package_records_the_leg_skipped(self):
        root = _scratch_repo()
        pkg = runner.Package(
            name="gate", root=root,
            decl={"legs": [{
                "leg": "rootportability",
                "name": "root portability coverage",
                "fail_on_denylist": "auto"}]},
            source=root / "gate.json")
        result = runner.run_package(pkg, repo_root=root)
        self.assertEqual(result.skipped,
                         ["root portability coverage"])
        self.assertEqual(result.outcomes, [])
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
