"""Pure domain rules for owner-attention (spec/backend/02-domain).

Plain dicts in, plain values out; labels live in services.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

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
)


def default_wait_classes() -> list:
    """Wait classes with their staleness pair (the
    decision-staleness plan, Step 1): ruled classes carry
    the 48 h age cap and expire to record; hard-stop
    classes carry no age cap and expire only on basis
    evidence, to the blocked-unruled form."""
    classes = [
        {
            "name": name,
            "hard_stop": False,
            "stale_after_hours": 48,
            "on_stale": "expire",
        }
        for name in RULED_CLASSES
    ]
    classes += [
        {
            "name": name,
            "hard_stop": True,
            "stale_after_hours": None,
            "on_stale": "expire_blocked",
        }
        for name in HARD_STOP_CLASSES
    ]
    return classes


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


# Condition fields are a registry: poster-settable fields
# ride in on the wait; derived fields are computed by the
# server and can never be posted (the self-attestation fix).
def _field(name, ftype, source):
    return {
        "name": name,
        "type": ftype,
        "source": source,
        "poster_settable": source == "poster",
    }


def default_fields() -> list:
    return [
        _field("wait_class", "enum", "poster"),
        _field("status_code", "enum", "poster"),
        _field("kind", "enum", "poster"),
        _field("handle", "string", "poster"),
        _field("program_approved", "bool", "poster"),
        _field("reversible", "bool", "poster"),
        _field("in_budget", "bool", "poster"),
        _field("only_blocker", "bool", "poster"),
        _field("age_minutes", "number", "derived"),
        _field("repeat_count", "number", "derived"),
        _field("presence", "enum", "derived"),
        _field("handler_status_code", "enum", "derived"),
    ]


# Post templates are data (kind, version, audience, slots,
# text): rules and agents bind slot values, never free text.
def _template(kind, audience, slots, text):
    return {
        "kind": kind,
        "version": 1,
        "audience": audience,
        "slots": slots,
        "text": text,
    }


def default_templates() -> list:
    return [
        _template(
            "continue-settled",
            "chat",
            ["summary"],
            "Continue — settled under a standing rule: {summary}",
        ),
        _template(
            "continue-standing-rule",
            "chat",
            ["summary"],
            "Continue under the standing rule: {summary}",
        ),
        _template(
            "grant-program",
            "chat",
            ["summary", "scope"],
            "Granted — program step inside the approved scope: "
            "{summary}. Scope restated: {scope}",
        ),
        _template(
            "grant-followup",
            "chat",
            ["summary"],
            "Granted — build it in a worktree for accept / reject / modify: {summary}",
        ),
        _template(
            "stall-nudge",
            "chat",
            ["summary", "age_minutes"],
            "Stall check — no report in {age_minutes}m on: {summary}. Status?",
        ),
        _template(
            "status-request",
            "chat",
            ["summary"],
            "Status request — {summary}: reply with the status "
            "form (done / ongoing / blockers).",
        ),
        _template(
            "approval-surface",
            "main",
            ["summary", "handle"],
            "Approval waiting — {summary} ({handle}).",
        ),
        _template(
            "record-reconcile", "chat", ["summary"], "Reconcile the record: {summary}"
        ),
        _template(
            "idleness-nudge",
            "chat",
            ["summary"],
            "Idle with work outstanding: {summary}. Continue, or report PARKED.",
        ),
        _template("venue-question", "chat", ["summary"], "Venue question: {summary}"),
        _template("venue-ping", "chat", ["summary"], "Venue check: {summary}"),
        _template(
            "verdict",
            "chat",
            ["summary", "verb", "note"],
            "Owner verdict — {verb}: {summary} {note}",
        ),
        _template(
            "reply", "chat", ["summary", "note"], "Owner reply on {summary} — {note}"
        ),
        _template(
            "status-ping",
            "chat",
            ["summary"],
            "Status ping — the owner asks for a fresh status on: {summary}. "
            "Reply with the status form (done / ongoing / blockers).",
        ),
        _template(
            "continuation",
            "chat",
            ["summary", "detail"],
            "Continue — {summary} {detail}",
        ),
        _template(
            "status-ping-urgent",
            "chat",
            ["summary"],
            "Status ping (second) — still no fresh status on: {summary}. "
            "Reply now with the status form (done / ongoing / blockers).",
        ),
        _template(
            "parallelize",
            "chat",
            ["summary"],
            "Parallelize — the owner directs this work staffed across "
            "the live fleet now: {summary}",
        ),
        _template(
            "commission",
            "chat",
            ["summary"],
            "Commission from the owner: {summary}",
        ),
    ]


# Program-scope grants (the sweeper's 5A conditions): all
# four flags must hold before that rule may auto-apply.
PROGRAM_FLAGS = ("program_approved", "reversible", "in_budget", "only_blocker")


def _rule(rule_id, wait_class, scope, requires=(), priority=100):
    return {
        "id": rule_id,
        "match": {
            "wait_class": wait_class,
            "status_code": None,
            "kind": None,
            "handle": None,
        },
        "where": None,
        "action": {"type": "auto_apply"},
        "scope": scope,
        "requires": list(requires),
        "priority": priority,
        "on_scope_miss": "pending",
        "trigger": {"on": "on_enter"},
        "guards": {},
        "mode": "active",
    }


def default_rules() -> list:
    """The shipped rule set: the sweeper taxonomy as data."""
    return [
        _rule("settled-continue", "settled_continue", "always", priority=10),
        _rule("program-step", "program_step", "always", PROGRAM_FLAGS, 20),
        _rule("defect-fix", "defect_fix", "always", priority=30),
        _rule("result-preserving", "result_preserving", "always", priority=40),
        _rule("followup-worktree", "followup_worktree", "away", priority=50),
        _rule("stall-hold", "stall_hold", "away", priority=60),
        _rule("redrive", "redrive", "active", priority=70),
        _rule("ruling-propagation", "ruling_propagation", "active", priority=80),
    ]


# Owner-action verbs (§1.13; D-A5: the vocabulary is
# served domain defaults in v1, not registry data —
# verbs are semantics, not labels).
VERB_LABELS = {
    "approve_once": "Approve",
    "approve_rule": "Approve + make rule",
    "deny": "Deny",
    "pick": "Pick",
    "rule_it": "Rule it standing",
    "accept": "Accept",
    "reject": "Reject",
    "modify": "Modify",
    "push": "Push",
    "close_on_verify": "Close — verified",
    "reply": "Reply",
    "snooze": "Snooze",
    "done": "Done",
    "mute_type": "Mute type",
    "leave_it": "Leave it",
    "continue": "Continue",
    "go": "Go",
    "accept_review": "Accept review",
    "reject_incomplete": "Reject as incomplete",
    "park": "Park",
    "close": "Close",
    "status_ping": "Status ping",
    "parallelize": "Parallelize",
    "critic_pass": "Critic pass",
    "perf_pass": "Performance pass",
    "consolidation_pass": "Consolidation pass",
    "organize_pass": "Organize pass",
    "stop": "Stop",
    "resume": "Resume",
    "accept_proposal": "Accept — create the rule",
    "reject_proposal": "Reject proposal",
}
# The named exception (§1.13): bookmarks send nothing.
BOOKMARK_VERBS = ("snooze", "done", "mute_type", "leave_it")
# Verdict-shaped taps the repetition counter reads;
# reply/modify carry their judgment in the note and are
# never counted toward a rule proposal.
COUNTED_VERBS = (
    "approve_once",
    "deny",
    "pick",
    "accept",
    "reject",
    "push",
    "close_on_verify",
    "continue",
    "go",
    "accept_review",
    "reject_incomplete",
)
PROPOSAL_THRESHOLD = 3


def _action_rule(rule_id, match, verb, note):
    return {
        "id": rule_id,
        "match": match,
        "verb": verb,
        "mode": "shadow",
        "created_from": "seed",
        "note": note,
    }


def default_action_rules() -> list:
    """The §1.13 seeds R1–R6, all shadow (D-A6). R1–R3
    are evaluated now; R4–R6 are recorded with their
    triggers for the follow-on tranche."""
    return [
        _action_rule(
            "R1-defect-clears-on-terminal",
            {"kind": "defect"},
            "close_on_verify",
            "A defect item closes when its handler posts a terminal status.",
        ),
        _action_rule(
            "R2-stale-status-pings",
            {"status_code": ["WORKING", "CONTINUE"]},
            "status_ping",
            "A stale working status draws a status ping.",
        ),
        _action_rule(
            "R3-perf-clears-as-fyi",
            {"kind": "performance", "provenance": "offer"},
            "clear_fyi",
            "Result-preserving performance clears as FYI.",
        ),
        _action_rule(
            "R4-done-with-conflict-returns",
            {"status_code": ["DONE", "CLOSED"]},
            "reject_incomplete",
            "Deferred: reads the workbench derivation.",
        ),
        _action_rule(
            "R5-ui-done-draws-critic",
            {"status_code": ["DONE", "CLOSED"], "ui_surface": True},
            "critic_pass",
            "Deferred: dispatches a commission.",
        ),
        _action_rule(
            "R6-completion-proposes-consolidation",
            {"status_code": ["DONE", "CLOSED"]},
            "consolidation_proposal",
            "Deferred: reads the workbench derivation.",
        ),
    ]


def normalize_rule(rule: dict) -> dict:
    """Fill the v2 fields on a stored rule (older rules carry
    a bare string action and no priority/trigger/mode)."""
    rule = dict(rule)
    action = rule.get("action", "auto_apply")
    if isinstance(action, str):
        action = {"type": action}
    rule["action"] = action
    rule.setdefault("where", None)
    rule.setdefault("requires", [])
    rule.setdefault("priority", 100)
    rule.setdefault("on_scope_miss", "pending")
    rule.setdefault("trigger", {"on": "on_enter"})
    rule.setdefault("guards", {})
    rule.setdefault("mode", "active")
    return rule


def action_type(rule: dict) -> str:
    return normalize_rule(rule)["action"]["type"]


def ordered_rules(rules: list) -> list:
    """Evaluation order: explicit priority, then stored
    order as the tiebreak (stable)."""
    indexed = sorted(
        enumerate(rules),
        key=lambda pair: (normalize_rule(pair[1]).get("priority", 100), pair[0]),
    )
    return [rule for _, rule in indexed]


# --- condition grammar: flat match shorthand + where tree ---
OPS = ("eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "exists")
OP_LABELS = {
    "eq": "is",
    "ne": "is not",
    "in": "is one of",
    "not_in": "is none of",
    "gt": "is over",
    "gte": "is at least",
    "lt": "is under",
    "lte": "is at most",
    "exists": "is set",
}
TRIGGER_LABELS = {
    "on_enter": "When the wait arrives",
    "on_age": "When it ages past",
    "on_repeat": "On the Nth matching wait",
    "on_state_change": "When the thread's status changes",
    "on_presence_enter": "When presence enters the scope",
}
ACTION_LABELS = {
    "auto_apply": "Apply it (clear the wait)",
    "surface": "Surface it to me",
    "hold": "Hold it",
    "post": "Post into the thread",
    "post_and_apply": "Post into the thread, then apply",
}


def eval_leaf(leaf: dict, values: dict) -> bool:
    field, op = leaf.get("field"), leaf.get("op")
    actual = values.get(field)
    if op == "exists":
        return actual is not None
    wanted = leaf.get("value")
    if op == "eq":
        return actual == wanted
    if op == "ne":
        return actual != wanted
    if op == "in":
        return actual in (wanted or [])
    if op == "not_in":
        return actual not in (wanted or [])
    if actual is None or wanted is None:
        return False
    if op == "gt":
        return actual > wanted
    if op == "gte":
        return actual >= wanted
    if op == "lt":
        return actual < wanted
    if op == "lte":
        return actual <= wanted
    return False


def eval_where(node, values: dict) -> bool:
    """A where tree: leaves {field, op, value} under all /
    any / not. None (no tree) is true."""
    if node is None:
        return True
    if "all" in node:
        return all(eval_where(child, values) for child in node["all"])
    if "any" in node:
        return any(eval_where(child, values) for child in node["any"])
    if "not" in node:
        return not eval_where(node["not"], values)
    return eval_leaf(node, values)


def rule_matches(rule: dict, values: dict) -> bool:
    """Flat match (equality per non-null field) AND the where
    tree AND every required flag, all over the value set
    (poster fields + derived fields)."""
    match = rule.get("match") or {}
    for field, wanted in match.items():
        if wanted is None:
            continue
        if isinstance(wanted, list):
            if values.get(field) not in wanted:
                return False
        elif values.get(field) != wanted:
            return False
    if not eval_where(rule.get("where"), values):
        return False
    return all(values.get(flag) for flag in rule.get("requires", ()))


def _where_classes(node, found: set) -> None:
    if not isinstance(node, dict):
        return
    for key in ("all", "any"):
        for child in node.get(key, []) or []:
            _where_classes(child, found)
    if "not" in node:
        _where_classes(node["not"], found)
    if node.get("field") == "wait_class":
        value = node.get("value")
        if isinstance(value, list):
            found.update(value)
        elif value is not None:
            found.add(value)


def rule_is_legal(rule: dict, classes: list | None = None) -> bool:
    """The floor: no applying rule may select a hard-stop
    class — by flat match or by a where leaf on wait_class."""
    rule = normalize_rule(rule)
    if rule["action"]["type"] not in ("auto_apply", "post_and_apply"):
        return True
    selected = set()
    wanted = (rule.get("match") or {}).get("wait_class")
    if wanted is not None:
        selected.add(wanted)
    _where_classes(rule.get("where"), selected)
    return not any(class_is_hard_stop(name, classes) for name in selected)


def classify_need(status_code: str | None, codes: list | None = None) -> str:
    """Need axis: a lookup in the status-code registry (§1.3)."""
    if not status_code:
        return "unclassified"
    for entry in codes if codes is not None else default_status_codes():
        if entry["code"] == status_code:
            return entry["need"]
    return "unclassified"


def assign_tier(item: dict, allowlist: list, now: datetime) -> str:
    """Tier axis by rule + allowlist, never by poster request (§2.2)."""
    if [item["handle"], item["kind"]] in allowlist:
        return "breakthrough"
    if item["kind"] == "fyi":
        return "fyi"
    due = item.get("due_at")
    if due is not None and due.date() <= now.date():
        return "due_today"
    return "digest"


def band_of(item: dict) -> str:
    """The today band an item renders in (§2.4 ordering)."""
    if item["tier"] == "breakthrough":
        return "breakthrough"
    if item["tier"] == "due_today":
        return "due_today"
    if item["tier"] == "fyi":
        return "fyi"
    if item["need"] == "owner_actionable":
        return "needs_decision"
    return "waiting"


def snooze_returned(item: dict, now: datetime) -> bool:
    """A snoozed item returns at its time, or on activity (§2.3)."""
    if item.get("snooze_return_at") is not None:
        return now >= item["snooze_return_at"]
    return False


def visible(item: dict, now: datetime) -> bool:
    """Whether an item is on the owner's surfaces right now."""
    if item["triage"] in ("done", "muted"):
        return False
    if item["triage"] == "snoozed" and not snooze_returned(item, now):
        return False
    return True


def order_key(item: dict, handler_order: dict) -> tuple:
    """Transparent, stable ordering (§2.4): band rank, then
    due time, then handler registry order, then age."""
    band_rank = {
        "breakthrough": 0,
        "due_today": 1,
        "needs_decision": 2,
        "waiting": 3,
        "fyi": 4,
    }[band_of(item)]
    due = item.get("due_at") or datetime.max.replace(tzinfo=now_tz(item))
    return (
        band_rank,
        due,
        handler_order.get(item["handle"], 99),
        item["waiting_since"],
    )


def now_tz(item: dict):
    return item["waiting_since"].tzinfo


def waiting_label(waiting_since: datetime, now: datetime) -> str:
    """Human age of a wait, e.g. '3 days', '2 h', 'just now'."""
    delta = now - waiting_since
    if delta < timedelta(hours=1):
        return "just now"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)} h"
    days = delta.days
    return f"{days} day" if days == 1 else f"{days} days"


def next_window(now: datetime, windows: tuple[str, ...]) -> datetime:
    """The next digest window at or after now (settings times)."""
    candidates = []
    for text in windows:
        hour, minute = (int(part) for part in text.split(":"))
        at = datetime.combine(now.date(), time(hour, minute), tzinfo=now.tzinfo)
        if at <= now:
            at += timedelta(days=1)
        candidates.append(at)
    return min(candidates)


def scope_matches(scope: str, mode: str, focus_scope: str) -> bool:
    """Whether a rule class's presence scope covers the mode."""
    if scope == "always":
        return True
    if scope == "away":
        return mode == "away" or (mode == "focus" and focus_scope == "away")
    if scope == "active":
        return mode == "active" or (mode == "focus" and focus_scope == "active")
    return False


def trigger_due(rule: dict, wait: dict, values: dict, ctx: dict) -> bool:
    """Whether a rule's trigger fires for this wait in this
    pass. ctx carries pass facts: presence_entered (bool)."""
    trigger = normalize_rule(rule).get("trigger") or {"on": "on_enter"}
    on = trigger.get("on", "on_enter")
    if on == "on_enter":
        # Due on every pass while pending: a scope-held
        # wait must re-evaluate when presence changes;
        # one-shotness comes from decisions and guards.
        return True
    if on == "on_age":
        return values.get("age_minutes", 0) >= trigger.get("after_minutes", 0)
    if on == "on_repeat":
        return values.get("repeat_count", 0) >= trigger.get("count", 1)
    if on == "on_state_change":
        return wait.get("fact_hash") != wait.get("last_fact_hash")
    if on == "on_presence_enter":
        return bool(ctx.get("presence_entered"))
    return False


def decide_for_rule(rule: dict, values: dict, mode: str, focus_scope: str):
    """One rule's verdict for a matched wait, or None when
    this rule does not decide (no match, or a scope miss
    with fallthrough)."""
    rule = normalize_rule(rule)
    if not rule_matches(rule, values):
        return None
    atype = rule["action"]["type"]
    if atype == "surface":
        return "surfaced"
    if atype == "hold":
        return "pending"
    if scope_matches(rule["scope"], mode, focus_scope):
        return {
            "auto_apply": "auto_applied",
            "post": "post",
            "post_and_apply": "post_and_apply",
        }.get(atype)
    if rule.get("on_scope_miss") == "fallthrough":
        return None
    return "pending"


def render_template(template: dict, slots: dict) -> str:
    """Render a template's text with its bound slot values;
    an unbound slot renders as its own name in brackets —
    never a silent blank."""
    text = template["text"]
    for slot in template.get("slots", []):
        value = slots.get(slot)
        text = text.replace(
            "{" + slot + "}", str(value) if value is not None else f"[{slot}]"
        )
    return text


def post_blocked(
    rule: dict, wait: dict, sends: list, now: datetime, template_kind: str | None = None
):
    """Guard check for a post action: a block reason, or
    None when it may fire. Dedupe is fact-keyed per
    template; cooldown and max-posts bind every send."""
    mine = [
        s
        for s in sends
        if s["rule_id"] == rule["id"]
        and s["wait_id"] == wait["id"]
        and s.get("mode") == "active"
    ]
    guards = normalize_rule(rule).get("guards") or {}
    max_posts = guards.get("max_posts")
    if max_posts is not None and len(mine) >= max_posts:
        return "max_posts"
    cooldown = guards.get("cooldown_minutes")
    if cooldown is not None and mine:
        last = max(s["at"] for s in mine)
        if (now - last).total_seconds() < cooldown * 60:
            return "cooldown"
    if template_kind is not None and any(
        s.get("fact_hash") == wait.get("fact_hash")
        and s.get("template") == template_kind
        for s in mine
    ):
        return "duplicate_facts"
    return None


def decide_wait(
    wait: dict,
    rules: list,
    mode: str,
    focus_scope: str,
    values: dict | None = None,
    classes: list | None = None,
    ctx: dict | None = None,
) -> tuple:
    """The engine's decision for one wait (§1.10): a
    (decision, rule_id) pair. Hard stops surface before any
    rule; rules decide in priority order."""
    if class_is_hard_stop(wait.get("wait_class"), classes):
        return "surfaced", None
    values = values if values is not None else dict(wait)
    for rule in ordered_rules(rules):
        if not trigger_due(rule, wait, values, ctx or {}):
            continue
        verdict = decide_for_rule(rule, values, mode, focus_scope)
        if verdict is not None:
            return verdict, rule["id"]
    return "surfaced", None
