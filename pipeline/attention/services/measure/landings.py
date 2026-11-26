"""Landing-record aggregates for the supervision
measure: gates-per-landing and phase wall clock, read
from the landing records the landing act writes
(pipeline/venue/results/landings, written by
pipeline/venue/bin/land-record).

Served as the staffing payload's `landings` section:
counts and prices over the window, medians per phase.
Honest absence: with no records in the window the
section carries the count 0 and null prices — it
never fabricates a ratio from no landings.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from .staffing_rows import _as_dt

WINDOW_DAYS = 7


def _read_records(landings_dir: Path, now: datetime) -> list:
    if not landings_dir.is_dir():
        return []
    cutoff = now - timedelta(days=WINDOW_DAYS)
    records = []
    for path in sorted(landings_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        landed_at = _as_dt(record.get("landed_at"))
        if landed_at is None or landed_at < cutoff or landed_at > now:
            continue
        records.append(record)
    return records


def _median_phase(records: list, key: str) -> float | None:
    values = [
        record["phases_minutes"][key]
        for record in records
        if isinstance(record.get("phases_minutes"), dict)
        and isinstance(record["phases_minutes"].get(key), (int, float))
    ]
    if not values:
        return None
    return round(float(median(values)), 1)


def summarize(landings_dir: Path, now: datetime) -> dict:
    records = _read_records(landings_dir, now)
    base = {
        "window_days": WINDOW_DAYS,
        "landings": len(records),
        "fires_per_landing": None,
        "venue_minutes_per_landing": None,
        "constituents_per_landing": None,
        "phase_median_minutes": {
            "formation_to_gate": None,
            "gate_to_landed": None,
            "formation_to_landed": None,
        },
    }
    if not records:
        return base
    count = len(records)
    base["fires_per_landing"] = round(
        sum(r.get("fires") or 0 for r in records) / count, 2
    )
    base["venue_minutes_per_landing"] = round(
        sum(r.get("venue_minutes") or 0 for r in records) / count, 1
    )
    base["constituents_per_landing"] = round(
        sum(r.get("constituent_count") or 1 for r in records) / count, 2
    )
    for key in base["phase_median_minutes"]:
        base["phase_median_minutes"][key] = _median_phase(records, key)
    return base
