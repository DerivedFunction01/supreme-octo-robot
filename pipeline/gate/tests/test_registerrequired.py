"""Pins for the register-required component: the
tracked set and the register must agree exactly, in
both directions, and a write surface the ignore rules
do not cover is a finding."""

import unittest

from gate import registerrequired


class CompareTests(unittest.TestCase):
    def test_exact_match_is_clean(self):
        rows, failures = registerrequired.compare(
            ["a.yaml", "b.yaml"], ["b.yaml", "a.yaml"])
        self.assertEqual(failures, [])
        self.assertEqual(rows, ["registered and tracked: 2"])

    def test_tracked_without_register_entry_fails(self):
        _, failures = registerrequired.compare(
            ["a.yaml", "instance.yaml"], ["a.yaml"])
        self.assertEqual(
            failures,
            ["tracked file with no register entry: instance.yaml"])

    def test_register_entry_without_tracked_file_fails(self):
        _, failures = registerrequired.compare(
            ["a.yaml"], ["a.yaml", "ghost.yaml"])
        self.assertEqual(
            failures,
            ["register entry with no tracked file: ghost.yaml"])


class ProbeCoverageTests(unittest.TestCase):
    def test_covered_surfaces_are_clean(self):
        rows, failures = registerrequired.probe_coverage(
            lambda relpath: True)
        self.assertEqual(failures, [])
        self.assertEqual(len(rows), len(registerrequired.WRITE_SURFACES))

    def test_uncovered_surface_is_a_finding(self):
        def check(relpath):
            return "staging" not in relpath
        _, failures = registerrequired.probe_coverage(check)
        self.assertEqual(
            failures,
            ["write surface with no ignore coverage: "
             "pipeline/scheduling/staging"])


if __name__ == "__main__":
    unittest.main()
