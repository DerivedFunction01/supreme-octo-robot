"""Storage watch: threshold levels and the crossing discipline.

The episode discipline is the vm-restart-detector's: baseline
adoption is silent, a crossing reports exactly once, a continuing
episode stays silent, de-escalation is silent, and recovery
re-arms. disk_usage is faked per path; the store list is forced
empty so no du runs.
"""

import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from collections import namedtuple
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
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
            "STORAGE_WATCH_TRASH_DIR": os.path.join(self.tmp, "trash"),
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


class RegisterCase(unittest.TestCase):
    """The register leg: re-measure every run, a row grown
    past the bound reports as an owning-thread defect, and
    the new figure is written back in the same run."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.state)
        self.store = os.path.join(self.tmp, "store")
        os.makedirs(self.store)
        self.register = {
            "measured_at": "2026-11-18T05:20Z",
            "rows": [
                {"path": self.store, "bytes_gb": 2.0,
                 "owner": "some thread", "class": "fixture", "prunable": "yes"},
                {"path": os.path.join(self.tmp, "absent"), "bytes_gb": 1.0,
                 "owner": "ghost", "class": "fixture", "prunable": "no"},
            ],
        }
        with open(os.path.join(self.state, "register.json"), "w") as fh:
            json.dump(self.register, fh)

    def run_pass(self, measured_bytes):
        def fake_run(argv, **kwargs):
            lines = []
            for path in argv[3:]:
                if path == self.store:
                    lines.append(f"{measured_bytes}\t{path}")
            return namedtuple("done", "stdout")(stdout="\n".join(lines))

        with mock.patch.object(sw.subprocess, "run", fake_run):
            return sw.register_pass(self.state, self.tmp, 5)

    def test_growth_reports_and_rewrites_the_figure(self):
        lines = self.run_pass(5 * GB)
        self.assertEqual(len(lines), 1)
        self.assertIn("STORAGE REGISTER GROWTH", lines[0])
        self.assertIn("some thread", lines[0])
        with open(os.path.join(self.state, "register.json")) as fh:
            data = json.load(fh)
        self.assertEqual(data["rows"][0]["bytes_gb"], 5.0)
        self.assertIn("measured_at", data["rows"][0])
        # The unmeasurable row keeps its recorded figure.
        self.assertEqual(data["rows"][1]["bytes_gb"], 1.0)

    def test_small_growth_is_silent_but_remeasured(self):
        lines = self.run_pass(2 * GB + GB // 2)
        self.assertEqual(lines, [])
        with open(os.path.join(self.state, "register.json")) as fh:
            data = json.load(fh)
        self.assertEqual(data["rows"][0]["bytes_gb"], 2.5)

    def test_missing_register_is_inert(self):
        os.unlink(os.path.join(self.state, "register.json"))
        self.assertEqual(sw.register_pass(self.state, self.tmp, 5), [])


class TrashCase(unittest.TestCase):
    """The trash leg: below the low tier, the contents of
    entries older than 7 days are purged; the entry shell
    and its .trashinfo stay; fresh entries are untouched."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.trash = os.path.join(self.tmp, "trash")
        old_stamp = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y%m%d-%H%M%S")
        fresh_stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.old_entry = os.path.join(self.trash, f"{old_stamp}-aaaa")
        self.fresh_entry = os.path.join(self.trash, f"{fresh_stamp}-bbbb")
        for entry in (self.old_entry, self.fresh_entry):
            os.makedirs(os.path.join(entry, "files", "sub"))
            with open(os.path.join(entry, ".trashinfo"), "w") as fh:
                fh.write("meta")
            with open(os.path.join(entry, "files", "sub", "x.bin"), "wb") as fh:
                fh.write(b"x" * 2048)
        self.env = {
            "STORAGE_WATCH_STATE_DIR": os.path.join(self.tmp, "state"),
            "STORAGE_WATCH_HOME_PATH": "/fakehome",
            "STORAGE_WATCH_TMP_PATH": "/faketmp",
            "STORAGE_WATCH_STORES": "",
            "STORAGE_WATCH_TRASH_DIR": self.trash,
        }

    def run_watch(self, home_free):
        def fake_usage(path):
            free = home_free if path == "/fakehome" else 512 * MB
            return Usage(total=free * 2, used=free, free=free)

        buf = io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=False):
            with mock.patch.object(shutil, "disk_usage", fake_usage):
                with redirect_stdout(buf):
                    rc = sw.main()
        return rc, buf.getvalue()

    def test_purge_below_low_keeps_metadata_and_fresh_entries(self):
        rc, out = self.run_watch(47 * GB)
        self.assertEqual(rc, 0)
        self.assertIn("STORAGE TRASH PURGE", out)
        self.assertEqual(os.listdir(os.path.join(self.old_entry, "files")), [])
        self.assertTrue(os.path.exists(os.path.join(self.old_entry, ".trashinfo")))
        self.assertTrue(os.path.exists(os.path.join(self.fresh_entry, "files", "sub", "x.bin")))

    def test_no_purge_at_a_healthy_level(self):
        rc, out = self.run_watch(60 * GB)
        self.assertNotIn("TRASH PURGE", out)
        self.assertTrue(os.path.exists(os.path.join(self.old_entry, "files", "sub", "x.bin")))
