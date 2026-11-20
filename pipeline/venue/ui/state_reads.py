"""Stale-while-recompute reads for the lease panel's state
path (the workbench prime discipline, applied to the
panel's own hot read).

The panel's state reads shell out to bin/colab-lease,
whose state build walks every lease record and live
session; under load a build takes seconds, and a wedged
core takes as long as the caller's timeout. Served
synchronously per request (the pre-split shape), each
poll pinned its request thread for the build's whole
duration, and the page's parallel part polls piled
unbounded threads onto a slow core.

This cache is the fix, in the shape the workbench's
feeds document established: the last successful build is
served immediately, a refresh recomputes behind it
(single-flight per key), and a never-built key computes
off the request path — once, single-flighted across
concurrent cold readers of the same key, on a background
thread the readers wait on only up to the cold-wait
bound. The bound governs the reader's wait, never the
build's life: a build slower than the wait still runs
to completion and warms the cache for the next read
(2026-11-15: a build slower than the compute's own
subprocess bound was killed at the bound on every read,
so a restarted panel under account load could never
warm a key and its state routes 502'd permanently).
A failed refresh keeps serving the last good build; a
failed cold compute caches nothing, so the next read
retries the core and the route answers its own 502
form, exactly as the uncached read did.

Keys are the core call's argument tuples — ("state",)
for the full document, ("state", "--part", part) per
portion — so each portion caches, stales, and refreshes
independently, mirroring the routes' portions-fail-alone
contract. The compute callable is injected: this module
owns the caching discipline, never the core call itself.
"""

import threading
import time


class StateReads:
    """A per-key stale-while-recompute cache over an
    injected compute() -> (rc, result, err). Only
    successful builds (a dict result, the core call's own
    success shape) are stored; failures are returned to
    the caller that computed them and never cached.

    An optional persister (load_all / save, the shape
    store's adapter) carries the stored builds across a
    process restart: landings save behind the cache, and
    construction primes from what the persister holds —
    primed builds born refresh-eligible, so a restart
    serves the last good build at once and recomputes
    behind it, never serving persisted state as fresh."""

    def __init__(self, compute, refresh_after_s: float,
                 cold_wait_s: float = 30.0,
                 clock=time.monotonic, persister=None):
        self._compute = compute
        self._refresh_after_s = refresh_after_s
        self._cold_wait_s = cold_wait_s
        self._clock = clock
        self._persister = persister
        self._lock = threading.Lock()
        self._entries: dict = {}
        self._refreshing: set = set()
        self._cold_in_flight: dict = {}
        if persister is not None:
            self._prime(persister)

    def _prime(self, persister) -> None:
        """Seed the cache from the persisted builds (the
        panel-restart path, 2026-11-17): a persisted build
        is the last successful build the previous process
        landed, so it enters exactly as a stored build
        does — except born refresh-eligible, its stamp set
        past the refresh cadence, so the first read serves
        it AND kicks the recompute behind it in the same
        motion. Liveness keeps its semantics mechanically:
        nothing primed is ever served as fresh. A
        persister that cannot load primes nothing, which
        is today's cold behaviour."""
        try:
            held = persister.load_all()
        except Exception:
            return
        stamp = self._clock() - self._refresh_after_s - 1.0
        for key, (rc, result, err) in held.items():
            if isinstance(result, dict):
                self._entries[key] = (rc, result, err, stamp)

    def read(self, key) -> tuple[int, dict | None, str]:
        """The (rc, result, err) for one state read: the
        cached build when one exists (served at once; a
        background refresh is kicked when the build is
        older than the refresh cadence and none is in
        flight), otherwise the key's single-flighted
        cold compute — waited on up to the cold-wait
        bound, never killed at it."""
        entry = self._entry(key)
        if entry is not None:
            self._kick(key, entry)
            return entry[0], entry[1], entry[2]
        return self._cold_read(key)

    def _cold_read(self, key) -> tuple[int, dict | None, str]:
        """Join the key's cold compute (starting it when
        this reader is first): serve the build when it
        lands inside the wait; past the wait, answer the
        failure form while the compute runs on — its
        landing still warms the cache, so the wedge a
        slow build used to cause (every read re-running
        a compute its own bound killed) cannot form."""
        with self._lock:
            event = self._cold_in_flight.get(key)
            if event is None:
                event = threading.Event()
                self._cold_in_flight[key] = event
                starter = True
            else:
                starter = False
        if starter:
            thread = threading.Thread(
                target=self._cold_compute, args=(key, event),
                name="venue-state-cold", daemon=True)
            thread.start()
        event.wait(self._cold_wait_s)
        entry = self._entry(key)
        if entry is not None:
            return entry[0], entry[1], entry[2]
        return 1, None, "state build has not landed yet " \
            "(cold compute in flight or failed; the " \
            "next read retries or serves its landing)"

    def _cold_compute(self, key, event) -> None:
        """One cold build, off the request path. A dict
        result stores exactly as a refresh landing does;
        a failure caches nothing. The in-flight marker
        always clears and the event always sets, so
        waiters wake and a later read can retry."""
        try:
            rc, result, err = self._compute(key)
            if isinstance(result, dict):
                self._store(key, rc, result, err)
        except Exception:
            pass
        finally:
            with self._lock:
                self._cold_in_flight.pop(key, None)
            event.set()

    def _entry(self, key):
        with self._lock:
            return self._entries.get(key)

    def _store(self, key, rc, result, err) -> None:
        with self._lock:
            self._entries[key] = (rc, result, err,
                                  self._clock())
        if self._persister is not None:
            # The landing persists behind the cache: a
            # failed persist loses only the restart
            # priming for this build, never the build.
            try:
                self._persister.save(key, rc, result, err)
            except Exception:
                pass

    def _kick(self, key, entry) -> None:
        with self._lock:
            if key in self._refreshing:
                return
            if self._clock() - entry[3] \
                    < self._refresh_after_s:
                return
            self._refreshing.add(key)
        thread = threading.Thread(
            target=self._refresh, args=(key,),
            name="venue-state-refresh", daemon=True)
        thread.start()

    def _refresh(self, key) -> None:
        """One background recompute. Contained: a failed
        or raising compute keeps the last good build and
        never surfaces in a read; the key always leaves
        the in-flight set, so a later read can kick
        again."""
        try:
            rc, result, err = self._compute(key)
            if isinstance(result, dict):
                self._store(key, rc, result, err)
        except Exception:
            pass
        finally:
            with self._lock:
                self._refreshing.discard(key)
