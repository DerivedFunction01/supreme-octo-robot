"""Task Manager feed tests: the load monitor's
snapshot store serves the full shape while fresh, and
honest absence (the stamp, stale: true, empty lists)
once the snapshot is older than the staleness bound —
and the same absence for a missing or unreadable
store. Rows are never fabricated.

The proof runs in a fresh interpreter (the neighbouring
server suites' pattern: the server package reads its
config at import, so this suite keeps its import in a
subprocess and never binds a config in-process). The
feed itself takes the store path and the judging
instant as parameters, so the driver needs no fixture
workspace — it writes the store JSON, calls the feed,
and prints the served shape.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

NOW = "2026-11-24T12:00:00+00:00"

DRIVER = r'''
import json
import sys
from datetime import datetime
from pathlib import Path

root = Path(sys.argv[1])
store_path = Path(sys.argv[2])
now = datetime.fromisoformat(sys.argv[3])
sys.path.insert(0, str(root))

from server import task_manager

print(json.dumps({
    "feed": task_manager.task_manager_feed(
        path=store_path, now=now),
    "default_path": str(task_manager.snapshot_path()),
}))
'''

PROCESS = {
    "pid": 4242, "ppid": 1, "cpu_pct": 87.5,
    "mem_pct": 3.25, "elapsed_s": 442,
    "argv": ["python3", "check.py", "--workers", "2"],
    "cwd": "/ws/supreme-octo-robot",
    "repo": "supreme-octo-robot", "thread": "main",
}

VENUE = {"kind": "local", "name": "msi", "live": True,
         "in_flight": 2}

MEM = {"total_kb": 16000000, "available_kb": 4000000,
       "used_kb": 12000000}


def _store(stamp):
    return {"current": {
        "stamp": stamp,
        "load": [9.5, 7.25, 5.0],
        "cpus": 2,
        "mem": MEM,
        "processes": [PROCESS],
        "venues": [VENUE],
        "episode": {"open": True,
                    "opened_at": "2026-11-24T11:58:00+00:00",
                    "last_spoke_at": None},
    }, "recent": []}


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class TaskManagerFeedTest(unittest.TestCase):

    def _run_driver(self, store_text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        store_path = base / "load-monitor-snapshot.json"
        if store_text is not None:
            store_path.write_text(store_text,
                                  encoding="utf-8")
        driver = base / "driver.py"
        driver.write_text(DRIVER, encoding="utf-8")
        proc = subprocess.run(
            [_python(), str(driver), str(WORKRECORD_ROOT),
             str(store_path), NOW],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(
            proc.returncode, 0,
            f"driver failed:\n{proc.stdout}\n{proc.stderr}")
        return json.loads(
            proc.stdout.strip().splitlines()[-1])

    def test_default_path_is_the_monitor_store(self):
        out = self._run_driver(None)
        self.assertTrue(out["default_path"].endswith(
            "pipeline/scheduling/state/"
            "load-monitor-snapshot.json"))

    def test_fresh_store_serves_the_full_shape(self):
        stamp = "2026-11-24T11:59:00+00:00"  # 60 s old
        out = self._run_driver(json.dumps(_store(stamp)))
        self.assertEqual(out["feed"], {
            "stamp": stamp,
            "stale": False,
            "load": [9.5, 7.25, 5.0],
            "cpus": 2,
            "mem": MEM,
            "processes": [PROCESS],
            "venues": [VENUE],
            "jobs": [],
        })

    def test_boundary_stamp_is_still_fresh(self):
        stamp = "2026-11-24T11:57:00+00:00"  # exactly 180 s
        out = self._run_driver(json.dumps(_store(stamp)))
        self.assertFalse(out["feed"]["stale"])
        self.assertEqual(out["feed"]["processes"],
                         [PROCESS])

    def test_stale_store_serves_honest_absence(self):
        stamp = "2026-11-24T11:56:59+00:00"  # 181 s old
        out = self._run_driver(json.dumps(_store(stamp)))
        self.assertEqual(out["feed"], {
            "stamp": stamp,
            "stale": True,
            "load": None,
            "cpus": None,
            "mem": None,
            "processes": [],
            "venues": [],
            "jobs": [],
        })

    def test_missing_store_serves_honest_absence(self):
        out = self._run_driver(None)
        self.assertEqual(out["feed"], {
            "stamp": None,
            "stale": True,
            "load": None,
            "cpus": None,
            "mem": None,
            "processes": [],
            "venues": [],
            "jobs": [],
        })

    def test_unreadable_store_serves_honest_absence(self):
        out = self._run_driver("{not json")
        self.assertEqual(out["feed"]["stamp"], None)
        self.assertTrue(out["feed"]["stale"])
        self.assertEqual(out["feed"]["processes"], [])


if __name__ == "__main__":
    unittest.main()
