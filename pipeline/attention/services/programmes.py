"""Programme declarations: the registry rows supervision
evaluates against — handles, cadence, band, escalation,
venue, rule text, worktree roots. A programme onboards
by declaring its row; the mechanism has no nouns."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def declarations(state: dict) -> list:
    """Every declared programme row, in registry order."""
    return state.get("programmes") or []


def active_declarations(state: dict) -> list:
    """Declarations supervision still evaluates: a retired
    programme leaves the evaluator with its programme."""
    return [p for p in declarations(state) if not p.get("retired")]


def wb_projects(programme: dict) -> list:
    """The workbench projects whose armed rows belong to
    this programme: its declared list, else its slug —
    unioned with the registry's declared list, the
    validated home after the Step 3 naming-seam fix, so
    a stale store row cannot hide a project's rows."""
    from attention.services.measure import registry

    declared = programme.get("wb_projects") or [programme["slug"]]
    seeded = registry.for_slug(programme["slug"])
    if seeded is not None:
        return sorted(set(declared) | set(registry.wb_projects_for(seeded)))
    return list(declared)


def armed_entries(state: dict, programme: dict) -> list:
    """Armed rows owned by this programme, matched on the
    workbench project the harness keys its rows by."""
    projects = set(wb_projects(programme))
    return [
        entry
        for entry in state.get("armed_rows") or []
        if entry.get("project") in projects
    ]


def by_handle(state: dict) -> dict:
    """handle -> programme for every declared handle."""
    index: dict = {}
    for programme in declarations(state):
        for handle in programme.get("handles") or []:
            index[handle] = programme
    return index


def cadence_for(state: dict, handle: str | None, default: float) -> float:
    """The checkpoint cadence a lane owes: its programme's
    declared value, else the service default."""
    programme = by_handle(state).get(handle or "")
    if programme and programme.get("cadence_minutes"):
        return float(programme["cadence_minutes"])
    return default


def escalation_for(state: dict, handle: str | None, default: float) -> float:
    """The escalation bound for a lane's rows: declared,
    else the service default."""
    programme = by_handle(state).get(handle or "")
    if programme and programme.get("escalation_hours"):
        return float(programme["escalation_hours"])
    return default


def ingest_armed(state: dict, armed_dir: Path, now: datetime) -> bool:
    """Sync the armed-row registry from the harness's file
    drop: rows appear at doing, retire by disappearing;
    fixture rows never supervise."""
    current: dict = {}
    if armed_dir.is_dir():
        for path in sorted(armed_dir.glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(row, dict):
                continue
            if (row.get("source") or {}).get("source_class") == "fixture":
                continue
            project, todo = row.get("project"), row.get("todo")
            if not project or not todo:
                continue
            current[(project, todo)] = row
    existing = {
        (row.get("project"), row.get("todo")): row
        for row in state.get("armed_rows") or []
    }
    if set(current) == set(existing) and all(
        current[key] == existing[key].get("row") for key in current
    ):
        return False
    state["armed_rows"] = [
        {
            "project": project,
            "todo": todo,
            "row": row,
            "ingested_at": existing.get((project, todo), {}).get("ingested_at", now),
        }
        for (project, todo), row in sorted(current.items())
    ]
    return True
