"""Feeds-document builders: the status vocabulary and
the per-project documents — split from assemble.py
along the document seam; server.assemble re-exports
this surface.
"""

from lib.plans import parser as plan_parser

from .. import feeds
from ..common import ApiError

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

