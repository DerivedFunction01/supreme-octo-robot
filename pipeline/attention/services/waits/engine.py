"""The auto-apply engine (spec §1.10): the sweeper, as a job
of this app. Waits are decided against the declarative rule
set and current presence; posts render templates into the
send ledger; every decision lands in the log.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from attention.domain import attention as dom
from attention.errors import Validation
from attention.services.waits import facts as facts_mod
from attention.settings import REPO_ROOT, Settings


def fact_hash(wait: dict) -> str:
    """The facts a dedupe decision keys on: what the wait
    says, not how it has been decided."""
    facts = {
        key: wait.get(key)
        for key in (
            "summary",
            "status_code",
            "kind",
            "wait_class",
            "program_approved",
            "reversible",
            "in_budget",
            "only_blocker",
        )
    }
    blob = json.dumps(facts, sort_keys=True, default=str).encode()
    return hashlib.sha1(blob).hexdigest()[:12]


def wait_values(state: dict, wait: dict, now: datetime) -> dict:
    """The value set rules match over: the wait's poster
    fields plus the server-derived fields (never posted)."""
    values = dict(wait)
    posted = wait.get("posted_at")
    values["age_minutes"] = int((now - posted).total_seconds() // 60) if posted else 0
    values["repeat_count"] = sum(
        1
        for s in state["sends"]
        if s["wait_id"] == wait["id"] and s.get("mode") == "active"
    )
    values["presence"] = state["presence"]["mode"]
    status = state["handler_status"].get(wait["handle"]) or {}
    values["handler_status_code"] = status.get("status_code")
    return values


def _template_for(state: dict, kind: str | None) -> dict | None:
    if kind is None:
        return None
    for template in state["templates"]:
        if template["kind"] == kind:
            return template
    return None


def _pick_template_kind(rule: dict, mode: str, attempt: int) -> str | None:
    action = dom.normalize_rule(rule)["action"]
    variants = action.get("variants") or {}
    if attempt > 1 and (variants.get("attempt") or {}).get("repeat"):
        return variants["attempt"]["repeat"]
    if (variants.get("presence") or {}).get(mode):
        return variants["presence"][mode]
    if attempt == 1 and (variants.get("attempt") or {}).get("first"):
        return variants["attempt"]["first"]
    return action.get("template")


def _new_send_id(state: dict) -> str:
    top = 0
    for send in state["sends"]:
        sid = str(send.get("id", ""))
        if sid.startswith("s") and sid[1:].isdigit():
            top = max(top, int(sid[1:]))
    return f"s{top + 1:04d}"


def _stamp_text(text: str, rule_id: str, wait_id: str | None, send_id: str) -> str:
    """The delivery-side provenance stamp: a
    delivered send arrives in a chat carrying only its
    text — the bridge record's meta (source, rule,
    template) never reaches the delivered message, and
    the channel stamps the executing chat's identity,
    not the minter's. So a machinery-fired send names
    its true origin IN the text, the one surface that
    survives any relay, including a human re-posting
    the text from their own chat: the machinery, its
    rule, and the send id a lane can check against the
    ledger. An owner's own act (rule owner:*) is
    unstamped — its text's claim is true, and the
    ledger is its proof."""
    if rule_id.startswith("owner:"):
        return text
    if wait_id:
        stamp = (
            f"[Provenance: owner-attention dispatch — wait {wait_id} post, "
            f"written by its poster, fired by the waits engine under rule "
            f"{rule_id} · send {send_id}]"
        )
    else:
        stamp = (
            f"[Provenance: owner-attention machinery — fired under rule "
            f"{rule_id} · send {send_id}. Machinery traffic, not an owner "
            f"or coordinator act.]"
        )
    return f"{text}\n{stamp}"


def _record_post(state, rule, wait, values, now, shadow: bool):
    """Render the rule's post into the send ledger (written
    before any dispatch). Returns the send, or a
    guard-block reason string."""
    rule = dom.normalize_rule(rule)
    mode = state["presence"]["mode"]
    prior = sum(
        1
        for s in state["sends"]
        if s["rule_id"] == rule["id"]
        and s["wait_id"] == wait["id"]
        and s.get("mode") == "active"
    )
    kind = _pick_template_kind(rule, mode, prior + 1)
    template = _template_for(state, kind)
    if template is None:
        return "no_template"
    if not shadow:
        blocked = dom.post_blocked(rule, wait, state["sends"], now, kind)
        if blocked:
            return blocked
    action = rule["action"]
    bindings = action.get("slots") or {}
    slots = {}
    for slot in template.get("slots", []):
        binding = bindings.get(slot, slot)
        slots[slot] = values.get(binding, binding)
    handler = next((h for h in state["handlers"] if h["handle"] == wait["handle"]), {})
    if template["audience"] == "main":
        target = "main"
    else:
        target = handler.get("thread_id") or wait["handle"]
    guards = rule.get("guards") or {}
    escalate_after = guards.get("escalate_after")
    if escalate_after is not None and prior + 1 >= escalate_after:
        target = "main"
    send_id = _new_send_id(state)
    send = {
        "id": send_id,
        "at": now,
        "rule_id": rule["id"],
        "wait_id": wait["id"],
        "handle": wait["handle"],
        "target": target,
        "template": template["kind"],
        "version": template["version"],
        "attempt": prior + 1,
        "presence": mode,
        "text": _stamp_text(
            dom.render_template(template, slots), rule["id"], wait["id"], send_id
        ),
        "fact_hash": wait.get("fact_hash"),
        "mode": "shadow" if shadow else "active",
        "outcome": "shadow" if shadow else "recorded",
        "dispatch": {
            "consumer": None,
            "claimed_at": None,
            "claim_expires_at": None,
            "delivered_at": None,
            "delivery_ref": None,
            "attempts": 0,
        },
    }
    state["sends"].append(send)
    return send


def record_send(
    state,
    template_kind: str,
    handle: str,
    slots: dict,
    now: datetime,
    rule_id: str,
    wait_id: str | None = None,
    target: str | None = None,
):
    """Write one send to the ledger before any dispatch
    (§1.13: owner verbs send through the same ledger).
    Returns the send, or None for an unregistered kind."""
    template = _template_for(state, template_kind)
    if template is None:
        return None
    handler = next((h for h in state["handlers"] if h["handle"] == handle), {})
    if target is None:
        target = (
            "main"
            if template["audience"] == "main"
            else handler.get("thread_id") or handle
        )
    send_id = _new_send_id(state)
    send = {
        "id": send_id,
        "at": now,
        "rule_id": rule_id,
        "wait_id": wait_id,
        "handle": handle,
        "target": target,
        "template": template["kind"],
        "version": template["version"],
        "attempt": 1,
        "presence": state["presence"]["mode"],
        "text": _stamp_text(
            dom.render_template(template, slots), rule_id, wait_id, send_id
        ),
        "fact_hash": None,
        "mode": "active",
        "outcome": "recorded",
        "dispatch": {
            "consumer": None,
            "claimed_at": None,
            "claim_expires_at": None,
            "delivered_at": None,
            "delivery_ref": None,
            "attempts": 0,
        },
    }
    state["sends"].append(send)
    return send


def evaluate_waits(state: dict, settings: Settings, now: datetime) -> list:
    """Decide every pending wait and fire due posts; returns
    the events (decisions and sends) this pass produced."""
    mode = state["presence"]["mode"]
    ctx = {"presence_entered": state.get("presence_seen") != mode}
    events = []
    for wait in state["waits"]:
        if wait["decision"] != "pending":
            continue
        if not wait.get("fact_hash"):
            wait["fact_hash"] = fact_hash(wait)
        values = wait_values(state, wait, now)
        if dom.class_is_hard_stop(wait.get("wait_class"), state["wait_classes"]):
            _apply_decision(state, wait, "surfaced", None, mode, now)
            events.append(wait)
            continue
        for rule in dom.ordered_rules(state["rules"]):
            rule = dom.normalize_rule(rule)
            if not dom.trigger_due(rule, wait, values, ctx):
                continue
            verdict = dom.decide_for_rule(rule, values, mode, settings.focus_scope)
            if verdict is None:
                continue
            shadow = rule.get("mode") == "shadow"
            if verdict in ("post", "post_and_apply"):
                result = _record_post(state, rule, wait, values, now, shadow)
                if isinstance(result, str):
                    continue  # guard-blocked: a later rule may still decide
                events.append(result)
                _log(state, wait, verdict, rule["id"], mode, now, shadow)
                wait["last_fact_hash"] = wait.get("fact_hash")
                if verdict == "post_and_apply" and not shadow:
                    _apply_decision(
                        state, wait, "auto_applied", rule["id"], mode, now, log=False
                    )
                    events.append(wait)
                break
            if verdict == "pending":
                break  # held by scope or a hold rule: silent, still pending
            if shadow:
                _log(state, wait, verdict, rule["id"], mode, now, shadow=True)
                events.append(wait)
                break
            _apply_decision(state, wait, verdict, rule["id"], mode, now)
            events.append(wait)
            break
        wait["evaluated"] = True
    state["presence_seen"] = mode
    return events


def _log(state, wait, decision, rule_id, mode, now, shadow):
    state["action_log"].append(
        {
            "at": now,
            "kind": "wait",
            "wait_id": wait["id"],
            "handle": wait["handle"],
            "wait_class": wait["wait_class"],
            "decision": decision,
            "rule_id": rule_id,
            "presence": mode,
            "acted": None,
            "shadow": shadow,
        }
    )


def _apply_decision(state, wait, decision, rule_id, mode, now, log=True):
    wait["decision"] = decision
    wait["rule_id"] = rule_id
    wait["decided_at"] = now
    wait["last_fact_hash"] = wait.get("fact_hash")
    if log:
        _log(state, wait, decision, rule_id, mode, now, shadow=False)
    if decision == "surfaced":
        _surface_item(state, wait, now)


def _surface_item(state: dict, wait: dict, now: datetime) -> None:
    """A surfaced wait becomes an owner item, once (§1.2
    de-duplication: one decision, however reported)."""
    item_id = f"wait-{wait['id']}"
    if any(i["id"] == item_id for i in state["items"]):
        return
    item = {
        "id": item_id,
        "handle": wait["handle"],
        "kind": "approval",
        "title": wait["summary"],
        "status_code": "BLOCKED-OWNER",
        "source_ref": wait["id"],
        "source_url": "",
        "clears_at_source": False,
        "due_at": None,
        "waiting_since": wait["posted_at"],
        "need": "owner_actionable",
        "tier": "digest",
        "triage": "open",
        "snooze_return_at": None,
        "snooze_on_activity": False,
        "resume_note": None,
        "wait_id": wait["id"],
        "options": [],
    }
    item["tier"] = dom.assign_tier(item, state["allowlist"], now)
    state["items"].append(item)


# --- expiry (the decision-staleness plan, Step 3) ---
# The tick's second pass: standing waits and waiting
# items are priced for staleness — basis detectors
# first (Step 2), the registry age cap as backstop
# (Step 1's stale_state) — and a stale record expires
# to record: the expiry record is written, the item
# leaves the waiting surface, the wait's decision
# moves off pending/surfaced. Expiry dispatches
# nothing: no send is written and no decision record
# is created — a record act, never a ruling.


def registry_entry(entries, key, name, defaults):
    """One registry entry by its key field: the stored
    registry first, the domain seed as fallback."""
    for entry in entries or []:
        if entry.get(key) == name:
            return entry
    for entry in defaults:
        if entry.get(key) == name:
            return entry
    return None


def basis_facts(state: dict, push_facts: dict | None = None, plans_root=None) -> dict:
    """The facts-provider dict the basis detectors read
    (services/waits/basis.py's ports), assembled from
    what the server holds: handler status and the
    terminal codes from the loaded state, push facts as
    measured by the caller, the repo's .plans root for
    sentinels. Two ports are deliberately absent, and
    their detectors return None (cannot decide — the
    age cap governs):
    - wait_facts: no write path re-reads a standing
      wait's poster facts (posts are idempotent; stored
      fields are never amended), so fact drift has no
      provider here — the Step 2 lane's named gap,
      carried forward.
    - source_records: a clears_at_source item's source
      lives outside this store (its ref is a poster
      ref, never one of this store's record ids), and
      no source-state path is configured; feeding the
      state's own records would read every such ref as
      gone and basis-expire the queue on a fiction."""
    terminal = tuple(
        entry["code"]
        for entry in state.get("status_codes") or dom.default_status_codes()
        if entry.get("terminal")
    )
    return {
        "handler_status": state.get("handler_status") or {},
        "terminal_codes": terminal,
        "plans_root": plans_root if plans_root is not None else REPO_ROOT / ".plans",
        "push_facts": push_facts or {},
    }


def _basis_input(record: dict, facts: dict) -> dict | None:
    # Deferred: basis.py imports this module for
    # fact_hash, so the composition is bound at call
    # time, never at import time.
    from attention.services.waits import basis

    verdict = basis.basis_for(record, facts)
    if verdict is None:
        return None
    return {"stale": verdict[0], "evidence": verdict[1]}


def item_hard_stop(state: dict, item: dict) -> bool:
    """An item is hard-stop-bearing when it carries the
    mark itself or its surfacing wait's class is on the
    floor (the domain's per-record rule for approvals)."""
    if item.get("hard_stop"):
        return True
    wait_id = item.get("wait_id")
    if not wait_id:
        return False
    wait = next((w for w in state.get("waits") or [] if w["id"] == wait_id), None)
    return wait is not None and dom.class_is_hard_stop(
        wait.get("wait_class"), state.get("wait_classes")
    )


def _expire_wait(state, wait, expired, blocked, now):
    """A stale wait expires to record, and its surfaced
    item — the same ask on the owner's surface —
    expires with it under the same record."""
    wait["expired"] = expired
    wait["decision"] = "expired_blocked" if blocked else "expired"
    wait["decided_at"] = now
    item = next(
        (i for i in state.get("items") or [] if i.get("wait_id") == wait["id"]),
        None,
    )
    if (
        item is not None
        and item["triage"] not in ("done", "muted")
        and not item.get("decision")
    ):
        item["expired"] = expired
        item["triage"] = "done"


def _expire_item(state, item, expired, blocked, now):
    """A stale item expires to record; a still-pending
    surfacing wait behind it expires under the same
    record, so the pair never disagrees."""
    item["expired"] = expired
    item["triage"] = "done"
    wait_id = item.get("wait_id")
    if not wait_id:
        return
    wait = next((w for w in state.get("waits") or [] if w["id"] == wait_id), None)
    if wait is not None and wait["decision"] in ("pending", "surfaced"):
        wait["expired"] = expired
        wait["decision"] = "expired_blocked" if blocked else "expired"
        wait["decided_at"] = now


def _expiry_verdict(record: dict, entry, hard_stop: bool, now: datetime, facts: dict):
    """stale_state over one waiting record, or None when
    it stands live. The caller-resolved registry pair
    rides the record, per the domain's contract."""
    verdict = dom.stale_state(
        {
            "waiting_since": record["waiting_since"],
            "stale_after_hours": entry.get("stale_after_hours") if entry else None,
            "hard_stop": hard_stop,
        },
        now,
        _basis_input(record, facts),
    )
    if verdict["state"] == dom.STALE_LIVE:
        return None
    blocked = bool(hard_stop or (entry and entry.get("on_stale") == "expire_blocked"))
    expired = {
        "at": now,
        "basis": "basis" if verdict["state"] == dom.STALE_BASIS else "age",
        "evidence": verdict["evidence"],
        "blocked": blocked,
    }
    return expired, blocked


def evaluate_expiry(state: dict, now: datetime, plans_root=None) -> list:
    """The tick's expiry pass (the decision-staleness
    plan, Step 3): every pending/surfaced wait and every
    waiting item is priced for staleness — basis first,
    age as backstop — and a stale record expires to
    record. Hard-stop records expire only on basis
    evidence, to the blocked-unruled form (the wait's
    decision becomes expired_blocked; it is never an
    approval). Decided items are exempt: expiry never
    erases a standing ruling, whatever its fulfillment
    state. Returns one event per expiry (a surfaced
    wait and its item expire together, one event)."""
    facts = basis_facts(
        state,
        push_facts=facts_mod.derive_push_facts(state, now),
        plans_root=plans_root,
    )
    events = []
    for wait in state["waits"]:
        if wait["decision"] not in ("pending", "surfaced"):
            continue
        entry = registry_entry(
            state.get("wait_classes"),
            "name",
            wait.get("wait_class"),
            dom.default_wait_classes(),
        )
        priced = _expiry_verdict(
            {**wait, "waiting_since": wait["posted_at"]},
            entry,
            dom.class_is_hard_stop(wait.get("wait_class"), state.get("wait_classes")),
            now,
            facts,
        )
        if priced is None:
            continue
        expired, blocked = priced
        _expire_wait(state, wait, expired, blocked, now)
        events.append({"kind": "wait", "id": wait["id"], "expired": expired})
    for item in state["items"]:
        if item["triage"] in ("done", "muted") or item.get("decision"):
            continue
        entry = registry_entry(
            state.get("item_kinds"),
            "kind",
            item.get("kind"),
            dom.default_item_kinds(),
        )
        priced = _expiry_verdict(
            item,
            entry,
            item_hard_stop(state, item),
            now,
            facts,
        )
        if priced is None:
            continue
        expired, blocked = priced
        _expire_item(state, item, expired, blocked, now)
        events.append({"kind": "item", "id": item["id"], "expired": expired})
    return events


def preview_rule(
    state: dict, candidate: dict, settings: Settings, now: datetime
) -> list:
    """Dry-run one candidate rule against current state on a
    scratch copy: what would fire, with rendered posts — no
    side effects on the real state, ever.

    A malformed candidate is a validation failure (422),
    never a 500: the structural minimum the evaluation
    keys on — an object carrying a usable id, with the
    container fields holding their shapes — is checked
    here, in the write path's field-error vocabulary,
    before normalize or the id dedupe can key on absent
    or mistyped values."""
    errors: list = []
    if not isinstance(candidate, dict):
        errors.append({"field": "rule", "message": "must be an object"})
    else:
        if not isinstance(candidate.get("id"), str) or not candidate["id"]:
            errors.append({"field": "id", "message": "is required"})
        action = candidate.get("action")
        if action is not None and not isinstance(action, (str, dict)):
            errors.append({"field": "action", "message": "must be a string or object"})
        for field in ("match", "trigger", "guards"):
            value = candidate.get(field)
            if value is not None and not isinstance(value, dict):
                errors.append({"field": field, "message": "must be an object"})
        where = candidate.get("where")
        if where is not None and not isinstance(where, dict):
            errors.append({"field": "where", "message": "must be an object"})
    if errors:
        raise Validation("Rule failed validation.", errors)
    import copy

    scratch = copy.deepcopy(state)
    cand = dom.normalize_rule(candidate)
    cand["mode"] = "active"
    scratch["rules"] = [cand] + [r for r in scratch["rules"] if r["id"] != cand["id"]]
    pending_before = {w["id"] for w in scratch["waits"] if w["decision"] == "pending"}
    sends_before = len(scratch["sends"])
    evaluate_waits(scratch, settings, now)
    out = []
    for send in scratch["sends"][sends_before:]:
        out.append(
            {
                "wait_id": send["wait_id"],
                "action": "post",
                "template": send["template"],
                "target": send["target"],
                "text": send["text"],
            }
        )
    for wait in scratch["waits"]:
        if wait["id"] in pending_before and wait["decision"] != "pending":
            out.append(
                {
                    "wait_id": wait["id"],
                    "action": wait["decision"],
                    "template": None,
                    "target": None,
                    "text": None,
                }
            )
    return out


def new_wait_id(existing: list) -> str:
    """Mint the next wait id from the persisted waits, so a
    server restart can never reissue an id already in state."""
    top = 0
    for wait in existing:
        wid = str(wait.get("id", ""))
        if wid.startswith("w") and wid[1:].isdigit():
            top = max(top, int(wid[1:]))
    return f"w{top + 1:04d}"
