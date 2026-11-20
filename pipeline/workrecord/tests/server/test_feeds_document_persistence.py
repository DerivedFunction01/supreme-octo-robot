"""The feeds document's cross-restart persistence
(assemble._persist_document / prime_document_cache
over assemble._DocumentStore.prime): every successful
assembly persists itself — payload bytes, assembly
instant, source fingerprint — into the shapes
database (server/shapestore), and a fresh process
primes its document store from that row, so the
first read after a restart serves the last assembly
stale-while-recompute instead of waiting on the cold
assembly. The pre-database persisted file
(feeds_document_file) stands as the prime's
one-transition fallback: a state dir whose last
assembly predates the database primes from the file.
A missing source primes nothing; a corrupt one logs,
primes nothing, and raises nothing — the cold
compute path stands.

The proof runs in a fresh interpreter (a driver
script over the shared fixture workspace), the same
way test_feeds_document_cache's does: the server
package reads its config at import, so the fixture
config must be installed before the import. A
restart is simulated by swapping in a fresh document
store (a new process's store is empty by
construction); the priming phase's refresh compute
blocks on events, so the served-stale assertions are
deterministic — no read can race the reassembly it
is served ahead of, and the refresh's landing is
awaited on its own event, never polled for. (The
fingerprint era's settle loop is gone with the
fingerprint: a TTL cannot be moved by the assembly's
own writes, so the first build's count is already
final.)
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
import hashlib
import json
import sys
import threading
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

from server import assemble, shapestore
from server import config as cfgmod

store_path = cfgmod.shapes_store_path(assemble.CFG)
legacy_path = cfgmod.feeds_document_path(assemble.CFG)


def store_row():
    return shapestore.open_store(
        assemble.CFG).get(shapestore.FEEDS_DOCUMENT)


def drop_store():
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(f"{store_path}{suffix}").unlink()
        except OSError:
            pass


result = {}

real_compute = assemble._build_feeds_compute
calls = {"n": 0}

def counting_compute():
    calls["n"] += 1
    return real_compute()

# Phase 1: no persisted document in either source —
# priming is a no-op; the first build computes, and
# the compute persists the document it built into
# the database (round-trip: the row's payload parses
# back to exactly the served document, and the
# row's fingerprint is the payload's own hash). The
# legacy file is not written any more: the database
# is the persist now.
result["row_before"] = store_row() is not None
result["file_before"] = legacy_path.is_file()
result["prime_missing"] = \
    assemble.prime_document_cache()
assemble._build_feeds_compute = counting_compute
first = assemble.build_feeds()
result["calls_first"] = calls["n"]
row = store_row()
result["row_after_compute"] = row is not None
result["persist_roundtrip"] = (
    json.loads(row["payload"].decode("utf-8"))
    == first)
result["row_fingerprint_is_payload_hash"] = (
    row["fingerprint"] == hashlib.sha256(
        row["payload"]).hexdigest())
result["payload_is_row"] = (
    assemble.feeds_payload_bytes() == row["payload"])
result["file_after_compute"] = legacy_path.is_file()
real_source = first["goalsSource"]

# Phase 2: a restart — a fresh store over a persisted
# sentinel row (the first document with a marker no
# real assembly produces). Priming serves the
# sentinel while the reassembly runs behind it: the
# wrapped compute blocks until released, so the
# served-stale reads cannot race it. Once released,
# the refresh replaces the prime and persists its
# own document.
sentinel = dict(first)
sentinel["goalsSource"] = "persisted-sentinel"
shapestore.open_store(assemble.CFG).put(
    shapestore.FEEDS_DOCUMENT,
    json.dumps(sentinel).encode("utf-8"),
    assembled_at="2026-10-25T00:00:00+00:00",
    fingerprint="sentinel-fingerprint",
    stored_at="2026-10-25T00:00:00+00:00")
assemble._document_store = assemble._DocumentStore()
result["prime_sentinel"] = \
    assemble.prime_document_cache()

entered = threading.Event()
release = threading.Event()
landed = threading.Event()

def blocking_compute():
    entered.set()
    release.wait(120)
    try:
        return real_compute()
    finally:
        landed.set()

assemble._build_feeds_compute = blocking_compute
served = assemble.build_feeds()
result["served_sentinel"] = (
    served["goalsSource"] == "persisted-sentinel")
result["refresh_entered"] = entered.wait(30)
served_again = assemble.build_feeds()
result["served_sentinel_while_blocked"] = (
    served_again["goalsSource"]
    == "persisted-sentinel")
release.set()
result["refresh_landed"] = landed.wait(60)
fresh = assemble.build_feeds()
result["fresh_after_release"] = (
    fresh["goalsSource"] == real_source)
row = store_row()
result["persist_after_refresh"] = (
    json.loads(row["payload"].decode("utf-8"))
    == fresh)

# Phase 3: a corrupt shapes database primes nothing
# and raises nothing (the store discards the file
# and rebuilds empty; no row stands, and no legacy
# file stands either); the next build takes the cold
# compute path and re-persists a valid row.
assemble._document_store = assemble._DocumentStore()
drop_store()
store_path.write_bytes(b"not a database at all")
result["prime_corrupt"] = \
    assemble.prime_document_cache()
assemble._build_feeds_compute = counting_compute
before = calls["n"]
recovered = assemble.build_feeds()
result["corrupt_calls_delta"] = calls["n"] - before
result["corrupt_served_real"] = (
    recovered["goalsSource"] == real_source)
row = store_row()
result["corrupt_repersisted"] = (
    row is not None
    and json.loads(row["payload"].decode("utf-8"))
    == recovered)

# Phase 4: the legacy file fallback — a state dir
# whose last assembly predates the database (no
# store stands) primes from the persisted file
# exactly as it always did; a corrupt file primes
# nothing.
drop_store()
assemble._document_store = assemble._DocumentStore()
legacy_path.write_text(json.dumps(sentinel),
                       encoding="utf-8")
result["prime_legacy"] = \
    assemble.prime_document_cache()
result["legacy_payload_served"] = (
    assemble.feeds_payload_bytes()
    == legacy_path.read_bytes())
assemble._document_store = assemble._DocumentStore()
legacy_path.write_bytes(b"{ not a document")
result["prime_corrupt_legacy"] = \
    assemble.prime_document_cache()
result["corrupt_legacy_no_payload"] = (
    assemble.feeds_payload_bytes() is None)

print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class FeedsDocumentPersistenceTest(unittest.TestCase):

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

    def test_missing_store_primes_nothing(self):
        self.assertFalse(self.result["row_before"])
        self.assertFalse(self.result["file_before"])
        self.assertFalse(self.result["prime_missing"])

    def test_successful_compute_persists_roundtrip(
            self):
        self.assertEqual(self.result["calls_first"], 1)
        self.assertTrue(
            self.result["row_after_compute"])
        self.assertTrue(self.result["persist_roundtrip"])
        self.assertTrue(
            self.result["row_fingerprint_is_payload_hash"])
        self.assertTrue(self.result["payload_is_row"])
        # The database is the persist: the legacy file
        # is no longer written by an assembly.
        self.assertFalse(
            self.result["file_after_compute"])

    def test_prime_serves_persisted_while_refresh_runs(
            self):
        self.assertTrue(self.result["prime_sentinel"])
        self.assertTrue(self.result["served_sentinel"])
        self.assertTrue(self.result["refresh_entered"])
        self.assertTrue(
            self.result["served_sentinel_while_blocked"])
        self.assertTrue(self.result["refresh_landed"])

    def test_refresh_replaces_prime_and_repersist(
            self):
        self.assertTrue(
            self.result["fresh_after_release"])
        self.assertTrue(
            self.result["persist_after_refresh"])

    def test_corrupt_store_falls_back_to_cold_compute(
            self):
        self.assertFalse(self.result["prime_corrupt"])
        self.assertEqual(
            self.result["corrupt_calls_delta"], 1)
        self.assertTrue(
            self.result["corrupt_served_real"])
        self.assertTrue(
            self.result["corrupt_repersisted"])

    def test_legacy_file_still_primes(self):
        self.assertTrue(self.result["prime_legacy"])
        self.assertTrue(
            self.result["legacy_payload_served"])

    def test_corrupt_legacy_file_primes_nothing(self):
        self.assertFalse(
            self.result["prime_corrupt_legacy"])
        self.assertTrue(
            self.result["corrupt_legacy_no_payload"])


if __name__ == "__main__":
    unittest.main()
