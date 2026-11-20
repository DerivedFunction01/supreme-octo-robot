"""Keyed stale-while-revalidate feed cache
(cache-refresh plan, 2026-11-05).

The feeds.py idiom (home/repos TTL caches), generalized
from wall-clock to content: each entry is stored under a
key WITH the fingerprint it was computed from. A read
whose fingerprint matches serves the entry as-is; a
mismatch serves the stale entry while ONE background
thread per key recomputes; only a never-filled key
computes on the request path (single-flighted per key).
invalidate_all() clears every registered cache and bumps
its generation, so a payload computed across an
invalidation is never stored. Instances register
themselves on construction; the module-level
invalidate_all() is the refresh endpoint's one call.

prime() is the cross-restart form of the same contract:
a payload a previous process persisted enters the cache
under a sentinel fingerprint no real fingerprint can
equal, so it always reads as stale — the first get()
serves it as-is and kicks a background refresh, and the
cold compute never sits on the first request after a
restart.
"""

import sys
import threading

_ALL: list = []
_ALL_LOCK = threading.Lock()

_STALE_FINGERPRINT = object()
"""The fingerprint a primed entry carries: an object
no real fingerprint (a content-hash string) can equal,
so a primed entry always takes the stale path in get()
— served as-is while a refresh recomputes behind it."""


def _register(cache) -> None:
    with _ALL_LOCK:
        _ALL.append(cache)


def invalidate_all() -> None:
    """Clear every KeyedFeedCache in the process (the
    POST /api/refresh bust)."""
    with _ALL_LOCK:
        caches = list(_ALL)
    for cache in caches:
        cache.invalidate_all()


class KeyedFeedCache:
    def __init__(self):
        self._entries: dict = {}
        self._refreshing: set = set()
        self._locks: dict = {}
        self._state = threading.Lock()
        self._generation = 0
        _register(self)

    def prime(self, key, result) -> None:
        """Store `result` under `key` as a stale entry
        (see _STALE_FINGERPRINT): the next get() serves
        it through the fingerprint-mismatch path and
        kicks a background refresh — how a payload
        persisted by a previous process enters the
        cache at startup. Priming never displaces a
        live entry: a key the cache already serves
        keeps its computed value."""
        with self._state:
            if key not in self._entries:
                self._entries[key] = {
                    "fp": _STALE_FINGERPRINT,
                    "result": result}

    def _lock_for(self, key) -> threading.Lock:
        with self._state:
            return self._locks.setdefault(
                key, threading.Lock())

    def get(self, key, fingerprint, compute):
        """The payload for `key` at `fingerprint`:
        `compute()` derives it when the cache cannot
        serve it fresh (see the module note)."""
        with self._state:
            entry = self._entries.get(key)
        if entry is not None:
            if entry["fp"] == fingerprint:
                return entry["result"]
            self._kick(key, fingerprint, compute)
            return entry["result"]
        with self._lock_for(key):
            # A racing cold request may have filled the
            # key while this one waited for the lock.
            with self._state:
                entry = self._entries.get(key)
                generation = self._generation
            if entry is not None:
                if entry["fp"] == fingerprint:
                    return entry["result"]
                self._kick(key, fingerprint, compute)
                return entry["result"]
            result = compute()
            with self._state:
                if generation == self._generation:
                    self._entries[key] = {
                        "fp": fingerprint,
                        "result": result}
            return result

    def _kick(self, key, fingerprint, compute) -> None:
        with self._state:
            if key in self._refreshing:
                return
            self._refreshing.add(key)
            generation = self._generation
        threading.Thread(
            target=self._refresh,
            args=(key, fingerprint, compute, generation),
            daemon=True).start()

    def _refresh(self, key, fingerprint, compute,
                 generation) -> None:
        try:
            result = compute()
            with self._state:
                if generation == self._generation:
                    self._entries[key] = {
                        "fp": fingerprint,
                        "result": result}
        except Exception as e:
            # The stale entry keeps serving; the next
            # mismatched read kicks another refresh.
            print(f"workbench-viewer: feed cache refresh "
                  f"failed for {key!r}: {e}",
                  file=sys.stderr)
        finally:
            with self._state:
                self._refreshing.discard(key)

    def invalidate_all(self) -> None:
        with self._state:
            self._generation += 1
            self._entries.clear()
