"""The feeds document's lazy freshness contract (the
restore): freshness is read-triggered and
TTL-bound — there is no keeper thread, no fingerprint,
and no cooldown machinery in assemble at all; with no
reads, no reassembly is ever kicked however far past
the TTL the clock runs; the route's kick
(assemble.kick_document_refresh) fires exactly one
background reassembly for a stale store and is a no-op
for a cold or fresh one. The census the per-repo
routes resolve through carries the same shape
(repos_feed._census_cached): repeated resolves pay
one walk, a new repo is invisible inside the TTL (the
lazy bound), and a stale resolve serves the old
census while the refresh lands it.

This suite replaces the fingerprint-era freshness
suite: its subject (the keeper tick, the cooldown,
the census snapshot) was removed by the owner's
ruling that continuous enumeration was the
divergence. The old driver also proved its cadence
by quiet-time convergence (a stability window over
wall-clock sleeps); the contract here is pinned with
fakes instead — an injected clock and a captured
spawn for the document store, a synchronous thread
stand-in for the census refresh — per the
determinism directive.
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

from server import assemble, repos_feed

result = {}

# The keeper machinery is gone, not parked.
result["no_keeper"] = not hasattr(
    assemble, "start_freshness_thread")
result["no_tick"] = not hasattr(
    assemble, "_freshness_tick")
result["no_fingerprint"] = not hasattr(
    assemble, "_document_fingerprint")

clock = {"now": 5000.0}
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

# A kick on a cold store is a no-op: there is no
# document to refresh — cold reads compute.
assemble.kick_document_refresh()
result["kick_cold_no_spawn"] = len(spawned) == 0

first = assemble.build_feeds()
result["calls_first"] = calls["n"]

# A kick inside the TTL is a no-op.
assemble.kick_document_refresh()
result["kick_fresh_no_spawn"] = len(spawned) == 0

# No reads, no work: the clock runs far past the TTL
# and nothing is kicked and nothing computes — the
# zero-background-work half of the lazy contract.
clock["now"] += 10 * ttl
result["idle_no_spawn"] = len(spawned) == 0
result["idle_no_compute"] = calls["n"] == 1

# The first stale kick spawns the one reassembly; a
# second kick while it is in flight spawns nothing.
assemble.kick_document_refresh()
result["kick_stale_spawns_one"] = len(spawned) == 1
assemble.kick_document_refresh()
result["kick_in_flight_no_second"] = len(spawned) == 1
for fn in spawned:
    fn()
del spawned[:]
result["calls_after_refresh"] = calls["n"]
assemble.kick_document_refresh()
result["kick_after_refresh_no_spawn"] = \
    len(spawned) == 0

# --- the census cache (repos_feed._census_cached) ---
walks = {"n": 0}
real_census = repos_feed._census

def counting_census(deadline=None):
    walks["n"] += 1
    return real_census(deadline)

repos_feed._census = counting_census
# The document builds above already filled the census
# cache through the repos feed; reset it cold so the
# legs below start from a never-filled cache.
repos_feed._census_cache.update(at=0.0, result=None)

ws = base / "ws"
repo_one = ws / "disc-one"
(repo_one / ".git").mkdir(parents=True)

record = repos_feed._repo_or_404("disc-one")
result["census_first_walk"] = walks["n"] == 1
result["census_record_root"] = \
    record["root"] == str(repo_one)
again = repos_feed._repo_or_404("disc-one")
result["census_repeat_no_walk"] = walks["n"] == 1

from server.common import ApiError
try:
    repos_feed._repo_or_404("disc-unknown")
    result["census_unknown_404"] = False
except ApiError as e:
    result["census_unknown_404"] = e.status == 404
result["census_unknown_no_walk"] = walks["n"] == 1

# A repo created inside the TTL is invisible (the
# lazy bound, stated): the cached census serves.
repo_two = ws / "disc-two"
(repo_two / ".git").mkdir(parents=True)
try:
    repos_feed._repo_or_404("disc-two")
    result["census_new_repo_hidden_in_ttl"] = False
except ApiError:
    result["census_new_repo_hidden_in_ttl"] = True
result["census_still_one_walk"] = walks["n"] == 1

# Past the TTL a resolve serves the stale census and
# kicks the refresh (run inline here by a synchronous
# thread stand-in, so the landing is an event, not a
# wait); the next resolve sees the new repo, and the
# walk count moved by exactly one.
import threading
import time as time_mod
repos_feed._census_cache["at"] = \
    time_mod.monotonic() - repos_feed.CFG[
        "repos_ttl_s"] - 1

real_thread = threading.Thread

class SyncThread(real_thread):
    """Runs the census refresh inline (its landing
    becomes an event the driver controls); every
    other thread keeps its real behaviour."""

    def start(self):
        if getattr(self._target, "__name__", "") == \
                "_census_refresh_background":
            self._target(*self._args)
        else:
            super().start()

threading.Thread = SyncThread
try:
    try:
        repos_feed._repo_or_404("disc-two")
        result["census_stale_served"] = False
    except ApiError:
        result["census_stale_served"] = True
finally:
    threading.Thread = real_thread
result["census_refresh_walked_once"] = walks["n"] == 2
record_two = repos_feed._repo_or_404("disc-two")
result["census_refreshed_record"] = \
    record_two["root"] == str(repo_two)
result["census_no_further_walk"] = walks["n"] == 2

print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class FeedsDocumentFreshnessTest(unittest.TestCase):

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

    def test_keeper_machinery_is_gone(self):
        self.assertTrue(self.result["no_keeper"])
        self.assertTrue(self.result["no_tick"])
        self.assertTrue(self.result["no_fingerprint"])

    def test_kick_is_a_noop_cold_and_fresh(self):
        self.assertTrue(
            self.result["kick_cold_no_spawn"])
        self.assertEqual(self.result["calls_first"], 1)
        self.assertTrue(
            self.result["kick_fresh_no_spawn"])

    def test_no_reads_no_work(self):
        self.assertTrue(self.result["idle_no_spawn"])
        self.assertTrue(self.result["idle_no_compute"])

    def test_stale_kick_spawns_exactly_one(self):
        self.assertTrue(
            self.result["kick_stale_spawns_one"])
        self.assertTrue(
            self.result["kick_in_flight_no_second"])
        self.assertEqual(
            self.result["calls_after_refresh"], 2)
        self.assertTrue(
            self.result["kick_after_refresh_no_spawn"])

    def test_census_resolves_from_one_walk(self):
        self.assertTrue(self.result["census_first_walk"])
        self.assertTrue(
            self.result["census_record_root"])
        self.assertTrue(
            self.result["census_repeat_no_walk"])
        self.assertTrue(
            self.result["census_unknown_404"])
        self.assertTrue(
            self.result["census_unknown_no_walk"])

    def test_census_new_repo_waits_for_the_ttl(self):
        self.assertTrue(
            self.result["census_new_repo_hidden_in_ttl"])
        self.assertTrue(
            self.result["census_still_one_walk"])

    def test_census_stale_serve_then_refresh(self):
        self.assertTrue(
            self.result["census_stale_served"])
        self.assertTrue(
            self.result["census_refresh_walked_once"])
        self.assertTrue(
            self.result["census_refreshed_record"])
        self.assertTrue(
            self.result["census_no_further_walk"])


if __name__ == "__main__":
    unittest.main()
