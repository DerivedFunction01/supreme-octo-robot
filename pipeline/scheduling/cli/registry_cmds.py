"""Registry report commands: validate, census, drift.
Read-only views over the registry directory and the
catalog's classification counts."""
import json
import sys

from server.entries import catalog as catalog_mod
from server import registry

from cli.common import ROOT, _load


def _overlay_absent_refs(entries):
    """Every (job_id, field, rel) body reference the load
    recorded as overlay-absent: the entry is valid, but this
    checkout carries no live overlay (bodies/ is gitignored
    working state), so the referenced body is not here to
    check. Named and counted, never silently passed over."""
    return [(job_id, field, rel) for job_id in sorted(entries)
            for field, rel in entries[job_id].overlay_absent_bodies]


def cmd_validate():
    entries, errors = _load()
    for err in errors:
        print(f"INVALID: {err}")
    print(f"{len(entries)} valid entries, {len(errors)} invalid")
    absent = _overlay_absent_refs(entries)
    for job_id, field, rel in absent:
        print(f"OVERLAY-ABSENT: {job_id}: {field} {rel} "
              f"(live overlay absent in this checkout)")
    if absent:
        print(f"{len(absent)} overlay-absent body reference(s) — the live "
              f"overlay (bodies/) is not present in this checkout")
    catalog, cat_errors = catalog_mod.load_catalog(ROOT)
    for err in cat_errors:
        print(f"INVALID: {err}")
    if catalog is not None:
        print(f"catalog v{catalog['version']}: {len(catalog['rows'])} classified rows, "
              f"{len(catalog['entries'])} adoptable entries, {len(cat_errors)} invalid")
    return 1 if (errors or cat_errors) else 0


def _cadence_text(entry):
    cad = entry.cadence
    if cad["type"] == "interval":
        return f"every {cad['every']}"
    if cad["type"] == "daily":
        return f"daily {cad['at']}"
    return f"weekly {','.join(cad['dow'])} {cad['at']}"


def _wakeups_per_day(entry):
    return registry.expected_wake_per_day(entry)


def cmd_census():
    entries, errors = _load()
    for err in errors:
        print(f"INVALID: {err}")
    total = 0.0
    for job_id in sorted(entries):
        entry = entries[job_id]
        wake = _wakeups_per_day(entry)
        total += wake
        flags = []
        if entry.status == "suspended":
            flags.append(f"SUSPENDED ({entry.get('suspend_reason')}, {entry.get('suspended_on')})")
        for field, rel in entry.overlay_absent_bodies:
            flags.append(f"OVERLAY-ABSENT {field}: {rel}")
        print(f"{job_id:44s} {entry.kind:8s} {_cadence_text(entry):18s} "
              f"{entry.get('owner'):38s} wake/day {wake:6.2f}  {'; '.join(flags)}")
    print(f"{len(entries)} entries; expected steady-state main-thread wake-ups/day: {total:.1f}")
    absent = _overlay_absent_refs(entries)
    if absent:
        print(f"{len(absent)} overlay-absent body reference(s) — the live "
              f"overlay (bodies/) is not present in this checkout")
    return 1 if errors else 0


def cmd_drift(path):
    entries, errors = _load()
    for err in errors:
        print(f"INVALID: {err}")
    raw = sys.stdin.read() if path == "-" else open(path, "r", encoding="utf-8").read()
    doc = json.loads(raw)
    schedules = doc.get("schedules", doc if isinstance(doc, list) else [])
    drift, notes = [], []
    registry_ids = set(entries)
    for job in schedules:
        if job.get("is_system") or job.get("is_heartbeat"):
            continue
        sched_key = job.get("schedule_key", "")
        job_id = job.get("id")
        if sched_key.startswith("runonce"):
            continue
        if job_id not in registry_ids:
            drift.append(f"live recurring cron {job_id} has no registry entry")
        else:
            drift.append(f"job {job_id} stands in the registry but its cron is still live")
    for job_id in sorted(registry_ids):
        if job_id not in {j.get("id") for j in schedules}:
            notes.append(f"{job_id}: in registry, no live cron (expected)")
    for note in notes:
        print(f"note: {note}")
    for item in drift:
        print(f"DRIFT: {item}")
    print(f"drift: {len(drift)} problem(s), {len(notes)} note(s)")
    return 1 if (drift or errors) else 0
