"""The feeds document: every served payload, assembled
once, in the pinned routes' shapes.

The workbench app's live adapter consumes this document
(plan §8, stage D3): one key per route family, each value
exactly what the pinned route serves for the same stores
— the S8 served-payload diff runs over these producers
against the pinned server's, route by route. A serving
process (S11) can serve the routes directly from the
same builders; the document is the stage form, not a
second shape.

Per-surface notes:
- /api/health is not here: it is process identity
  (uptime, commit, stackdump state) — the serving
  process's own surface, not app data.
- Projects index (SPEC §21): the document
  carries the unified project index (projects_feed —
  adopted and repository-only projects, code summaries
  on the rows) and NO repo detail. The retired
  repoDetails assembly (eager per-repo files, peeks,
  and datasets for a scoped subset of the census) is
  deleted wholesale: Code detail is served on demand
  by the project-scoped Code routes, which is both
  the consolidation's shape and the end of the cold
  assembly's long tail — the census runs to hundreds
  of repos, and detailing any of them eagerly was
  what kept the assembly from finishing at production
  scale (the detail-scope history: W4 project-linked
  only, the leg 7a extension to top-level
  repos, the scratch exclusion — all of it
  superseded by on-demand serving).
- goals: contract 11's goal-record store (lib/goals)
  serves its records through server/goals; `goalsSource`
  names the store on the document's face, and an empty
  store serves an empty array with the same naming —
  honest absence, never invented records.
- statusVocabulary: contract 06's rows as the merged
  registry carries them (the attention store's attstore
  seed state — the migrated store's backfill source;
  the live store read re-points at S11's cutover).

Caching (the lazy restore — the original
workbench-viewer's shape, per the owner's ruling that
continuous enumeration was the divergence): the
assembled document serves from a TTL cache
(_DocumentStore, below) under the stale-while-
recompute idiom the per-feed caches in feeds.py use.
Within config feeds_document_ttl_s of the last
assembly the cached document serves as-is; past the
TTL a read serves the stale document while ONE
background thread reassembles; only a never-filled
store assembles on the caller's path (serving warms
it at startup, off the request path). Freshness is
the TTL bound, full stop: no process computes
anything about the document between reads, and a
store write moves the served document at the next
post-TTL read, not before. POST /api/refresh busts
the store with every other keyed cache
(feedcache.invalidate_all) and stays the manual
escape, as it is for the other feeds.

What this replaced, and why: freshness used to be a
continuous keeper thread polling a content
fingerprint (the combined project fingerprint folded
with stat rows over every non-project input,
including each census repo's git state). The
fingerprint cost seconds-to-minutes per pricing, and
it could never read quiet after an assembly — the
assembly cycle's own repos pass rewrites the repos
registry (reconcile refreshes every entry's
last_seen, so the fold is changed by the clock alone)
and appends history records, both of them fingerprint
inputs, so every cycle's comparison found the signal
"moved" and reassembled again: ~85% assembly duty at
idle, ~20% of a core with no requests at all (the
serve burn; the 600s-cooldown cure capped the rate
without touching the mechanism). The TTL store has
no signal to chase and no thread to chase it.

Persistence (the cross-restart prime): every
successful assembly also persists itself — the
payload bytes, the assembly instant, and the
payload's own hash as its source fingerprint — into
the shapes database (server/shapestore; the state
dir's shapes_store_file), and prime_document_cache()
at startup stores the persisted document in the
store marked stale, so a restart's first read serves
the last assembly while a reassembly runs behind it:
after the first successful assembly, the cold one
never sits on a request path again. A persist failure is contained (logged, never
raised); only the next restart's prime is lost. The
prime reads the database row first; the pre-database
persist (the feeds_document_file JSON, written by
the staged writer) stands as a one-transition
fallback — a state dir whose last assembly predates
the database primes from the file, and the first
assembly under the database writes the row every
later restart reads. The prime refuses a persisted
document above the
configured size bound, from either source (see prime_document_cache):
an oversized persist is a symptom the assembly's
persist log already records, and the guard's whole
job is that it can never again make restarts
un-survivable.

Serving payload (the request path's form of the same
contract): the route neither serializes nor
recomputes per request. The store keeps the
assembly's serialized payload beside the document
(the very serialization the persist writes), the
prime stores the persisted text as-is, and
GET /api/feeds serves the stored bytes verbatim. The
route's one freshness act is the lazy kick
(kick_document_refresh): when the stored document is
past its TTL, the read that notices spawns the one
background reassembly and still serves the stale
bytes — a reader never waits on an assembly after
the startup warm, and a serve nobody reads does no
assembly work at all. The payload is written only by
the two paths that put a document into the store
(the compute and the prime), so its bytes always
serialize the document the store most recently
accepted.

Timing: the assembly logs its sections to stderr as
they close (sweep + project documents, repos summary,
repo documents with a line per linked repo, home,
messages, outbox, armed, goals, and the total). The
cold assembly's cost was estimated blind through
three cure rounds without ever finishing at
production scale; the sections are measured where
they run, permanently, so the next diagnosis reads
the server log instead of guessing.

Footprint (the OOM cure): the service was
OOM-killed in a pattern (kills at 08:21Z and 08:49Z,
each mid-refresh-cycle) — the assembly's peak is two
document generations by contract (the stale document
serves from the cache while its successor builds),
and everything beyond those two generations is waste
the cure removes: the document is serialized ONCE,
to bytes, and the serving holder and the persist
share that one form (the persist and the payload
fingerprint previously re-encoded the string twice
more at the peak moment), and the allocator's freed
arenas are returned to the OS at the assembly's
boundaries (_reclaim) instead of ratcheting the
process's RSS across refresh cycles — the prime's
parse alone strands ~80 MB of arenas behind a
~190 MB live document. The document's shape and the
cache's contract are untouched: this is footprint,
not format.
"""

# The implementation is split by seam — documents (the
# status vocabulary and the per-project documents),
# store (the TTL document store), persist (the serving
# payload, the cross-restart persist, and the prime),
# and compute (the one assembly pass) — and this
# package re-exports the whole surface, so existing
# imports of server.assemble are unchanged. The store
# singleton and the glue functions live here, resolving
# the package globals at call time exactly as the flat
# module did (the document suites rebind
# _document_store / _build_feeds_compute on the
# package).

import gc
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

from lib.plans import parser as plan_parser
from lib.util import fan_out, now_iso

from .. import armed as armed_mod
from .. import config as cfgmod
from .. import feedcache
from .. import feeds
from .. import goals as goals_feed_mod
from .. import messages_api
from .. import shapestore
from ..common import CFG, ApiError, get_sweep

from . import compute as _compute
from . import persist as _persist
from .compute import _AssemblyTimer  # noqa: F401
from .documents import (  # noqa: F401
    _api_error,
    _project_document,
    _projects_document,
    status_vocabulary,
)
from .persist import (  # noqa: F401
    _persist_document,
    _persisted_document_path,
    _reclaim,
)
from .store import _DocumentStore, _spawn_background  # noqa: F401

_document_store = _DocumentStore()


def build_feeds() -> dict:
    """The whole document over the configured stores,
    served from the TTL document store (see the
    caching note at the top of this module): fresh
    within the TTL, stale with one reassembly running
    behind it past the TTL, computed on the caller's
    thread only when the store has never filled."""
    return _document_store.get(
        lambda: _build_feeds_compute())


def kick_document_refresh() -> None:
    """The /api/feeds route's lazy trigger (see the
    serving-payload note at the top of this module):
    when the stored document is past its TTL, kick the
    one background reassembly. The route calls this on
    every read; it costs a lock and a clock read, and
    the read still serves the stored bytes."""
    _document_store.kick(lambda: _build_feeds_compute())


def _build_feeds_compute() -> dict:
    return _compute.build_feeds_compute(_document_store)


def feeds_payload_bytes() -> bytes | None:
    return _persist.feeds_payload_bytes(_document_store)


def invalidate_payload() -> None:
    _persist.invalidate_payload(_document_store)


def _store_payload(payload: bytes) -> None:
    _persist._store_payload(_document_store, payload)


def prime_document_cache() -> bool:
    return _persist.prime_document_cache(_document_store)


def _prime_document_from_store():
    return _persist._prime_document_from_store(_document_store)


def _prime_document_from_file() -> bool:
    return _persist._prime_document_from_file(_document_store)
