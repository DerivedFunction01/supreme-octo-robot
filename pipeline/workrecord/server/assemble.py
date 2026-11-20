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
- Repo peeks and dataset feeds are pre-computed for the
  tracked and untracked files the tree lists (ignored
  entries — dependency trees, build output, venv
  contents — stay listed but are never peeked: the
  adapter reads peeks optionally and the pinned file
  route serves one on demand), bounded by lib/files'
  own peek caps (an over-cap or withheld file records
  its refusal shape instead of content) — and by an
  eager bound: a
  file over the peek byte cap is stat-gated out of the
  eager pass (its entry records size + the too-large
  verdict, no content read, no dataset assembly) and is
  served on demand by the pinned file / dataset routes
  instead. The assembly fans out over projects, repos,
  and each repo's files on the feed pool (lib.util's
  fan_out, CFG's feed_pool_workers): the per-file peek
  is a full read + sha256, and its git-diff subprocess
  is batched per repo — the status derivation's
  porcelain pass names the staged/unstaged paths, and
  only those files are peeked with a diff (a clean or
  untracked file's diff reads None either way). The
  census runs to hundreds of repos and tens of
  thousands of files, so a serial cold assembly — or
  one paying a subprocess per file — never finishes at
  production scale. A repo whose assembly
  raises degrades to that repo's error entry (five keys
  kept, status null so the adapter falls back to the
  census summary); it never stalls or sinks the whole
  document.
- Repo detail scope: a full repo document (files,
  peeks, datasets, history) assembles for the
  workspace's own repos — a swept project's main
  checkout (census root == project root, the sweep's
  own repo identity) and every other top-level main
  checkout the census finds (not a worktree, not
  nested inside another census repo). A plain
  top-level repo is a surface the Repos browser
  opens: summary-only left it with no tree, no
  dataset, and no saveable file, because the adapter
  builds repo documents from this document alone
  (the leg 7a cure, 2026-11-15). Every remaining
  census repo rides the document as its repos-feed
  summary only, with no repoDetails entry — the
  linked repos' own worktrees (census parent_id)
  and nested discoveries included: a worktree's
  untracked data files are most of the document's
  weight (five edgar-sec worktrees ran 314–345s each
  in one measured assembly and swelled the persisted
  document to ~871 MB, a write the watchdog-killed
  unit never finished), and the adapter tolerates
  the absence (its detail reads are optional-chained
  with summary fallbacks — branch, dirty counts,
  sync label — and its file tree, worktree list, and
  history read empty), while the pinned per-repo
  routes still serve that repo's detail on demand.
  The census runs to hundreds of repos the
  workbench's project surfaces never open; detailing
  all of them is what kept the cold assembly from
  ever finishing even after the per-file costs were
  batched away. One exclusion stands in front of
  both arms of the rule (the detail-scope ruling,
  2026-11-16): a census repo under one of the
  configured scratch roots (config
  repos_detail_scratch_roots — the gate's scratch
  trees, whose pristine per-gate clones are reset
  and discarded) earns no document either, whichever
  arm would have linked it. Scratch trees are the
  gate's working state, not workspace repos: they
  stay in the census and ride as summaries, honestly
  listed, and the per-repo routes serve a scratch
  repo's detail on demand like any other unlinked
  repo. On the census that prompted the ruling, 477
  of the 599 detailed repos were scratch clones
  taking ~91% of the assembly's wall time.
- goals: contract 11's goal-record store (lib/goals)
  serves its records through server/goals; `goalsSource`
  names the store on the document's face, and an empty
  store serves an empty array with the same naming —
  honest absence, never invented records.
- statusVocabulary: contract 06's rows as the merged
  registry carries them (the attention store's attstore
  seed state — the migrated store's backfill source;
  the live store read re-points at S11's cutover).

Caching (the lazy restore, 2026-11-16 — the original
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

Footprint (the OOM cure, 2026-11-16): the service was
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

import gc
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

from lib.plans import parser as plan_parser
from lib.util import fan_out, now_iso
from lib.writes import files as files_mod

from . import armed as armed_mod
from . import config as cfgmod
from . import feedcache
from . import feeds
from . import goals as goals_feed_mod
from . import messages_api
from . import repos_feed
from . import shapestore
from .common import CFG, ApiError, get_sweep

_DATASET_SUFFIXES = {".csv", ".tsv", ".db", ".sqlite",
                     ".sqlite3", ".jsonl", ".parquet"}


def status_vocabulary() -> list:
    """Contract 06's status rows, from the merged
    registry (the attention store's attstore seed state)."""
    from attention.infra import attstore
    return attstore.empty_state()["status_codes"]


def _api_error(e: ApiError) -> dict:
    return {"api_error": e.status, **e.payload}


def _project_document(project) -> dict:
    slug = project.slug
    entries = feeds.entries_feed(project, archived=False)
    entries_archived = feeds.entries_feed(project,
                                          archived=True)
    details = {}
    db = project.manifest.registry
    if db is not None:
        for row in entries.get("entries", []) \
                + entries_archived.get("entries", []):
            try:
                details[row["id"]] = feeds.entry_detail(
                    db, row["id"])
            except Exception as e:  # contained per entry
                details[row["id"]] = {"error": str(e)[:200]}
    plans = feeds.plans_feed(project)
    plan_docs = {}
    if project.manifest.plans is not None:
        # Plan summaries ride both the loose-plans list
        # and each bundle's plan block; documents load
        # for the union (bundle plans are the common case).
        summaries = list(plans.get("plans", []))
        for bundle in plans.get("bundles", []):
            if bundle.get("plan"):
                summaries.append(bundle["plan"])
        for summary in summaries:
            try:
                plan_docs[summary["path"]] = \
                    plan_parser.load_plan(
                        project.manifest.plans,
                        summary["path"])
            except (ValueError, FileNotFoundError) as e:
                plan_docs[summary["path"]] = \
                    {"error": str(e)[:200]}
    try:
        diff = feeds.diff_feed(project, {})
    except ApiError as e:
        diff = _api_error(e)
    return {
        "entries": entries,
        "entriesArchived": entries_archived,
        "entryDetails": details,
        "plans": plans,
        "planDocs": plan_docs,
        "todos": feeds.todos_feed(project),
        "classification": feeds.classification_feed(project),
        "board": feeds.board_project_feed(project),
        "worktrees": feeds.worktrees_feed(project),
        "diff": diff,
    }


def _deferred_peek(path: str, size: int) -> dict:
    """The eager entry for a file over the peek byte
    cap: the fields the adapter reads (size, the
    too-large editability verdict), no content — the
    pinned file route serves the real peek on demand.
    Mirrors the over-cap peek's own verdict: a file
    that size is never editable through the caps."""
    return {"path": path, "size_bytes": size,
            "content": None, "sha256": None,
            "editable": False,
            "editable_reason": "too large",
            "deferred": True}


def _file_payloads(record, entry, with_diff=True) -> tuple:
    """One file's (path, peek, dataset-or-None, size)
    for the eager pass, contained per file: a peek
    failure records its error shape and never sinks
    the repo, let alone the document. with_diff is the
    caller's per-repo batching verdict (see
    _repo_document): False peeks without repo_peek's
    git-diff subprocess, recording the no-diff value a
    clean file carries. The size rides along for the
    caller's payload budget (the deferred form a
    past-budget file takes needs it)."""
    from evaluation import datasets as datasets_mod

    path = entry["path"]
    root = Path(record["root"])
    try:
        size = (root / path).stat().st_size
    except OSError:
        size = None
    if size is not None \
            and size > files_mod.PEEK_MAX_BYTES:
        return (path, _deferred_peek(path, size), None,
                size)
    try:
        peek = files_mod.repo_peek(
            record["root"], path,
            editing_enabled=CFG["file_editing_enabled"],
            with_diff=with_diff)
    except files_mod.FileError_ as e:
        peek = {"error": str(e), "status": e.status}
    except Exception as e:  # contained per file
        peek = {"error": str(e)[:200], "status": 500}
    dataset = None
    if Path(path).suffix.lower() in _DATASET_SUFFIXES:
        try:
            dataset = {
                "schema": datasets_mod.dataset_schema(
                    record["root"], path),
                "rows": datasets_mod.dataset_rows(
                    record["root"], path),
                "stats": datasets_mod.dataset_stats(
                    record["root"], path),
            }
        except Exception:
            # Not a dataset this module reads — the
            # schema feed stays on-demand for it.
            pass
    return (path, peek, dataset, size)


def _repo_document(record) -> dict:
    from evaluation import repo_state as repo_state_mod
    from evaluation import repos as repos_mod

    files = repos_mod.repo_files(record, include_all=True)
    entries = [e for e in files.get("entries", [])
               if e.get("path")
               and e.get("kind") != "folder"]
    # The eager payload pass covers tracked and
    # untracked files only. Ignored entries (dependency
    # trees, build output, venv contents) stay in the
    # files block's listing exactly as repo_files
    # served them, but earn no peek or dataset entry:
    # the adapter reads peeks optionally (an absent
    # peek renders the placeholder on open, and the
    # pinned file route serves the real peek on
    # demand), and peeking tens of thousands of
    # ignored files was the cold assembly's long tail.
    peek_entries = [e for e in entries
                    if e.get("kind") in ("tracked",
                                         "untracked")]
    # The status derivation runs first because it doubles
    # as the eager pass's dirty set: its porcelain pass
    # names the staged and unstaged paths, and those are
    # exactly the files whose diff against HEAD can be
    # non-empty — so only they pay repo_peek's per-file
    # git-diff subprocess. Every other file is clean or
    # untracked, and both read as no diff in _repo_diff,
    # so its peek is taken with_diff=False and records
    # the same None. A status that comes back degraded
    # (error) names no paths; the fallback is the old
    # behaviour — every file pays — so such a repo's
    # document stays faithful whatever made it degrade.
    status = repos_feed.repo_status_feed(record)
    if status.get("error"):
        dirty = {e["path"] for e in peek_entries}
    else:
        dirty = set()
        for group in ("staged", "unstaged"):
            dirty.update(row["path"]
                         for row in status.get(group, []))
    payloads = fan_out(
        lambda e: _file_payloads(
            record, e, with_diff=e["path"] in dirty),
        peek_entries, workers=CFG["feed_pool_workers"])
    # The per-repo payload budget (config
    # feeds_repo_document_payload_max_bytes): the
    # per-file caps have no aggregate, so a
    # corpus-shaped repo — thousands of capped files —
    # outweighs the rest of the document by itself.
    # Payloads are spent in entry order; once the
    # running total reaches the budget, a file's peek
    # takes the deferred form and its dataset is
    # omitted — the listing stays whole and the pinned
    # file/dataset routes serve the real content on
    # demand, the same honest absence as an over-cap
    # single file. Error peeks carry no content and
    # stay as they are: their news is the error.
    budget = CFG["feeds_repo_document_payload_max_bytes"]
    spent = 0
    peeks = {}
    datasets = {}
    for path, peek, dataset, size in payloads:
        if spent >= budget:
            if peek.get("content") is not None:
                peek = _deferred_peek(
                    path,
                    size if size is not None
                    else peek.get("size_bytes") or 0)
            dataset = None
        else:
            spent += len(json.dumps(
                peek, ensure_ascii=False).encode("utf-8"))
            if dataset is not None:
                spent += len(json.dumps(
                    dataset,
                    ensure_ascii=False).encode("utf-8"))
        peeks[path] = peek
        if dataset is not None:
            datasets[path] = dataset
    return {
        "status": status,
        "files": files,
        "history": repo_state_mod.history_for(
            repos_feed._repos_history_path(), record["id"]),
        "peeks": peeks,
        "datasets": datasets,
    }


def _repo_error_document(error: Exception) -> dict:
    """A repo whose assembly raised, in the detail
    shape: the five keys stay, status is null (the
    adapter falls back to the census summary's branch
    and dirty counts), and `error` names the failure —
    the census summary's own error idiom, one level
    down."""
    return {
        "status": None,
        "files": {"entries": [], "tracked": [],
                  "untracked": []},
        "history": {"records": []},
        "peeks": {},
        "datasets": {},
        "error": str(error)[:200],
    }


def _linked_repo_ids(sweep, census) -> set:
    """The census ids that earn a full repo document
    (see the scope note at the top of this module):
    the workspace's own repos — a swept project's
    main checkout (the census record whose root is
    the project root, the sweep's own repo identity;
    lib/discovery/sweep: project identity is the
    repo, registered at its main checkout) and every
    other top-level main checkout: not a worktree
    (parent_id set) and not nested inside another
    census repo's root. A plain top-level repo earns
    one because the Repos browser opens it and the
    adapter builds repo documents from this document
    alone — summary-only left it unbrowsable (the
    leg 7a cure). Worktrees and nested discoveries
    do NOT earn one: they ride the repos-feed
    summary, and the pinned per-repo routes serve
    their detail on demand. A project's folded
    also_at copies are NOT linked either: the sweep
    registers the project at its canonical root only,
    and an export copy is not a surface the adapter
    opens as the project. Roots compare resolved, so
    a symlinked or relative spelling of the same
    checkout still matches. One exclusion stands in
    front of both arms: a repo under a configured
    scratch root (see _scratch_root_paths) earns no
    document — scratch trees are the gate's working
    state, not workspace repos, whichever arm would
    have linked them."""
    project_roots = {str(Path(p.root).resolve())
                     for p in sweep.projects}
    roots = {rid: str(Path(record["root"]).resolve())
             for rid, record in census.items()}
    scratch = _scratch_root_paths()

    def _nested(rid):
        root = roots[rid]
        return any(other != rid
                   and root.startswith(other_root + "/")
                   for other, other_root in roots.items())

    def _under_scratch(rid):
        root = roots[rid]
        return any(root == s or root.startswith(s + "/")
                   for s in scratch)

    linked = set()
    for rid, record in census.items():
        if _under_scratch(rid):
            continue
        if roots[rid] in project_roots:
            linked.add(rid)
        elif not record.get("parent_id") \
                and not _nested(rid):
            linked.add(rid)
    return linked


def _scratch_root_paths() -> list:
    """The resolved scratch roots the detail scope
    excludes (config repos_detail_scratch_roots):
    the gate's scratch trees, named as configuration
    — workspace-relative entries resolve against
    workspace_root, absolute entries stand as
    written — so the exclusion is path knowledge in
    one place, never a name pattern in the scope
    derivation. An empty config restores the full
    top-level scope."""
    base = Path(CFG["workspace_root"])
    resolved = []
    for entry in CFG.get("repos_detail_scratch_roots") \
            or []:
        path = Path(entry)
        if not path.is_absolute():
            path = base / path
        resolved.append(str(path.resolve()))
    return resolved


def _projects_document(sweep) -> dict:
    """The sweep summary's shape, plus each project's
    manifest block: the pinned HTTP surface never served
    the manifest contents (the summary carries sections
    only), but the adapter's Project shape reads them —
    they ride the document from the in-process Manifest
    object, declared strings as written (WR3)."""
    rows = []
    by_slug = {p.slug: p for p in sweep.projects}
    for row in sweep.summary()["projects"]:
        project = by_slug[row["slug"]]
        manifest = None
        m = project.manifest
        if m is not None:
            declared = m.declared or {}
            def _path(key, value):
                if value is None:
                    return None
                return declared.get(key) or str(value)
            catalog = m.catalog or {}
            manifest = {
                "registry": _path("registry", m.registry),
                "plans": _path("plans", m.plans),
                "mockups": _path("mockups", m.mockups),
                "archive": _path("archive", m.archive),
                "catalog": {
                    "origin": catalog.get("origin"),
                    "generality": catalog.get("generality"),
                    "use_case": catalog.get("use_case"),
                } if catalog else None,
            }
        rows.append({**row, "manifest": manifest})
    return {"projects": rows, "errors": sweep.errors}


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


class _AssemblyTimer:
    """Section timings for one assembly, printed to
    stderr as each section closes (`workbench-viewer:
    feeds assembly: <section> took <n>s`, plus a total
    line). The server log is where a slow assembly
    gets diagnosed: the cold assembly's cost was
    estimated blind through three cure rounds, so the
    sections are measured where they run, permanently
    (see the timing note at the top of this module)."""

    def __init__(self):
        self._started = time.monotonic()
        self._last = self._started

    def section(self, name: str) -> None:
        now = time.monotonic()
        print(f"workbench-viewer: feeds assembly: "
              f"{name} took {now - self._last:.2f}s",
              file=sys.stderr)
        self._last = now

    def total(self) -> None:
        print(f"workbench-viewer: feeds assembly: "
              f"total "
              f"{time.monotonic() - self._started:.2f}s",
              file=sys.stderr)


def _persisted_document_path() -> Path:
    """Where the last successful assembly persists:
    the config seam's feeds_document_file, in the
    state dir (runtime state — gitignored with the
    rest of state/, regenerable by the next assembly).
    """
    return cfgmod.feeds_document_path(CFG)


def feeds_payload_bytes() -> bytes | None:
    """The serialized feeds document the route serves:
    the store's payload, or None when nothing has been
    computed or primed yet in this process (the route
    then falls back to build_feeds(), the cold path).
    The bytes are a complete response body — the route
    returns them verbatim, with no serialization and
    no recompute on the request path."""
    return _document_store.payload_bytes()


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


def _store_payload(payload: bytes) -> None:
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
    _document_store.store_payload(payload)


def invalidate_payload() -> None:
    """Drop the store's document and payload (the
    refresh endpoint's bust, beside
    feedcache.invalidate_all — the store is registered
    there too, so either call clears it): the next
    /api/feeds read finds no payload and falls back to
    build_feeds(), re-deriving exactly as a busted
    cache read does — the escape hatch keeps its
    meaning."""
    _document_store.invalidate_all()


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


def prime_document_cache() -> bool:
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
    one primes nothing too (the prime guard,
    2026-11-16): the parse transient runs ~6x the
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
    primed = _prime_document_from_store()
    if primed is not None:
        return primed
    return _prime_document_from_file()


def _prime_document_from_store():
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
    _document_store.prime(document, row["payload"])
    # The parse's transient strands its arenas here,
    # as the file prime's does (see its note).
    _reclaim()
    return True


def _prime_document_from_file() -> bool:
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
    _document_store.prime(document, raw.encode("utf-8"))
    # The parse's transient (the raw text plus the
    # parser's intermediates over a ~190 MB live
    # document) strands its arenas here; return them
    # before the first assembly starts from the debris.
    _reclaim()
    return True


def _build_feeds_compute() -> dict:
    """The assembly itself: every payload, built once
    over the configured stores. Each section times
    itself to stderr as it closes (see _AssemblyTimer),
    and a successful assembly persists itself for the
    next process's prime (see _persist_document) and
    stores its one serialization in the document
    store (see _store_payload). The census comes from
    the repos feed's shared cached census
    (repos_feed._census_cached): the assembly reads
    the same enumeration every other consumer reads,
    refreshed on the census cache's own TTL — the
    assembly no longer walks the workspace itself."""
    timer = _AssemblyTimer()
    sweep = get_sweep()
    projects = dict(fan_out(
        lambda p: (p.slug, _project_document(p)),
        sweep.projects,
        workers=CFG["feed_pool_workers"]))
    projects_doc = _projects_document(sweep)
    timer.section("sweep + project documents")
    repos = repos_feed.repos_feed()
    timer.section("repos summary")
    census = repos_feed._census_cached()
    linked = _linked_repo_ids(sweep, census)

    def _detail_pair(summary):
        record = census.get(summary["id"])
        if record is None \
                or summary["id"] not in linked:
            # Not a project-linked repo: the summary
            # above is its whole document presence (see
            # the scope note at the top of this module).
            return None
        started = time.monotonic()
        try:
            pair = (summary["id"],
                    _repo_document(record))
        except Exception as e:  # contained per repo
            pair = (summary["id"],
                    _repo_error_document(e))
        print(f"workbench-viewer: feeds assembly: "
              f"repo document {summary['id']} took "
              f"{time.monotonic() - started:.2f}s",
              file=sys.stderr)
        return pair

    repo_details = dict(
        pair for pair in fan_out(
            _detail_pair, repos.get("repos", []),
            workers=CFG["feed_pool_workers"])
        if pair is not None)
    timer.section("repo documents")
    # The fan-out's per-repo intermediates (file
    # listings, payload tuples, census records) are
    # dead here; return their arenas before the
    # remaining sections build on top of them.
    _reclaim()
    home = feeds.home_feed()
    timer.section("home")
    messages = messages_api.messages_list({})
    timer.section("messages")
    outbox = messages_api.outbox_feed({})
    timer.section("outbox")
    settings = messages_api.effective_settings()
    vocabulary = status_vocabulary()
    armed = armed_mod.armed_feed()
    timer.section("armed")
    goals_block = goals_feed_mod.goals_feed()
    timer.section("goals")
    document = {
        "config": {
            "config": CFG,
            "config_hash": cfgmod.config_hash(CFG),
            "config_file": str(cfgmod.config_path()),
        },
        "home": home,
        "projects": projects_doc,
        "projectFeeds": projects,
        "repos": repos,
        "repoDetails": repo_details,
        "messages": messages,
        "outbox": outbox,
        "settings": settings,
        "armedRows": armed["rows"],
        "armedSkipped": armed["skipped"],
        "statusVocabulary": vocabulary,
        "goals": goals_block["goals"],
        "goalsSource": goals_block["goalsSource"],
    }
    timer.total()
    # One serialization, to bytes: the holder stores
    # these bytes and the persist writes them — the
    # dumps string dies with the encode, and no second
    # encoded copy stands beside the first at the
    # peak (see the footprint note at the top).
    payload = json.dumps(
        document, ensure_ascii=False).encode("utf-8")
    _store_payload(payload)
    _persist_document(payload)
    _reclaim()
    return document
