"""Line-cap component: enumeration and counting on a
scratch tree (no git — the walk fallback), wc -l counting
semantics, the at-cap rule, the creep band with its
test-suite exemption, the growth ban against a committed
baseline, and the repo form's tracked-only population."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from gate import linecap


def _write(path: Path, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n" * lines, encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         *args], cwd=root, check=True, capture_output=True)


class LinecapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-linecap-"))
        _write(self.tmp / "small.py", 10)
        _write(self.tmp / "big.py", 25)
        _write(self.tmp / "state" / "ignored.py", 40)

    def test_scan_flags_only_over_cap(self):
        result = linecap.scan(str(self.tmp), cap=20)
        self.assertEqual(result.findings, [("big.py", 25)])
        self.assertEqual(result.missing, [])

    def test_at_the_cap_passes(self):
        _write(self.tmp / "atcap.py", 20)
        result = linecap.scan(str(self.tmp), cap=20)
        self.assertNotIn(("atcap.py", 20), result.findings)

    def test_count_lines_counts_newlines(self):
        probe = self.tmp / "probe.txt"
        probe.write_bytes(b"a\nb\nno-trailing-newline")
        self.assertEqual(linecap.count_lines(str(probe)), 2)

    def test_enumeration_skips_state(self):
        names = linecap.enumerate_files(str(self.tmp))
        self.assertIn("big.py", names)
        self.assertNotIn("state/ignored.py", names)
        self.assertTrue(os.path.isdir(self.tmp / "state"))


class BandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-linecap-band-"))
        _write(self.tmp / "creeping.py", 18)
        _write(self.tmp / "tests" / "test_suite.py", 18)
        _write(self.tmp / "tests" / "conftest.py", 18)
        _write(self.tmp / "calm.py", 10)

    def test_band_lists_non_test_files_at_or_over_band(self):
        result = linecap.scan(str(self.tmp), cap=20, band=15)
        banded = [rel for rel, _ in result.band]
        self.assertIn("creeping.py", banded)
        # Shared test infrastructure is not a suite: banded.
        self.assertIn("tests/conftest.py", banded)

    def test_band_exempts_test_suites_but_cap_does_not(self):
        result = linecap.scan(str(self.tmp), cap=20, band=15)
        banded = [rel for rel, _ in result.band]
        self.assertNotIn("tests/test_suite.py", banded)
        _write(self.tmp / "tests" / "test_suite.py", 25)
        result = linecap.scan(str(self.tmp), cap=20, band=15)
        self.assertIn(("tests/test_suite.py", 25),
                      result.findings)


class GrowthBanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-linecap-git-"))
        _git(self.tmp, "init", "-q")
        _write(self.tmp / "creeping.py", 18)
        _write(self.tmp / "tracked.py", 12)
        _git(self.tmp, "add", "-A")
        _git(self.tmp, "commit", "-qm", "seed")

    def test_band_file_at_committed_count_is_clean(self):
        result = linecap.scan_repo(str(self.tmp), cap=20, band=15)
        self.assertEqual(result.growth, [])
        self.assertEqual(
            result.band, [("creeping.py", 18)])

    def test_band_file_grown_past_committed_count_fails(self):
        _write(self.tmp / "creeping.py", 19)
        result = linecap.scan_repo(str(self.tmp), cap=20, band=15)
        self.assertEqual(
            result.growth, [("creeping.py", 19, 18)])

    def test_repo_population_is_tracked_only(self):
        _write(self.tmp / "untracked_big.py", 30)
        result = linecap.scan_repo(str(self.tmp), cap=20, band=15)
        self.assertEqual(result.findings, [])
        self.assertNotIn(
            "untracked_big.py",
            [rel for rel, _ in result.band])

    def test_repo_population_counts_code_extensions_only(self):
        _write(self.tmp / "data.json", 30)
        _git(self.tmp, "add", "data.json")
        result = linecap.scan_repo(str(self.tmp), cap=20, band=15)
        self.assertEqual(result.findings, [])


if __name__ == "__main__":
    unittest.main()
