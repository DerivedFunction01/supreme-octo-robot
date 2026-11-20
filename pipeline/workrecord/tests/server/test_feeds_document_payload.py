"""The feeds document's serving payload (assemble's
document store + serving's /api/feeds route): the
route serves the serialized bytes the last assembly
stored — the very serialization the persist writes —
with no serialization and no recompute on the request
path. Freshness is the lazy TTL contract (the
restore, 2026-11-16): a primed payload is stale by
construction, so the first read serves it and kicks
the one reassembly behind it; a read past the TTL
does the same for a computed payload; inside the TTL
a moved input changes nothing until the bound
passes. The freshness-tick phases this suite used to
pin are gone with the keeper they tested.

Two drivers, both fresh interpreters over the shared
fixture workspace (the persistence suite's pattern:
the server package reads its config at import, so
the fixture config must be installed before the
import). The first drives assemble's store through
compute, prime, and TTL expiry with an injected
clock and a captured spawn (determinism directive:
no wall clock, no real thread). The second builds
the real mount — its store swapped for the same
fakes — and dispatches GET /api/feeds through it:
the warm-filled store serves with zero computes, a
past-TTL read kicks exactly one reassembly and
still serves the stored bytes, and an emptied store
falls back to building on the request path.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

FAKES = r'''
clock = {"now": 1000.0}
spawned = []

def install_store():
    store = assemble._DocumentStore(
        clock=lambda: clock["now"],
        spawn=spawned.append)
    assemble._document_store = store
    return store
'''

DRIVER = r'''
import json
import os
import sys
from pathlib import Path

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))

from tests.server import fixture_ws

info = fixture_ws.build_fixture_workspace(base)
cfg = fixture_ws.fixture_config(base, base / "state-test")

os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])

from server import assemble, shapestore

''' + FAKES + r'''
install_store()

result = {}

real_compute = assemble._build_feeds_compute
calls = {"n": 0}

def counting_compute():
    calls["n"] += 1
    return real_compute()

assemble._build_feeds_compute = counting_compute

# Phase 0: a fresh process has no payload; no
# persisted document primes nothing.
result["payload_none_at_start"] = \
    assemble.feeds_payload_bytes() is None
result["prime_missing"] = \
    assemble.prime_document_cache()
result["payload_none_after_missing_prime"] = \
    assemble.feeds_payload_bytes() is None

# Phase 1: the first compute fills the store with
# the one serialization it also persists: the bytes
# parse back to exactly the served document and
# equal the persisted row's payload byte for byte.
# Within the TTL a repeat build serves the same
# document and the payload still parses to it — no
# settle dance: a TTL cannot be moved by the
# assembly's own writes.
first = assemble.build_feeds()
payload = assemble.feeds_payload_bytes()
result["payload_after_compute"] = payload is not None
result["payload_parses_to_document"] = (
    json.loads(payload.decode("utf-8")) == first)
row = shapestore.open_store(assemble.CFG).get(
    shapestore.FEEDS_DOCUMENT)
result["payload_equals_persisted_row"] = (
    row is not None and payload == row["payload"])
result["repeat_within_ttl_same_document"] = (
    assemble.build_feeds() is first)
result["calls_after_repeat"] = calls["n"]
real_source = first["goalsSource"]

# Phase 2: prime stores the persisted bytes as-is.
# The sentinel row is written with distinctive
# whitespace no compute produces; the payload must
# carry those exact bytes. The store is swapped
# fresh (a new process's store), so the prime is
# the only filler.
sentinel = dict(first)
sentinel["goalsSource"] = "persisted-sentinel"
sentinel_bytes = json.dumps(
    sentinel, indent=3).encode("utf-8")
shapestore.open_store(assemble.CFG).put(
    shapestore.FEEDS_DOCUMENT, sentinel_bytes,
    assembled_at="2026-10-25T00:00:00+00:00",
    fingerprint=None,
    stored_at="2026-10-25T00:00:00+00:00")
install_store()
result["prime_sentinel"] = \
    assemble.prime_document_cache()
payload = assemble.feeds_payload_bytes()
result["payload_is_persisted_text"] = (
    payload == sentinel_bytes)
result["payload_prime_parses_sentinel"] = (
    json.loads(payload.decode("utf-8"))["goalsSource"]
    == "persisted-sentinel")

# Phase 3: the primed payload is stale by
# construction: the first read serves the sentinel
# document and kicks exactly one reassembly; when
# it lands, the payload is the real document's
# serialization again.
before = calls["n"]
served = assemble.build_feeds()
result["primed_read_serves_sentinel"] = (
    served["goalsSource"] == "persisted-sentinel")
result["primed_read_kicked_one"] = len(spawned) == 1
result["primed_read_no_compute_yet"] = \
    calls["n"] == before
for fn in spawned:
    fn()
del spawned[:]
refreshed = json.loads(
    assemble.feeds_payload_bytes().decode("utf-8"))
result["payload_refreshed_to_real"] = (
    refreshed["goalsSource"] == real_source)
result["calls_after_primed_refresh"] = calls["n"]

# Phase 4: a moved input inside the TTL changes
# nothing; past the TTL the next read kicks the
# reassembly. The delta repo's git index is bumped
# (no content change anywhere): the read inside
# the bound serves and kicks nothing, the read
# past it serves stale and kicks one.
index = info["delta"] / ".git" / "index"
st = index.stat()
os.utime(index, ns=(st.st_atime_ns,
                    st.st_mtime_ns + 1_000_000))
before = calls["n"]
assemble.build_feeds()
result["moved_input_within_ttl_no_kick"] = (
    len(spawned) == 0 and calls["n"] == before)
clock["now"] += assemble.CFG[
    "feeds_document_ttl_s"] + 1
assemble.build_feeds()
result["past_ttl_kicked_one"] = len(spawned) == 1
for fn in spawned:
    fn()
del spawned[:]
result["calls_after_ttl_refresh"] = calls["n"]

# Phase 5: prime never displaces a filled store —
# a later persisted row (a previous process's
# document, say) leaves the live payload serving.
held = assemble.feeds_payload_bytes()
shapestore.open_store(assemble.CFG).put(
    shapestore.FEEDS_DOCUMENT,
    json.dumps(sentinel).encode("utf-8"),
    assembled_at="2026-10-25T00:00:00+00:00",
    fingerprint=None,
    stored_at="2026-10-25T00:00:00+00:00")
assemble.prime_document_cache()
result["prime_never_displaces"] = (
    assemble.feeds_payload_bytes() == held)

print(json.dumps(result))
'''

ROUTE_DRIVER = r'''
import json
import os
import sys
import time
from pathlib import Path

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))

from tests.server import fixture_ws

info = fixture_ws.build_fixture_workspace(base)
cfg = fixture_ws.fixture_config(base, base / "state-test")

os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])

from server import assemble, serving

''' + FAKES + r'''
install_store()

core = serving.serving
result = {}

real_compute = assemble._build_feeds_compute
calls = {"n": 0}

def counting_compute():
    calls["n"] += 1
    return real_compute()

assemble._build_feeds_compute = counting_compute

mount, workers, host, port = serving.build_mount()

# The warm-up's build_feeds fills the store (no
# persisted document exists in this fresh state
# dir, so the prime is a no-op and the warm compute
# is the fill). The wait is for a guaranteed event:
# the warm thread always lands the fill.
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    if assemble._document_store._result is not None \
            and assemble.feeds_payload_bytes() \
            is not None:
        break
    time.sleep(0.05)
result["warm_filled_store"] = (
    assemble.feeds_payload_bytes() is not None)

# The route serves the store's bytes verbatim and
# invokes no compute doing it.
request = core.Request("GET", "/api/feeds", {}, b"")
before = calls["n"]
reply = mount.dispatch(request)
result["route_status"] = reply.status
result["route_content_type"] = reply.content_type
result["route_serves_store_bytes"] = (
    reply.body == assemble.feeds_payload_bytes())
result["route_computes"] = calls["n"] - before
result["route_body_parses"] = isinstance(
    json.loads(reply.body.decode("utf-8"))
    .get("projectFeeds"), dict)
result["route_within_ttl_no_kick"] = \
    len(spawned) == 0

# Past the TTL a read still serves the stored bytes
# and computes nothing — it kicks the one background
# reassembly; a second read shares the flight. When
# the reassembly lands, the route serves the new
# bytes.
held = assemble.feeds_payload_bytes()
clock["now"] += assemble.CFG[
    "feeds_document_ttl_s"] + 1
before = calls["n"]
reply = mount.dispatch(request)
result["past_ttl_serves_stale_bytes"] = (
    reply.status == 200 and reply.body == held)
result["past_ttl_computes"] = calls["n"] - before
result["past_ttl_kicked_one"] = len(spawned) == 1
reply = mount.dispatch(request)
result["second_read_shares_flight"] = (
    reply.body == held and len(spawned) == 1)
for fn in spawned:
    fn()
del spawned[:]
result["refresh_computed_once"] = \
    calls["n"] - before == 1
reply = mount.dispatch(request)
result["route_serves_refreshed_bytes"] = (
    reply.status == 200
    and reply.body == assemble.feeds_payload_bytes()
    and reply.body != held)

# The fallback: an empty store builds on the
# request path, exactly as the route did before the
# store existed.
install_store()
before = calls["n"]
reply = mount.dispatch(
    core.Request("GET", "/api/feeds", {}, b""))
result["fallback_status"] = reply.status
result["fallback_computes"] = calls["n"] - before
result["fallback_body_parses"] = (
    "projectFeeds" in json.loads(
        reply.body.decode("utf-8")))

print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _run_driver(driver):
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name) / "fx"
    proc = subprocess.run(
        [_python(), "-c", driver, str(base),
         str(WORKRECORD_ROOT)],
        capture_output=True, text=True, timeout=280)
    if proc.returncode != 0:
        raise AssertionError(
            f"driver failed:\n{proc.stdout}\n"
            f"{proc.stderr}")
    result = json.loads(
        proc.stdout.strip().splitlines()[-1])
    return tmp, result


class FeedsDocumentPayloadTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp, cls.result = _run_driver(DRIVER)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_no_payload_before_compute_or_prime(self):
        self.assertTrue(
            self.result["payload_none_at_start"])
        self.assertFalse(self.result["prime_missing"])
        self.assertTrue(
            self.result["payload_none_after_missing_prime"])

    def test_compute_stores_the_persisted_serialization(
            self):
        self.assertTrue(
            self.result["payload_after_compute"])
        self.assertTrue(
            self.result["payload_parses_to_document"])
        self.assertTrue(
            self.result["payload_equals_persisted_row"])
        self.assertTrue(
            self.result["repeat_within_ttl_same_document"])
        self.assertEqual(
            self.result["calls_after_repeat"], 1)

    def test_prime_stores_persisted_text_as_is(self):
        self.assertTrue(self.result["prime_sentinel"])
        self.assertTrue(
            self.result["payload_is_persisted_text"])
        self.assertTrue(
            self.result["payload_prime_parses_sentinel"])

    def test_primed_payload_kicks_one_reassembly(self):
        self.assertTrue(
            self.result["primed_read_serves_sentinel"])
        self.assertTrue(
            self.result["primed_read_kicked_one"])
        self.assertTrue(
            self.result["primed_read_no_compute_yet"])
        self.assertTrue(
            self.result["payload_refreshed_to_real"])
        self.assertEqual(
            self.result["calls_after_primed_refresh"], 2)

    def test_moved_input_waits_for_the_ttl(self):
        self.assertTrue(
            self.result["moved_input_within_ttl_no_kick"])
        self.assertTrue(
            self.result["past_ttl_kicked_one"])
        self.assertEqual(
            self.result["calls_after_ttl_refresh"], 3)

    def test_prime_never_displaces_a_filled_store(
            self):
        self.assertTrue(
            self.result["prime_never_displaces"])


class FeedsDocumentRouteTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp, cls.result = _run_driver(ROUTE_DRIVER)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_warm_up_fills_the_store(self):
        self.assertTrue(
            self.result["warm_filled_store"])

    def test_route_serves_store_bytes_without_compute(
            self):
        self.assertEqual(self.result["route_status"],
                         200)
        self.assertEqual(
            self.result["route_content_type"],
            "application/json; charset=utf-8")
        self.assertTrue(
            self.result["route_serves_store_bytes"])
        self.assertEqual(self.result["route_computes"],
                         0)
        self.assertTrue(self.result["route_body_parses"])
        self.assertTrue(
            self.result["route_within_ttl_no_kick"])

    def test_past_ttl_read_kicks_and_serves_stale(self):
        self.assertTrue(
            self.result["past_ttl_serves_stale_bytes"])
        self.assertEqual(
            self.result["past_ttl_computes"], 0)
        self.assertTrue(
            self.result["past_ttl_kicked_one"])
        self.assertTrue(
            self.result["second_read_shares_flight"])
        self.assertTrue(
            self.result["refresh_computed_once"])
        self.assertTrue(
            self.result["route_serves_refreshed_bytes"])

    def test_empty_store_falls_back_to_building(self):
        self.assertEqual(
            self.result["fallback_status"], 200)
        self.assertEqual(
            self.result["fallback_computes"], 1)
        self.assertTrue(
            self.result["fallback_body_parses"])


if __name__ == "__main__":
    unittest.main()
