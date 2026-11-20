"""Read-time derivation from the workbench surface: a
lane's armed entries are pulled at read time and never
stored. There is no posted code left to disagree with,
so the conflict list is empty by construction.
"""

from __future__ import annotations

from datetime import datetime

from attention.infra import wb_client
from attention.settings import Settings

_last_good: dict[str, datetime] = {}


def derive_counts(settings: Settings, project: str, wanted: set | None, now: datetime):
    """Todo counts for one workbench project, optionally
    restricted to todo ids — the fetch+count derive_for
    delegates to. None when the project cannot be served
    (the last-good stamp is kept for the caller)."""
    try:
        payload = wb_client.fetch_todos(settings.wb_url, project, settings.wb_timeout_s)
    except wb_client.WbUnavailable as err:
        last = _last_good.get(project)
        return {
            "available": False,
            "reason": str(err),
            "last_good_at": last.isoformat() if last else None,
            "todos": None,
        }
    _last_good[project] = now
    todos = payload.get("todos") or []
    if wanted is not None:
        todos = [t for t in todos if t.get("id") in wanted]
    return {
        "available": True,
        "reason": None,
        "last_good_at": now.isoformat(),
        "todos": {
            "total": len(todos),
            "done": sum(1 for t in todos if t.get("status") == "done"),
            "doing": sum(1 for t in todos if t.get("status") == "doing"),
            "blocked": sum(1 for t in todos if t.get("status") == "blocked"),
        },
    }


def _entries_for_handle(state: dict, handle: str) -> list:
    """The armed entries a handler's derived block reads:
    entries the handle names directly (an armed row's
    own handle is its todo id), or the entries of the
    programme the handle belongs to — its coordinator
    handle, or a lane handle carrying the programme's
    slug stem. An armed row names its todo, never a
    posting lane, so the lane is resolved through the
    programme, not the row."""
    rows = state.get("armed_rows") or []
    direct = [e for e in rows if ((e.get("row") or {}).get("handle") or "") == handle]
    if direct:
        return direct
    for programme in state.get("programmes") or []:
        if programme.get("retired"):
            continue
        handles = programme.get("handles") or []
        if handle in handles:
            return _entries_for_programme(state, programme)
        stem = programme["slug"].split("-", 1)[0]
        base = handle.lstrip("@").split(":", 1)[0]
        if base == stem or base.startswith(stem + "-"):
            return _entries_for_programme(state, programme)
    return []


def _entries_for_programme(state: dict, programme: dict) -> list:
    from attention.services import programmes as programmes_mod

    return programmes_mod.armed_entries(state, programme)


def derive_for(state: dict, settings: Settings, handle: str, now: datetime):
    """The derived block for a handler: its armed
    workbench entries — the post's refs, re-homed.
    None when the handle has no armed work to derive
    from."""
    entries = _entries_for_handle(state, handle)
    if not entries:
        return None
    newest = max(
        entries,
        key=lambda e: (
            ((e.get("row") or {}).get("armed_at")) or "",
            e.get("todo") or "",
        ),
    )
    project = newest.get("project")
    if not project:
        return None
    wanted = {e.get("todo") for e in entries if e.get("project") == project}
    derived = derive_counts(settings, project, wanted, now)
    if not derived.get("available"):
        return {**derived, "worst": None, "conflicts": []}
    counts = derived["todos"]
    worst = None
    if counts["blocked"]:
        worst = "blocked"
    elif counts["doing"]:
        worst = "doing"
    elif counts["total"] and counts["done"] == counts["total"]:
        worst = "done"
    return {
        "available": True,
        "reason": None,
        "last_good_at": now.isoformat(),
        "todos": counts,
        "worst": worst,
        "conflicts": [],
    }
