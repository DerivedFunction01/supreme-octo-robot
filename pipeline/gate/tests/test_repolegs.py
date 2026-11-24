"""The repo-scoped default-on legs (the default-on
reversal): coverage derives from the tree, never from a per-package
declaration. Pinned here:

- writer-uniqueness in its repo form scans the tracked
  population only — an untracked staging file carrying a
  violating write is not yet the tree's code and is not
  measured; the same file, tracked, fails by name.
- import-isolation in its repo form runs for every
  composed package automatically and takes its recorded
  exceptions from the repo declaration (passed in,
  repo-relative paths rebased per package): a covered
  import is a note, an undeclared one a failure, a
  declaration whose file no longer imports the root a
  stale-exception failure.
- the scanner-runner row discovers a package's
  scanners.py by tree shape alone and runs it; a tree
  with none reports an empty population, green.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gate import importisolation, runner, writeruniqueness as wu


def _git(root, *args):
    subprocess.run(
        ["git", "-c", "core.fsync=none", *args],
        cwd=root, check=True, capture_output=True, text=True,
        env={**os.environ,
             "GIT_AUTHOR_NAME": "gate-test",
             "GIT_AUTHOR_EMAIL": "gate-test@example.invalid",
             "GIT_COMMITTER_NAME": "gate-test",
             "GIT_COMMITTER_EMAIL": "gate-test@example.invalid"})


VIOLATING = (
    "import os\n"
    "STATE = os.path.join('var', 'state.json')\n"
    "def save(data):\n"
    "    with open(STATE, 'w') as fh:\n"
    "        fh.write(data)\n"
)


class RepoWriterUniquenessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="repolegs-"))
        self.addCleanup(
            shutil.rmtree, self.root, ignore_errors=True)
        _git(self.root, "init", "-q")
        (self.root / "clean.py").write_text(
            "VALUE = 1\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "fixture")

    def test_untracked_violating_file_is_not_measured(self):
        (self.root / "staging.py").write_text(
            VIOLATING, encoding="utf-8")
        _rows, failures, scanned = wu.scan(
            self.root, self.root, tracked=True)
        self.assertEqual(failures, [])
        self.assertEqual(scanned, 1)

    def test_tracked_violating_file_fails_by_name(self):
        (self.root / "staging.py").write_text(
            VIOLATING, encoding="utf-8")
        _git(self.root, "add", "-A")
        _rows, failures, _scanned = wu.scan(
            self.root, self.root, tracked=True)
        self.assertEqual(
            [(row[0], row[2]) for row in failures],
            [("staging.py", "truncate-write")])


class RepoImportIsolationTests(unittest.TestCase):
    def _package(self, root, name, files):
        pkg = root / "pipeline" / name
        pkg.mkdir(parents=True)
        (pkg / "gate.json").write_text(
            '{"package": "%s", "legs": []}' % name,
            encoding="utf-8")
        for rel, text in files.items():
            (pkg / rel).write_text(text, encoding="utf-8")
        return pkg

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="repolegs-"))
        self.addCleanup(
            shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "pipeline").mkdir()
        self._package(self.root, "gate", {})
        self._package(self.root, "alpha", {
            "init_venv.py": "from gate.venvbuild import build\n",
            "core.py": "import dispatch.ledger\n",
        })
        self._package(self.root, "dispatch", {})

    def test_repo_form_covers_undeclared_packages(self):
        # alpha declares no importisolation leg anywhere;
        # the repo form measures it anyway. The recorded
        # exception (repo-relative) covers the bootstrap
        # import as a note; the dispatch import fails.
        packages = runner.load_packages(self.root)
        gate_pkg = next(p for p in packages if p.name == "gate")
        gate_pkg.decl["legs"] = [{
            "leg": "repoimportisolation",
            "exceptions": [{
                "path": "pipeline/alpha/init_venv.py",
                "root": "gate", "kind": "bootstrap",
            }],
        }]
        outcome = runner.run_repo_importisolation(
            self.root, packages)
        self.assertFalse(outcome.ok)

    def test_covered_import_alone_passes(self):
        packages = runner.load_packages(self.root)
        alpha = next(p for p in packages if p.name == "alpha")
        (alpha.root / "core.py").write_text(
            "VALUE = 1\n", encoding="utf-8")
        gate_pkg = next(p for p in packages if p.name == "gate")
        gate_pkg.decl["legs"] = [{
            "leg": "repoimportisolation",
            "exceptions": [{
                "path": "pipeline/alpha/init_venv.py",
                "root": "gate", "kind": "bootstrap",
            }],
        }]
        outcome = runner.run_repo_importisolation(
            self.root, packages)
        self.assertTrue(outcome.ok)


class RepoScannerDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="repolegs-"))
        self.addCleanup(
            shutil.rmtree, self.root, ignore_errors=True)
        pkg = self.root / "pipeline" / "demo"
        pkg.mkdir(parents=True)
        (pkg / "gate.json").write_text(
            '{"package": "demo", "python": "system", "legs": []}',
            encoding="utf-8")

    def test_empty_population_is_green(self):
        packages = runner.load_packages(self.root)
        outcome = runner.run_repo_scanners(self.root, packages)
        self.assertTrue(outcome.ok)

    def test_discovered_runner_runs(self):
        pkg = self.root / "pipeline" / "demo"
        (pkg / "scanners.py").write_text(
            "def run_all(root):\n    return 0\n",
            encoding="utf-8")
        packages = runner.load_packages(self.root)
        outcome = runner.run_repo_scanners(self.root, packages)
        self.assertTrue(outcome.ok)

    def test_failing_runner_fails_the_row(self):
        pkg = self.root / "pipeline" / "demo"
        (pkg / "scanners.py").write_text(
            "def run_all(root):\n    return 3\n",
            encoding="utf-8")
        packages = runner.load_packages(self.root)
        outcome = runner.run_repo_scanners(self.root, packages)
        self.assertFalse(outcome.ok)


if __name__ == "__main__":
    unittest.main()
