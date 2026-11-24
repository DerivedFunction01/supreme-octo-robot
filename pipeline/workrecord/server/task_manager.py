"""The Task Manager feed: the load monitor's snapshot
store, served ready for the workbench section.

The sampler is the scheduler-side load monitor; it
writes the snapshot store (pipeline/scheduling/state/
load-monitor-snapshot.json, resolved through the paths
foundation like every cross-package value). This feed
only reads that store — the request path never samples
/proc, so the page's cost is constant while the box is
overloaded.

Staleness is honest absence: a snapshot older than
STALE_AFTER_S (or a store missing, unreadable, or
carrying no parseable stamp) serves its stamp (or
null), stale: true, and empty lists — never the old
rows presented as current, and never fabricated rows.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from lib import util as _util

from . import paths as _paths

STALE_AFTER_S = 180


def snapshot_path() -> Path:
    """The monitor's snapshot store, from the paths
    foundation (the neighbouring feeds' convention)."""
    return _paths.LOAD_MONITOR_SNAPSHOT


def _absent(stamp) -> dict:
    return {"stamp": stamp, "stale": True, "load": None,
            "cpus": None, "mem": None, "processes": [],
            "venues": [], "jobs": []}


def task_manager_feed(path=None, now=None) -> dict:
    """The served Task Manager shape over the snapshot
    store at `path` (the monitor's store unless one is
    named — the tests name a fixture store), judged
    against `now` (the current instant unless one is
    named).

    Fresh: {stamp, stale: false, load, cpus, mem,
    processes, venues, jobs} with the process rows and
    venues exactly as stored. `jobs` is empty: the
    scheduler's running-job view (its serving api's
    jobs_list) stands on the coupled process's engine,
    which this surface does not hold, and no second
    scheduler-state reader is built here — the list
    fills when that view is exposed to this surface.
    """
    path = Path(path) if path is not None \
        else snapshot_path()
    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _absent(None)
    current = store.get("current") \
        if isinstance(store, dict) else None
    if not isinstance(current, dict):
        return _absent(None)
    stamp_raw = current.get("stamp")
    stamp = _util.parse_instant(stamp_raw)
    if stamp is None:
        return _absent(
            stamp_raw if isinstance(stamp_raw, str)
            else None)
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if (now - stamp).total_seconds() > STALE_AFTER_S:
        return _absent(stamp_raw)
    processes = current.get("processes")
    venues = current.get("venues")
    return {
        "stamp": stamp_raw,
        "stale": False,
        "load": current.get("load"),
        "cpus": current.get("cpus"),
        "mem": current.get("mem"),
        "processes": processes
        if isinstance(processes, list) else [],
        "venues": venues if isinstance(venues, list)
        else [],
        "jobs": [],
    }
