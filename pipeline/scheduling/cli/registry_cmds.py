"""Registry report commands: validate, census, drift.
Read-only views over the registry directory and the
catalog's classification counts."""
import json
import os
import sys
from datetime import datetime, timezone

from server.entries import catalog as catalog_mod
from server import config as config_mod
from server import registry
from server.firing import schedule as schedule_mod

from cli.common import ROOT, _load
from dispatch.ledger import parse_iso
from dispatch.outbox import Outbox
from dispatch.stateio import StateError

UTC = timezone.utc


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


def _cadence_period_secs(entry):
    """One cadence of the entry, in seconds — the unit the
    unworked-ping naming measures standing time against."""
    cad = entry.cadence
    if cad["type"] == "interval":
        return schedule_mod.parse_every(cad["every"]).total_seconds()
    if cad["type"] == "daily":
        return 86400.0
    return 86400.0 * 7 / len(cad["dow"])


def _age_text(seconds):
    if seconds >= 2 * 86400:
        return f"{seconds / 86400:.1f}d"
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}h"
    return f"{max(1, round(seconds / 60))}m"


def unworked_agent_pings(entries, pings, now):
    """The liveness defects: agent jobs whose due pings stand
    unclaimed past two of their cadences. `pings` is the
    outbox's pending set (a pending ping is unacked by
    construction — ack is the claim's receipt). A ping's
    standing time runs from its creation: coalescing moves
    its due, never its birth, so a ping occurrences keep
    folding into ages honestly. Only agent-due pings of
    active agent entries are named — a scripted job's report
    pings are the operator's reading, not an executor's
    charge, and a suspended entry is a deliberate pause.
    Returns one line per defect, in job-id order."""
    lines = []
    for job_id in sorted(entries):
        entry = entries[job_id]
        if entry.kind != "agent" or entry.status != "active":
            continue
        budget = 2 * _cadence_period_secs(entry)
        for ping in pings:
            if ping.get("job_id") != job_id \
                    or ping.get("kind") != "agent-due":
                continue
            try:
                created = parse_iso(ping["created"])
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            age = (now - created).total_seconds()
            if age <= budget:
                continue
            lines.append(
                f"UNWORKED: {job_id}: agent-due ping {ping['id']} "
                f"unclaimed {_age_text(age)} — past two cadences "
                f"({_cadence_text(entry)}), coalesced "
                f"{ping.get('coalesced_count', 1)} — executor: "
                f"{entry.executor}")
    return lines


def _pending_pings():
    """The live outbox's pending pings, or [] when this
    checkout carries no live state (a clean clone, the
    gate's venue tree): liveness is a property of the live
    registry, and a tree with no outbox has no standing
    pings to name. An unreadable outbox names nothing here;
    the server's own surfaces own that defect."""
    values, _sources = config_mod.resolve()
    state_dir = os.path.join(values["home"], "state")
    if not os.path.isfile(os.path.join(state_dir, "outbox.json")):
        return []
    try:
        return Outbox(state_dir).pending()
    except (StateError, OSError, ValueError):
        return []


def cmd_census(now=None):
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
    unworked = unworked_agent_pings(
        entries, _pending_pings(), now or datetime.now(UTC))
    for line in unworked:
        print(line)
    if unworked:
        print(f"{len(unworked)} unworked agent ping(s) — agent jobs "
              f"whose due pings stand unclaimed past two cadences")
    absent = _overlay_absent_refs(entries)
    if absent:
        print(f"{len(absent)} overlay-absent body reference(s) — the live "
              f"overlay (bodies/) is not present in this checkout")
    return 1 if (errors or unworked) else 0


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
