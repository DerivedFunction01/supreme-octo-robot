"""Session load and warmth: the acquire sort's
spreading inputs (load-aware assignment).

Load is the count of a session's in-flight runs,
read from the runner's own results store
(results/runs/*.json beside the lease records' repo
root): a run counts while its state is non-terminal
and it started within LOAD_WINDOW_MINUTES — the
window keeps a stale non-terminal record (a launcher
that died before the sweep terminalled it) from
inflating a session's load forever. The store is
read-only here; an unreadable file is skipped and a
missing store reads as no load, so the census can
never block an acquire.

Warmth is a lease record's provisioning verdict: a
record whose provisioning stands at its verdict has
its environment built and can take work at once; a
record with provisioning still in flight is cold and
ranks below every warm session (it stays eligible —
a cold session is still adopted when nothing warm
can be). A record carrying no provisioning field
predates the machinery and reads warm: the legacy
default never demotes the fleet that was already
standing when the field arrived.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..core import foundation

LOAD_WINDOW_MINUTES = 120
NONTERMINAL_STATES = {"starting", "launching", "polling", "running", "active"}


def session_load(repo: Path, now_dt: datetime | None = None) -> dict[str, int]:
    """In-flight run counts per session name, from
    the results store under the venue root. Sessions
    with no in-flight runs are absent from the map
    (read as zero)."""
    now_dt = now_dt or datetime.now(timezone.utc)
    runs_dir = Path(repo) / "results" / "runs"
    counts: dict[str, int] = {}
    if not runs_dir.is_dir():
        return counts
    horizon = now_dt - timedelta(minutes=LOAD_WINDOW_MINUTES)
    for path in runs_dir.glob("*.json"):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        if record.get("state") not in NONTERMINAL_STATES:
            continue
        session = record.get("session")
        if not session:
            continue
        started_raw = record.get("started_at") or record.get("launch_at")
        started = None
        if isinstance(started_raw, str) and started_raw:
            try:
                started = foundation.parse_dt(started_raw)
            except ValueError:
                started = None
            if started is not None and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
        if started is not None and started < horizon:
            continue
        counts[session] = counts.get(session, 0) + 1
    return counts


def is_warm(record: dict) -> bool:
    """True when the record's environment stands
    built: its provisioning reached a verdict, or it
    carries no provisioning field at all (a record
    that predates the machinery)."""
    provisioning = record.get("provisioning")
    if not isinstance(provisioning, dict):
        return True
    return provisioning.get("state") == "verdict"
