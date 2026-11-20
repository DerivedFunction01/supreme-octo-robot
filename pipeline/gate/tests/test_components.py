"""The remaining components: isolation hashing, the
scanner-leg invocation shape, and the venv bootstrap's
resolution/config (no venv is built here — the build proof
runs against a real package in the gate record)."""
import tempfile
import unittest
from pathlib import Path

from gate import isolation, staticlegs, venvbuild


class IsolationTests(unittest.TestCase):
    def test_snapshot_detects_change(self):
        root = Path(tempfile.mkdtemp(prefix="gate-isolation-"))
        state = root / "var"
        (state / "data").mkdir(parents=True)
        (state / "data" / "a.txt").write_text("one\n")
        (state / "venv" / "skip.txt").parent.mkdir(parents=True)
        (state / "venv" / "skip.txt").write_text("skip\n")
        before = isolation.state_snapshot(
            str(root), ["var"], exclude_first=())
        self.assertIn("var/data/a.txt", before)
        nested = isolation.state_snapshot(
            str(root), ["var"], exclude_first=("venv",))
        self.assertNotIn("var/venv/skip.txt", nested)
        (state / "data" / "a.txt").write_text("two\n")
        after = isolation.state_snapshot(str(root), ["var"])
        self.assertEqual(
            isolation.changed_paths(before, after),
            ["var/data/a.txt"])


class ScannerLegTests(unittest.TestCase):
    def test_scanner_leg_invokes_runner(self):
        root = Path(tempfile.mkdtemp(prefix="gate-scanners-"))
        (root / "stubrunner.py").write_text(
            "def run_all(root):\n    return 0\n", encoding="utf-8")
        self.assertEqual(
            staticlegs.scanners(str(root), "stubrunner"), 0)
        # A different size, and the stale bytecode cache
        # cleared: a same-length rewrite inside one mtime
        # tick would otherwise serve the first stub's pyc.
        (root / "stubrunner.py").write_text(
            "def run_all(root):\n    return 1 + 2\n", encoding="utf-8")
        for pyc in (root / "__pycache__").glob("stubrunner.*.pyc"):
            pyc.unlink()
        self.assertEqual(
            staticlegs.scanners(str(root), "stubrunner"), 3)


class VenvBuildTests(unittest.TestCase):
    def test_find_uv_resolves_or_none(self):
        found = venvbuild.find_uv()
        self.assertTrue(found is None or Path(found).exists())

    def test_config_defaults(self):
        cfg = venvbuild.VenvConfig(
            root=Path("pkg"), venv_dir=Path(".venv"),
            python_spec="3.11")
        self.assertIsNone(cfg.requirements)
        self.assertFalse(cfg.fallback)


if __name__ == "__main__":
    unittest.main()
