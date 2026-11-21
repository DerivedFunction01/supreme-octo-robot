"""The folder census: counts over a fixture tree, the
warn/fail thresholds, and the family exemption (exact and
subtree declarations)."""
import unittest

from gate import foldercensus


def _files(folder, count):
    return [f"{folder}/f{i:02d}.py" for i in range(count)]


class CountTests(unittest.TestCase):
    def test_counts_direct_files_per_folder(self):
        counts = foldercensus.count_by_folder(
            _files("a/b", 3) + _files("a", 2) + ["top.py"])
        self.assertEqual(counts, {"a/b": 3, "a": 2, "": 1})

    def test_nested_files_do_not_inflate_the_parent(self):
        counts = foldercensus.count_by_folder(_files("a/deep", 20))
        self.assertEqual(counts, {"a/deep": 20})


class ThresholdTests(unittest.TestCase):
    def test_below_warn_is_not_reported(self):
        rows, failures = foldercensus.evaluate({"a": 15}, [])
        self.assertEqual(rows, [])
        self.assertEqual(failures, [])

    def test_warn_band_reports_without_failing(self):
        rows, failures = foldercensus.evaluate({"a": 16, "b": 23}, [])
        self.assertEqual(failures, [])
        self.assertEqual(
            [(r[0], r[2]) for r in rows],
            [("b", "warn"), ("a", "warn")])

    def test_at_fail_threshold_fails(self):
        rows, failures = foldercensus.evaluate({"a": 24}, [])
        self.assertEqual(failures, ["a"])
        self.assertEqual(rows[0][2], "fail")


class FamilyTests(unittest.TestCase):
    FAMILIES = [
        {"path": "jobs", "kind": "registry entries"},
        {"path": "holding/**", "kind": "held copies"},
    ]

    def test_declared_family_is_reported_but_exempt(self):
        rows, failures = foldercensus.evaluate(
            {"jobs": 36}, self.FAMILIES)
        self.assertEqual(failures, [])
        self.assertEqual(
            rows, [("jobs", 36, "family", "registry entries")])

    def test_subtree_declaration_covers_subfolders(self):
        rows, failures = foldercensus.evaluate(
            {"holding/src/jobs": 25}, self.FAMILIES)
        self.assertEqual(failures, [])
        self.assertEqual(rows[0][2], "family")
        self.assertEqual(rows[0][3], "held copies")

    def test_declaration_covers_exactly_its_path(self):
        _rows, failures = foldercensus.evaluate(
            {"jobs/extra": 25}, self.FAMILIES)
        self.assertEqual(failures, ["jobs/extra"])

    def test_mixed_folder_at_fail_count_fails(self):
        rows, failures = foldercensus.evaluate(
            {"sync/lease": 25, "ops": 22}, self.FAMILIES)
        self.assertEqual(failures, ["sync/lease"])
        self.assertEqual(
            {r[0]: r[2] for r in rows},
            {"sync/lease": "fail", "ops": "warn"})


class ScanTests(unittest.TestCase):
    def test_scan_over_a_fixture_tree(self):
        import subprocess
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp(prefix="gate-census-"))
        (root / "pkg").mkdir()
        for i in range(17):
            (root / "pkg" / f"m{i:02d}.py").write_text("x = 1\n")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        rows, failures = foldercensus.scan(
            root, [], warn=16, fail=24)
        self.assertEqual(failures, [])
        self.assertEqual(rows, [("pkg", 17, "warn", None)])

    def test_scan_ignores_untracked_files(self):
        import subprocess
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp(prefix="gate-census-untracked-"))
        (root / "pkg").mkdir()
        for i in range(17):
            (root / "pkg" / f"m{i:02d}.py").write_text("x = 1\n")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        # Nothing staged: the tracked population is empty,
        # so the census reports no folder at the warn line.
        rows, failures = foldercensus.scan(
            root, [], warn=16, fail=24)
        self.assertEqual(failures, [])
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
