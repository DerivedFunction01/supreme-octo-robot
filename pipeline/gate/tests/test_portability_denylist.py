"""Denylist-leg tests for the portability component.

The personal-literal leg resolves its list from untracked
per-deployment state, so a bare clone provisions nothing
and the leg prints a NOTICE and skips — in a bare-clone
gate (the venue leg on Colab is the measured case) the
enforcement silently never ran. These tests prove the leg
end to end with a FICTIONAL literal seeded in a tracked
fixture denylist (tests/fixtures/denylist/): the literal
is a made-up person's name in plain form, never a real
term, and this module reads it from the fixture rather
than carrying it. A specimen fixture carries it; the
scanner must flag the specimen by name and must never
print the literal itself.
"""
import contextlib
import io
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from gate import denylist_match, portability

FIXTURES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures", "denylist")
FIXTURE_DENYLIST = os.path.join(FIXTURES, "denylist.txt")
SPECIMEN = os.path.join(FIXTURES, "specimen.md")
CLEAN = os.path.join(FIXTURES, "clean.md")


def _fixture_literal():
    with open(FIXTURE_DENYLIST, encoding="utf-8") as fh:
        for line in denylist_match.parse_literals(fh):
            return line
    raise AssertionError("fixture denylist carries no literal")


def _scratch_tree(*fixture_names, provisioned):
    """A scratch scan root holding copies of the named
    fixture files; when provisioned, the fixture denylist
    sits at state/denylist.txt — the bare-clone seam the
    runner's auto form resolves."""
    root = tempfile.mkdtemp(prefix="gate-denylist-")
    for name in fixture_names:
        shutil.copy(os.path.join(FIXTURES, name),
                    os.path.join(root, name))
    if provisioned:
        state = os.path.join(root, "state")
        os.makedirs(state)
        shutil.copy(FIXTURE_DENYLIST,
                    os.path.join(state, "denylist.txt"))
    return root


def _run_main(root, *extra_argv):
    """portability.main exactly as the gate runner invokes
    it (runner passes --root, plus --fail-on-denylist when
    its auto form finds a denylist provisioned)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = portability.main(["--root", root, *extra_argv])
    return code, out.getvalue()


class ProvisionedLegTests(unittest.TestCase):
    def test_specimen_flagged_by_name_literal_never_printed(self):
        root = _scratch_tree("specimen.md", "clean.md",
                             provisioned=True)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(portability.denylist_provisioned(root))
            code, output = _run_main(root, "--fail-on-denylist")
        self.assertEqual(code, 1)
        flagged = re.search(
            r"denylist/personal-literal: specimen\.md:\d+ "
            r"\(content withheld\)", output)
        self.assertIsNotNone(flagged, output)
        self.assertNotIn("clean.md", output)
        self.assertNotIn(_fixture_literal(), output)
        self.assertNotIn(_fixture_literal().lower(),
                         output.lower())

    def test_case_variant_specimen_flagged(self):
        # Matching is case-insensitive, consumed from
        # denylist_match (the one home): the fixture
        # literal at lowercase is the same leak.
        root = _scratch_tree("clean.md", provisioned=True)
        with open(os.path.join(root, "variant.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("approved by "
                     + _fixture_literal().lower() + "\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            code, output = _run_main(root, "--fail-on-denylist")
        self.assertEqual(code, 1)
        self.assertIn("variant.md", output)
        self.assertNotIn("clean.md", output)

    def test_clean_tree_leg_runs_and_passes_not_skipped(self):
        root = _scratch_tree("clean.md", provisioned=True)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(portability.denylist_provisioned(root))
            code, output = _run_main(root, "--fail-on-denylist")
        self.assertEqual(code, 0)
        self.assertIn("denylist: 0 finding(s)", output)
        self.assertNotIn("personal-literal leg skipped", output)
        self.assertNotIn("NOTICE", output)


class UnprovisionedLegTests(unittest.TestCase):
    def test_skip_notice_survives_when_nothing_provisioned(self):
        # Bare-clone honesty for real trees: no denylist
        # anywhere (env cleared, no state/denylist.txt) —
        # the leg notices and skips, and the scan passes.
        root = _scratch_tree("clean.md", provisioned=False)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(
                portability.denylist_provisioned(root))
            code, output = _run_main(root)
        self.assertEqual(code, 0)
        self.assertIn("NOTICE", output)
        self.assertIn("personal-literal leg skipped", output)


if __name__ == "__main__":
    unittest.main()
