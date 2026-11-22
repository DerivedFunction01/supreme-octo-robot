"""Projects feed: the unified project index and the
Code facet's addressing (SPEC §21).

The consolidation's server half: the index joins the
manifest sweep with the census summaries through
lib/derived/projects (the one identity derivation),
and the Code routes resolve a canonical project id +
an optional checkout (a census id of the project —
its main checkout by default, or one of its linked
worktrees) to the census record the repos derivations
read. The derivations themselves stay in
evaluation.repos / lib.writes.files / evaluation
.datasets, exactly as the retired /api/repos family
called them; only the addressing changed.
"""

import threading
from pathlib import Path

from evaluation import repo_state as repo_state_mod  # noqa: E402
from lib.derived import projects as projects_mod  # noqa: E402
from lib.util import now_iso  # noqa: E402

from . import repos_feed  # noqa: E402
from .common import CFG, ApiError, get_sweep  # noqa: E402


def _scratch_roots() -> list:
    """The resolved scratch roots the index excludes
    (config repos_detail_scratch_roots — the same
    configuration the retired detail scope read, now
    applied at the index)."""
    base = Path(CFG["workspace_root"])
    resolved = []
    for entry in CFG.get("repos_detail_scratch_roots") or []:
        path = Path(entry)
        if not path.is_absolute():
            path = base / path
        resolved.append(str(path.resolve()))
    return resolved


def projects_index_feed() -> dict:
    """GET /api/projects-index: every canonical project
    once — adopted and repository-only — with its
    checkouts, code summary, and tracking record, plus
    the header exposure totals and the scratch
    exclusion count. Built over the repos feed's
    cached census payload, so the git fan-out is the
    census's own, never a second one."""
    sweep = get_sweep()
    repos = repos_feed.repos_feed()
    registry = repo_state_mod.load_registry(
        repos_feed._repos_registry_path())["repos"]
    return projects_mod.build_index(
        sweep.summary()["projects"],
        repos.get("repos", []),
        registry,
        _scratch_roots(),
        now_iso())


_root_map_cache = {"at": None, "map": None}
_root_map_lock = threading.Lock()


def _main_id_by_root(census) -> dict:
    """resolved root string -> main census record id,
    built lazily per census state (keyed by the census
    cache's stored timestamp, the _id_map memo's key
    discipline): resolve_checkout used to Path-resolve
    every census record's root on every call to find
    the one main checkout under a swept project's
    root; the map resolves each root once per census.
    First record wins, in census order — the same
    record the per-call loop's break settled on."""
    at = repos_feed._census_cache["at"]
    with _root_map_lock:
        if _root_map_cache["map"] is not None \
                and _root_map_cache["at"] == at:
            return _root_map_cache["map"]
        by_root = {}
        for record in census.values():
            if not record.get("is_worktree"):
                by_root.setdefault(
                    str(Path(record["root"]).resolve()),
                    record["id"])
        _root_map_cache.update(at=at, map=by_root)
        return by_root


def resolve_checkout(project_id: str, checkout_id=None):
    """Resolve (project_id, checkout) to the census
    record the Code derivations read.

    project_id is the canonical id: a manifest slug, or
    a repository-only project's main census id. The
    checkout defaults to the project's main checkout;
    an explicit checkout must be the main or one of
    its linked worktrees — anything else is a 400, an
    unknown project a 404. Returns (record, main_id,
    checkouts) where checkouts is the project's
    [{id, root, is_worktree}] list, main first."""
    census = repos_feed._census_cached()
    sweep = get_sweep()
    id_map = projects_mod.identity_map(
        sweep.summary()["projects"], list(census.values()))
    main_id = None
    if project_id in census \
            and not census[project_id].get("is_worktree") \
            and id_map.get(project_id) == project_id:
        main_id = project_id
    else:
        project = sweep.by_slug(project_id)
        if project is not None:
            root = str(Path(project.root).resolve())
            main_id = _main_id_by_root(census).get(root)
    if main_id is None:
        raise ApiError(404, f"unknown project: {project_id}")
    checkouts = [{"id": main_id,
                  "root": census[main_id]["root"],
                  "is_worktree": False}]
    for record in sorted(census.values(), key=lambda r: r["id"]):
        if record.get("is_worktree") \
                and record.get("parent_id") == main_id:
            checkouts.append({"id": record["id"],
                              "root": record["root"],
                              "is_worktree": True})
    if checkout_id is None:
        return census[main_id], main_id, checkouts
    record = census.get(checkout_id)
    if record is None or id_map.get(checkout_id) != project_id \
            and not (checkout_id == main_id):
        raise ApiError(
            400, f"checkout {checkout_id} is not a checkout "
                 f"of project {project_id}")
    return record, main_id, checkouts


def code_status_feed(project_id: str, checkout_id=None) -> dict:
    """GET /api/projects/code/<id>/status: the selected
    checkout's full status, headed by the project's
    identity and its checkout list."""
    record, _main_id, checkouts = resolve_checkout(
        project_id, checkout_id)
    status = repos_feed.repo_status_feed(record)
    status["project_id"] = project_id
    status["checkout"] = record["id"]
    status["checkouts"] = checkouts
    return status


def code_history_feed(project_id: str) -> dict:
    """GET /api/projects/code/<id>/history: the
    project's observation history (recorded under the
    canonical project id since the §21 fold)."""
    resolve_checkout(project_id)
    return repo_state_mod.history_for(
        repos_feed._repos_history_path(), project_id)


def projects_registry_feed() -> dict:
    """GET /api/projects/registry: the tracking
    registry, keyed by canonical project id."""
    data = repo_state_mod.load_registry(
        repos_feed._repos_registry_path())
    return {"projects": data["repos"],
            "captured_at": now_iso()}


def projects_registry_save(project_id, patch) -> dict:
    """POST /api/projects/registry: one validated
    tracking patch under a canonical project id."""
    if not project_id or not isinstance(patch, dict):
        raise ApiError(400, "need {id, patch}")
    data = repo_state_mod.load_registry(
        repos_feed._repos_registry_path())
    entry, err = repo_state_mod.update_entry(
        data, project_id, patch)
    if err:
        raise ApiError(400, err)
    repo_state_mod.save_registry(
        repos_feed._repos_registry_path(), data)
    repos_feed._repos_invalidate_cache()
    return {"id": project_id, "registry": entry}
