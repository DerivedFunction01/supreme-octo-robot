"""Contract tests for the stack-dump watchdog
(`stackdump-contract: v1`, clause 5): (a) a health path
parked past the threshold produces a dump naming the
parked frame, the watcher never blocking on the parked
path's locks; (b) a healthy server produces no dump over
several cadences; (c) the dump file's size cap holds under
repeated lag events. Plus the config defaults and the
health payload's last-dump field (clause 6).

All state lives in temp dirs — the live state area is
never touched.
"""
import contextlib
import os
import tempfile
import threading
import time
import unittest

from server import config as config_mod
from server.firing import stackdump as stackdump_mod
from server.firing.engine import Engine
from server.firing.stackdump import StackDumpWatchdog
from tests.helpers import Clock, T0, make_home

PARK_RELEASE = threading.Event()
PARK_LOCK = threading.Lock()


def parked_health_check():
    """A health computation parked on an event while
    holding a lock — the wedge shape the dump must name
    without ever needing that lock."""
    with PARK_LOCK:
        PARK_RELEASE.wait(30)


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def dump_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


class FakeClock:
    """A manually advanced stand-in for the `time` reference
    inside server.firing.stackdump: monotonic() reads the fake now
    and sleep() blocks until an advance() carries the fake
    now past the sleeper's wake point. The watchdog's lag
    arithmetic runs entirely on this clock, so when a dump
    fires is decided by the test's advances — never by how
    the OS happens to schedule the watchdog's threads.

    The epoch starts large because the watcher's repeat
    discipline measures from 0.0: a real monotonic clock is
    far past any repeat interval by the time a watchdog
    starts, and the fake keeps that shape."""

    def __init__(self, start=10_000.0):
        self._now = start
        self._cond = threading.Condition()

    def monotonic(self):
        with self._cond:
            return self._now

    def sleep(self, seconds):
        with self._cond:
            wake = self._now + seconds
            while self._now < wake:
                self._cond.wait()

    def advance(self, seconds):
        with self._cond:
            self._now += seconds
            self._cond.notify_all()


@contextlib.contextmanager
def fake_stackdump_clock(clock):
    real = stackdump_mod.time
    stackdump_mod.time = clock
    try:
        yield clock
    finally:
        stackdump_mod.time = real


class WatchdogCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "stackdumps.log")
        PARK_RELEASE.clear()

    def tearDown(self):
        PARK_RELEASE.set()

    def watchdog(self, health, **over):
        params = {"cadence_s": 0.05, "threshold_s": 0.3,
                  "repeat_s": 60.0, "max_bytes": 16 * 1024 * 1024}
        params.update(over)
        wd = StackDumpWatchdog("test-server", health, self.path,
                               **params)
        wd.start()
        return wd


class ParkedDumpTest(WatchdogCase):
    def test_parked_health_dumps_the_parked_frame(self):
        # The watchdog runs on a fake clock: the test parks
        # the health path first (a rendezvous on the lock
        # actually being held), then advances fake time past
        # the threshold, so the dump is guaranteed to catch
        # the checker inside parked_health_check. On the
        # real clock this raced under CPU contention — lag
        # was measured from construction, and the wait below
        # observed the dump's first effect (the flushed
        # file) and asserted on its second (last_dump_at,
        # stamped after the flush), which a descheduled
        # watcher thread could lose to the test thread.
        clock = FakeClock()
        entered = threading.Event()

        def health():
            entered.set()
            parked_health_check()

        with fake_stackdump_clock(clock):
            wd = self.watchdog(health)
            self.assertTrue(entered.wait(5.0))
            self.assertTrue(wait_for(lambda: PARK_LOCK.locked()))
            clock.advance(0.4)  # past the 0.3 fake threshold
            found = wait_for(
                lambda: "parked_health_check" in dump_text(self.path)
                and wd.last_dump_at is not None)
            self.assertTrue(found)
            # The dump landed while the health path is still
            # parked and still holding its lock: the watcher
            # never blocked on either.
            self.assertFalse(PARK_RELEASE.is_set())
            self.assertTrue(PARK_LOCK.locked())
            text = dump_text(self.path)
            self.assertIn("=== stackdump", text)
            self.assertIn("server=test-server", text)
            self.assertIn("contract=v1", text)
            self.assertIsNotNone(wd.last_dump_at)


class HealthySilenceTest(WatchdogCase):
    def test_healthy_server_produces_no_dump(self):
        wd = self.watchdog(lambda: None)
        time.sleep(1.0)  # ~20 cadences, several thresholds
        self.assertIsNone(wd.last_dump_at)
        self.assertEqual(dump_text(self.path), "")


class SizeCapTest(WatchdogCase):
    def test_size_cap_holds_under_repeated_lag(self):
        # Fake clock, like ParkedDumpTest: each advance fires
        # exactly one dump, and the size is measured with the
        # clock frozen — no dump in flight. On the real clock
        # the old shape slept 1.2 s and sampled the size
        # wherever the dump cycle happened to be: a dump that
        # finds the handle past the cap truncates first and
        # the new dump lands through a buffered flush, so for
        # the whole generation of an over-cap dump the file
        # reads 0 bytes on disk — a sample in that window
        # failed assertGreater(size, 0) even though the cap
        # held (seen in the single-process serial suite, where
        # accumulated threads make every dump over-cap).
        clock = FakeClock()
        with fake_stackdump_clock(clock):
            wd = self.watchdog(parked_health_check,
                               cadence_s=0.02, threshold_s=0.15,
                               repeat_s=0.1, max_bytes=2000)
            self.assertTrue(wait_for(lambda: PARK_LOCK.locked()))
            clock.advance(0.2)  # past the 0.15 fake threshold
            self.assertTrue(wait_for(
                lambda: wd.last_dump_at is not None))
            # One dump in a fresh file, measured quiescent:
            # this is "one dump's bytes" for the bound below,
            # whatever the process's thread count makes it.
            one_dump = os.path.getsize(self.path)
            self.assertGreater(one_dump, 0)
            # Each further advance fires exactly one more
            # dump; the rendezvous is the dump stamp changing
            # (the stamp lands after the flush), never a count
            # of headers in the file — a truncating dump
            # resets the file to one header by design.
            for _ in range(4):
                stamp = wd.last_dump_at
                clock.advance(0.12)  # past the 0.1 fake repeat
                self.assertTrue(wait_for(
                    lambda: wd.last_dump_at != stamp))
            size = os.path.getsize(self.path)
        self.assertGreater(size, 0)
        # Steady state is one dump past the cap: the file
        # may exceed max_bytes by at most one dump's bytes
        # (one_dump measured above, plus a small allowance
        # for header-width variance between dumps).
        self.assertLessEqual(size, 2000 + one_dump + 512)
        self.assertIn("=== stackdump", dump_text(self.path))


class ConfigDefaultsTest(unittest.TestCase):
    def test_contract_defaults_are_the_shipped_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            values, sources = config_mod.resolve(
                path=os.path.join(tmp, "absent.json"), env={})
        self.assertEqual(values["stackdump_cadence_s"], 5.0)
        self.assertEqual(values["stackdump_threshold_s"], 15.0)
        self.assertEqual(values["stackdump_repeat_s"], 60.0)
        self.assertEqual(values["stackdump_max_bytes"],
                         16 * 1024 * 1024)
        self.assertEqual(sources["stackdump_cadence_s"], "default")


class HealthFieldTest(unittest.TestCase):
    def test_health_data_carries_the_last_dump_field(self):
        tmp = tempfile.mkdtemp()
        values, _sources = make_home(tmp)
        engine = Engine(values, now_fn=Clock(T0), inline=True)
        data = engine.health_data()
        self.assertIn("stackdump_last_dump_at", data)
        self.assertIsNone(data["stackdump_last_dump_at"])
        # The engine's watchdog is wired to the state area
        # and to this engine's own health computation.
        self.assertTrue(engine.stackdump._path.endswith(
            os.path.join("state", "stackdumps.log")))
        self.assertEqual(engine.stackdump._health,
                         engine.health_data)


if __name__ == "__main__":
    unittest.main()
