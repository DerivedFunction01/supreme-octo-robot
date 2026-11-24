"""The assembled feeds document's TTL cache behaviour
(assemble.build_feeds over assemble._DocumentStore —
the lazy restore): within the TTL a repeat
build serves the stored document without reassembling,
and a store write inside the TTL moves nothing (the
named trade: freshness is the TTL bound, not the
write); past the TTL a read serves the stale document
while exactly one reassembly runs behind it, then
fresh; the refresh endpoint's bust takes the cold path
again. The document's shape is the pinned one.

The proof runs in a fresh interpreter (a driver script
over the shared fixture workspace), the same way
test_goals_feed's does: the server package reads its
config at import, so the fixture config must be
installed before the import — a subprocess keeps this
suite's in-process server tests untouched by the
second config. The store's clock and spawn are fakes
(an injected clock, a captured spawn the driver runs
explicitly), per the determinism directive: no wall
clock, no real thread, no quiet-time convergence —
which is also why this suite no longer needs the old
fingerprint era's settle dance: the assembly's own
writes cannot move a TTL.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))

from tests.server import fixture_ws

info = fixture_ws.build_fixture_workspace(base)
cfg = fixture_ws.fixture_config(base, base / "state-test")

import os
os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])

from server import assemble

clock = {"now": 1000.0}
spawned = []
store = assemble._DocumentStore(
    clock=lambda: clock["now"], spawn=spawned.append)
assemble._document_store = store

calls = {"n": 0}
real_compute = assemble._build_feeds_compute

def counting_compute():
    calls["n"] += 1
    return real_compute()

assemble._build_feeds_compute = counting_compute

ttl = assemble.CFG["feeds_document_ttl_s"]
result = {}

first = assemble.build_feeds()
result["calls_first"] = calls["n"]
result["shape_keys"] = sorted(first)
result["alpha_keys"] = sorted(
    first["projectFeeds"]["alpha"])

repeat = assemble.build_feeds()
result["same_object"] = repeat is first
result["calls_repeat"] = calls["n"]
result["spawned_within_ttl"] = len(spawned)

from lib.progress import attention as attention_mod
probe = Path(info["armed_dir"]) / (
    f"{attention_mod.ROW_PREFIX}alpha-cache-probe.json")
probe.write_text(json.dumps(
    {"project": "alpha", "todo": "cache-probe"}),
    encoding="utf-8")
after_write = assemble.build_feeds()
result["write_within_ttl_served_stale"] = \
    after_write is first
result["calls_after_write"] = calls["n"]
result["spawned_after_write"] = len(spawned)

clock["now"] += ttl + 1
stale = assemble.build_feeds()
result["stale_served"] = stale is first
result["spawned_past_ttl"] = len(spawned)
again = assemble.build_feeds()
result["single_flight"] = \
    again is first and len(spawned) == 1
result["calls_before_refresh_runs"] = calls["n"]

for fn in spawned:
    fn()
del spawned[:]
fresh = assemble.build_feeds()
result["fresh_has_probe"] = "cache-probe" in {
    r["todo"] for r in fresh["armedRows"]}
result["calls_total"] = calls["n"]
result["spawned_after_refresh"] = len(spawned)

from server import feedcache
feedcache.invalidate_all()
after_bust = assemble.build_feeds()
result["calls_after_bust"] = calls["n"]
result["bust_recomputed"] = after_bust is not fresh
result["bust_keeps_probe"] = "cache-probe" in {
    r["todo"] for r in after_bust["armedRows"]}
print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class FeedsDocumentCacheTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name) / "fx"
        proc = subprocess.run(
            [_python(), "-c", DRIVER, str(base),
             str(WORKRECORD_ROOT)],
            capture_output=True, text=True, timeout=280)
        if proc.returncode != 0:
            raise AssertionError(
                f"driver failed:\n{proc.stdout}\n"
                f"{proc.stderr}")
        cls.result = json.loads(
            proc.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_first_build_computes_once(self):
        self.assertEqual(self.result["calls_first"], 1)

    def test_repeat_build_within_ttl_serves_the_store(
            self):
        self.assertTrue(self.result["same_object"])
        self.assertEqual(self.result["calls_repeat"], 1)
        self.assertEqual(
            self.result["spawned_within_ttl"], 0)

    def test_document_shape_is_the_pinned_one(self):
        self.assertEqual(
            self.result["shape_keys"],
            sorted(["config", "home", "projects",
                    "projectFeeds", "projectsIndex",
                    "messages", "outbox", "settings",
                    "armedRows", "armedSkipped",
                    "statusVocabulary", "goals",
                    "goalsSource"]))
        for key in ("entries", "entriesArchived",
                    "entryDetails", "plans", "planDocs",
                    "todos", "classification", "board",
                    "worktrees", "diff"):
            self.assertIn(key, self.result["alpha_keys"])

    def test_write_within_ttl_moves_nothing(self):
        self.assertTrue(
            self.result["write_within_ttl_served_stale"])
        self.assertEqual(self.result["calls_after_write"],
                         1)
        self.assertEqual(
            self.result["spawned_after_write"], 0)

    def test_past_ttl_serves_stale_and_kicks_one(
            self):
        self.assertTrue(self.result["stale_served"])
        self.assertEqual(self.result["spawned_past_ttl"],
                         1)
        self.assertTrue(self.result["single_flight"])
        self.assertEqual(
            self.result["calls_before_refresh_runs"], 1)

    def test_kicked_refresh_lands_the_fresh_document(
            self):
        self.assertTrue(self.result["fresh_has_probe"])
        self.assertEqual(self.result["calls_total"], 2)
        self.assertEqual(
            self.result["spawned_after_refresh"], 0)

    def test_bust_takes_the_cold_path(self):
        self.assertEqual(self.result["calls_after_bust"],
                         3)
        self.assertTrue(self.result["bust_recomputed"])
        self.assertTrue(self.result["bust_keeps_probe"])


if __name__ == "__main__":
    unittest.main()
