"""Domain logic: the condition grammar's evaluation, the
classification / tier / band derivations, and the wait
decision engine — split from attention.py;
attention.domain.attention re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime

from .catalogs import class_is_hard_stop, default_status_codes
from .rules import normalize_rule, ordered_rules

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


def next_window(now: datetime, windows: tuple[str, ...], tz=None) -> datetime:
    """The next digest window at or after now. The window
    times are wall times in `tz` when one is given (the
    owner's timezone, from the digest prefs), else in
    now's own frame (the settings form)."""
    frame = tz or now.tzinfo
    local = now.astimezone(frame)
    candidates = []
    for text in windows:
        hour, minute = (int(part) for part in text.split(":"))
        at = datetime.combine(local.date(), time(hour, minute), tzinfo=frame)
        if at <= local:
            at += timedelta(days=1)
        candidates.append(at)
    return min(candidates)


def window_start(now: datetime, windows: tuple, tz=None) -> datetime:
    """The most recent digest window at or before now —
    the ping cooldown's unit (D-A4). Wall times read in
    `tz` when given, else in now's own frame."""
    frame = tz or now.tzinfo
    local = now.astimezone(frame)
    starts = []
    for text in windows:
        hour, minute = (int(part) for part in text.split(":"))
        at = datetime.combine(local.date(), time(hour, minute), tzinfo=frame)
        if at > local:
            at -= timedelta(days=1)
        starts.append(at)
    return max(starts)


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
