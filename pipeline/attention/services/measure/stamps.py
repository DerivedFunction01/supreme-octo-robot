"""Workbench checkpoint stamps: a programme whose lanes
report through the workbench moves on their todos'
progress-checkpoint stamps; the capacity loop snapshots
the latest stamp per armed todo, plus every blocked todo
of each declared programme — the record source for
blocked claims once the status-code transport is gone.
A blocked todo carries its body, so the citation and
basis a blocked claim needs are read from the record."""

from __future__ import annotations

from datetime import datetime

from attention.infra import wb_client
from attention.services import programmes
from attention.services.measure import records
from attention.settings import Settings


def normalize(value) -> str | None:
    """A stored stamp in one canonical text form, whether
    it was saved as text or revived as a datetime."""
    if value is None:
        return None
    stamp = records._parse_stamp(str(value))
    return stamp.isoformat() if stamp is not None else None


def _latest(body: str | None) -> datetime | None:
    latest = None
    for match in records.CHECKPOINT.finditer(body or ""):
        stamp = records._parse_stamp(match.group(1))
        if stamp is not None and (latest is None or stamp > latest):
            latest = stamp
    return latest


def _blocked_key(rows: list) -> list:
    return sorted(
        (
            row.get("todo") or "",
            row.get("project") or "",
            row.get("title") or "",
            row.get("body") or "",
        )
        for row in rows
    )


def collect(state: dict, settings: Settings, now: datetime) -> bool:
    """Snapshot each armed todo's latest workbench
    checkpoint stamp and each declared programme's
    blocked todos. A project the workbench cannot serve
    keeps its prior stamps and blocked rows; a blocked
    todo is in the snapshot while its status is blocked.
    A programme with no armed entries still gets its
    blocked snapshot — a blocked todo leaves the armed
    set, so skipping it would hide the claim."""
    snapshot = state.setdefault("stamp_snapshot", {})
    blocked_snapshot = state.setdefault("blocked_snapshot", {})
    changed = False
    for programme in programmes.active_declarations(state):
        slug = programme["slug"]
        entries = programmes.armed_entries(state, programme)
        by_project: dict = {}
        for entry in entries:
            by_project.setdefault(entry.get("project"), []).append(entry)
        projects = set(programmes.wb_projects(programme)) | set(by_project)
        prior = (snapshot.get(slug) or {}).get("stamps") or {}
        prior_blocked = (blocked_snapshot.get(slug) or {}).get("blocked") or []
        stamps: dict = {}
        blocked: list = []
        failed: set = set()
        for project in sorted(projects):
            try:
                payload = wb_client.fetch_todos(
                    settings.wb_url, project, settings.wb_collect_timeout_s
                )
            except wb_client.WbUnavailable:
                failed.add(project)
                continue
            todos = {t.get("id"): t for t in payload.get("todos") or []}
            for entry in by_project.get(project) or []:
                todo = todos.get(entry["todo"])
                stamp = _latest((todo or {}).get("body")) if todo else None
                if stamp is not None:
                    stamps[entry["todo"]] = stamp.isoformat()
            for t in payload.get("todos") or []:
                if t.get("status") != "blocked":
                    continue
                stamp = _latest(t.get("body") or "")
                blocked.append(
                    {
                        "todo": t.get("id"),
                        "project": t.get("project") or project,
                        "title": t.get("title"),
                        "body": t.get("body") or "",
                        "checkpoint_at": stamp.isoformat() if stamp else None,
                    }
                )
        for entry in entries:
            if entry["todo"] not in stamps:
                kept = normalize(prior.get(entry["todo"]))
                if kept is not None:
                    stamps[entry["todo"]] = kept
        blocked.extend(row for row in prior_blocked if row.get("project") in failed)
        if {k: normalize(v) for k, v in prior.items()} != stamps or _blocked_key(
            prior_blocked
        ) != _blocked_key(blocked):
            snapshot[slug] = {"at": now, "stamps": stamps}
            blocked_snapshot[slug] = {"at": now, "blocked": blocked}
            changed = True
    return changed
