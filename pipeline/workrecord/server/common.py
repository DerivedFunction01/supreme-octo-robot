"""Server-shared state and helpers.

The seam every server module stands on: the loaded
config, the process identity (version, start time,
commit), the sweep cache with its project/layout/
degraded helpers, and ApiError — the one refusal type
the HTTP layer renders. Siblings import from here;
nothing here imports a sibling (no cycles).

Target-shape note (S8): the pinned module inserted its
own sys.path entries and imported config flat; here the
package's __init__ owns the seams and config is a
sibling import. COMMIT resolves against the mega repo
(the work-record root's second parent) instead of the
pinned repo.
"""

import hashlib
import subprocess
import threading
import time
from datetime import datetime, timezone

import sys
from pathlib import Path

from . import config as cfgmod  # noqa: E402
from lib.derived import fingerprint as fingerprint_mod  # noqa: E402
from lib.discovery import sweep as sweep_mod  # noqa: E402
from lib.util import fan_out  # noqa: E402

VERSION = "1.0.0"
MAX_BODY = 1024 * 1024

CFG = cfgmod.load()
STARTED_AT = datetime.now(timezone.utc)

_sweep_cache = {"at": 0.0, "result": None}
_sweep_compute_lock = threading.Lock()
_sweep_state_lock = threading.Lock()
_sweep_refreshing = False
_fingerprint_cache = {"map": {}, "at": 0.0, "sweep": None}
_fingerprint_lock = threading.Lock()


def _git_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cfgmod.REPO_ROOT.parent.parent),
             "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or None
    except Exception:
        return None


COMMIT = _git_head()


# ----------------------------------------------------------------
# Sweep cache
# ----------------------------------------------------------------

def _compute_sweep():
    return sweep_mod.sweep(
        cfgmod.sweep_roots(CFG),
        manifest_name=CFG["sweep_manifest"],
        max_depth=CFG["sweep_max_depth"],
        prune=CFG["sweep_prune"])


def _sweep_store(result) -> None:
    with _sweep_state_lock:
        _sweep_cache.update(at=time.monotonic(),
                            result=result)


def _sweep_refresh_background() -> None:
    global _sweep_refreshing
    try:
        # A background recompute serializes with a cold
        # compute on the same lock; its result stores
        # whenever it lands (no invalidation generation
        # exists for the sweep cache — a fresher sweep is
        # a fresher sweep).
        with _sweep_compute_lock:
            _sweep_store(_compute_sweep())
    except Exception as e:
        # The stale result keeps serving; the next stale
        # request kicks another refresh.
        print(f"workbench-viewer: sweep refresh failed: "
              f"{e}", file=sys.stderr)
    finally:
        with _sweep_state_lock:
            _sweep_refreshing = False


def _sweep_kick_refresh() -> None:
    global _sweep_refreshing
    with _sweep_state_lock:
        if _sweep_refreshing:
            return
        _sweep_refreshing = True
    threading.Thread(target=_sweep_refresh_background,
                     daemon=True).start()


def get_sweep(force: bool = False):
    """The swept projects, TTL-cached, stale-while-
    recompute (the repos feed's shape): within the TTL
    the cached result serves as-is; past the TTL the
    stale result serves while ONE background thread
    recomputes; only a never-filled cache (or force)
    computes on the caller's thread, single-flighted so
    a burst of cold requests shares one walk.

    The pre-2026-11-10 shape computed inline past the
    TTL behind the lock, so under a storage stall every
    request queued behind one slow recompute while the
    last good result sat in memory (the wedge capture:
    handler threads parked at this lock for minutes).
    Stale data here costs one cadence of discovery lag;
    queueing cost the whole server."""
    ttl = CFG["sweep_ttl_s"]
    if not force:
        cached = _sweep_cache["result"]
        if cached is not None:
            if time.monotonic() - _sweep_cache["at"] \
                    < ttl:
                return cached
            _sweep_kick_refresh()
            return cached
    with _sweep_compute_lock:
        # A racing request may have filled the cache while
        # this one waited for the lock.
        if not force and _sweep_cache["result"] is not None \
                and time.monotonic() - _sweep_cache["at"] \
                < ttl:
            return _sweep_cache["result"]
        result = _compute_sweep()
        _sweep_store(result)
        return result


def peek_sweep():
    """The cached sweep result, or None when the cache
    has never filled: a pure read of the cache — it
    never computes, never kicks a background refresh,
    and never takes the compute lock. For callers that
    must answer whether or not the sweep has landed
    (the health route: the process being up and bound
    is the health fact, while the sweep's warmth is
    data the route reports — not a precondition it
    queues behind the first fill for)."""
    return _sweep_cache["result"]


def _compute_fingerprints(projects) -> dict:
    """Per-project content fingerprints (lib/fingerprint):
    one stat walk per project, fanned out over the feed
    pool — stat calls are syscall-bound, so the pool's
    threads genuinely help."""
    pairs = fan_out(
        lambda p: (p.slug,
                   fingerprint_mod.project_fingerprint(
                       p.root)),
        projects, workers=CFG["feed_pool_workers"])
    by_slug: dict = {}
    for slug, fp in pairs:
        by_slug.setdefault(slug, []).append(fp)
    # A slug borne by two swept roots (a repo and its
    # checkout) folds both walks into one value, so a
    # write to either root moves the slug's fingerprint.
    return {slug: fps[0] if len(fps) == 1 else
            hashlib.sha256(
                "\n".join(sorted(fps)).encode("utf-8"))
            .hexdigest()
            for slug, fps in by_slug.items()}


def _fingerprints_fresh(result) -> bool:
    """The cached fingerprint map is current when it was
    computed from THIS sweep result (a re-discovery —
    forced or TTL-expired — replaces the roots the walks
    stand on) and is younger than the sweep cadence."""
    return _fingerprint_cache["sweep"] is result \
        and time.monotonic() - _fingerprint_cache["at"] \
        < CFG["sweep_ttl_s"]


_fingerprint_state_lock = threading.Lock()
_fingerprint_refreshing = False


def _fingerprints_refresh_background(result) -> None:
    global _fingerprint_refreshing
    try:
        with _fingerprint_lock:
            fmap = _compute_fingerprints(
                getattr(result, "projects", None) or [])
            _fingerprint_cache.update(
                map=fmap, at=time.monotonic(),
                sweep=result)
    except Exception as e:
        # The stale map keeps serving; the next stale
        # read kicks another refresh.
        print(f"workbench-viewer: fingerprint refresh "
              f"failed: {e}", file=sys.stderr)
    finally:
        with _fingerprint_state_lock:
            _fingerprint_refreshing = False


def _fingerprints_kick_refresh(result) -> None:
    global _fingerprint_refreshing
    with _fingerprint_state_lock:
        if _fingerprint_refreshing:
            return
        _fingerprint_refreshing = True
    threading.Thread(
        target=_fingerprints_refresh_background,
        args=(result,), daemon=True).start()


def get_fingerprints() -> dict:
    """{slug: fingerprint} for the currently swept
    projects. Decoupled from the sweep compute (B5): the
    walks stand on the last sweep's known project roots
    and refresh on their own path — same cadence value as
    the sweep TTL, but stale-while-recompute (the lazy
    restore, 2026-11-16): a read past the cadence serves
    the cached map and kicks ONE background refresh, so
    no read ever waits on the stat walks; only a
    never-filled cache computes on the caller's thread,
    single-flighted under the fingerprint lock. A .plans
    write moves the fingerprint at the refresh the first
    stale read kicks — the bound every feed here already
    carries — instead of inside the read that notices
    it, which is what queued board and home reads behind
    the walks (and behind an assembly's own fan-out
    holding the same lock) under the burn."""
    result = get_sweep()
    if _fingerprints_fresh(result):
        return dict(_fingerprint_cache["map"])
    if _fingerprint_cache["sweep"] is not None:
        _fingerprints_kick_refresh(result)
        return dict(_fingerprint_cache["map"])
    with _fingerprint_lock:
        # A racing caller may have refreshed while this
        # one waited for the lock.
        if _fingerprints_fresh(result):
            return dict(_fingerprint_cache["map"])
        # A result without projects (never in production)
        # simply leaves every feed uncached, never breaks
        # discovery.
        fmap = _compute_fingerprints(
            getattr(result, "projects", None) or [])
        _fingerprint_cache.update(
            map=fmap, at=time.monotonic(), sweep=result)
        return dict(fmap)


def combined_fingerprint() -> str:
    """One hash over every project's fingerprint (sorted
    slug:fp pairs) — the home feed's change signal: any
    project's corpus moving moves the combination."""
    fps = get_fingerprints()
    h = hashlib.sha256()
    for slug in sorted(fps):
        h.update(f"{slug}:{fps[slug]}\n".encode("utf-8"))
    return h.hexdigest()


def find_project(slug: str):
    return get_sweep().by_slug(slug)


def layout_of(project):
    m = project.manifest
    return (m.mockups, m.archive)


def degraded(base: dict, exc: Exception) -> dict:
    out = dict(base)
    out["degraded"] = True
    out["reason"] = str(exc)[:200]
    return out


class ApiError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.payload = {"error": message, **extra}
