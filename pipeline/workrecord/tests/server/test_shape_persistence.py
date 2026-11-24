"""The assembled shapes' database persistence
(server/shapestore + the census half of the owner's
persistence ruling): the store's own
contract, and the census's persist / prime round
trip.

The store legs run in-process (shapestore imports no
config state — the path is the caller's argument).
The census legs run in a fresh interpreter over the
shared fixture workspace (the document suites'
pattern: the server package reads its config at
import, so the fixture config must be installed
before the import), with the walk counted through a
wrapper — the freshness suite's counting form — and
every refresh driven synchronously, so no leg waits
on a thread or a clock: each phase's verdict is read
off the walk count it leaves behind.
"""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

from server import shapestore  # noqa: E402


class ShapeStoreTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "shapes.db"

    def tearDown(self):
        self._tmp.cleanup()

    def _put(self, store, name="census",
             payload=b"payload"):
        store.put(name, payload,
                  assembled_at="2026-10-25T00:00:00+00:00",
                  fingerprint="fp-1",
                  stored_at="2026-10-25T00:00:01+00:00")

    def test_put_get_roundtrip(self):
        store = shapestore.ShapeStore(self.path)
        self._put(store)
        row = store.get("census")
        self.assertEqual(row["payload"], b"payload")
        self.assertEqual(row["assembled_at"],
                         "2026-10-25T00:00:00+00:00")
        self.assertEqual(row["fingerprint"], "fp-1")

    def test_put_replaces_the_one_row(self):
        store = shapestore.ShapeStore(self.path)
        self._put(store, payload=b"first")
        self._put(store, payload=b"second")
        self.assertEqual(store.get("census")["payload"],
                         b"second")
        con = sqlite3.connect(str(self.path))
        try:
            count = con.execute(
                "SELECT COUNT(*) FROM shapes").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(count, 1)

    def test_absent_shape_reads_none(self):
        store = shapestore.ShapeStore(self.path)
        self.assertIsNone(store.get("census"))
        self.assertIsNone(store.payload_size("census"))

    def test_payload_size_without_loading(self):
        store = shapestore.ShapeStore(self.path)
        self._put(store, payload=b"x" * 1234)
        self.assertEqual(store.payload_size("census"),
                         1234)

    def test_version_mismatch_discards_and_rebuilds(
            self):
        store = shapestore.ShapeStore(self.path)
        self._put(store)
        con = sqlite3.connect(str(self.path))
        try:
            con.execute("PRAGMA user_version = 999")
            con.commit()
        finally:
            con.close()
        rebuilt = shapestore.ShapeStore(self.path)
        self.assertIsNone(rebuilt.get("census"))
        self._put(rebuilt, payload=b"fresh")
        self.assertEqual(
            rebuilt.get("census")["payload"], b"fresh")

    def test_non_database_file_discarded_and_rebuilt(
            self):
        self.path.write_bytes(b"not a database at all")
        store = shapestore.ShapeStore(self.path)
        self.assertIsNone(store.get("census"))
        self._put(store)
        self.assertEqual(store.get("census")["payload"],
                         b"payload")


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

from server import repos_feed, shapestore
from server import config as cfgmod

store_path = cfgmod.shapes_store_path(repos_feed.CFG)
result = {}

walks = {"n": 0}
real_census = repos_feed._census

def counting_census(deadline=None):
    walks["n"] += 1
    return real_census(deadline)

repos_feed._census = counting_census

def census_row():
    return shapestore.open_store(repos_feed.CFG).get(
        shapestore.CENSUS)

def reset_cache():
    repos_feed._census_cache.update(at=0.0, result=None)

def drop_store():
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(f"{store_path}{suffix}").unlink()
        except OSError:
            pass

# Phase 1: a cold resolve walks once, and the walk
# persists its census: the row's records are exactly
# the served census, and its fingerprint is the
# census's footprint fingerprint of that same census.
reset_cache()
served = repos_feed._census_cached()
result["cold_walks"] = walks["n"]
row = census_row()
result["row_after_walk"] = row is not None
records = json.loads(row["payload"].decode("utf-8"))
result["row_records_are_served"] = (
    records == [served[k] for k in sorted(served)])
result["row_fingerprint_is_footprint"] = (
    row["fingerprint"]
    == repos_feed._census_fingerprint(served))
result["served_ids"] = sorted(served)

# Phase 2: a restart — the prime installs the
# persisted census, and the per-repo resolve serves
# the primed census itself (object identity, not
# just an equal root: the refresh the stale read
# kicks — run inline here by a synchronous thread
# stand-in, the freshness suite's form — re-walks
# behind it, and the walk count moves only there).
reset_cache()
result["prime"] = repos_feed.prime_census_cache()
primed = repos_feed._census_cache["result"]
import threading
real_thread = threading.Thread

class SyncThread(real_thread):
    def start(self):
        if getattr(self._target, "__name__", "") == \
                "_census_refresh_background":
            self._target(*self._args)
        else:
            super().start()

threading.Thread = SyncThread
try:
    record = repos_feed._repo_or_404("delta-repo")
finally:
    threading.Thread = real_thread
result["boot_resolve_from_primed"] = (
    record is primed["delta-repo"])
result["boot_resolve_root"] = (
    record["root"] == str(info["delta"]))
result["refresh_rewalks"] = walks["n"]

# Phase 3: the tree moves (a new repo appears). The
# next refresh re-walks, and the new walk
# re-persists: the row now carries the new repo
# under a moved fingerprint.
gamma = base / "ws" / "gamma"
(gamma / ".git").mkdir(parents=True)
repos_feed._census_refresh_background()
result["moved_walks"] = walks["n"]
record = repos_feed._repo_or_404("gamma")
result["gamma_resolves"] = (
    record["root"] == str(gamma))
row2 = census_row()
records2 = json.loads(row2["payload"].decode("utf-8"))
result["row_has_gamma"] = any(
    r["id"] == "gamma" for r in records2)
result["row_fingerprint_moved"] = (
    row2["fingerprint"] != row["fingerprint"])

# Phase 4: an absent store primes nothing; the cold
# walk stands, and it re-persists.
drop_store()
reset_cache()
result["prime_absent"] = \
    repos_feed.prime_census_cache()
repos_feed._census_cached()
result["absent_walks"] = walks["n"]
result["absent_repersisted"] = \
    census_row() is not None

# Phase 5: a corrupt store primes nothing and
# raises nothing; the cold walk stands.
drop_store()
store_path.write_bytes(b"not a database at all")
reset_cache()
result["prime_corrupt"] = \
    repos_feed.prime_census_cache()
repos_feed._census_cached()
result["corrupt_walks"] = walks["n"]

print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class CensusShapePersistenceTest(unittest.TestCase):

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

    def test_walk_persists_the_served_census(self):
        self.assertEqual(self.result["cold_walks"], 1)
        self.assertTrue(self.result["row_after_walk"])
        self.assertTrue(
            self.result["row_records_are_served"])
        self.assertTrue(
            self.result["row_fingerprint_is_footprint"])
        self.assertEqual(self.result["served_ids"],
                         ["alpha", "delta-repo"])

    def test_prime_serves_and_refresh_rewalks(self):
        self.assertTrue(self.result["prime"])
        self.assertTrue(
            self.result["boot_resolve_from_primed"])
        self.assertTrue(
            self.result["boot_resolve_root"])
        self.assertEqual(
            self.result["refresh_rewalks"], 2)

    def test_moved_tree_rewalks_and_repersist(self):
        self.assertEqual(self.result["moved_walks"], 3)
        self.assertTrue(self.result["gamma_resolves"])
        self.assertTrue(self.result["row_has_gamma"])
        self.assertTrue(
            self.result["row_fingerprint_moved"])

    def test_absent_store_falls_back_to_the_walk(self):
        self.assertFalse(self.result["prime_absent"])
        self.assertEqual(self.result["absent_walks"], 4)
        self.assertTrue(
            self.result["absent_repersisted"])

    def test_corrupt_store_falls_back_to_the_walk(
            self):
        self.assertFalse(self.result["prime_corrupt"])
        self.assertEqual(self.result["corrupt_walks"], 5)


if __name__ == "__main__":
    unittest.main()
