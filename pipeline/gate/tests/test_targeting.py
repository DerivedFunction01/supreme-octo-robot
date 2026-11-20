"""Targeting: the AST lineage over a scratch package, the
change classifier, and the prose-only filter (the git
cases build a real scratch repo)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from gate.targeting.gitdiff import (GitStatusSnapshot,
                                    PackageLayout, classify)
from gate.targeting.lineage import LineageGraph
from gate.targeting.prose import is_prose_only, prose_only_python_files


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="gate-lineage-"))
        _write(self.root / "pkg" / "__init__.py", "")
        _write(self.root / "pkg" / "core.py", "VALUE = 1\n")
        _write(self.root / "pkg" / "uses.py",
               "from pkg import core\n\nOTHER = core.VALUE\n")
        _write(self.root / "tests" / "__init__.py", "")
        _write(self.root / "tests" / "test_core.py",
               "from pkg import core\n")
        _write(self.root / "tests" / "test_uses.py",
               "from pkg import uses\n")
        _write(self.root / "tests" / "test_other.py",
               "import unittest\n")
        self.graph = LineageGraph(
            self.root, [self.root], [self.root])
        self.graph.sync_files()

    def _resolve(self, sources=(), tests=(), conftests=()):
        return self.graph.resolve_tests(
            tuple(sources), tuple(tests), tuple(conftests),
            test_prefixes=("tests/",),
            mirror_dirs=[self.root / "tests"])

    def test_change_selects_direct_and_transitive(self):
        result = self._resolve(sources=("pkg/core.py",))
        self.assertEqual(
            set(result.test_files),
            {"tests/test_core.py", "tests/test_uses.py"})
        self.assertIn("mirror_of:pkg/core.py",
                      result.reasons["tests/test_core.py"])

    def test_changed_test_selects_itself(self):
        result = self._resolve(tests=("tests/test_other.py",))
        self.assertEqual(result.test_files, ("tests/test_other.py",))
        self.assertEqual(result.reasons["tests/test_other.py"],
                         ["direct_test_edit"])

    def test_unrelated_change_selects_nothing(self):
        result = self._resolve(sources=("pkg/uses.py",))
        self.assertEqual(set(result.test_files),
                         {"tests/test_uses.py"})


class ClassifyTests(unittest.TestCase):
    def test_classification_by_layout(self):
        snapshot = GitStatusSnapshot(modified_files=(
            "pipeline/pkg/lib/core.py",
            "pipeline/pkg/tests/test_core.py",
            "pipeline/pkg/tests/conftest.py",
            "pipeline/pkg/gate.json",
            "pipeline/other/lib/x.py",
            "pipeline/pkg/notes.md",
        ))
        layout = PackageLayout(
            root="pipeline/pkg", test_dirs=("tests",),
            full_suite_triggers=("gate.json",))
        changes = classify(snapshot, layout)
        self.assertEqual(changes.sources, ("lib/core.py",))
        self.assertEqual(changes.tests, ("tests/test_core.py",))
        self.assertEqual(changes.conftests, ("tests/conftest.py",))
        self.assertTrue(changes.touches_trigger)
        self.assertFalse(changes.docs_only)

    def test_docs_only(self):
        snapshot = GitStatusSnapshot(
            modified_files=("pipeline/pkg/notes.md",))
        layout = PackageLayout(root="pipeline/pkg")
        changes = classify(snapshot, layout)
        self.assertTrue(changes.has_changes)
        self.assertTrue(changes.docs_only)


class ProseTests(unittest.TestCase):
    def test_is_prose_only(self):
        base = '"""Old docstring."""\n\nVALUE = 1\n'
        prose = '"""New docstring."""\n\nVALUE = 1\n'
        logic = '"""Old docstring."""\n\nVALUE = 2\n'
        self.assertTrue(is_prose_only(base, prose))
        self.assertFalse(is_prose_only(base, logic))

    def test_prose_only_files_against_head(self):
        root = Path(tempfile.mkdtemp(prefix="gate-prose-"))
        _write(root / "mod.py", '"""One."""\n\nVALUE = 1\n')
        env = {"GIT_CONFIG_NOSYSTEM": "1",
               "GIT_AUTHOR_NAME": "gate-test",
               "GIT_AUTHOR_EMAIL": "gate-test@localhost",
               "GIT_COMMITTER_NAME": "gate-test",
               "GIT_COMMITTER_EMAIL": "gate-test@localhost"}
        import os
        full_env = {**os.environ, **env}
        subprocess.run(["git", "init", "-q"], cwd=root,
                       env=full_env, check=True)
        subprocess.run(["git", "add", "mod.py"], cwd=root,
                       env=full_env, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=root,
                       env=full_env, check=True)
        _write(root / "mod.py", '"""Two."""\n\nVALUE = 1\n')
        found = prose_only_python_files(("mod.py",), (), root)
        self.assertEqual(found, frozenset({"mod.py"}))
        _write(root / "mod.py", '"""Two."""\n\nVALUE = 2\n')
        found = prose_only_python_files(("mod.py",), (), root)
        self.assertEqual(found, frozenset())


if __name__ == "__main__":
    unittest.main()
