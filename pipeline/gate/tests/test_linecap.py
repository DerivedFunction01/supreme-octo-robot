"""Line-cap component: enumeration and counting on a
scratch tree (no git — the walk fallback), plus wc -l
counting semantics."""
import os
import tempfile
import unittest
from pathlib import Path

from gate import linecap


def _write(path: Path, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n" * lines, encoding="utf-8")


class LinecapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-linecap-"))
        _write(self.tmp / "small.py", 10)
        _write(self.tmp / "big.py", 25)
        _write(self.tmp / "state" / "ignored.py", 40)

    def test_scan_flags_only_over_cap(self):
        findings, missing = linecap.scan(str(self.tmp), cap=20)
        self.assertEqual(findings, [("big.py", 25)])
        self.assertEqual(missing, [])

    def test_count_lines_counts_newlines(self):
        probe = self.tmp / "probe.txt"
        probe.write_bytes(b"a\nb\nno-trailing-newline")
        self.assertEqual(linecap.count_lines(str(probe)), 2)

    def test_enumeration_skips_state(self):
        names = linecap.enumerate_files(str(self.tmp))
        self.assertIn("big.py", names)
        self.assertNotIn("state/ignored.py", names)
        self.assertTrue(os.path.isdir(self.tmp / "state"))


if __name__ == "__main__":
    unittest.main()
