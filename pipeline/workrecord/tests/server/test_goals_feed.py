"""Goal-feed tests (contract 11): the assembly document
serves the goal-record store's records in the adapter's
shape, and an empty store reads honestly.

The proof runs in a fresh interpreter (a driver script
over the shared fixture workspace), the same way the
app's validate-live harness consumes the document: the
server package reads its config at import, so the
fixture config must be installed before the import —
a subprocess keeps this suite's in-process server tests
untouched by the second config.

The rehearsal loop, end to end: records are created
through the store's own writer (which arms their ping
entries into the fixture registry), a cited blocked
post lands on one of them, and the assembled document
then serves both records with the pair on the blocked
post's face.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
import json
import os
import sys
from pathlib import Path

base = Path(sys.argv[1])
root = Path(sys.argv[2])
seed = sys.argv[3] == "seed"
sys.path.insert(0, str(root))

from tests.server import fixture_ws

info = fixture_ws.build_fixture_workspace(base)
cfg = fixture_ws.fixture_config(base, base / "state-live")
os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])
os.environ["WB_SCHEDULER_JOBS_DIR"] = str(info["jobs_dir"])

syncs = {}
if seed:
    from server import config as cfgmod
    from lib.writes import goals as goals_mod
    store = goals_mod.GoalStore(cfgmod.goals_path(
        cfgmod.load()))
    contract = {
        "objective": "Exercise the goal feed.",
        "complete_when": "the document serves the "
                         "record",
        "blocked_only_when": "a cited owner decision "
                             "is missing",
        "continuation": "continue",
    }
    out = store.create(
        "fixture-alpha-goal", "alpha",
        "Fixture alpha goal", contract,
        now="2026-10-25T12:00:00+00:00")
    syncs["alpha"] = out["ping_sync"]
    store.create(
        "fixture-blocked-goal", "alpha",
        "Fixture blocked goal", contract,
        now="2026-10-25T12:00:00+00:00")
    store.post_status(
        "fixture-blocked-goal",
        {"handle": "main",
         "status_code": "BLOCKED-OWNER",
         "summary": "waiting on the fixture decision",
         "basis_citation": {
             "thread": "main",
             "at": "2026-10-25T09:00:00+00:00"}},
        now="2026-10-25T12:05:00+00:00")

from server import assemble
doc = assemble.build_feeds()
print(json.dumps({
    "goals": doc["goals"],
    "goalsSource": doc["goalsSource"],
    "syncs": syncs,
    "entries": sorted(
        p.name for p in info["jobs_dir"].glob("*.yaml")),
}))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class GoalsFeedTest(unittest.TestCase):

    def _run_driver(self, seed):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name) / "fx"
        driver = Path(tmp.name) / "driver.py"
        driver.write_text(DRIVER, encoding="utf-8")
        proc = subprocess.run(
            [_python(), str(driver), str(base),
             str(WORKRECORD_ROOT), "seed" if seed else
             "empty"],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(
            proc.returncode, 0,
            f"driver failed:\n{proc.stdout}\n{proc.stderr}")
        return json.loads(proc.stdout.strip().splitlines()
                          [-1])

    def test_store_backed_document_serves_records(self):
        out = self._run_driver(seed=True)
        goals = out["goals"]
        self.assertEqual(
            [g["slug"] for g in goals],
            ["fixture-alpha-goal", "fixture-blocked-goal"])
        self.assertIn("goal-record store",
                      out["goalsSource"])
        self.assertIn("2 record(s)", out["goalsSource"])
        self.assertEqual(out["syncs"]["alpha"]["action"],
                         "written")
        self.assertIn("goal-ping-fixture-alpha-goal.yaml",
                      out["entries"])
        self.assertIn(
            "goal-ping-fixture-blocked-goal.yaml",
            out["entries"])
        alpha = goals[0]
        self.assertEqual(
            alpha["contract"]["completeWhen"],
            "the document serves the record")
        self.assertEqual(
            alpha["ping"],
            {"entryId": "goal-ping-fixture-alpha-goal",
             "cadenceMinutes": 15, "armed": True})
        self.assertIsNone(alpha["lastPost"])
        blocked = goals[1]
        last = blocked["lastPost"]
        self.assertEqual(last["status_code"],
                         "BLOCKED-OWNER")
        self.assertEqual(
            last["basis_citation"],
            {"thread": "main",
             "at": "2026-10-25T09:00:00+00:00"})
        self.assertEqual(last["verification"]["by"],
                         "main")
        self.assertEqual(last["postedAt"],
                         "2026-10-25T12:05:00+00:00")

    def test_empty_store_reads_honestly(self):
        out = self._run_driver(seed=False)
        self.assertEqual(out["goals"], [])
        self.assertIn("goal-record store",
                      out["goalsSource"])
        self.assertIn("no records", out["goalsSource"])


if __name__ == "__main__":
    unittest.main()
