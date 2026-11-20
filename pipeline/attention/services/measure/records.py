"""Lane record locations: a programme declares where
its lanes keep their run-log records; their conforming
progress-checkpoint lines are lane evidence alongside
the posts, snapshotted for the measure on the slow loop.
The goal store is collected beside them: its
owner-waiting declarations are the record source for
owner-waiting rows once the status-code transport is
gone."""

from __future__ import annotations

import glob as glob_mod
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from attention.paths import WORKRECORD_GOALS
from attention.services import programmes

CHECKPOINT = re.compile(r"progress-checkpoint:\s*(\S+)")
TAIL_BYTES = 65536


def _parse_stamp(text: str) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _latest_checkpoint(path: Path) -> datetime | None:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > TAIL_BYTES:
                handle.seek(size - TAIL_BYTES)
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    latest = None
    for match in CHECKPOINT.finditer(text):
        stamp = _parse_stamp(match.group(1))
        if stamp is not None and (latest is None or stamp > latest):
            latest = stamp
    return latest


def _files(locations: list) -> list[Path]:
    found: list[Path] = []
    for entry in locations or []:
        if any(ch in str(entry) for ch in "*?["):
            found.extend(
                Path(p) for p in sorted(glob_mod.glob(str(entry))) if Path(p).is_file()
            )
        elif Path(str(entry)).is_file():
            found.append(Path(str(entry)))
    return found


def collect(state: dict, now: datetime) -> bool:
    """Refresh the record snapshot for every declared
    programme; True when the snapshot changed."""
    snapshot: dict = {}
    for programme in programmes.declarations(state):
        locations = programme.get("record_locations") or []
        if not locations:
            continue
        entries = {}
        for path in _files(locations):
            stamp = _latest_checkpoint(path)
            entries[str(path)] = {
                "lane": path.stem,
                "checkpoint_at": stamp,
            }
        snapshot[programme["slug"]] = {"at": now, "records": entries}
    before = {
        slug: entry.get("records")
        for slug, entry in (state.get("record_snapshot") or {}).items()
    }
    if {s: e["records"] for s, e in snapshot.items()} == before:
        return False
    state["record_snapshot"] = snapshot
    return True


def _goals_file() -> Path:
    override = os.environ.get("WB_GOALS_FILE")
    if override:
        return Path(override)
    return WORKRECORD_GOALS


def collect_goals(state: dict, now: datetime) -> bool:
    """Snapshot the goal store's owner-waiting
    declarations per programme, from each goal record's
    latest post — the declaration is sticky in the store
    until an explicit null clears it. A missing store
    file is honest absence: no declarations, not an
    error."""
    snapshot: dict = {}
    try:
        store = json.loads(_goals_file().read_text())
    except (OSError, ValueError):
        store = {}
    records = store.get("goals") if isinstance(store, dict) else None
    by_slug: dict = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        by_slug.setdefault(record.get("slug"), []).append(record)
    for programme in programmes.active_declarations(state):
        waiting = []
        for record in by_slug.get(programme["slug"]) or []:
            posts = record.get("posts") or []
            decl = (posts[-1] or {}).get("owner_waiting") if posts else None
            if decl:
                waiting.append(
                    {
                        "goal": record.get("slug"),
                        "label": decl.get("label"),
                        "commissioned_at": decl.get("commissioned_at"),
                        "declared_at": decl.get("declared_at"),
                    }
                )
        snapshot[programme["slug"]] = {"at": now, "owner_waiting": waiting}
    before = {
        slug: entry.get("owner_waiting")
        for slug, entry in (state.get("goal_snapshot") or {}).items()
    }
    if {s: e["owner_waiting"] for s, e in snapshot.items()} == before:
        return False
    state["goal_snapshot"] = snapshot
    return True
