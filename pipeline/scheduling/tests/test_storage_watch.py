"""Storage watch: threshold levels and the crossing discipline.

The episode discipline is the vm-restart-detector's: baseline
adoption is silent, a crossing reports exactly once, a continuing
episode stays silent, de-escalation is silent, and recovery
re-arms. disk_usage is faked per path; the store list is forced
empty so no du runs.
"""

import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from collections import namedtuple
from contextlib import redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "storage_watch", os.path.join(REPO, "ops", "watches", "storage_watch.py")
)
sw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sw)

Usage = namedtuple("usage", "total used free")
GB = 1024 ** 3
MB = 1024 ** 2


class LevelCase(unittest.TestCase):
    def test_level_boundaries(self):
        low, crit = 50 * GB, 45 * GB
        self.assertEqual(sw.level_for(60 * GB, low, crit), 0)
        self.assertEqual(sw.level_for(low, low, crit), 0)  # at, not below
        self.assertEqual(sw.level_for(low - 1, low, crit), 1)
        self.assertEqual(sw.level_for(crit, low, crit), 1)  # at crit = low
        self.assertEqual(sw.level_for(crit - 1, low, crit), 2)


class EpisodeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.frees = {"/fakehome": 60 * GB, "/faketmp": 512 * MB}
        self.env = {
            "STORAGE_WATCH_STATE_DIR": os.path.join(self.tmp, "state"),
            "STORAGE_WATCH_HOME_PATH": "/fakehome",
            "STORAGE_WATCH_TMP_PATH": "/faketmp",
            "STORAGE_WATCH_STORES": "",
        }

    def run_watch(self):
        def fake_usage(path):
            free = self.frees[path]
            return Usage(total=free * 2, used=free, free=free)

        buf = io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=False):
            with mock.patch.object(shutil, "disk_usage", fake_usage):
                with redirect_stdout(buf):
                    rc = sw.main()
        return rc, buf.getvalue()

    def test_episode_discipline(self):
        # Baseline adoption: silent even though state starts empty.
        rc, out = self.run_watch()
        self.assertEqual((rc, out), (0, ""))

        # Crossing below low: exactly one report.
        self.frees["/fakehome"] = 47 * GB
        rc, out = self.run_watch()
        self.assertEqual(rc, 0)
        self.assertIn("STORAGE LOW", out)
        self.assertIn("home", out)

        # Continuing episode: silent.
        rc, out = self.run_watch()
        self.assertEqual(out, "")

        # Deepening to critical: one more report.
        self.frees["/fakehome"] = 44 * GB
        rc, out = self.run_watch()
        self.assertIn("STORAGE CRITICAL", out)

        # De-escalation and recovery: silent, and the episode re-arms.
        self.frees["/fakehome"] = 47 * GB
        rc, out = self.run_watch()
        self.assertEqual(out, "")
        self.frees["/fakehome"] = 60 * GB
        rc, out = self.run_watch()
        self.assertEqual(out, "")
        self.frees["/fakehome"] = 47 * GB
        rc, out = self.run_watch()
        self.assertIn("STORAGE LOW", out)

    def test_tmp_crossing_reports_independently(self):
        rc, out = self.run_watch()
        self.assertEqual(out, "")
        self.frees["/faketmp"] = 64 * MB
        rc, out = self.run_watch()
        self.assertIn("STORAGE LOW", out)
        self.assertIn("/tmp", out)

    def test_unreadable_filesystem_is_exit_3(self):
        def boom(path):
            raise OSError("gone")

        with mock.patch.dict(os.environ, self.env, clear=False):
            with mock.patch.object(shutil, "disk_usage", boom):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = sw.main()
        self.assertEqual(rc, 3)
        self.assertIn("cannot read free space", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
