"""Continuation dispatch: a measured stall in a declared
programme dispatches its own continue ping to the owning
thread, repeating on the programme's cadence until the
measure itself clears — never an acknowledgement."""

from __future__ import annotations

from datetime import datetime, timedelta

from attention.domain import attention as dom
from attention.infra import wb_client
from attention.services import programmes
from attention.services.dispatch import dispatch
from attention.services.measure import registry, staffing, stamps
from attention.services.waits import engine, fulfillment
from attention.services.writes import ingest

TRIGGER_KINDS = (
    "record_gap",
    "unarmed_work",
    "no_successor",
    "blocked_uncited",
    "blocked_unverified",
)

_ACTS = {
    "record_gap": (
        "Write a conforming progress-checkpoint to the lane record "
        "naming the current state, or declare the blocker there."
    ),
    "unarmed_work": (
        "Staff the standing work and arm it, or declare it settled with its evidence."
    ),
    "no_successor": (
        "Staff the successor step now; a verdict is not a stopping condition."
    ),
    "blocked_uncited": (
        "The blocked claim is VOID — it cites no basis. Resume the "
        "work under its standing authorization, or cite the owner's "
        "actual message (thread + time) as the claim's basis."
    ),
    "blocked_unverified": (
        "The blocked claim is VOID — its cited basis carries no "
        "verification stamp. Resume the work under its standing "
        "authorization while verification is sought."
    ),
}

DEFAULT_IDLE_CLASSES = [
    "plan starts",
    "docs reconciliation",
    "performance improvements (result-preserving)",
    "consolidation and duplication",
    "doc updates",
]

_CLEARING = (
    "Sent by owner-attention's evaluator; this ping repeats on the "
    "programme's cadence and clears only when the measure moves — "
    "a reply alone does not clear it."
)


def _cadence(state: dict, handle: str, settings) -> float:
    programme = programmes.by_handle(state).get(handle)
    if programme and programme.get("cadence_minutes"):
        return programme["cadence_minutes"]
    return settings.checkpoint_cadence_minutes


def _raise_void_item(state: dict, row: dict, now: datetime) -> None:
    """A void blocked claim stands as a defect item."""
    ingest.upsert_item(
        state,
        {
            "handle": row["handle"],
            "kind": "defect",
            "source_ref": f"void-block:{row['handle']}",
            "title": (
                f"Void blocked claim — {row['handler_label']}: {row['detail']} "
                "The claim is void; the programme is treated as resumable "
                "under its standing authorization."
            ),
            "provenance": "commission",
            "status": "WORKING",
        },
        now,
    )


def _signature(state: dict, programme: dict) -> str:
    slug = programme["slug"]
    records = (state.get("record_snapshot") or {}).get(slug, {}).get("records") or {}
    trees = (state.get("worktree_snapshot") or {}).get(slug, {}).get("trees") or []
    parts = [
        ("rec", path, str(entry.get("checkpoint_at")))
        for path, entry in sorted(records.items())
    ]
    parts += [
        ("tree", tree["name"], tree.get("tip"), tree.get("dirty"), tree.get("landed"))
        for tree in trees
    ]
    lane_stamps = (state.get("stamp_snapshot") or {}).get(slug, {}).get("stamps") or {}
    parts += [
        (
            "armed",
            entry["todo"],
            (entry.get("row") or {}).get("status"),
            stamps.normalize(lane_stamps.get(entry["todo"])),
        )
        for entry in programmes.armed_entries(state, programme)
    ]
    return repr(parts)


def _is_complete(state: dict, programme: dict) -> bool:
    """Complete reads from records alone: every armed
    todo terminal and no worktree standing unlanded.
    A standing tree is unfinished work whatever any
    earlier post claimed."""
    entries = programmes.armed_entries(state, programme)
    if entries and any(
        (entry.get("row") or {}).get("status") not in ("done",) for entry in entries
    ):
        return False
    trees = (state.get("worktree_snapshot") or {}).get(programme["slug"], {}).get(
        "trees"
    ) or []
    return not any(tree.get("landed") is False for tree in trees)


def _idle_triggers(state: dict, settings, now: datetime) -> tuple[dict, bool]:
    """The scripted idle detector: no signal moved for two
    cadence intervals fires by goal state — continuation
    when incomplete, the follow-on queue when complete."""
    watch = state.setdefault("idle_watch", {})
    triggers: dict = {}
    changed = False
    for programme in programmes.active_declarations(state):
        handles = programme.get("handles") or []
        if not handles:
            continue
        slug = programme["slug"]
        signature = _signature(state, programme)
        entry = watch.get(slug)
        if entry is None or entry.get("signature") != signature:
            watch[slug] = {"signature": signature, "since": now}
            changed = True
            continue
        cadence = programme.get("cadence_minutes") or (
            settings.checkpoint_cadence_minutes
        )
        idle_minutes = (now - entry["since"]).total_seconds() / 60
        if idle_minutes < 2 * cadence:
            continue
        complete = _is_complete(state, programme)
        classes = programme.get("idle_classes") or DEFAULT_IDLE_CLASSES
        state_word = (
            "goal complete — follow-on work"
            if complete
            else "goal incomplete — continuation"
        )
        summary = f"{programme['label']} — idle {int(idle_minutes)}m, {state_word}."
        detail = (
            "No signal has moved for two cadence intervals — no "
            "checkpoint, no worktree change, no run activity. "
            "Standing work, in order: "
            + "; ".join(classes)
            + ". Post the chosen work and staff it; agent-suggested "
            "follow-ups are built in a worktree for the owner's "
            f"review — triggered is not landed. {_CLEARING}"
        )
        triggers[f"idle:{slug}"] = (handles[0], summary, detail, cadence)
    return triggers, changed


def _triggers(
    state: dict, settings, now: datetime, view: dict | None = None
) -> tuple[dict, bool]:
    triggers: dict = {}
    if view is None:
        view = staffing.build_staffing(state, settings, now)
    for row in view["rows"]:
        if row["kind"] not in TRIGGER_KINDS or not row.get("handle"):
            continue
        if row["kind"] in ("blocked_uncited", "blocked_unverified"):
            _raise_void_item(state, row, now)
        sat = (
            row.get("checkpoint_gap_minutes")
            or row.get("stall_minutes")
            or row.get("idle_minutes")
        )
        sat_text = f" It has sat {int(sat)}m." if sat else ""
        summary = f"{row['handler_label']} — {row['kind_label']}."
        detail = f"{row['detail']}{sat_text} Next act: {_ACTS[row['kind']]} {_CLEARING}"
        key = (
            f"{row['kind']}:{row.get('topic') or row.get('handle') or ''}"
            f":{row.get('handler_label') or ''}"
        )
        triggers[key] = (
            row["handle"],
            summary,
            detail,
            _cadence(state, row["handle"], settings),
        )
    for item in fulfillment.returned_items(state, now, settings):
        derived = fulfillment.derive(item, state, now, settings)
        if not derived or derived["state"] != "stalled":
            continue
        summary = f"{item['title']} — decided, unfulfilled."
        detail = (
            "The owner's decision on this item was recorded but the "
            "act never landed, past the stall bound. Next act: "
            "fulfill the recorded decision, or declare the blocker "
            f"on the item. {_CLEARING}"
        )
        triggers[f"fulfillment:{item['id']}"] = (
            item["handle"],
            summary,
            detail,
            _cadence(state, item["handle"], settings),
        )
    idle, watch_changed = _idle_triggers(state, settings, now)
    triggers.update(idle)
    return triggers, watch_changed


# ----------------------------------------------------------------
# Drain (supervision plan Step 4): a programme whose
# bundle's todos are all terminal with nothing doing is
# drained; on the transition the workbench raises the
# programme's registry tail set as fresh todos on the
# bundle and archives its standing worktrees down to
# two, through the existing archive/trim lifecycle. The
# computation and both acts live workbench-side
# (lib/drain, behind POST /api/projects/<slug>/drain);
# this leg only hands over the declarations and reports
# that a drain fired. The detector never writes a lane's
# progress checkpoint — checkpoints stay the lane's act.
#
# Registry seam: the declaration fields below are what
# Step 4 reads from a programme row. The Step 1
# supervision registry has landed: its accessor is the
# tail set's one binding (the registry is the tail's
# home), and the store row's own field is the fallback
# for a programme the registry does not declare. The
# bundle-link and tree-scope fields stay store picks —
# the registry carries no worktree roots by design.
# ----------------------------------------------------------------

# A drain pass can archive trees and drain the trim's
# origin-deletion queue; it gets a longer leash than a
# read-time pull.
DRAIN_TIMEOUT_S = 300.0


def _drain_declaration(programme: dict) -> dict:
    """The drain fields of one programme row, picked for
    the workbench detector: the tail set, the bundle
    link, and the tree scope."""
    tail = registry.drain_tail_for(programme["slug"])
    return {
        "slug": programme["slug"],
        "drain_tail": tail or programme.get("drain_tail"),
        "drain_bundles": programme.get("drain_bundles"),
        "contract_path": programme.get("contract_path"),
        "contract": programme.get("contract"),
        "worktree_roots": programme.get("worktree_roots"),
    }


def run_drain_pass(state: dict, settings, now: datetime) -> bool:
    """One drain pass over every active programme,
    grouped by workbench project. A project the
    workbench cannot serve skips its programmes — the
    pass clears nothing and retries next tick."""
    by_project: dict = {}
    for programme in programmes.active_declarations(state):
        declaration = _drain_declaration(programme)
        for project in programmes.wb_projects(programme):
            by_project.setdefault(project, []).append(declaration)
    changed = False
    for project, declarations in by_project.items():
        try:
            payload = wb_client.run_drain(
                settings.wb_url,
                project,
                declarations,
                DRAIN_TIMEOUT_S,
            )
        except wb_client.WbUnavailable:
            continue
        for outcome in payload.get("drain") or []:
            if outcome.get("raised") or outcome.get("archived"):
                changed = True
    return changed


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
    "phantom_stop": ("idle", "stall"),
    "blocked_uncited": ("idle",),
    "blocked_unverified": ("idle",),
    "owner_waiting": ("unreported",),
    "owner_waiting_unanswered": ("unreported",),
    "unrouted_defect": ("unreported",),
    "steer_undeliverable": ("unreported",),
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
        "Next act: collect the failure — read the run record, "
        "post the disposition in the programme's own record — "
        "and verify the collecting lane."
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
        parts.append(
            f"Live sessions carrying no work: {idle_text} — that idleness "
            f"is priced while open family work stands."
        )
    if row.get("conditions"):
        parts.append(f"Conditions met: {', '.join(row['conditions'])}.")
    parts.append(
        "Next act: staff a second family on a live session, or verify "
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


def run_pass(state: dict, settings, now: datetime) -> bool:
    """One continuation pass: a trigger with no ping inside
    its cadence window writes a continuation send; a trigger
    the measure no longer raises leaves the ledger."""
    view = staffing.build_staffing(state, settings, now)
    triggers, watch_changed = _triggers(state, settings, now, view)
    ledger = state.setdefault("continuation", {})
    changed = watch_changed
    if run_drain_pass(state, settings, now):
        changed = True
    if run_staffing_pass(state, settings, now, view):
        changed = True
    if run_sweep_pass(state, settings, now, view):
        changed = True
    for key in list(ledger):
        if key not in triggers:
            del ledger[key]
            changed = True
    for key, (handle, summary, detail, cadence) in triggers.items():
        entry = ledger.get(key)
        if entry and now - entry["last_ping_at"] < timedelta(minutes=cadence):
            continue
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
                # The last ping still stands undelivered in
                # the queue; a twin mint helps no one.
                continue
        send = engine.record_send(
            state,
            "continuation",
            handle,
            {"summary": summary, "detail": detail},
            now,
            rule_id="attention:continuation",
        )
        ledger[key] = {
            "last_ping_at": now,
            "pings": (entry or {}).get("pings", 0) + 1,
            "send_id": send["id"],
        }
        changed = True
    return changed
