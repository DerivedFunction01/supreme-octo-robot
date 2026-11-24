"""Staffing rows, venue family: orphan, terminal,
family-concurrency, and plan-frontier rows — split
from staffing_rows.py; attention.services.measure.
staffing_rows re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime

from attention.services.measure import lanes, registry, venue

from .staffing_common import _as_dt, _row


def _orphan_rows(state: dict, now: datetime) -> list:
    """The sweep's orphan class, from the venue
    snapshot: a run record claiming work the records
    do not support — no payload finish, evidence
    stale past the programme's window. The row names
    the record, its session, and the evidence age;
    it clears when the record is disposed (abandoned
    and re-fired) or its finish lands. Gated on the
    programme declaring the orphan class."""
    snapshot = state.get("venue_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for declaration in registry.active_declarations():
        slug = declaration["slug"]
        if "orphan" not in registry.measure_classes_for(slug):
            continue
        facts = snapshot.get(slug)
        if not facts:
            continue
        contract = registry.staffing_contract_for(slug)
        window = (
            contract["evidence_window_minutes"]
            if contract
            else venue.DEFAULT_EVIDENCE_WINDOW_MINUTES
        )
        handle = (declaration.get("handles") or [slug])[0]
        for entry in facts.get("orphans") or []:
            evidence = _as_dt(entry.get("evidence_at"))
            age = int((now - evidence).total_seconds() // 60) if evidence else None
            age_text = f"{age} minutes ago" if age is not None else "never"
            rows.append(
                _row(
                    slug,
                    handle,
                    declaration["label"],
                    "orphan_record",
                    f"Run {entry['id']} ({entry.get('job') or 'unnamed job'}) "
                    f"on {entry.get('session') or 'no session'} claims "
                    f"state {entry.get('state') or 'unknown'} with no "
                    f"payload finish; its last evidence advanced "
                    f"{age_text} against a {window:g}-minute window — "
                    f"the launch died or the record stuck, and no lane "
                    f"is advancing it. Next act: dispose the record — "
                    f"abandon the launch and re-fire the work — and "
                    f"verify the collecting lane.",
                    idle_minutes=age,
                    key=f"orphan_record:{slug}:{entry['id']}",
                    extra={
                        "run_id": entry["id"],
                        "job": entry.get("job"),
                        "session": entry.get("session"),
                    },
                )
            )
    return rows


def _terminal_rows(state: dict, now: datetime) -> list:
    """The terminal-unconsumed class, from the venue
    snapshot and the consumption snapshot: a run in a
    terminal shape — failed, closed orphaned, or
    complete with declared outputs never pulled — at
    least one cadence interval past its terminal
    instant, whose owning programme's own records
    nowhere cite it in that state. The recording is
    not consumption — the runner's collector stamped
    the record within seconds in every specimen; what
    never happened was the owning seat registering
    the outcome. The row names the run, its job and
    session, its shape, and the terminal age; it
    clears when consumption evidence lands in the
    programme's own record (a todo, a pass record, a
    lane record citing the run in its terminal state)
    or the record ages out of the measure window.
    Gated on the programme declaring the terminal
    class."""
    snapshot = state.get("venue_snapshot") or {}
    if not snapshot:
        return []
    consumption = state.get("consumption_snapshot") or {}
    rows = []
    for declaration in registry.active_declarations():
        slug = declaration["slug"]
        if "terminal" not in registry.measure_classes_for(slug):
            continue
        facts = snapshot.get(slug)
        if not facts:
            continue
        consumed = set((consumption.get(slug) or {}).get("consumed") or [])
        cadence = float(declaration.get("cadence_minutes") or 15)
        handle = (declaration.get("handles") or [slug])[0]
        for entry in facts.get("terminal_unconsumed") or []:
            if entry["id"] in consumed:
                continue
            finished = _as_dt(entry.get("finished_at"))
            age = int((now - finished).total_seconds() // 60) if finished else None
            if age is None or age < cadence:
                continue
            shape = entry.get("shape") or "failed"
            if shape == "orphaned":
                outcome = (
                    f"was closed as orphaned {age} minutes ago, its "
                    f"evidence long frozen"
                )
            elif shape == "unpulled":
                missing = entry.get("missing_outputs") or []
                outcome = (
                    f"completed {age} minutes ago with "
                    f"{len(missing)} declared outputs never pulled "
                    f"({', '.join(missing)}) — the terminal state reads "
                    f"complete while the substance is absent"
                )
            else:
                outcome = f"reached a terminal failed state {age} minutes ago"
            rows.append(
                _row(
                    slug,
                    handle,
                    declaration["label"],
                    "terminal_unconsumed",
                    f"Run {entry['id']} ({entry.get('job') or 'unnamed job'}) "
                    f"on {entry.get('session') or 'no session'} {outcome}, "
                    f"and no record of this programme cites it in that "
                    f"state — the outcome is recorded by the runner and "
                    f"unconsumed by its owner. Next act: collect the "
                    f"record — read it, post the disposition in the "
                    f"programme's own record — and verify the collecting "
                    f"lane.",
                    idle_minutes=age,
                    key=f"terminal_unconsumed:{slug}:{entry['id']}",
                    extra={
                        "run_id": entry["id"],
                        "job": entry.get("job"),
                        "session": entry.get("session"),
                        "shape": shape,
                    },
                )
            )
    return rows


def _unlanded_rows(state: dict, now: datetime) -> list:
    """The unlanded class, from the unlanded
    snapshot: a build the programme's own record
    claimed complete — a checkpoint line naming the
    commit beside a completion word — at least one
    cadence interval ago, whose commit main still
    does not carry. The claim is the checkpoint's;
    the measure is ancestry, so the row clears on
    the landing itself and never on a later
    checkpoint's word. A claim whose commit cannot
    be measured locally raises nothing. Gated on
    the programme declaring the unlanded class."""
    snapshot = state.get("unlanded_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for declaration in registry.active_declarations():
        slug = declaration["slug"]
        if "unlanded" not in registry.measure_classes_for(slug):
            continue
        facts = snapshot.get(slug)
        if not facts:
            continue
        cadence = float(declaration.get("cadence_minutes") or 15)
        handle = (declaration.get("handles") or [slug])[0]
        for entry in facts.get("claims") or []:
            if entry.get("landed") is not False:
                continue
            claimed = _as_dt(entry.get("claimed_at"))
            age = int((now - claimed).total_seconds() // 60) if claimed else None
            if age is None or age < cadence:
                continue
            rows.append(
                _row(
                    slug,
                    handle,
                    declaration["label"],
                    "unlanded_build",
                    f"Build {entry['sha']} was checkpointed complete "
                    f"{age} minutes ago and is still not on main — "
                    f"built, unlanded: the claim measured against "
                    f"main's ancestry, not the checkpoint's word. "
                    f"Next act: land it on main — a gate verdict is "
                    f"not a landing — or correct the checkpoint's "
                    f"claim.",
                    idle_minutes=age,
                    key=f"unlanded_build:{slug}:{entry['sha']}",
                    extra={
                        "sha": entry["sha"],
                        "claimed_at": entry.get("claimed_at"),
                    },
                )
            )
    return rows


def _programme_armed(state: dict, row: dict) -> list:
    """The armed rows a registry declaration owns,
    matched through its declared wb projects (the
    same linkage the frontier keys bundles by)."""
    projects = set(registry.wb_projects_for(row))
    return [
        entry
        for entry in state.get("armed_rows") or []
        if entry.get("project") in projects
        or (entry.get("row") or {}).get("programme") == row["slug"]
    ]


def _queue_due(queue: list, in_flight: set) -> list:
    """The queue's due work, in queue order: a work
    item whose gate has resolved — no gate, a landed
    marker, or a gate key no longer in the queue
    (landed work is pruned by amendment; markers
    stay and flip) — and whose family is not in
    flight. A gated item never reads due while its
    gate stands unresolved."""
    by_key = {entry.get("key"): entry for entry in queue}
    due = []
    for entry in queue:
        if entry.get("marker") is True:
            continue
        when = entry.get("staffable_when")
        if when is not None:
            gate = by_key.get(when)
            if gate is not None and not (
                gate.get("marker") is True and gate.get("landed") is True
            ):
                continue
        if entry.get("family") in in_flight:
            continue
        due.append(
            {
                "key": entry.get("key"),
                "label": entry.get("label"),
                "staffable_when": when,
            }
        )
    return due


def _lane_payload(
    state: dict, declaration: dict, contract: dict, families: dict
) -> tuple:
    """One programme's lane payload — the single
    assembly the serial-staffing row's evidence and
    the digest's per-programme lane block both serve
    from. The lane records are the measure's primary
    staffing source where the programme carries
    them: a due item an open, non-stale lane record
    covers — by queue item or by family — is
    staffed, and the counted actual reads against
    the queue-derived expected (the gate-resolved
    work items, in flight or not). Returns (block,
    lane_extra): lane_extra is the row's lane_records
    evidence, present only where the programme
    carries lane records; the block is served
    wherever a queue is named, records or none —
    declared reads None and lanes empty where no
    lane snapshot stands."""
    slug = declaration["slug"]
    queue = contract.get("staffable_queue") or []
    due = _queue_due(queue, set(families))
    facts_lanes = lanes.record_facts(state, slug)
    lane_extra = None
    declared = None
    actual = 0
    lane_list: list = []
    if facts_lanes is not None:
        family_of = {
            entry.get("key"): entry.get("family")
            for entry in queue
            if not entry.get("marker")
        }
        covered = set(facts_lanes["covered_queue_items"])
        covered |= {
            key
            for key, family in family_of.items()
            if family in facts_lanes["covered_families"]
        }
        due = [entry for entry in due if entry["key"] not in covered]
        lane_extra = {
            "declared": facts_lanes["declared"],
            "expected": len(_queue_due(queue, set())),
            "actual": facts_lanes["actual"],
            "lanes": facts_lanes["lanes"],
        }
        declared = lane_extra["declared"]
        actual = lane_extra["actual"]
        lane_list = lane_extra["lanes"]
    block = {
        "slug": slug,
        "label": declaration["label"],
        "declared": declared,
        "expected": len(_queue_due(queue, set())),
        "actual": actual,
        "lanes": lane_list,
        "queue_unstaffed": due,
    }
    return block, lane_extra


def lane_blocks(state: dict) -> dict:
    """The per-programme lane blocks the digest
    serves, keyed by slug: one block for each active
    programme whose registry contract names a
    staffable queue, absent entirely where no queue
    is named — served unconditionally, at full
    staffing as at a shortfall, so a standing
    programme row renders from the block and honest
    absence (no queue named) reads apart from every
    other absence."""
    snapshot = state.get("venue_snapshot") or {}
    blocks = {}
    for declaration in registry.active_declarations():
        contract = registry.staffing_contract_for(declaration["slug"])
        if contract is None or not contract.get("staffable_queue"):
            continue
        facts = snapshot.get(declaration["slug"]) or {}
        block, _lane_extra = _lane_payload(
            state, declaration, contract, facts.get("families") or {}
        )
        blocks[declaration["slug"]] = block
    return blocks


def _family_rows(state: dict, now: datetime, live: list, idle_since: dict) -> list:
    """The family-concurrency measure (owner
    enforcement ruling, carried as the registry's
    staffing contract): fewer families in
    flight than the contract's minimum, or all
    compute on one session while another live session
    carries none, or prerequisite-due queue work
    standing unstaffed, is a serial staffing defect
    while open family work stands. Facts come from
    the venue snapshot; the bands come from the
    registry — no evaluator constants, no programme
    names."""
    snapshot = state.get("venue_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for declaration in registry.active_declarations():
        slug = declaration["slug"]
        contract = registry.staffing_contract_for(slug)
        if contract is None:
            continue
        if "serial" not in registry.measure_classes_for(slug):
            continue
        facts = snapshot.get(slug)
        if not facts:
            continue
        if len(live) < contract["min_live_sessions"]:
            continue
        if not _programme_armed(state, declaration):
            continue
        families = facts.get("families") or {}
        carrying_sessions = {
            session
            for entry in families.values()
            for session in entry.get("sessions") or []
            if session in live
        }
        idle_sessions = []
        for name in live:
            if name in carrying_sessions:
                continue
            since = _as_dt(idle_since.get(name))
            minutes = int((now - since).total_seconds() // 60) if since else 0
            idle_sessions.append({"name": name, "idle_minutes": minutes})
        conditions = []
        if len(families) < contract["min_families_in_flight"]:
            conditions.append("fewer_than_min_families_in_flight")
        if (
            len(carrying_sessions) < contract["min_sessions_carrying_work"]
            and idle_sessions
            and families
        ):
            conditions.append(
                "all_compute_on_one_session_while_another_live_session_carries_none"
            )
        # The payload assembly is shared with the
        # digest's lane block (_lane_payload): the
        # row's queue_unstaffed and lane_records
        # evidence are the block's own fields.
        _block, lane_extra = _lane_payload(state, declaration, contract, families)
        due = _block["queue_unstaffed"]
        if lane_extra is not None and lane_extra["actual"] < lane_extra["expected"]:
            conditions.append("lane_shortfall")
        if due:
            conditions.append("prerequisite_due_family_unstaffed")
        if not conditions:
            continue
        handle = (declaration.get("handles") or [slug])[0]
        fam_text = ", ".join(
            f"{name} on {', '.join(entry.get('sessions') or []) or 'no session'}"
            for name, entry in sorted(families.items())
        )
        parts = [
            f"{len(families)} famil{'y' if len(families) == 1 else 'ies'} "
            f"in flight ({fam_text or 'none'}) against a minimum of "
            f"{contract['min_families_in_flight']}, measured from venue "
            f"run records over a {contract['evidence_window_minutes']}-"
            f"minute evidence window."
        ]
        if idle_sessions:
            idle_text = ", ".join(
                f"{s['name']} idle {s['idle_minutes']}m" for s in idle_sessions
            )
            parts.append(
                f"Live sessions carrying no work: {idle_text} — while "
                f"open family work stands, that idleness is priced here."
            )
        if due:
            names = ", ".join(entry["label"] for entry in due)
            parts.append(f"Prerequisite-due queue work stands unstaffed: {names}.")
        if lane_extra is not None:
            parts.append(
                f"Lane records: {lane_extra['actual']} open lane(s) "
                f"counted against {lane_extra['expected']} staffable "
                f"queue item(s) expected "
                f"(declared {lane_extra['declared']})."
            )
        parts.append(
            "The defect clears only on a later measure at or above the "
            "contract's bands — never on an acknowledgement."
        )
        rows.append(
            _row(
                slug,
                handle,
                declaration["label"],
                "serial_staffing",
                " ".join(parts),
                workers=facts.get("workers"),
                child_workers=facts.get("child_workers"),
                sessions_used=len(carrying_sessions),
                sessions_live=len(live),
                idle_minutes=max((s["idle_minutes"] for s in idle_sessions), default=0),
                jobs_run=facts.get("jobs"),
                key=f"serial_staffing:{slug}",
                extra={
                    "families": [
                        {
                            "name": name,
                            "sessions": entry.get("sessions") or [],
                            "runs": entry.get("runs"),
                            "child_runs": entry.get("child_runs"),
                        }
                        for name, entry in sorted(families.items())
                    ],
                    "idle_sessions": idle_sessions,
                    "conditions": conditions,
                    "queue_unstaffed": due,
                    "coordinator_caller": facts.get("coordinator_caller"),
                    **({"lane_records": lane_extra} if lane_extra is not None else {}),
                },
            )
        )
    return rows


def _frontier_rows(state: dict) -> list:
    """The plan-frontier comparison (supervision
    plan, Step 2 as amended): an armed bundle whose
    declared fan-out — its plan's eligible fanout
    steps, serial exceptions excluded — exceeds its
    actual in-flight set stands short; the shortfall
    is a staffing defect of the same class, and this
    row is the form the reminder's ping takes."""
    snapshot = state.get("frontier_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for bundle, entry in sorted(snapshot.items()):
        missing = entry.get("missing") or []
        if not missing or entry.get("plan_error"):
            continue
        slug = entry.get("slug")
        declaration = registry.for_slug(slug) if slug else None
        if declaration and "serial" not in registry.measure_classes_for(slug):
            continue
        handle = (declaration.get("handles") or [None])[0] if declaration else None
        label = declaration["label"] if declaration else bundle
        expected = entry.get("expected") or []
        actual = entry.get("actual") or []
        serial = entry.get("serial_excluded") or []
        detail = (
            f"Bundle {bundle}: the plan's declared frontier expects "
            f"{', '.join(expected)} in flight — fanout steps whose "
            f"prerequisites have landed — but the actual in-flight "
            f"set is {', '.join(actual) or 'empty'}; "
            f"{', '.join(missing)} stand unstaffed."
        )
        if serial:
            detail += (
                f" Serial exceptions excluded by the plan's own "
                f"declaration: {', '.join(serial)}."
            )
        rows.append(
            _row(
                slug or entry.get("project"),
                handle,
                label,
                "frontier_shortfall",
                detail,
                key=f"frontier_shortfall:{bundle}",
                extra={
                    "bundle": bundle,
                    "expected": expected,
                    "actual": actual,
                    "missing": missing,
                    "serial_excluded": serial,
                },
            )
        )
    return rows
