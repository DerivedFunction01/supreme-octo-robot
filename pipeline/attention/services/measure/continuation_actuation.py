"""Continuation actuation: the staffing and sweep
actuation passes (supervision plan Steps 3 and 6) —
split from continuation.py; attention.services.
measure.continuation re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from attention.domain import attention as dom
from attention.services.dispatch import dispatch
from attention.services.measure import registry, staffing
from attention.services.waits import engine

# ----------------------------------------------------------------
# Staffing actuation (supervision plan Step 3): the Step 2
# rows a defect leaves standing actuate on the tick — a
# steer to the owning coordinator through the dispatch
# path, re-posted on the registry reminder cadence until
# a later measure clears the row, escalating to main
# past the registry escalation bound naming the
# coordinator's non-response. Steers are app-issued
# records in the attention store (the sends ledger),
# visible in the app — not cron chat messages. The
# hard-stop floor is structural: only the two measure
# kinds actuate, and a row naming a hard-stop class
# never does. Prerequisite-due work rides the frontier
# row: its missing list is the unstarted steps whose
# prerequisites have landed.
#
# Addressing: the registry route where the row names
# a programme (chat → the coordinator's handle,
# todo → the route's bundle); a row the frontier
# could not attribute to a programme steers addressed
# by the bundle and project it carries — never
# dropped, never an invented slug — and never
# escalates, since no registry declaration names a
# coordinator to hold to the bound.
# ----------------------------------------------------------------

STAFFING_KINDS = ("serial_staffing", "frontier_shortfall")
STAFFING_LEDGER = "staffing_actuation"
STAFFING_RULE_ID = "attention:staffing"

# Sweep actuation (supervision plan Step 6): the
# gap-closure sweep's classes, homed in the tick —
# wb is the sender, over the registry route. Each
# row kind maps to the sweep classes it is: the pass
# actuates a row only where its programme declares
# one of the row's classes in the registry. The
# staffing kinds are the staffing pass's own and
# never actuate twice.
SWEEP_LEDGER = "sweep_actuation"
SWEEP_RULE_ID = "attention:sweep"
SWEEP_CLASSES = {
    "fleet_idle": ("serial",),
    "understaffed": ("serial",),
    "idle_unlanded": ("idle",),
    "armed_unreported": ("idle", "stall"),
    "record_gap": ("idle", "stall"),
    "no_successor": ("stall",),
    "unlanded_claim": ("stall",),
    "unarmed_work": ("orphan",),
    "orphan_record": ("orphan",),
    "terminal_unconsumed": ("terminal",),
    "unlanded_build": ("unlanded",),
    "phantom_stop": ("idle", "stall"),
    "blocked_uncited": ("idle",),
    "blocked_unverified": ("idle",),
    "owner_waiting": ("unreported",),
    "owner_waiting_unanswered": ("unreported",),
    "unrouted_defect": ("unreported",),
    "steer_undeliverable": ("unreported",),
    "step_overdue": ("stall",),
}
_SWEEP_NEXT_ACT = {
    "fleet_idle": (
        "Next act: spread the queued work onto the idle session, "
        "or verify family by family that no parallelizable work stands."
    ),
    "understaffed": (
        "Next act: staff a second worker on a live session, or "
        "verify that no parallelizable work stands."
    ),
    "idle_unlanded": ("Next act: land the done work, or staff its landing."),
    "armed_unreported": (
        "Next act: the lane posts a conforming checkpoint naming "
        "the todo, or its exact blocker."
    ),
    "record_gap": (
        "Next act: the lane posts a conforming checkpoint, or its exact blocker."
    ),
    "no_successor": (
        "Next act: staff the successor step now; a verdict is not a stopping condition."
    ),
    "unlanded_claim": ("Next act: land the claimed work, or correct the claim."),
    "unarmed_work": (
        "Next act: arm the work — a doing todo on the bundle — or "
        "archive the standing tree."
    ),
    "orphan_record": (
        "Next act: dispose the record — abandon the launch and "
        "re-fire the work — and verify the collecting lane."
    ),
    "terminal_unconsumed": (
        "Next act: collect the record — read it, post the "
        "disposition in the programme's own record — and "
        "verify the collecting lane."
    ),
    "unlanded_build": (
        "Next act: land the build on main — a gate verdict is "
        "not a landing — or correct the checkpoint's claim."
    ),
    "phantom_stop": (
        "Next act: cite the owner's message (thread and time) with "
        "a verification stamp, or resume the work under its "
        "standing authorization."
    ),
    "blocked_uncited": (
        "Next act: state the blocked basis with its cited owner "
        "message and time, or resume the work."
    ),
    "blocked_unverified": ("Next act: get the citation verified, or resume the work."),
    "owner_waiting": (
        "Next act: staff the owner-waiting deliverable — it outranks queue position."
    ),
    "owner_waiting_unanswered": (
        "Next act: answer the owner's ask about the waiting item before lane work."
    ),
    "unrouted_defect": (
        "Next act: notify the owning thread with the defect's routing."
    ),
    "steer_undeliverable": (
        "Next act: repair the delivery route — an undeliverable steer is a defect."
    ),
}
_SWEEP_CLEARING = (
    "Sent by wb — this steer repeats on the registry reminder "
    "cadence and clears only when a later measure shows the "
    "condition resolved; a reply alone does not clear it."
)

_STAFFING_CLEARING = (
    "Sent by the app's supervision measure — this steer "
    "repeats on the registry reminder cadence and clears "
    "only when a later measure shows the bands met; a "
    "reply alone does not clear it."
)


def _staffing_slug(row: dict) -> str | None:
    """The programme a row names, or None where the
    frontier could not attribute it: the row's topic
    is a programme slug only where the registry
    declares it."""
    topic = row.get("topic")
    return topic if topic and registry.for_slug(topic) else None


def _staffing_cadence(slug: str | None, settings) -> float:
    """Re-post cadence in minutes: the ruled contract's
    reminder cadence where one exists, else the
    programme's cadence, else the lane default."""
    if slug:
        contract = registry.staffing_contract_for(slug)
        if contract:
            return float(contract["reminder_cadence_minutes"])
        declaration = registry.for_slug(slug)
        if declaration:
            return float(declaration["cadence_minutes"])
    return settings.checkpoint_cadence_minutes


def _staffing_bound_hours(slug: str | None) -> float | None:
    """The escalation bound in hours, or None where no
    registry declaration names the coordinator."""
    if not slug:
        return None
    declaration = registry.for_slug(slug)
    if declaration:
        return float(declaration["escalation_hours"])
    return None


def _commission_text(queue_due: list, contract) -> str:
    """The commission form of a serial steer's next
    act: the due queue items named in queue order as
    the acts to staff, then one gate clause for each
    later queue item still gated on an unlanded
    marker."""
    labels = [entry["label"] for entry in queue_due]
    text = f"Staffing commission — staff: {labels[0]}"
    for label in labels[1:]:
        text += f"; then {label}"
    text += "."
    queue = (contract or {}).get("staffable_queue") or []
    by_key = {entry.get("key"): entry for entry in queue}
    due_keys = {entry.get("key") for entry in queue_due}
    for entry in queue:
        when = entry.get("staffable_when")
        if entry.get("key") in due_keys or not when:
            continue
        gate = by_key.get(when) or {}
        if gate.get("marker") is True and gate.get("landed") is not True:
            text += f" {entry['label']} staffs on {gate.get('label')}."
    return text


def _serial_steer(row: dict, slug: str | None, escalated: bool, bound) -> tuple:
    """The steer for a serial staffing row: families in
    flight, idle sessions, and the unstaffed remainder,
    in prose — lists ride inside sentences, never as a
    joined item string."""
    families = row.get("families") or []
    fam_text = (
        ", ".join(
            f"{entry['name']} on "
            f"{', '.join(entry.get('sessions') or []) or 'no session'}"
            for entry in families
        )
        or "none"
    )
    idle = row.get("idle_sessions") or []
    idle_text = ", ".join(
        f"{entry['name']} idle {entry['idle_minutes']}m" for entry in idle
    )
    contract = registry.staffing_contract_for(slug) if slug else None
    minimum = contract["min_families_in_flight"] if contract else None
    band = f" against a minimum of {minimum}" if minimum else ""
    summary = (
        f"{row['handler_label']} — serial staffing: "
        f"{len(families)} famil{'y' if len(families) == 1 else 'ies'} "
        f"in flight"
        + (f", {idle_text} carrying nothing" if idle else "")
        + (" — escalated to main" if escalated else "")
        + "."
    )
    parts = [
        f"{len(families)} famil{'y' if len(families) == 1 else 'ies'} in flight "
        f"({fam_text}){band}, measured from venue run records over the "
        f"contract's evidence window."
    ]
    if idle:
        parts.append(f"Live sessions carrying no work: {idle_text}.")
    if row.get("conditions"):
        parts.append(f"Conditions met: {', '.join(row['conditions'])}.")
    queue_due = row.get("queue_unstaffed") or []
    if queue_due:
        parts.append(_commission_text(queue_due, contract))
    else:
        floor = f" of {minimum}" if minimum else ""
        parts.append(
            f"Next act: staff distinct register families up to the "
            f"contract's floor{floor} in active work, or verify "
            "family by family that no parallelizable work stands."
        )
    if escalated:
        parts.insert(
            0,
            f"Escalated to main: {row.get('handle')} has not responded to "
            f"this defect for {bound:g}h — past the registry escalation "
            f"bound. The coordinator's non-response is named here, not "
            f"cleared.",
        )
    parts.append(_STAFFING_CLEARING)
    return summary, " ".join(parts)


def _frontier_steer(row: dict, escalated: bool, bound) -> tuple:
    """The steer for a frontier shortfall row: the
    plan's expected frontier against the actual
    in-flight set, naming the missing prerequisite-due
    steps."""
    expected = row.get("expected") or []
    actual = row.get("actual") or []
    missing = row.get("missing") or []
    serial = row.get("serial_excluded") or []
    summary = (
        f"{row['handler_label']} — frontier shortfall: "
        f"{len(missing)} step{'s' if len(missing) != 1 else ''} unstaffed "
        f"in bundle {row.get('bundle')}"
        + (" — escalated to main" if escalated else "")
        + "."
    )
    parts = [
        f"Bundle {row.get('bundle')}: the plan's declared frontier expects "
        f"{', '.join(expected)} in flight — fanout steps whose prerequisites "
        f"have landed — but the actual in-flight set is "
        f"{', '.join(actual) or 'empty'}; {', '.join(missing)} stand "
        f"unstaffed."
    ]
    if serial:
        parts.append(
            f"Serial exceptions excluded by the plan's own declaration: "
            f"{', '.join(serial)}."
        )
    parts.append(
        "Next act: staff the missing steps now; a verdict is not a stopping condition."
    )
    if escalated:
        parts.insert(
            0,
            f"Escalated to main: {row.get('handle')} has not responded to "
            f"this defect for {bound:g}h — past the registry escalation "
            f"bound. The coordinator's non-response is named here, not "
            f"cleared.",
        )
    parts.append(_STAFFING_CLEARING)
    return summary, " ".join(parts)


def _staffing_steer(row: dict, slug: str | None, escalated: bool, bound) -> tuple:
    """One row's steer text, by kind."""
    if row["kind"] == "frontier_shortfall":
        return _frontier_steer(row, escalated, bound)
    return _serial_steer(row, slug, escalated, bound)


def _staffing_route(row: dict, slug: str | None) -> tuple:
    """(handle, target) for one row's steer: the registry
    route where the row names a programme — a chat route
    resolves to the coordinator's thread, a todo route
    to the route's bundle — else the bundle and project
    the row itself carries."""
    if slug:
        route = registry.coordinator_route_for(slug)
        handle = row.get("handle") or (route or {}).get("handle") or slug
        if route and route.get("kind") == "todo":
            return handle, route.get("bundle")
        return handle, None
    return row.get("topic") or row.get("bundle") or "main", None


def _staffing_key(row: dict) -> str:
    """The ledger key for one defect row, derived from
    the served fields: the served view pops the
    measure's private `_key` before serving, so the
    actuation keys on kind plus the row's own
    identity — the bundle for a frontier row, the
    programme topic for a serial row."""
    identity = row.get("bundle") or row.get("topic") or row.get("handle") or ""
    return f"{row.get('kind')}:{identity}"


def _actuate_rows(
    state: dict,
    settings,
    now: datetime,
    rows: dict,
    ledger_name: str,
    rule_id: str,
    steer_fn,
) -> bool:
    """One actuation ledger's mechanics, shared by the
    staffing and sweep passes: a row standing in the
    served view steers its owning coordinator — exactly
    one steer per tick, re-posted on the registry
    reminder cadence until a later measure clears the
    row, escalating to main past the registry
    escalation bound. A row the measure no longer
    raises leaves the ledger. The caller filters kinds
    and gates classes before handing rows in."""
    ledger = state.setdefault(ledger_name, {})
    changed = False
    for key in list(ledger):
        if key not in rows:
            del ledger[key]
            changed = True
    for key, row in rows.items():
        slug = _staffing_slug(row)
        cadence = _staffing_cadence(slug, settings)
        entry = ledger.get(key)
        if entry and now - entry["last_ping_at"] < timedelta(minutes=cadence):
            continue
        handle = row.get("handle")
        if handle:
            handler = next(
                (h for h in state.get("handlers", []) if h["handle"] == handle),
                None,
            )
            if handler is not None and handler.get("retired"):
                continue
        if entry and entry.get("send_id"):
            prior = next(
                (x for x in state.get("sends", []) if x["id"] == entry["send_id"]),
                None,
            )
            if prior is not None and dispatch.state_of(prior, now) in (
                "undispatched",
                "claimed",
            ):
                # The last steer still stands undelivered
                # in the queue; a twin mint helps no one.
                continue
        bound = _staffing_bound_hours(slug)
        first_seen = (entry or {}).get("first_seen_at")
        escalated = bool(
            bound is not None
            and first_seen is not None
            and (now - first_seen).total_seconds() / 3600 >= bound
        )
        send_handle, target = _staffing_route(row, slug)
        if escalated:
            target = "main"
        summary, detail = steer_fn(row, slug, escalated, bound)
        send = engine.record_send(
            state,
            "continuation",
            send_handle,
            {"summary": summary, "detail": detail},
            now,
            rule_id=rule_id,
            target=target,
        )
        if send is None:
            continue
        ledger[key] = {
            "first_seen_at": first_seen or now,
            "last_ping_at": now,
            "pings": (entry or {}).get("pings", 0) + 1,
            "send_id": send["id"],
            "escalated": escalated,
        }
        changed = True
    return changed


def run_staffing_pass(
    state: dict, settings, now: datetime, view: dict | None = None
) -> bool:
    """One staffing actuation pass: each Step 2 defect
    row standing in the served view steers its owning
    coordinator — exactly one steer per tick, re-posted
    on the registry reminder cadence until a later
    measure clears the row, escalating to main past
    the registry escalation bound. A row the measure
    no longer raises leaves the ledger; a row naming
    a hard-stop class never actuates."""
    if view is None:
        view = staffing.build_staffing(state, settings, now)
    rows = {}
    for row in view.get("rows") or []:
        kind = row.get("kind")
        if dom.class_is_hard_stop(kind, state.get("wait_classes")):
            continue
        if kind not in STAFFING_KINDS:
            continue
        rows[_staffing_key(row)] = row
    return _actuate_rows(
        state,
        settings,
        now,
        rows,
        STAFFING_LEDGER,
        STAFFING_RULE_ID,
        _staffing_steer,
    )


def _overdue_commission(row: dict) -> str:
    """The commission form of an overdue step's next
    act, in the staffing commission's form: the step
    named as the act to staff, in its plan. An overdue
    step is a commission, not a report."""
    step_title = row.get("step_title") or ""
    label = f"step {row.get('step')}"
    if step_title:
        label += f" ({step_title})"
    label += f" of plan {row.get('plan_title') or row.get('plan')}"
    return (
        f"Staffing commission — staff: {label}. The step stands "
        f"overdue against its own estimate; build it, or "
        f"re-estimate it in the plan with its reason stated."
    )


def _sweep_steer(row: dict, slug: str | None, escalated: bool, bound) -> tuple:
    """The steer for a sweep-class row: the row's
    measured sentence plus its next act, sent by wb."""
    summary = (
        f"{row['handler_label']} — {row['kind_label']}"
        + (" — escalated to main" if escalated else "")
        + "."
    )
    parts = [row.get("detail") or ""]
    next_act = _SWEEP_NEXT_ACT.get(row["kind"])
    if row["kind"] == "step_overdue":
        next_act = _overdue_commission(row)
    if next_act:
        parts.append(next_act)
    if escalated:
        parts.insert(
            0,
            f"Escalated to main: {row.get('handle')} has not responded to "
            f"this defect for {bound:g}h — past the registry escalation "
            f"bound. The coordinator's non-response is named here, not "
            f"cleared.",
        )
    parts.append(_SWEEP_CLEARING)
    return summary, " ".join(parts)


def run_sweep_pass(
    state: dict, settings, now: datetime, view: dict | None = None
) -> bool:
    """One sweep actuation pass: each sweep-class defect
    row standing in the served view steers its owning
    coordinator, sent by wb over the registry route —
    the gap-closure sweep's classes, homed in the tick.
    A row actuates only where its programme declares
    one of the row's classes; a row the frontier could
    not attribute actuates without a declaration to
    gate it, and never escalates. A row naming a
    hard-stop class never actuates, and the staffing
    kinds are the staffing pass's own — they never
    actuate twice."""
    if view is None:
        view = staffing.build_staffing(state, settings, now)
    rows = {}
    for row in view.get("rows") or []:
        kind = row.get("kind")
        if dom.class_is_hard_stop(kind, state.get("wait_classes")):
            continue
        if row.get("owner_only"):
            # An owner-only row routes to the digest:
            # it stands in the served staffing view the
            # digest embeds, escalates there on the
            # standing bound, and never steers a
            # coordinator for an act that is the owner's.
            continue
        classes = SWEEP_CLASSES.get(kind)
        if classes is None:
            continue
        slug = _staffing_slug(row)
        if slug is not None:
            declared = registry.measure_classes_for(slug)
            if not any(c in declared for c in classes):
                continue
        rows[_staffing_key(row)] = row
    return _actuate_rows(
        state, settings, now, rows, SWEEP_LEDGER, SWEEP_RULE_ID, _sweep_steer
    )
