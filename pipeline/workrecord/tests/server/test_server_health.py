"""The health route's discipline (GET /api/health):
health never computes. The route serves the sweep
cache by peek (common.peek_sweep) — while the cache
has never filled it answers 200 anyway, reporting
the sweep's warmth as data (sweep_warm: false, zero
counts) instead of queueing behind the first fill;
once a result is cached it serves exactly the body
it always served, plus the sweep_warm field.

One driver, a fresh interpreter over the shared
fixture workspace (the payload suite's pattern: the
server package reads its config at import, so the
fixture config must be installed before the import).
The driver replaces the sweep compute with a
counting stub that parks inside the call, holding
the compute lock — the cold start's fill genuinely
in flight and never landing. Against the pre-cure
route (health calling get_sweep) the cold dispatch
below parks behind that lock and the driver times
out: that hang is the defect this suite pins. With
the cure, health answers from the peek while the
fill is still parked, and no dispatch — cold, warm,
or stale — ever spends a compute.
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
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))

from tests.server import fixture_ws

info = fixture_ws.build_fixture_workspace(base)
cfg = fixture_ws.fixture_config(base, base / "state-test")

os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])

from server import assemble, common, serving

core = serving.serving
result = {}

# Park the freshness keeper: its tick computes the
# feeds fingerprint (a get_sweep caller); this
# driver asserts health behavior, and a tick landing
# mid-assertion would spend sweep computes the route
# never asked for.
assemble._FRESHNESS_INTERVAL_S = 3600

# The counting, parking compute stub: the warm
# thread's cold fill enters it and never lands (the
# gate is never set), holding the compute lock for
# the driver's whole life — so any compute a route
# triggers either shows in the count or parks the
# dispatch behind the lock, exactly the production
# cold start's shape.
calls = {"n": 0}
gate = threading.Event()
fake = SimpleNamespace(
    projects=[object(), object(), object()],
    errors=[object()])

def stub_compute():
    calls["n"] += 1
    gate.wait(120)
    return fake

common._compute_sweep = stub_compute

# Peek on the never-filled cache: None, and no
# compute spent learning it.
result["peek_cold_is_none"] = \
    common.peek_sweep() is None
result["peek_cold_no_compute"] = calls["n"] == 0

mount, workers, host, port = serving.build_mount()

# The warm thread's fill is genuinely in flight:
# inside the stub, holding the compute lock.
deadline = time.monotonic() + 30
while time.monotonic() < deadline and calls["n"] < 1:
    time.sleep(0.05)
result["warm_fill_in_flight"] = calls["n"] == 1

def get_health():
    reply = mount.dispatch(
        core.Request("GET", "/api/health", {}, b""))
    return reply.status, json.loads(
        reply.body.decode("utf-8"))

# Cold arm: the cache has never filled and the fill
# is parked. Health must answer anyway — 200, the
# full field set, zero counts, sweep_warm false —
# and must not compute.
status, body = get_health()
result["cold_status"] = status
result["cold_body"] = body
result["cold_no_compute"] = calls["n"] == 1

# Warm arm: a result lands in the cache (stored
# directly — the parked fill never lands, and the
# cache's state is what health reads, whoever filled
# it). The body is the one the route always served,
# plus sweep_warm true.
common._sweep_store(fake)
result["peek_warm_is_stored"] = \
    common.peek_sweep() is fake
status, body = get_health()
result["warm_status"] = status
result["warm_body"] = body
result["warm_no_compute"] = calls["n"] == 1

# A stale peek neither kicks a refresh nor
# computes: the entry is long past its TTL, and the
# peek still just reads it.
common._sweep_cache["at"] = 0.0
result["peek_stale_is_stored"] = \
    common.peek_sweep() is fake
result["peek_stale_no_kick"] = \
    not common._sweep_refreshing
result["peek_stale_no_compute"] = calls["n"] == 1

print(json.dumps(result))
'''

EXPECTED_KEYS = {
    "ok", "version", "commit", "started_at", "uptime_s",
    "host", "port", "projects_count", "stackdump_last_at",
    "config_hash", "sweep", "sweep_warm",
}


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


class ServerHealthTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp, cls.result = _run_driver(DRIVER)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_peek_on_cold_cache_is_none_without_compute(
            self):
        self.assertTrue(self.result["peek_cold_is_none"])
        self.assertTrue(
            self.result["peek_cold_no_compute"])

    def test_cold_health_answers_without_the_fill(self):
        # The fill was genuinely in flight (parked
        # inside the compute, holding the lock) when
        # health was dispatched — and health answered.
        self.assertTrue(
            self.result["warm_fill_in_flight"])
        self.assertEqual(self.result["cold_status"],
                         200)
        self.assertTrue(self.result["cold_no_compute"])

    def test_cold_health_body_reports_unwarm_sweep(self):
        body = self.result["cold_body"]
        self.assertEqual(set(body), EXPECTED_KEYS)
        self.assertTrue(body["ok"])
        self.assertFalse(body["sweep_warm"])
        self.assertEqual(body["projects_count"], 0)
        self.assertEqual(body["sweep"],
                         {"projects": 0, "errors": 0})

    def test_warm_health_body_is_the_served_body(self):
        self.assertTrue(
            self.result["peek_warm_is_stored"])
        self.assertEqual(self.result["warm_status"],
                         200)
        body = self.result["warm_body"]
        self.assertEqual(set(body), EXPECTED_KEYS)
        self.assertTrue(body["ok"])
        self.assertTrue(body["sweep_warm"])
        self.assertEqual(body["projects_count"], 3)
        self.assertEqual(body["sweep"],
                         {"projects": 3, "errors": 1})
        self.assertTrue(self.result["warm_no_compute"])

    def test_stale_peek_neither_kicks_nor_computes(self):
        self.assertTrue(
            self.result["peek_stale_is_stored"])
        self.assertTrue(self.result["peek_stale_no_kick"])
        self.assertTrue(
            self.result["peek_stale_no_compute"])


if __name__ == "__main__":
    unittest.main()
