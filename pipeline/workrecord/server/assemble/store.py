"""The feeds document's TTL store — split from
assemble.py along the store seam; server.assemble
re-exports this surface. The singleton lives in the
package __init__, as it lived in the flat module.
"""

import sys
import threading
import time

from .. import feedcache
from ..common import CFG

def _spawn_background(fn) -> None:
    """The document store's background spawn: a daemon
    thread, named for the stack dumps. The store takes
    it as a seam so the document suites can capture the
    spawned reassembly and run it on the test thread —
    the TTL contract pinned without a real thread."""
    threading.Thread(target=fn, daemon=True,
                     name="workbench-feeds-refresh").start()


class _DocumentStore:
    """The assembled document's TTL store (see the
    caching note at the top of this module): the
    document and its serialized payload under one
    timestamp, served stale-while-recompute in the
    per-feed caches' idiom.

    - fresh (stored younger than config
      feeds_document_ttl_s): get() serves the document
      as-is.
    - stale (older, or primed — a primed entry carries
      no timestamp, so it is stale by construction):
      get() serves the stale document and kicks ONE
      background reassembly; concurrent stale reads
      share it (the refreshing flag is the single
      flight).
    - cold (never filled): get() computes on the
      caller's thread, single-flighted on the compute
      lock, so a burst of cold reads shares one
      assembly.
    - invalidate_all() clears the store under a
      generation bump, so a document computed across
      an invalidation is never stored. The store
      registers itself with feedcache, so the refresh
      endpoint's feedcache.invalidate_all() busts it
      with every keyed cache, exactly as it did when
      the document rode a KeyedFeedCache.

    The clock and the spawn are seams (the document
    suites drive both with fakes — an injected clock,
    a captured spawn), so the TTL contract is pinned
    deterministically: no wall clock, no real thread,
    no quiet-time convergence.
    """

    def __init__(self, clock=None, spawn=None):
        self._clock = clock or time.monotonic
        self._spawn = spawn or _spawn_background
        self._lock = threading.Lock()
        self._compute_lock = threading.Lock()
        self._result = None
        self._payload = None
        self._at = None
        self._refreshing = False
        self._generation = 0
        feedcache._register(self)

    def _fresh(self) -> bool:
        return self._result is not None \
            and self._at is not None \
            and self._clock() - self._at \
            < CFG["feeds_document_ttl_s"]

    def get(self, compute):
        """The document (see the class note): fresh
        from the store, stale with a reassembly kicked
        behind it, or computed on this thread when the
        store has never filled."""
        with self._lock:
            result = self._result
            fresh = self._fresh()
        if result is not None:
            if not fresh:
                self.kick(compute)
            return result
        with self._compute_lock:
            # A racing cold read (or the startup warm)
            # may have filled the store while this one
            # waited for the lock.
            with self._lock:
                result = self._result
                generation = self._generation
            if result is not None:
                return result
            result = compute()
            with self._lock:
                if generation == self._generation:
                    self._result = result
            return result

    def kick(self, compute) -> None:
        """Spawn the one background reassembly when the
        store holds a stale document and none is in
        flight; a no-op otherwise. This is the lazy
        shape's only freshness trigger: the read paths
        call it (build_feeds' stale serve, and the
        /api/feeds route through kick_document_refresh)
        and nothing else in the process ever does."""
        with self._lock:
            if self._result is None or self._fresh() \
                    or self._refreshing:
                return
            self._refreshing = True
            generation = self._generation
        self._spawn(
            lambda: self._refresh(compute, generation))

    def _refresh(self, compute, generation) -> None:
        try:
            result = compute()
            with self._lock:
                if generation == self._generation:
                    self._result = result
        except Exception as e:
            # The stale document keeps serving; the
            # next stale read kicks another reassembly.
            print(f"workbench-viewer: feeds document "
                  f"refresh failed: {e}", file=sys.stderr)
        finally:
            with self._lock:
                self._refreshing = False

    def store_payload(self, payload: bytes) -> None:
        """Record a freshly assembled document's
        serialized payload (the compute's call, through
        _store_payload): the payload and the freshness
        timestamp move together, so the bytes the route
        serves carry the age of the assembly that
        produced them."""
        with self._lock:
            self._payload = payload
            self._at = self._clock()

    def prime(self, document, payload: bytes) -> None:
        """Store a persisted document as a stale entry
        (prime_document_cache's call): the next read
        serves it and kicks the reassembly behind it.
        Priming never displaces a live entry — a part
        the compute already filled keeps its value —
        and the timestamp stays unset, so a primed
        entry is stale however fresh the file was."""
        with self._lock:
            if self._result is None:
                self._result = document
            if self._payload is None:
                self._payload = payload

    def payload_bytes(self):
        """The stored serialized payload, or None when
        nothing has been computed or primed yet."""
        with self._lock:
            return self._payload

    def invalidate_all(self) -> None:
        """Clear the store (feedcache.invalidate_all's
        bust, and invalidate_payload's): the next read
        finds no document and takes the cold path."""
        with self._lock:
            self._generation += 1
            self._result = None
            self._payload = None
            self._at = None


_document_store = _DocumentStore()

