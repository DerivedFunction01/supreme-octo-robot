"""Feeds-document persistence: the serving payload, the
cross-restart persist, and the prime — split from
assemble.py along the persistence seam; server.
assemble re-exports this surface. The store is passed
in by the package __init__ (the singleton's owner), so
the package-level store the suites rebind is the one
these functions act on.
"""

import gc
import hashlib
import json
import sys
from pathlib import Path

from lib.util import now_iso

from .. import config as cfgmod
from .. import shapestore
from ..common import CFG

def _persisted_document_path() -> Path:
    """Where the last successful assembly persists:
    the config seam's feeds_document_file, in the
    state dir (runtime state — gitignored with the
    rest of state/, regenerable by the next assembly).
    """
    return cfgmod.feeds_document_path(CFG)


def feeds_payload_bytes(store) -> bytes | None:
    """The serialized feeds document the route serves:
    the store's payload, or None when nothing has been
    computed or primed yet in this process (the route
    then falls back to build_feeds(), the cold path).
    The bytes are a complete response body — the route
    returns them verbatim, with no serialization and
    no recompute on the request path."""
    return store.payload_bytes()


def _reclaim() -> None:
    """Return the assembly's freed memory to the OS
    (see the footprint note at the top of this module):
    a collection, then malloc_trim, so the arenas the
    sections' intermediates died in go back instead of
    stranding as RSS the next cycle's peak starts from.
    Best-effort hygiene, never semantics: any failure
    is silent."""
    try:
        gc.collect()
    except Exception:
        pass
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def _store_payload(store, payload: bytes) -> None:
    """Record a freshly assembled document's serialized
    payload in the store. Called only from
    _build_feeds_compute — one of the two paths that
    put a document into the store — so the payload
    never names a document the store does not hold.
    The caller serializes once, to bytes: the store
    keeps those very bytes (the persist writes the
    same ones), so no second encoded copy of the
    document ever stands beside the first at the
    assembly's peak."""
    store.store_payload(payload)


def invalidate_payload(store) -> None:
    """Drop the store's document and payload (the
    refresh endpoint's bust, beside
    feedcache.invalidate_all — the store is registered
    there too, so either call clears it): the next
    /api/feeds read finds no payload and falls back to
    build_feeds(), re-deriving exactly as a busted
    cache read does — the escape hatch keeps its
    meaning."""
    store.invalidate_all()


def _persist_document(payload: bytes) -> None:
    """Persist a successful assembly's serialized
    payload for the next process's prime, into the
    shapes database (see the persistence note at the
    top of this module): the payload bytes, the
    assembly instant, and the payload's own hash as
    the source fingerprint, one row replaced per
    assembly. The caller serializes once, to bytes,
    and shares them with the serving holder (see
    _store_payload): the database holds the very
    bytes the route serves, and no re-encoding of
    the document stands beside them at the assembly's
    peak. The payload is JSON by construction — it
    is the /api/feeds response body. Contained: a
    persist failure logs and never propagates; the
    document serves from memory regardless, and only
    the next restart's prime is lost. A successful
    persist logs the document's byte size: the size
    is how the worktree-detail weight hid (an ~871 MB
    document whose write the watchdog kept killing),
    so it stays on the record."""
    try:
        shapestore.open_store(CFG).put(
            shapestore.FEEDS_DOCUMENT, payload,
            assembled_at=now_iso(),
            fingerprint=hashlib.sha256(
                payload).hexdigest(),
            stored_at=now_iso())
    except Exception as e:
        print(f"workbench-viewer: feeds document "
              f"persist failed: {e}", file=sys.stderr)
    else:
        print(f"workbench-viewer: feeds document "
              f"persisted: {len(payload)} bytes",
              file=sys.stderr)


def prime_document_cache(store) -> bool:
    """Prime the document cache from the persisted
    document (serving calls this at startup, before
    the warm-up thread). Priming stores the persisted
    document in the store marked stale, so the first
    read serves it as-is while a background
    reassembly runs behind it — the cross-restart
    form of stale-while-revalidate. The persisted
    text enters the store as the serving payload
    as-is, so the first /api/feeds read serves it
    without waiting on either. The shapes database's
    row is the prime's source; the pre-database
    persisted file (feeds_document_file) is the
    fallback for a state dir whose last assembly
    predates the database. A missing source primes
    nothing (the first-ever run has nothing to prime
    from) and a corrupt one logs and primes nothing:
    the cold path stands either way. An OVERSIZED
    one primes nothing too (the prime guard):
    the parse transient runs ~6x the
    payload's size, so a persisted document above
    the configured bound (config
    feeds_document_prime_max_bytes) would kill the
    process before it could assemble the document's
    successor — the refusal is read off the payload's
    length, before a byte of it is parsed, and logs
    the size. An oversized database row refuses
    outright, without falling through to the file:
    the file, where one stands, holds the same
    assembly's bytes class, so the fall-through
    would only re-ask the question the guard
    answered. Returns whether a document was
    primed."""
    primed = _prime_document_from_store(store)
    if primed is not None:
        return primed
    return _prime_document_from_file(store)


def _prime_document_from_store(doc_store):
    """The database arm of the prime: True when the
    shapes database's feeds-document row primed the
    cache, False when the row refused (oversized —
    terminal, per prime_document_cache's note), and
    None when the store holds no usable row (absent,
    unreadable, or unparseable) and the file fallback
    should speak."""
    try:
        store = shapestore.open_store(CFG)
        size = store.payload_size(
            shapestore.FEEDS_DOCUMENT)
    except Exception as e:
        print(f"workbench-viewer: feeds document "
              f"prime: shapes store unreadable ({e}); "
              f"trying the persisted file",
              file=sys.stderr)
        return None
    if size is None:
        return None
    bound = CFG["feeds_document_prime_max_bytes"]
    if size > bound:
        print(f"workbench-viewer: feeds document "
              f"prime refused: persisted document is "
              f"{size} bytes, over the prime bound of "
              f"{bound} bytes; cold assembly stands",
              file=sys.stderr)
        return False
    row = store.get(shapestore.FEEDS_DOCUMENT)
    if row is None:
        return None
    try:
        document = json.loads(
            row["payload"].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        print(f"workbench-viewer: persisted feeds "
              f"document in the shapes store does not "
              f"parse ({e}); trying the persisted "
              f"file", file=sys.stderr)
        return None
    if not isinstance(document, dict):
        print(f"workbench-viewer: persisted feeds "
              f"document in the shapes store is not a "
              f"document; trying the persisted file",
              file=sys.stderr)
        return None
    doc_store.prime(document, row["payload"])
    # The parse's transient strands its arenas here,
    # as the file prime's does (see its note).
    _reclaim()
    return True


def _prime_document_from_file(store) -> bool:
    """The file arm of the prime: the pre-database
    persist (the config seam's feeds_document_file,
    written by the staged writer), kept as the
    one-transition fallback — a state dir whose last
    assembly predates the database primes from the
    file exactly as it always did, guard included.
    The file itself is left in place either way: the
    next successful assembly's persist writes the
    database row, and the file simply stops being
    the freshest source."""
    path = _persisted_document_path()
    try:
        size = path.stat().st_size
    except OSError:
        return False
    bound = CFG["feeds_document_prime_max_bytes"]
    if size > bound:
        print(f"workbench-viewer: feeds document "
              f"prime refused: persisted document is "
              f"{size} bytes, over the prime bound of "
              f"{bound} bytes; cold assembly stands",
              file=sys.stderr)
        return False
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        document = json.loads(raw)
    except ValueError as e:
        print(f"workbench-viewer: persisted feeds "
              f"document at {path} does not parse "
              f"({e}); cold assembly stands",
              file=sys.stderr)
        return False
    if not isinstance(document, dict):
        print(f"workbench-viewer: persisted feeds "
              f"document at {path} is not a document; "
              f"cold assembly stands", file=sys.stderr)
        return False
    store.prime(document, raw.encode("utf-8"))
    # The parse's transient (the raw text plus the
    # parser's intermediates over a ~190 MB live
    # document) strands its arenas here; return them
    # before the first assembly starts from the debris.
    _reclaim()
    return True

