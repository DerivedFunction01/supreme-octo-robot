"""Domain catalogs: the shipped registries (item kinds,
status codes, wait classes) and the staleness evaluation
— split from attention.py along the catalog seam;
attention.domain.attention re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime

KINDS = ("decision", "action", "defect", "approval", "fyi")
STATUS_KINDS = (
    "followup",
    "defect",
    "improvement",
    "consolidation",
    "performance",
    "push_needed",
)

# Digest placement per status kind (Step 4): whose hands the
# kind waits in — the owner (a tap), the posting lane itself
# (agent-clearable, routed back), or the poster's closeout.
STATUS_KIND_OWNERS = {
    "push_needed": "owner",
    "defect": "lane",
    "followup": "self",
    "improvement": "owner",
    "consolidation": "owner",
    "performance": "owner",
}


def default_item_kinds() -> list:
    """Item kinds as a registry: the seed for stored data.

    status_kind marks the kinds a status post's tail may
    carry (the status-posts plan's six, defect shared).
    stale_after_hours / on_stale are the staleness pair
    (the decision-staleness plan, Step 1): the age cap in
    hours (null = no age cap) and the expiry disposition.
    The approval kind mixes: its 48 h cap governs ordinary
    approvals, while a hard-stop-bearing approval record
    is basis-only whatever the kind seed says (the
    per-record hard_stop flag wins in stale_state).
    """
    seed = (
        ("decision", "Decision", 72, "expire"),
        ("action", "Action", None, "expire"),
        ("defect", "Defect", None, "expire"),
        ("approval", "Approval", 48, "expire"),
        ("fyi", "FYI", None, "expire"),
        ("rule_proposal", "Rule proposal", 168, "expire"),
        ("followup", "Follow-up", 168, "expire"),
        ("improvement", "Improvement", 168, "expire"),
        ("consolidation", "Consolidation", 168, "expire"),
        ("performance", "Performance", 168, "expire"),
        ("push_needed", "Push needed", 24, "expire"),
    )
    return [
        {
            "kind": kind,
            "label": label,
            "status_kind": kind in STATUS_KINDS,
            "digest_owner": STATUS_KIND_OWNERS.get(kind),
            "stale_after_hours": stale_after_hours,
            "on_stale": on_stale,
        }
        for kind, label, stale_after_hours, on_stale in seed
    ]


NEEDS = ("owner_actionable", "agent_clearable", "unclassified")
TRIAGE_STATES = ("open", "acknowledged", "snoozed", "done", "muted")
TIERS = ("breakthrough", "due_today", "digest", "fyi")
PRESENCE_MODES = ("active", "focus", "away")


# The status vocabulary ships as a registry (stored data,
# spec/backend/03-declarative-rules-gap.md): new codes are
# added in-app, never by editing this file.
def _code(code, short, label, need, terminal=False):
    return {
        "code": code,
        "short": short,
        "label": label,
        "need": need,
        "terminal": terminal,
    }


def default_status_codes() -> list:
    return [
        _code("WORKING", "W", "Working", "agent_clearable"),
        _code("CONTINUE", "C", "Continue", "agent_clearable"),
        _code("DONE", "D", "Done", "agent_clearable", terminal=True),
        _code("CLOSED", "CL", "Closed", "agent_clearable", terminal=True),
        _code("PARKED", "P", "Parked", "agent_clearable"),
        _code("BLOCKED-OWNER", "BO", "Blocked — owner", "owner_actionable"),
        _code("BLOCKED-HARD", "BH", "Blocked — hard stop", "owner_actionable"),
        _code("REVIEW", "R", "Review", "owner_actionable"),
    ]


STATUS_NEED = {c["code"]: c["need"] for c in default_status_codes()}


# The handler-freshness vocabulary ships as a registry
# too (the handler-freshness plan, D3 registry-held): the
# verdict set, the binding states, the retirement causes,
# and the staleness windows the serve derives from. The
# reconciler composes verdicts; this registry names what
# a verdict may say — new entries are added in-app, never
# by editing this file.
FRESHNESS_VERDICTS = (
    "current",
    "stale",
    "dead-binding",
    "unresolvable",
    "retired-with-cause",
)
FRESHNESS_BINDING_STATES = (
    "live-seat",
    "superseded",
    "deleted",
    "unresolvable",
    "none",
)
# The fixed retirement causes; "superseded-by <handle>"
# is the one parameterized form (the successor's handle
# rides in the cause string itself).
FRESHNESS_CAUSES = ("seat-deleted", "lane-dissolved")
FRESHNESS_CAUSE_PREFIX = "superseded-by "


def default_freshness_registry() -> dict:
    """The freshness registry's shipped shape: the
    vocabularies with their labels, and the windows —
    a verdict older than verdict_stale_after_hours
    renders stale; the evidence windows (24 h seats,
    7 d lanes) bound the reconciler's last-evidence
    composition."""
    return {
        "verdicts": [
            {"code": "current", "label": "Current"},
            {"code": "stale", "label": "Stale"},
            {"code": "dead-binding", "label": "Dead binding"},
            {"code": "unresolvable", "label": "Unresolvable"},
            {"code": "retired-with-cause", "label": "Retired — with cause"},
        ],
        "binding_states": [
            {"code": "live-seat", "label": "Live seat"},
            {"code": "superseded", "label": "Superseded"},
            {"code": "deleted", "label": "Deleted"},
            {"code": "unresolvable", "label": "Unresolvable"},
            {"code": "none", "label": "No binding"},
        ],
        "causes": [
            {"code": "seat-deleted", "label": "Seat deleted"},
            {"code": "lane-dissolved", "label": "Lane dissolved"},
            {"code": "superseded-by", "label": "Superseded by"},
        ],
        "verdict_stale_after_hours": 2,
        "evidence_window_seat_hours": 24,
        "evidence_window_lane_hours": 168,
    }


def freshness_registry(state: dict) -> dict:
    """The state's freshness registry, or the shipped
    default when the state predates it."""
    return state.get("freshness") or default_freshness_registry()


def freshness_cause_ok(state: dict, cause) -> bool:
    """A cause is one of the registry's fixed codes, or
    the parameterized superseded-by form naming a
    handler the registry itself carries."""
    if not isinstance(cause, str) or not cause:
        return False
    if cause in FRESHNESS_CAUSES:
        return True
    if cause.startswith(FRESHNESS_CAUSE_PREFIX):
        successor = cause[len(FRESHNESS_CAUSE_PREFIX) :].strip()
        return successor in {h["handle"] for h in state.get("handlers", [])}
    return False


# Wait classes are a registry too: the hard-stop mark is a
# property of the class, not of any rule — hard-stop
# classes are the non-declarable floor (spec §1.10).
HARD_STOP_CLASSES = (
    "permission_card",
    "scope_expansion",
    "login",
    "external_send",
    "purchase",
    "form_submit",
    "calendar_write",
    "schedule_change",
)
RULED_CLASSES = (
    "settled_continue",
    "program_step",
    "defect_fix",
    "result_preserving",
    "followup_worktree",
    "stall_hold",
    "redrive",
    "ruling_propagation",
    "execution_risk_flag",
    "unreported_stall",
)


# The stop-reason enumeration (the stopped-lane plan,
# Step 3): the wait-class register is the enumeration.
# Each row carries the fields a stop verdict reads —
# the standing disposition (the act when the row's
# verdict fires), the evidence form the verdict reads,
# the proof the actuation records, and the ruling that
# admitted the row. A row may carry approval-reference
# flags (requires_plan / requires_goal / requires_todo):
# a stop declaring the reason must carry a reference of
# a named kind, and the verdict validates the
# reference's recorded approval — validated, the row's
# disposition fires; unvalidated, the stop stands. The
# flags are present only where the reference kind rides
# the stop line's form (plan / goal / todo): the
# permission card's own record and the purchase
# preapproval's are not stop-line references, so those
# rows carry no flag and verdict as plain hard stops.
# form_submit's evidence is None by ruling: sensitivity
# is a property of the content submitted, no registered
# artifact decides it — the row is judgment-only.
def _stop_row(name, hard_stop, disposition, evidence, proof, admitted_by, flags=None):
    entry = {
        "name": name,
        "hard_stop": hard_stop,
        "stale_after_hours": None if hard_stop else 48,
        "on_stale": "expire_blocked" if hard_stop else "expire",
        "disposition": disposition,
        "evidence": evidence,
        "proof": proof,
        "admitted_by": admitted_by,
    }
    if flags:
        entry.update(flags)
    return entry


_INCUMBENT = "incumbent wait-class register"
_STOP_ROWS = (
    _stop_row(
        "settled_continue",
        False,
        "continue",
        "the ruling of record",
        "the lane's next conforming checkpoint, work resumed inside the ruling's scope",
        _INCUMBENT,
    ),
    _stop_row(
        "program_step",
        False,
        "commission_next_step",
        "the plan of record and landed state",
        "the lane's next conforming checkpoint naming the commissioned step",
        _INCUMBENT,
    ),
    _stop_row(
        "defect_fix",
        False,
        "fix_proceeds",
        "the diagnosis on record",
        "the lane's next conforming checkpoint naming the fix under way",
        _INCUMBENT,
    ),
    _stop_row(
        "result_preserving",
        False,
        "proceed_with_proof",
        "the change and its equivalence check",
        "the equivalence check's record, then the lane's next conforming checkpoint",
        _INCUMBENT,
    ),
    _stop_row(
        "followup_worktree",
        False,
        "build_in_worktree",
        "the plan's closeout record",
        "the follow-up worktree standing, then the lane's next conforming checkpoint",
        _INCUMBENT,
    ),
    _stop_row(
        "stall_hold",
        False,
        "successor_actuation",
        "checkpoints and run records",
        "the successor's first checkpoint on the same todo",
        _INCUMBENT,
    ),
    _stop_row(
        "redrive",
        False,
        "redrive",
        "the lane's own records",
        "a new run record or a moved checkpoint inside the interval",
        _INCUMBENT,
    ),
    _stop_row(
        "ruling_propagation",
        False,
        "propagate_ruling",
        "the landed ruling and the carrier states",
        "the carriers' synced state at the next pass",
        _INCUMBENT,
    ),
    _stop_row(
        "execution_risk_flag",
        False,
        "reroute_and_continue",
        "the flag's own record — its named output — and the commission of record",
        "the re-routed artifact's venue verification, then the "
        "lane's next conforming checkpoint",
        "stopped-lane actuation commission",
    ),
    _stop_row(
        "unreported_stall",
        False,
        "press_then_successor",
        "the commission record and the ping ledger",
        "the pressed lane's checkpoint inside the interval, or the "
        "successor's first checkpoint on the same commission",
        "stopped-lane actuation commission — nine-hour-silence amendment",
    ),
    _stop_row(
        "permission_card",
        True,
        "owner_item",
        "the card record in the permission store",
        "the card's resolution record in the permission store",
        _INCUMBENT,
    ),
    _stop_row(
        "scope_expansion",
        True,
        "proceed_within_approved_scope",
        "the plan or goal of record against the claimed scope",
        "the validated reference's record, then the lane's next conforming checkpoint",
        _INCUMBENT,
        {"requires_plan": True},
    ),
    _stop_row(
        "login",
        True,
        "owner_item",
        "the target service's auth state",
        "the target service's auth state reading signed-in",
        _INCUMBENT,
    ),
    _stop_row(
        "external_send",
        True,
        "proceed_under_recorded_approval",
        "the programme's recorded send rulings",
        "the validated reference's record, then the lane's next conforming checkpoint",
        _INCUMBENT,
        {"requires_plan": True, "requires_goal": True},
    ),
    _stop_row(
        "purchase",
        True,
        "owner_item",
        "the standing preapproval records",
        "the owner's act on the digest item",
        _INCUMBENT,
    ),
    _stop_row(
        "form_submit",
        True,
        "owner_item",
        None,
        "the owner's act on the digest item",
        _INCUMBENT,
    ),
    _stop_row(
        "calendar_write",
        True,
        "proceed_under_recorded_approval",
        "the programme's recorded calendar authority",
        "the validated reference's record, then the lane's next conforming checkpoint",
        _INCUMBENT,
        {"requires_plan": True, "requires_goal": True},
    ),
    _stop_row(
        "schedule_change",
        True,
        "proceed_within_approved_scope",
        "the cron registry and the plan of record",
        "the validated reference's record, then the lane's next conforming checkpoint",
        _INCUMBENT,
        {"requires_plan": True},
    ),
)


# Candidate reasons the census window showed that no
# ruling has admitted (the stopped-lane census, §3):
# named so a stop declaring one reads as a candidate
# for the register — never as a class. Admission is by
# owner ruling only, as a row in the enumeration above.
STOP_REASON_CANDIDATES = ("venue_governance", "external_platform_cap")

# The residue forms are not reasons and never rows: a
# stop with no declared reason, and a stop whose reason
# is outside the enumeration. They surface to judgment
# and are never actuated.
STOP_RESIDUE_FORMS = ("unreasoned_stop", "unenumerated_reason")


def default_wait_classes() -> list:
    """Wait classes with their staleness pair (the
    decision-staleness plan, Step 1) and their
    stop-enumeration fields (the stopped-lane plan,
    Step 3): ruled classes carry the 48 h age cap and
    expire to record; hard-stop classes carry no age
    cap and expire only on basis evidence, to the
    blocked-unruled form."""
    return [dict(row) for row in _STOP_ROWS]


def class_is_hard_stop(wait_class: str | None, classes: list | None) -> bool:
    """The floor, keyed on the wait's registered class."""
    if wait_class is None:
        return False
    for entry in classes if classes is not None else default_wait_classes():
        if entry["name"] == wait_class:
            return bool(entry["hard_stop"])
    return wait_class in HARD_STOP_CLASSES


# --- staleness (the decision-staleness plan, Step 1) ---
# The pure evaluation over one waiting record: the record
# carries waiting_since plus its registry entry's pair
# (stale_after_hours, resolved by the caller) and its
# hard_stop mark; basis is a detector verdict
# {"stale": bool, "evidence": str} or None when no
# detector can probe the record's basis. Basis beats age;
# a null cap never age-stales; a hard-stop record stales
# only via basis, never via age.
STALE_LIVE = "live"
STALE_AGE = "stale_age"
STALE_BASIS = "stale_basis"
ON_STALE_DISPOSITIONS = ("expire", "expire_blocked")


def stale_state(record: dict, now: datetime, basis: dict | None) -> dict:
    """{"state", "evidence", "age_hours"} for one record.

    state is live | stale_age | stale_basis; evidence is
    the detector's string for a basis verdict, the cap
    comparison for an age verdict, else None."""
    age_hours = (now - record["waiting_since"]).total_seconds() / 3600
    if basis is not None and basis.get("stale"):
        return {
            "state": STALE_BASIS,
            "evidence": basis.get("evidence"),
            "age_hours": age_hours,
        }
    if record.get("hard_stop"):
        return {"state": STALE_LIVE, "evidence": None, "age_hours": age_hours}
    cap = record.get("stale_after_hours")
    if cap is not None and age_hours >= cap:
        return {
            "state": STALE_AGE,
            "evidence": f"age {age_hours:.1f}h at or over the {cap:g}h cap",
            "age_hours": age_hours,
        }
    return {"state": STALE_LIVE, "evidence": None, "age_hours": age_hours}


# The digest's expired-note row (Step 3 serves it): the
# digest row shape (services/reads/digest._row) plus the
# expiry record's own fields — nothing else.
EXPIRED_NOTE_FIELDS = (
    "kind",
    "title",
    "handle",
    "handler_label",
    "provenance",
    "provenance_label",
    "at",
    "age_label",
    "expired_at",
    "stale_basis",
    "evidence",
    "blocked",
)


def expired_note(row: dict, expired: dict) -> dict:
    """Assemble one expired-note row from a served digest
    row and its expiry record {at, basis, evidence,
    blocked}."""
    note = {field: row.get(field) for field in EXPIRED_NOTE_FIELDS[:8]}
    note.update(
        {
            "expired_at": expired["at"],
            "stale_basis": expired["basis"],
            "evidence": expired["evidence"],
            "blocked": bool(expired.get("blocked")),
        }
    )
    return note
