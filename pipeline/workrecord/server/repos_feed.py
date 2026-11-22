"""Repos feed: the cross-repo census and datasets.

One slice of the companion server: the repos feed
derivation behind its TTL cache (background refresh,
write invalidation by generation), the per-repo status
feed, and the dataset console schema/rows/stats feeds.

Target-shape note (S8): the derivations (repos,
repo_state, datasets) were homed in pipeline/evaluation
at S4 and come through the evaluation package; siblings
are relative imports; the package's __init__ owns the
path seams the pinned module inserted for itself.
"""

import hashlib
import json
import os
import stat
import sys
import threading
import time
from pathlib import Path

from . import config as cfgmod  # noqa: E402
from . import shapestore  # noqa: E402
from evaluation import datasets as datasets_mod  # noqa: E402
from lib.writes import files as files_mod  # noqa: E402
from evaluation import repo_state as repo_state_mod  # noqa: E402
from evaluation import repos as repos_mod  # noqa: E402
from lib.util import fan_out, now_iso  # noqa: E402

from .common import CFG, ApiError, get_sweep  # noqa: E402
from lib.derived import projects as projects_mod  # noqa: E402

# ----------------------------------------------------------------
# Repos (absorption plan, steps 2-7): census, status, tree,
# peek/save, registry, history — every derivation in lib/;
# this layer only resolves ids and shapes payloads.
# ----------------------------------------------------------------

def _census(deadline=None) -> dict:
    """id -> census record, freshly walked. Callers
    read the shared cache (_census_cached); this is
    the walk itself, and the cache's refresh."""
    prune = CFG["repos_prune"] or repos_mod.DEFAULT_PRUNE
    records = repos_mod.discover_repos(
        CFG["workspace_root"],
        max_depth=CFG["repos_max_depth"], prune=prune,
        deadline=deadline)
    return {r["id"]: r for r in records}


# ----------------------------------------------------------------
# Census cache (the lazy restore, 2026-11-16)
#
# The walk is the discovery cost: seconds even in its
# fast form, and it used to run fresh inside every
# consumer — the repos feed's compute, the feeds
# assembly, and (the named defect) EVERY per-repo
# route through _repo_or_404, which paid a full
# uncached walk to resolve one id. The cache holds
# the last walked census in the repos feed's own TTL
# idiom (the feed cache below): within repos_ttl_s it
# serves as-is; past the TTL it serves stale while
# ONE background thread re-walks; only a never-filled
# cache walks on the caller's thread, single-flighted
# so a burst of cold reads shares one walk. Discovery
# freshness is the TTL bound: a repo created on disk
# appears at the next refresh past the TTL, and the
# refresh endpoint's repos invalidation does not bust
# the census — a registry curation changes no repo's
# existence.
#
# Persistence (the owner's database ruling,
# 2026-11-17): every walk also persists its census to
# the shapes database (server/shapestore) — the
# record set, the walk instant, and a stat
# fingerprint of the census's own footprint — and
# prime_census_cache() at startup installs the
# persisted census marked stale, so a restart's
# first per-repo resolve serves it while the refresh
# re-walks behind it: the cold walk, like the
# document's cold assembly, never sits on a request
# path after the first successful walk. The refresh
# behind a prime always re-walks — no fingerprint
# skips it. Two probes were priced and neither
# earned the skip: a workspace-wide scandir skeleton
# fingerprint measured SLOWER than the walk itself
# on the real tree (7.9s against the walk's
# 4.2–6.5s, warm, this box), and the footprint
# fingerprint below, though genuinely cheap, covers
# the census's footprint rather than the workspace —
# a repo appearing two levels under a recordless
# directory would pass it unseen, so it is stored on
# the row as the census's change signal, not trusted
# as a freshness gate. Freshness stays the TTL's and
# the walk's word, exactly as before the ruling.
# ----------------------------------------------------------------

_census_cache = {"at": 0.0, "result": None}
_census_state_lock = threading.Lock()
_census_compute_lock = threading.Lock()
_census_refreshing = False


def _census_store(result) -> None:
    with _census_state_lock:
        _census_cache.update(at=time.monotonic(),
                             result=result)
    _persist_census(result)


def _census_fingerprint(result) -> str:
    """A stat fingerprint of a census's own
    footprint: each record's `.git` marker (kind,
    mtime, size by lstat) and each directory that
    directly holds a record (mtime by lstat), hashed
    in sorted order. Priced on the real tree at
    ~0.02s for ~890 records — it stats only what the
    census already found, never walks. Stored on the
    persisted row as the census's change signal; see
    the persistence note above for why it does not
    gate the re-walk."""
    lines = []
    parents = set()
    for repo_id in sorted(result):
        root = result[repo_id]["root"]
        parents.add(str(Path(root).parent))
        try:
            st = os.lstat(Path(root) / ".git")
            kind = ("d" if stat.S_ISDIR(st.st_mode)
                    else "f")
            lines.append(
                f"g {root} {kind} {st.st_mtime_ns} "
                f"{st.st_size}")
        except OSError:
            lines.append(f"g {root} missing")
    for parent in sorted(parents):
        try:
            st = os.lstat(parent)
            lines.append(f"p {parent} {st.st_mtime_ns}")
        except OSError:
            lines.append(f"p {parent} missing")
    return hashlib.sha256(
        "\n".join(lines).encode("utf-8")).hexdigest()


def _persist_census(result) -> None:
    """Persist a walked census to the shapes database
    (see the persistence note above): the record set
    as canonical JSON (records in id order, keys
    sorted — the bytes are a contract the prime
    parses back), the walk instant, and the census's
    footprint fingerprint. Contained exactly as the
    document's persist is: a failure logs and never
    propagates; the census serves from memory
    regardless, and only the next restart's prime is
    lost."""
    try:
        payload = json.dumps(
            [result[k] for k in sorted(result)],
            sort_keys=True,
            ensure_ascii=False).encode("utf-8")
        shapestore.open_store(CFG).put(
            shapestore.CENSUS, payload,
            assembled_at=now_iso(),
            fingerprint=_census_fingerprint(result),
            stored_at=now_iso())
    except Exception as e:
        print(f"workbench-viewer: census persist "
              f"failed: {e}", file=sys.stderr)


def prime_census_cache() -> bool:
    """Prime the census cache from the shapes
    database's persisted census, if one stands and
    parses (serving calls this at startup, beside the
    document prime). The primed census installs
    marked stale — its timestamp backdated past the
    TTL — so the first read serves it while the
    refresh re-walks behind it. Priming never
    displaces a filled cache. A missing or corrupt
    row primes nothing and raises nothing: the cold
    walk stands. Returns whether a census was
    primed."""
    try:
        row = shapestore.open_store(CFG).get(
            shapestore.CENSUS)
    except Exception as e:
        print(f"workbench-viewer: census prime "
              f"failed: {e}", file=sys.stderr)
        return False
    if row is None:
        return False
    try:
        records = json.loads(
            row["payload"].decode("utf-8"))
        census = {r["id"]: r for r in records}
    except Exception as e:
        print(f"workbench-viewer: persisted census "
              f"does not parse ({e}); cold walk stands",
              file=sys.stderr)
        return False
    with _census_state_lock:
        if _census_cache["result"] is not None:
            return False
        _census_cache.update(
            at=time.monotonic() - CFG["repos_ttl_s"] - 1,
            result=census)
    print(f"workbench-viewer: census primed: "
          f"{len(census)} repos, walked at "
          f"{row['assembled_at']}", file=sys.stderr)
    return True


def _census_refresh_background() -> None:
    global _census_refreshing
    try:
        _census_store(_census())
    except Exception as e:
        # The stale census keeps serving; the next
        # stale read kicks another refresh.
        print(f"workbench-viewer: census refresh "
              f"failed: {e}", file=sys.stderr)
    finally:
        with _census_state_lock:
            _census_refreshing = False


def _census_kick_refresh() -> None:
    global _census_refreshing
    with _census_state_lock:
        if _census_refreshing:
            return
        _census_refreshing = True
    threading.Thread(target=_census_refresh_background,
                     daemon=True).start()


def _census_cached() -> dict:
    """id -> census record, from the shared census
    cache (see the cache note above): the one
    enumeration every consumer reads — the repos
    feed's compute, the feeds assembly, and the
    per-repo routes."""
    cached = _census_cache["result"]
    if cached is not None:
        if time.monotonic() - _census_cache["at"] \
                < CFG["repos_ttl_s"]:
            return cached
        _census_kick_refresh()
        return cached
    with _census_compute_lock:
        # The startup warm or a racing read may have
        # filled the cache while this one waited.
        cached = _census_cache["result"]
        if cached is not None:
            return cached
        result = _census()
        _census_store(result)
        return result


def _repo_or_404(repo_id: str) -> dict:
    record = _census_cached().get(repo_id)
    if record is None:
        raise ApiError(404, f"unknown repo: {repo_id}")
    return record


_id_map_cache = {"key": None, "result": None}
_id_map_lock = threading.Lock()


def _id_map() -> dict:
    """census id -> canonical project id (SPEC §21),
    from the sweep and the shared census cache — the
    one identity map every registry/history touch in
    this module folds through. Memoized on (the sweep
    result's identity, the census cache's stored
    timestamp): the derivation Path-resolves every
    census root (~seconds over the real census), and
    neither input can change without one of those two
    moving — a sweep recompute replaces the result
    object, a census refresh re-stores its timestamp —
    so the memoized map is the map a fresh derivation
    would return, until one does."""
    sweep = get_sweep()
    census = _census_cached()
    key = (id(sweep), _census_cache["at"])
    with _id_map_lock:
        if _id_map_cache["key"] == key \
                and _id_map_cache["result"] is not None:
            return _id_map_cache["result"]
        result = projects_mod.identity_map(
            sweep.summary()["projects"],
            list(census.values()))
        _id_map_cache.update(key=key, result=result)
        return result


def _repos_registry_path():
    return cfgmod.state_file(CFG, "repos_registry_file")


def _repos_history_path():
    return cfgmod.state_file(CFG, "repos_history_file")


def _compute_repos_feed() -> dict:
    """The /api/repos derivation itself: every discovered
    repo's summary with its registry entry attached;
    registry entries that discovery did not find ride as
    missing rows. Serves record history, as the reference
    did. Expensive — a git fan-out per repo — so the
    request path goes through the cache below, never
    straight here. The summary pass runs under ONE
    aggregate deadline (lib/repos CENSUS_BUDGET_S): under
    a storage stall, per-call timeouts alone let ~20
    repos × a dozen calls burn minutes in sequence; at
    the deadline the remaining repos degrade to their
    error shape and the payload still lands, with the
    stale payload serving meanwhile (wedge fix,
    2026-11-10). The census itself comes from the
    shared census cache (_census_cached): the walk is
    that cache's to refresh, never this pass's."""
    deadline = time.monotonic() + repos_mod.CENSUS_BUDGET_S
    census = _census_cached()
    data = repo_state_mod.load_registry(_repos_registry_path())
    data, changed = repo_state_mod.reconcile(
        data, list(census.values()),
        healthy_scan=len(census) > 0, now=now_iso())
    # The consolidation fold (SPEC §21): registry and
    # history keys migrate once from census ids to
    # canonical project ids. Reconcile runs first in
    # census-id space (it is discovery's own fold);
    # migration then renames what reconcile settled,
    # and is a no-op once every key is project-keyed.
    sweep = get_sweep()
    id_map = projects_mod.identity_map(
        sweep.summary()["projects"], list(census.values()))
    data, migrated = repo_state_mod.migrate_keys(data, id_map)
    if migrated:
        changed = True
        repo_state_mod.migrate_history_keys(
            _repos_history_path(), id_map)
    if changed:
        repo_state_mod.save_registry(_repos_registry_path(),
                                     data)
    # The summaries are a per-repo git fan-out — computed
    # on the pool (fan_out preserves census order); the
    # registry attach and the history recording stay
    # serial, in the original iteration order.
    records = list(census.values())

    def _summary(record):
        return repos_mod.repo_summary(record,
                                      deadline=deadline)

    computed = fan_out(_summary, records,
                       workers=CFG["feed_pool_workers"])
    summaries = []
    for record, s in zip(records, computed):
        project_id = id_map.get(record["id"], record["id"])
        s["registry"] = data["repos"].get(project_id)
        if not s.get("error"):
            repo_state_mod.record_history(
                _repos_history_path(),
                {**s, "id": project_id})
        summaries.append(s)
    known_project_ids = set(id_map.values())
    for repo_id, entry in data["repos"].items():
        if repo_id not in census \
                and repo_id not in known_project_ids:
            summaries.append({
                "id": repo_id, "name": repo_id,
                "root": entry.get("root"),
                "is_worktree": False, "parent_id": None,
                "missing": True, "error": None,
                "registry": dict(entry)})
    summaries.sort(key=lambda s: s["id"])
    return {"repos": summaries, "captured_at": now_iso()}


# ----------------------------------------------------------------
# Repos feed cache
#
# The derivation fans out git subprocesses per repo and
# costs seconds even warm (measured 7.2 s cold, 1.2 s warm
# over ~20 repos), so the request path serves the last
# computed payload: within repos_ttl_s as-is; past the TTL
# the stale payload while ONE background thread recomputes;
# and only a never-filled cache computes on the request
# path, single-flighted so a burst of cold requests shares
# one derivation. main() warms the cache in a thread at
# startup, so the first open after a restart does not pay
# the cold cost either. Writes that change what the feed
# derives (registry curation, a guarded repo save)
# invalidate the cache — a save must never look unstuck
# for a TTL — and the generation counter keeps a payload
# computed across an invalidation from being stored.
# ----------------------------------------------------------------

_repos_cache = {"at": 0.0, "result": None}
_repos_state_lock = threading.Lock()
_repos_compute_lock = threading.Lock()
_repos_refreshing = False
_repos_generation = 0


def _repos_invalidate_cache() -> None:
    global _repos_generation
    with _repos_state_lock:
        _repos_generation += 1
        _repos_cache.update(at=0.0, result=None)
    _status_invalidate_cache()


def _repos_store(result, generation: int) -> None:
    with _repos_state_lock:
        if generation == _repos_generation:
            _repos_cache.update(at=time.monotonic(),
                                result=result)


def _repos_refresh_background() -> None:
    global _repos_refreshing
    try:
        with _repos_state_lock:
            generation = _repos_generation
        _repos_store(_compute_repos_feed(), generation)
    except Exception as e:
        # The stale payload keeps serving; the next stale
        # request kicks another refresh.
        print(f"workbench-viewer: repos feed refresh "
              f"failed: {e}", file=sys.stderr)
    finally:
        with _repos_state_lock:
            _repos_refreshing = False


def _repos_kick_refresh() -> None:
    global _repos_refreshing
    with _repos_state_lock:
        if _repos_refreshing:
            return
        _repos_refreshing = True
    threading.Thread(target=_repos_refresh_background,
                     daemon=True).start()


def repos_feed() -> dict:
    """GET /api/repos: the cached census payload (see the
    cache note above); captured_at is when the payload was
    computed, not when it was served."""
    cached = _repos_cache["result"]
    if cached is not None:
        if time.monotonic() - _repos_cache["at"] \
                < CFG["repos_ttl_s"]:
            return cached
        _repos_kick_refresh()
        return cached
    with _repos_compute_lock:
        # The startup warm or a racing request may have
        # filled the cache while this one waited.
        cached = _repos_cache["result"]
        if cached is not None:
            return cached
        with _repos_state_lock:
            generation = _repos_generation
        result = _compute_repos_feed()
        _repos_store(result, generation)
        return result


def _compute_repo_status_feed(record) -> dict:
    """One checkout's full status with its project's
    registry entry; the compute records history under
    the canonical project id (SPEC §21). Expensive —
    the full git derivation, fresh — so the request
    path goes through the cache below, never straight
    here."""
    status = repos_mod.repo_status(record)
    data = repo_state_mod.load_registry(_repos_registry_path())
    project_id = _id_map().get(record["id"], record["id"])
    status["registry"] = data["repos"].get(project_id)
    if not status.get("error"):
        repo_state_mod.record_history(
            _repos_history_path(), {**status, "id": project_id})
    return status


# ----------------------------------------------------------------
# Per-checkout status cache
#
# The Code status serve paid the full derivation on
# EVERY request (measured: the status route was the
# slow tail of the projects surface), so the request
# path serves the last computed payload per checkout,
# in the repos feed cache's idiom above: within
# repos_ttl_s as-is; past the TTL the stale payload
# while ONE background thread recomputes that
# checkout; only a never-filled entry computes on the
# request path, single-flighted under the compute
# lock so a burst of cold requests shares one
# derivation. History recording rides the compute,
# exactly as the repos feed's does — a cached serve
# records nothing. Registry saves invalidate through
# _repos_invalidate_cache (which clears this cache
# too), and the generation counter keeps a payload
# computed across an invalidation from being stored.
# ----------------------------------------------------------------

_status_cache = {}
_status_state_lock = threading.Lock()
_status_compute_lock = threading.Lock()
_status_refreshing = set()
_status_generation = 0


def _status_invalidate_cache() -> None:
    global _status_generation
    with _status_state_lock:
        _status_generation += 1
        _status_cache.clear()


def _status_store(record_id, result, generation: int) -> None:
    with _status_state_lock:
        if generation == _status_generation:
            _status_cache[record_id] = {
                "at": time.monotonic(), "result": result}


def _status_refresh_background(record) -> None:
    try:
        with _status_state_lock:
            generation = _status_generation
        _status_store(record["id"],
                      _compute_repo_status_feed(record),
                      generation)
    except Exception as e:
        # The stale payload keeps serving; the next
        # stale request kicks another refresh.
        print(f"workbench-viewer: repo status refresh "
              f"failed: {e}", file=sys.stderr)
    finally:
        with _status_state_lock:
            _status_refreshing.discard(record["id"])


def _status_kick_refresh(record) -> None:
    with _status_state_lock:
        if record["id"] in _status_refreshing:
            return
        _status_refreshing.add(record["id"])
    threading.Thread(target=_status_refresh_background,
                     args=(record,), daemon=True).start()


def repo_status_feed(record) -> dict:
    """GET one checkout's full status: the cached
    payload (see the cache note above); the derivation
    and its history recording happen per compute, not
    per request."""
    record_id = record["id"]
    with _status_state_lock:
        entry = _status_cache.get(record_id)
    if entry is not None:
        if time.monotonic() - entry["at"] \
                < CFG["repos_ttl_s"]:
            return entry["result"]
        _status_kick_refresh(record)
        return entry["result"]
    with _status_compute_lock:
        # A racing request may have filled the entry
        # while this one waited.
        with _status_state_lock:
            entry = _status_cache.get(record_id)
        if entry is not None:
            return entry["result"]
        with _status_state_lock:
            generation = _status_generation
        result = _compute_repo_status_feed(record)
        _status_store(record_id, result, generation)
        return result


def _dataset_call(fn, *args, **kwargs):
    """One dataset derivation with the house error shape:
    lib/files refusals keep their status; dataset
    refusals are 400 with the module's renderable
    message."""
    try:
        return fn(*args, **kwargs)
    except files_mod.FileError_ as e:
        raise ApiError(e.status, str(e))
    except datasets_mod.DatasetError as e:
        raise ApiError(400, str(e))


def dataset_schema_feed(record, query) -> dict:
    """GET /api/repos/<id>/dataset?path=: the dataset's
    schema (for database kinds, every table's)."""
    rel = query.get("path")
    if not rel:
        raise ApiError(400, "dataset needs ?path=")
    return _dataset_call(datasets_mod.dataset_schema,
                         record["root"], rel)


def dataset_rows_feed(record, query) -> dict:
    """GET /api/repos/<id>/dataset/rows: one bounded
    page; filters ride as one JSON array parameter."""
    rel = query.get("path")
    if not rel:
        raise ApiError(400, "dataset rows need ?path=")
    try:
        limit = int(query.get("limit", "100"))
        offset = int(query.get("offset", "0"))
    except ValueError:
        raise ApiError(400, "limit/offset must be integers")
    filters = []
    raw_filters = query.get("filters")
    if raw_filters:
        try:
            filters = json.loads(raw_filters)
        except json.JSONDecodeError:
            raise ApiError(400, "filters must be a JSON array")
        if not isinstance(filters, list):
            raise ApiError(400, "filters must be a JSON array")
    return _dataset_call(
        datasets_mod.dataset_rows, record["root"], rel,
        table=query.get("table") or None, limit=limit,
        offset=offset, sort=query.get("sort") or None,
        descending=query.get("dir") == "desc",
        filters=filters)


def dataset_stats_feed(record, query) -> dict:
    """GET /api/repos/<id>/dataset/stats?path=: the
    on-demand column statistics."""
    rel = query.get("path")
    if not rel:
        raise ApiError(400, "dataset stats need ?path=")
    return _dataset_call(
        datasets_mod.dataset_stats, record["root"], rel,
        table=query.get("table") or None)
