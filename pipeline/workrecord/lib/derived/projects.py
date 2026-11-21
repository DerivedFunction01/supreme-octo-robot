"""The canonical project index: ONE identity space over
the manifest sweep and the git census (SPEC §3.1, §21).

The sweep knows adopted projects (manifest slug, root,
sections); the census knows every checkout (main +
linked worktrees, by workspace-relative id). They are
two enumerations of the same ground. This derivation
joins them into the single list every surface reads:

- a project is keyed by its manifest slug where a
  manifest exists, else by its main checkout's census
  id;
- a linked worktree is a checkout of its project,
  never a peer row;
- a census main checkout with no manifest is a
  repository-only project — same index, membership
  named, work sections honestly absent;
- checkouts under the scratch roots are excluded from
  the rows and counted in the header;
- a registry entry the census did not find rides as a
  missing row (folded into its project when its root
  names one).

Pure: callers pass the sweep summary rows, the census
summaries (evaluation.repos.repo_summary shapes, with
registry entries attached by census id or not at all),
the project-keyed registry, and the resolved scratch
roots. The git work stays with the census; the sweep
stays with discovery; this module only joins.
"""

from pathlib import Path


def _resolved(path) -> str:
    return str(Path(path).resolve())


def _code_of(summary):
    """The code summary a project row carries: the
    census summary's headline derivations, nothing
    re-derived."""
    if summary is None:
        return None
    return {
        "branch": summary.get("branch"),
        "head": summary.get("head"),
        "head_full": summary.get("head_full"),
        "head_short": summary.get("head_short"),
        "head_subject": summary.get("head_subject"),
        "upstream": summary.get("upstream"),
        "ahead": summary.get("ahead"),
        "behind": summary.get("behind"),
        "dirty_counts": summary.get("dirty_counts"),
        "is_clean": summary.get("is_clean"),
        "error": summary.get("error"),
        "remotes": summary.get("remotes"),
        "publication": summary.get("publication"),
        "sync": summary.get("sync"),
        "exposure": summary.get("exposure"),
    }


def identity_map(sweep_projects, census_records) -> dict:
    """census id -> canonical project id, for every
    census record (mains and worktrees) and nothing
    else. `census_records` are census-shaped dicts
    carrying at least {id, root, is_worktree,
    parent_id}; summaries of the same records serve
    as well. A main checkout whose resolved root is a
    swept project's root maps to that project's slug;
    every other main maps to its own census id;
    worktrees map through their parent."""
    by_root = {}
    for record in census_records:
        by_root.setdefault(_resolved(record["root"]),
                           record)
    slug_by_main = {}
    for project in sweep_projects:
        record = by_root.get(_resolved(project["root"]))
        if record is not None and not record.get("is_worktree"):
            slug_by_main[record["id"]] = project["slug"]
    result = {}
    for record in census_records:
        if record.get("is_worktree"):
            parent = record.get("parent_id")
            result[record["id"]] = slug_by_main.get(
                parent, parent)
        else:
            result[record["id"]] = slug_by_main.get(
                record["id"], record["id"])
    return result


def build_index(sweep_projects, repo_summaries, registry,
                scratch_roots, captured_at) -> dict:
    """The unified index payload (SPEC §21).

    sweep_projects: sweep summary rows {slug, name,
    root, sections, also_at}.
    repo_summaries: census summaries (repo_summary
    shapes); a summary with `missing: true` is a
    registry row discovery did not find.
    registry: {project_id: entry} — the project-keyed
    tracking registry (post-migration keys).
    scratch_roots: resolved absolute path strings.
    """
    census_records = [s for s in repo_summaries
                      if not s.get("missing")]
    id_map = identity_map(sweep_projects, census_records)
    scratch = [str(Path(s).resolve()) for s in scratch_roots]

    def _under_scratch(root) -> bool:
        resolved = _resolved(root)
        return any(resolved == s or resolved.startswith(s + "/")
                   for s in scratch)

    mains = {}
    worktrees = {}
    for summary in census_records:
        if summary.get("is_worktree"):
            worktrees.setdefault(summary.get("parent_id"),
                                 []).append(summary)
        else:
            mains[summary["id"]] = summary

    projects_by_root = {_resolved(p["root"]): p
                        for p in sweep_projects}
    rows = []
    claimed_mains = set()

    def _checkouts(main_summary):
        out = [{"id": main_summary["id"],
                "root": main_summary["root"],
                "is_worktree": False,
                "branch": main_summary.get("branch")}]
        for wt in sorted(worktrees.get(main_summary["id"], []),
                         key=lambda s: s["id"]):
            out.append({"id": wt["id"], "root": wt["root"],
                        "is_worktree": True,
                        "branch": wt.get("branch")})
        return out

    # Adopted projects first: the sweep's order is the
    # index's spine.
    for project in sweep_projects:
        main = None
        for candidate in mains.values():
            if _resolved(candidate["root"]) == \
                    _resolved(project["root"]):
                main = candidate
                break
        if main is not None:
            claimed_mains.add(main["id"])
        entry = registry.get(project["slug"])
        rows.append({
            "id": project["slug"],
            "slug": project["slug"],
            "name": (entry or {}).get("display_name")
            or project["name"],
            "root": project["root"],
            "membership": "adopted",
            "sections": project.get("sections"),
            "also_at": project.get("also_at") or [],
            "checkouts": _checkouts(main) if main else [],
            "code": _code_of(main),
            "registry": entry,
            "missing": False,
        })

    # Repository-only mains: every unclaimed main
    # checkout, scratch excluded and counted.
    excluded_scratch = 0
    for main_id in sorted(mains):
        if main_id in claimed_mains:
            continue
        main = mains[main_id]
        if _under_scratch(main["root"]):
            excluded_scratch += 1
            continue
        entry = registry.get(main_id)
        rows.append({
            "id": main_id,
            "slug": None,
            "name": (entry or {}).get("display_name")
            or main.get("name") or main_id,
            "root": main["root"],
            "membership": "repository-only",
            "sections": None,
            "also_at": [],
            "checkouts": _checkouts(main),
            "code": _code_of(main),
            "registry": entry,
            "missing": False,
        })

    # Missing registry rows: fold into their project
    # when the recorded root names one, else stand as
    # missing rows of their own.
    row_by_id = {row["id"]: row for row in rows}
    for summary in repo_summaries:
        if not summary.get("missing"):
            continue
        entry = summary.get("registry") or {}
        root = summary.get("root") or entry.get("root")
        project = projects_by_root.get(_resolved(root)) \
            if root else None
        if project is not None and project["slug"] in row_by_id:
            row = row_by_id[project["slug"]]
            row["registry"] = row["registry"] or entry
            if row.get("code") is None:
                # The project's own checkout is what
                # discovery missed.
                row["missing"] = True
            continue
        rows.append({
            "id": summary["id"],
            "slug": None,
            "name": entry.get("display_name") or summary["id"],
            "root": root,
            "membership": "missing",
            "sections": None,
            "also_at": [],
            "checkouts": [],
            "code": None,
            "registry": entry or None,
            "missing": True,
        })

    # Exposure over canonical mains only — the rows'
    # own code summaries, worktrees never counted.
    tracked = 0
    unpushed = 0
    uncommitted_repos = 0
    uncommitted_files = 0
    local_only = 0
    for row in rows:
        code = row.get("code")
        if code is None:
            continue
        tracked += 1
        sync = code.get("sync") or {}
        unpushed += sync.get("unpushed_count") or 0
        dirty = code.get("dirty_counts") or {}
        dirty_total = sum(dirty.values())
        if dirty_total > 0:
            uncommitted_repos += 1
            uncommitted_files += dirty_total
        if code.get("publication") == "local_only":
            local_only += 1

    return {
        "projects": rows,
        "exposure": {
            "tracked": tracked,
            "unpushed_commits": unpushed,
            "uncommitted_repos": uncommitted_repos,
            "uncommitted_files": uncommitted_files,
            "local_only": local_only,
        },
        "excluded_scratch": excluded_scratch,
        "captured_at": captured_at,
    }
