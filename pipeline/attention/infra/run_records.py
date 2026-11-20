"""The runner's local detached-run records: read-only.

One JSON file per run carries its caller, session, state,
and start/finish times. This reader returns the running
records inside the current window; it never writes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

WINDOW_HOURS = 24


class RunRecordsUnavailable(Exception):
    """The detached-run records could not be read."""


def _filename_time(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.name[:15], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_time(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _read_window(records_dir: Path, now: datetime) -> list:
    if not records_dir.is_dir():
        raise RunRecordsUnavailable("Run records could not be read.")
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    out = []
    try:
        paths = sorted(records_dir.glob("*.json"))
    except OSError as err:
        raise RunRecordsUnavailable("Run records could not be read.") from err
    for path in paths:
        stamp = _filename_time(path)
        if stamp is not None and stamp < cutoff:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        started = _parse_time(record.get("started_at")) or stamp
        if started is not None and started < cutoff:
            continue
        out.append(
            {
                "id": record.get("id") or path.stem,
                "caller": record.get("caller") or "",
                "session": record.get("session") or "",
                "state": record.get("state") or "",
                "started_at": started,
                "finished_at": _parse_time(record.get("finished_at")),
            }
        )
    return out


def read_running(records_dir: Path, now: datetime) -> list:
    """Running records no older than the window, oldest
    first; records on dead sessions are aged out later,
    against the capacity snapshot."""
    out = [
        r
        for r in _read_window(records_dir, now)
        if r["state"] == "running" and not r["finished_at"]
    ]
    return sorted(out, key=lambda r: (r["started_at"] or now, r["id"]))


def read_recent(records_dir: Path, now: datetime) -> list:
    """Every record in the window, running or finished —
    the ground-truth evidence of work moving."""
    return _read_window(records_dir, now)
