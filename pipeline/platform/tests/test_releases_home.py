"""Commission 13: the release store has exactly one live home.

Proves the home-split cure: the two historical callers —
a backfill run with `var/release-state/` as home, a later
append run with the default — can no longer diverge. The
default construction records into the canonical home; an
explicit non-canonical home under the live posture (the
repo root as workspace root) raises at construction and
founds nothing, so a `record` or `drift_check` under it
can never be served.

Scratch discipline: the default-construction case re-points
the paths derivation (`releases._paths.STATE_DIR`) at a
scratch copy of the package state layout, so the record
lands in the scratch canonical file, never the live ledger.
The scratch tree must sit under the workspace root (a temp
dir inside the package, removed on teardown) because the
unified writer refuses paths outside it — the same reason
both historical homes were in-tree. The existing fixture
suite (test_releases.py) is untouched: its scratch-root
construction is the fixture posture the guard preserves.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM))

import releases  # noqa: E402

CANONICAL = Path(os.path.realpath(releases._paths.STATE_DIR))
HISTORICAL_SPLIT_HOME = PLATFORM / "var" / "release-state"


class TestDefaultConstructionLandsCanonical(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(dir=str(PLATFORM))
        self.state_dir = Path(self.scratch.name) / "state"
        self.state_dir.mkdir()
        self._real_state_dir = releases._paths.STATE_DIR
        releases._paths.STATE_DIR = str(self.state_dir)

    def tearDown(self):
        releases._paths.STATE_DIR = self._real_state_dir
        self.scratch.cleanup()

    def test_record_lands_in_the_canonical_file(self):
        store = releases.ReleaseStore()
        self.assertEqual(store.home, os.path.realpath(self.state_dir))
        self.assertEqual(
            store.path,
            os.path.join(os.path.realpath(self.state_dir),
                         releases.STORE_FILE))
        store.record(repo="specimen-repo", commit="c13aaaa",
                     artifact="workhorse-superapp", stage="v99",
                     result="deployed", caller="test-lane")
        landed = Path(store.path)
        self.assertTrue(landed.exists())
        entries = store.entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["commit"], "c13aaaa")
        check = store.drift_check("workhorse-superapp", "v99")
        self.assertEqual(check["status"], "deployed")
        self.assertEqual(check["commit"], "c13aaaa")


class TestNonCanonicalHomeRefused(unittest.TestCase):
    def test_historical_split_home_raises_and_founds_nothing(self):
        target = HISTORICAL_SPLIT_HOME / releases.STORE_FILE
        existed_before = target.exists()
        with self.assertRaises(ValueError) as cm:
            releases.ReleaseStore(HISTORICAL_SPLIT_HOME)
        message = str(cm.exception)
        self.assertIn(str(CANONICAL), message)
        self.assertIn(
            os.path.realpath(HISTORICAL_SPLIT_HOME), message)
        self.assertEqual(target.exists(), existed_before)

    def test_drift_check_under_split_home_fails_the_same_way(self):
        with self.assertRaises(ValueError):
            releases.ReleaseStore(
                HISTORICAL_SPLIT_HOME).drift_check(
                    "workhorse-superapp")

    def test_record_under_split_home_fails_the_same_way(self):
        with self.assertRaises(ValueError):
            releases.ReleaseStore(HISTORICAL_SPLIT_HOME).record(
                repo="specimen-repo", commit="c13bbbb",
                artifact="workhorse-superapp", stage="v99",
                result="deployed", caller="test-lane")


class TestCanonicalSpellingsAccepted(unittest.TestCase):
    def test_explicit_canonical_home_constructs(self):
        store = releases.ReleaseStore(CANONICAL)
        self.assertEqual(store.home, str(CANONICAL))
        self.assertEqual(
            store.path, str(CANONICAL / releases.STORE_FILE))

    def test_respelled_canonical_home_constructs(self):
        respelled = CANONICAL / ".." / "state"
        store = releases.ReleaseStore(respelled)
        self.assertEqual(store.home, str(CANONICAL))


if __name__ == "__main__":
    unittest.main()
