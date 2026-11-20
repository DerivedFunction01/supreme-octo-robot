"""Stack-dump watchdog — `stackdump-contract: v1` (the
starter SPEC's canonical text; this module is the scheduler
server's conformance).

Two daemon threads, started with the server:

- the checker calls the server's own health computation
  directly (never an HTTP self-call) on the configured
  cadence and stamps each success;
- the watcher observes the stamp's age and, past the lag
  threshold, writes one dump of every live Python thread's
  stack (faulthandler form — thread names, frame files,
  line numbers, function names; never locals, never
  payload data) through a dedicated file handle opened at
  startup.

The split is the point: the watcher never calls the health
computation itself, so a health path parked on a lock a
wedged handler holds cannot park the watcher — its work
per cycle is a deadline check plus an in-memory frame read
and one append, taking no lock shared with request
handling. Dumps repeat at most once per repeat interval
while a lag persists, the first dump after a recovery
begins a new event, and the dump file truncates at the
aggregate size cap so a long wedge cannot fill the disk.
Diagnostic only: nothing here restarts, kills, or mutates
anything.
"""
import faulthandler
import os
import threading
import time
from datetime import datetime, timezone

UTC = timezone.utc


class StackDumpWatchdog:
    def __init__(self, name, health, dump_path, cadence_s=5.0,
                 threshold_s=15.0, repeat_s=60.0,
                 max_bytes=16 * 1024 * 1024):
        self._name = name
        self._health = health
        self._path = dump_path
        self._cadence = cadence_s
        self._threshold = threshold_s
        self._repeat = repeat_s
        self._max_bytes = max_bytes
        self._last_ok = time.monotonic()
        self._last_dump = 0.0
        self._in_event = False
        self.last_dump_at = None
        self._handle = None

    def start(self):
        parent = os.path.dirname(os.path.abspath(self._path))
        os.makedirs(parent, exist_ok=True)
        self._handle = open(self._path, "a", encoding="utf-8")
        threading.Thread(target=self._check, daemon=True,
                         name="stackdump-check").start()
        threading.Thread(target=self._watch, daemon=True,
                         name="stackdump-watch").start()

    def _check(self):
        while True:
            try:
                self._health()
            except Exception:
                # A health computation that raises has not
                # answered: no stamp. The checker stays alive
                # so a later success can still stamp.
                pass
            else:
                self._last_ok = time.monotonic()
            time.sleep(self._cadence)

    def _watch(self):
        while True:
            time.sleep(self._cadence)
            lag = time.monotonic() - self._last_ok
            if lag < self._threshold:
                # Recovery: the next lag is a new event whose
                # first dump is not gated by this event's
                # repeat discipline.
                self._in_event = False
                self._last_dump = 0.0
                continue
            now = time.monotonic()
            if now - self._last_dump >= self._repeat:
                self._dump(lag)
                self._last_dump = now
                self._in_event = True

    def _dump(self, lag):
        if self._handle.tell() > self._max_bytes:
            self._handle.seek(0)
            self._handle.truncate()
        stamp = datetime.now(UTC).isoformat()
        self._handle.write(
            f"\n=== stackdump {stamp} server={self._name} "
            f"contract=v1 lag={lag:.1f}s "
            f"heartbeat_age={lag:.1f}s ===\n")
        faulthandler.dump_traceback(file=self._handle)
        self._handle.flush()
        self.last_dump_at = stamp
