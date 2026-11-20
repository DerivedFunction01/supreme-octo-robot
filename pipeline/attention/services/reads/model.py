"""The model builders: one function per API section.

Every derivation and label is made here, display-ready;
presence filters here, server-side (API.md principles 2–4).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from attention.domain import attention as dom
from attention.services.dispatch import dispatch as dispatch_mod
from attention.services.waits import basis, engine, fulfillment
from attention.services.waits import facts as facts_mod
from attention.settings import Settings

CONTRACT = "api/1"

KIND_LABELS = {
    "decision": "Decision",
    "action": "Action",
    "defect": "Defect",
    "approval": "Approval",
    "fyi": "FYI",
}
TIER_LABELS = {
    "breakthrough": "Breakthrough",
    "due_today": "Due today",
    "digest": "Digest",
    "fyi": "FYI",
}
BAND_LABELS = {
    "breakthrough": "Breakthrough",
    "due_today": "Due today",
    "needs_decision": "Needs a decision",
    "waiting": "Waiting on agents",
    "fyi": "FYI",
}
DECISION_LABELS = {
    "auto_applied": "Auto-applied",
    "surface": "Surfaced",
    "pending": "Held pending",
    "held": "Held",
    "post": "Posted",
    "posted": "Posted",
    "fallthrough": "Fell through",
}
OUTCOME_LABELS = {
    "recorded": "Recorded",
    "deduped": "Held — facts unchanged",
    "cooldown": "Held — cooldown",
    "max_posts": "Held — max posts",
    "no_template": "Held — no template",
}
BAND_ORDER = ("breakthrough", "due_today", "needs_decision", "waiting", "fyi")
MODE_LABELS = {"active": "Active", "focus": "Focus", "away": "Away"}
PROVENANCE_LABELS = {
    "commission": "Owner commission",
    "offer": "Agent offer — awaiting your tap",
}
DIGEST_OWNER_LABELS = {
    "owner": "Waiting on you",
    "lane": "Back with the lane",
    "self": "Poster closeout",
}


def status_label(state: dict, code: str) -> str:
    """A status code's display label from the registry —
    every surface renders the label, never the raw code."""
    for entry in state.get("status_codes") or dom.default_status_codes():
        if entry["code"] == code:
            return entry["label"]
    return code


def class_label(name: str) -> str:
    """A wait class's display name (classes carry no label
    field; the name title-cased is the display form)."""
    text = name.replace("_", " ")
    return text[:1].upper() + text[1:]


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _kind_label(state: dict, kind: str) -> str:
    for entry in state.get("item_kinds", []):
        if entry["kind"] == kind:
            return entry["label"]
    return KIND_LABELS.get(kind, kind)


def handler_map(state: dict) -> dict:
    return {h["handle"]: h for h in state["handlers"]}


def digest_windows(state: dict, settings: Settings) -> list:
    """The digest windows in force (AC-8): the configured
    times minus any the owner switched off on state
    (digest_prefs — the digest page's and the shell
    Settings row's write). One home: the digest's next_at,
    the glance clock, and the snooze "next digest" time
    all read windows through here, so a disabled window
    disappears from every surface at once."""
    prefs = (state.get("digest_prefs") or {}).get("windows") or {}
    return [t for t in settings.digest_windows if prefs.get(t, True)]


def digest_include(state: dict) -> dict:
    """The digest include flags in force (AC-8): stored
    prefs over the all-on default."""
    stored = (state.get("digest_prefs") or {}).get("include") or {}
    return {key: stored.get(key, True) for key in ("decisions", "waiting", "fyi")}


def handler_presentation(handler: dict) -> dict:
    """A handler's presentation pair, defaulted at read
    (AC-12): registration writes color_slot/icon with the
    defaults below (writes.register_handler), but a record
    that reaches state without passing registration — a
    hand-edited or partially migrated store — must not
    KeyError the reads that serve it (item views, the
    glance dots, the registries list). This is the one
    home for the read-side defaults; they mirror the
    registration defaults exactly."""
    return {
        "color_slot": handler.get("color_slot", 1),
        "icon": handler.get("icon", "dot"),
    }


def handler_order(state: dict) -> dict:
    return {h["handle"]: i for i, h in enumerate(state["handlers"])}


def effective_mode(state: dict, now: datetime) -> str:
    """The served presence mode: a declared mode whose
    expiry has passed no longer holds — the owner is
    back, and no surface keeps withholding for it."""
    mode = state["presence"]["mode"]
    expires = state["presence"].get("expires_at")
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if mode != "active" and expires is not None and expires <= now:
        return "active"
    return mode


def presence_view(state: dict, now: datetime) -> dict:
    presence = state["presence"]
    mode = effective_mode(state, now)
    return {
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "expires_at": _iso(presence.get("expires_at")),
        "expectation": presence.get("expectation", ""),
    }


OFFER_KINDS = ("followup", "improvement", "consolidation", "performance")


def _verb_entry(verb: str, primary: bool = False, hint: str | None = None) -> dict:
    return {
        "verb": verb,
        "label": dom.VERB_LABELS.get(verb, verb),
        "primary": primary,
        "rule_hint": hint,
        "sends": verb not in dom.BOOKMARK_VERBS,
    }


def _shadow_hint(state: dict, item: dict, verb: str) -> str | None:
    """A shadow action rule that would fire on this item
    makes its verb primary (§1.13)."""
    for rule in state.get("action_rules", []):
        if rule.get("mode") != "shadow" or rule.get("verb") != verb:
            continue
        match = rule.get("match") or {}
        if match.get("handle") and match["handle"] != item["handle"]:
            continue
        if match.get("kind") and match["kind"] != item["kind"]:
            continue
        if match.get("wait_class"):
            continue
        return (
            f"A shadow rule would {dom.VERB_LABELS.get(verb, verb).lower()} "
            "this — the tap applies it once."
        )
    return None


def verbs_for(item: dict, state: dict, fulfillment_view: dict | None = None) -> list:
    """The served verb list (§1.13): derived from kind,
    provenance, wait class, and state — the frontend
    renders these and derives nothing."""
    if item["triage"] in ("done", "muted"):
        # A decided item keeps its verbs while its
        # fulfillment is unfulfilled or returned; a
        # fulfilled decision is closed for good.
        if not (
            item.get("decision")
            and fulfillment_view
            and fulfillment_view["state"] != "fulfilled"
        ):
            return []
    verbs: list[str] = []
    kind = item["kind"]
    wait = None
    if item.get("wait_id"):
        wait = next(
            (w for w in state.get("waits", []) if w["id"] == item["wait_id"]), None
        )
    if kind == "rule_proposal":
        verbs = ["accept_proposal", "reject_proposal"]
    elif (
        kind == "approval"
        and wait is not None
        and wait["decision"]
        in (
            "pending",
            "surfaced",
        )
    ):
        verbs = ["approve_once"]
        if not dom.class_is_hard_stop(wait.get("wait_class"), state["wait_classes"]):
            verbs.append("approve_rule")
        verbs.append("deny")
    elif kind == "decision":
        verbs = ["pick", "rule_it", "reply"]
    elif kind in OFFER_KINDS and item.get("provenance", "offer") == "offer":
        verbs = ["accept", "reject", "modify"]
    elif kind == "push_needed":
        verbs = ["push"]
    elif kind == "defect":
        verbs = ["close_on_verify", "reply"]
    if item.get("status_code") == "REVIEW" and kind != "rule_proposal":
        verbs += ["accept_review", "reject_incomplete"]
    if item["need"] == "agent_clearable" and kind not in (
        "rule_proposal",
        "push_needed",
    ):
        verbs.append("continue")
    verbs += ["reply", "snooze", "done", "mute_type", "leave_it"]
    seen: list[str] = []
    for verb in verbs:
        if verb not in seen:
            seen.append(verb)
    out = []
    for verb in seen:
        hint = _shadow_hint(state, item, verb)
        out.append(_verb_entry(verb, primary=hint is not None, hint=hint))
    return out


def quick_verbs_for_status(state: dict, handle: str, record: dict) -> list:
    """The quick action buttons on a status (§1.13
    amendment): named from the owner's one-tap patterns,
    placed by the status code."""
    code = record.get("status_code")
    verbs: list[str] = []
    if code == "REVIEW":
        verbs = ["accept_review", "reject_incomplete"]
    elif code == "DONE":
        verbs = ["close"]
    elif code in ("WORKING", "CONTINUE", "BLOCKED-OWNER", "BLOCKED-HARD"):
        verbs = ["park"]
    if code not in ("CLOSED",):
        verbs.append("leave_it")
    return [_verb_entry(v) for v in verbs]


def handler_verbs(exclude: set | None = None) -> list:
    from attention.services.waits.actions import HANDLER_VERBS

    skip = exclude or set()
    return [_verb_entry(v) for v in HANDLER_VERBS if v not in skip]


def item_staleness(item: dict, state: dict, facts: dict | None = None) -> dict:
    """The served staleness fields (the decision-
    staleness plan, Step 3): the basis evidence when a
    detector currently prices the item stale (None when
    live or undecidable — a decided or closed item is
    not priced at all), the moment the item's age cap
    falls due under its kind's current registry entry
    (None for an uncapped kind or a hard-stop-bearing
    record, which never age-expires), and the expiry
    record when one stands."""
    entry = engine.registry_entry(
        state.get("item_kinds"), "kind", item["kind"], dom.default_item_kinds()
    )
    cap = entry.get("stale_after_hours") if entry else None
    expires_at = None
    if cap is not None and not engine.item_hard_stop(state, item):
        expires_at = _iso(item["waiting_since"] + timedelta(hours=cap))
    stale_basis = None
    if item["triage"] not in ("done", "muted") and not item.get("decision"):
        verdict = basis.basis_for(item, engine.basis_facts(state, push_facts=facts))
        if verdict is not None and verdict[0]:
            stale_basis = verdict[1]
    expired = item.get("expired")
    return {
        "stale_basis": stale_basis,
        "expires_at": expires_at,
        "expired": (
            {
                "at": _iso(expired["at"]),
                "basis": expired["basis"],
                "evidence": expired["evidence"],
                "blocked": bool(expired.get("blocked")),
            }
            if expired
            else None
        ),
    }


def item_view(
    item: dict,
    state: dict,
    now: datetime,
    settings: Settings,
    facts: dict | None = None,
) -> dict:
    handler = handler_map(state)[item["handle"]]
    fact = (facts or {}).get(item["id"])
    fulfillment_view = fulfillment.derive(item, state, now, settings, fact)
    verbs = verbs_for(item, state, fulfillment_view)
    staleness = item_staleness(item, state, facts)
    return {
        "id": item["id"],
        "handler": {
            "handle": handler["handle"],
            "label": handler["label"],
            **handler_presentation(handler),
        },
        "kind": item["kind"],
        "kind_label": _kind_label(state, item["kind"]),
        "title": facts_mod.served_title(item, fact),
        "fact_check": (
            {
                "repo": fact["repo"],
                "state": fact["state"],
                "head": fact["head"],
                "ahead": fact["ahead"],
                "behind": fact.get("behind"),
                "dirty": fact.get("dirty"),
                "verified_at": _iso(fact["verified_at"]),
            }
            if fact
            else None
        ),
        "repo": item.get("repo"),
        "due_at": _iso(item.get("due_at")),
        "waiting_since": _iso(item["waiting_since"]),
        "waiting_label": dom.waiting_label(item["waiting_since"], now),
        "tier": item["tier"],
        "tier_label": TIER_LABELS[item["tier"]],
        "need": item["need"],
        "triage": item["triage"],
        "verbs": verbs,
        "options": item.get("options") or [],
        "mode": item.get("mode") or "single",
        "stale_basis": staleness["stale_basis"],
        "expires_at": staleness["expires_at"],
        "expired": staleness["expired"],
        "wait_id": item.get("wait_id"),
        "snooze_options": {
            "times": [
                _iso(
                    now.replace(hour=9, minute=0, second=0, microsecond=0)
                    + timedelta(days=1)
                ),
                *(
                    [_iso(dom.next_window(now, tuple(digest_windows(state, settings))))]
                    if digest_windows(state, settings)
                    else []
                ),
            ],
            "on_activity": True,
        },
        "clears_at_source": item["clears_at_source"],
        "source_url": item["source_url"],
        "routing": item.get("routing"),
        "decision": (
            {
                "verb": fulfillment_view["verb"],
                "verb_label": fulfillment_view["verb_label"],
                "at": _iso(fulfillment_view["at"]),
                "option_id": fulfillment_view["option_id"],
                "note": item["decision"].get("note"),
                "send_id": fulfillment_view.get("send_id"),
                "evidence": fulfillment_view.get("evidence"),
            }
            if fulfillment_view
            else None
        ),
        "fulfillment": (
            {
                "state": fulfillment_view["state"],
                "label": fulfillment_view["label"],
            }
            if fulfillment_view
            else None
        ),
        "decision_history": [
            {
                "verb": h["verb"],
                "verb_label": dom.VERB_LABELS.get(h["verb"], h["verb"]),
                "at": _iso(h["at"]),
                "outcome": h.get("outcome"),
                "option_id": h.get("option_id"),
                "note": h.get("note"),
                "send_id": h.get("send_id"),
            }
            for h in item.get("decision_history") or []
        ],
        "resume_note": item.get("resume_note"),
        "snooze_return_at": _iso(item.get("snooze_return_at")),
        "snooze_on_activity": bool(item.get("snooze_on_activity")),
        "proposal": item.get("proposal"),
        "provenance": item.get("provenance", "offer"),
        "provenance_label": PROVENANCE_LABELS.get(
            item.get("provenance", "offer"), item.get("provenance", "offer")
        ),
    }


def retired_handles(state: dict) -> set:
    return {h["handle"] for h in state["handlers"] if h.get("retired")}


def open_items(state: dict, now: datetime) -> list:
    retired = retired_handles(state)
    return [
        i
        for i in state["items"]
        if dom.visible(i, now)
        and not (i["handle"] in retired and i["need"] != "owner_actionable")
    ]


def _live_items(state: dict, now: datetime, facts: dict | None) -> list:
    items = open_items(state, now)
    if not facts:
        return items
    return [
        i
        for i in items
        if facts.get(i["id"], {}).get("state") not in facts_mod.CLEARED_STATES
    ]


def build_glance(
    state: dict, settings: Settings, now: datetime, facts: dict | None = None
) -> dict:
    mode = effective_mode(state, now)
    items = _live_items(state, now, facts)
    returned = fulfillment.returned_items(state, now, settings, facts)
    items = items + [i for i in returned if i not in items]
    owner_items = [i for i in items if i["need"] == "owner_actionable"]
    order = handler_order(state)
    due_items = sorted(
        (i for i in owner_items if i.get("due_at") is not None),
        key=lambda i: (i["due_at"], i["waiting_since"]),
    )
    breakthrough = [i for i in items if i["tier"] == "breakthrough"]
    dots = []
    for handle in order:
        count = sum(
            1
            for i in owner_items
            if i["handle"] == handle and dom.band_of(i) == "needs_decision"
        )
        if count:
            dots.append(
                {
                    "handle": handle,
                    "color_slot": handler_presentation(handler_map(state)[handle])[
                        "color_slot"
                    ],
                    "needs_decision": count,
                }
            )
    held = [i for i in owner_items if i["tier"] != "breakthrough"]
    return {
        "contract": CONTRACT,
        "presence": presence_view(state, now),
        "clock": {
            "now": _iso(now),
            "next_window_at": (
                _iso(dom.next_window(now, tuple(digest_windows(state, settings))))
                if digest_windows(state, settings)
                else None
            ),
        },
        "next_due": (
            {
                "title": facts_mod.served_title(
                    due_items[0], (facts or {}).get(due_items[0]["id"])
                ),
                "handler_handle": due_items[0]["handle"],
                "handler_label": handler_map(state)[due_items[0]["handle"]]["label"],
                "due_label": dom.waiting_label(due_items[0]["due_at"], now),
            }
            if due_items and mode != "away"
            else None
        ),
        "decision_count": len(owner_items),
        "handler_dots": dots if mode == "active" else [],
        "held_count": len(held),
        "breakthrough_count": len(breakthrough),
        "breakthrough_items": (
            [
                {
                    "id": i["id"],
                    "title": facts_mod.served_title(i, (facts or {}).get(i["id"])),
                    "handler_label": handler_map(state)[i["handle"]]["label"],
                }
                for i in breakthrough
            ]
            if mode == "away"
            else []
        ),
        "down_sources": [
            handler_map(state)[h]["label"]
            for h, health in state.get("source_health", {}).items()
            if not health.get("available", True) and h in handler_map(state)
        ],
    }


def build_today(
    state: dict, settings: Settings, now: datetime, facts: dict | None = None
) -> dict:
    items = _live_items(state, now, facts)
    returned = fulfillment.returned_items(state, now, settings, facts)
    decided = fulfillment.decided_items(state, now, settings, facts)
    items = items + [i for i in returned if i not in items]
    order = handler_order(state)
    health = state.get("source_health", {})
    unavailable_handles = {
        handle for handle, h in health.items() if not h.get("available", True)
    }
    bands = []
    headline = 0
    # The opened queue is never presence-filtered, and the
    # headline counts the same owner set the glance counts.
    for band in BAND_ORDER:
        band_items = sorted(
            (i for i in items if dom.band_of(i) == band),
            key=lambda i: dom.order_key(i, order),
        )
        headline += sum(1 for i in band_items if i["need"] == "owner_actionable")
        view = {
            "band": band,
            "band_label": BAND_LABELS[band],
            "collapsed": band == "fyi",
            "items": [item_view(i, state, now, settings, facts) for i in band_items],
            "unavailable": None,
        }
        gone = [i for i in band_items if i["handle"] in unavailable_handles]
        if gone:
            first = health[gone[0]["handle"]]
            view["unavailable"] = {
                "reason": first["reason"],
                "last_good_at": _iso(first.get("last_good_at")),
            }
        bands.append(view)
    if decided:
        bands.append(
            {
                "band": "decided",
                "band_label": "Decided — awaiting fulfillment",
                "collapsed": False,
                "items": [item_view(i, state, now, settings, facts) for i in decided],
                "unavailable": None,
            }
        )
    return {
        "contract": CONTRACT,
        "presence": presence_view(state, now),
        "bands": bands,
        "headline_count": headline,
        "decided_count": len(decided),
        "held_owner_count": 0,
        "held_total_count": 0,
        "generated_at": _iso(now),
    }


def build_handler(
    state: dict,
    settings: Settings,
    now: datetime,
    handle: str,
    derived=None,
    facts: dict | None = None,
):
    handlers = handler_map(state)
    if handle not in handlers:
        return None
    items = _live_items(state, now, facts)
    mine = sorted(
        (i for i in items if i["handle"] == handle),
        key=lambda i: dom.order_key(i, handler_order(state)),
    )
    delivered = [
        log
        for log in state["action_log"]
        if log["handle"] == handle and log["kind"] == "breakthrough"
    ]
    acted = [log for log in delivered if log.get("acted")]
    status = status_view(state, handle, derived)
    quick_ids = {v["verb"] for v in status["quick_verbs"]} if status else set()
    return {
        "contract": CONTRACT,
        "handle": handle,
        "label": handlers[handle]["label"],
        "items": [item_view(i, state, now, settings, facts) for i in mine],
        "agent_clearable_count": sum(1 for i in mine if i["need"] == "agent_clearable"),
        "muted_types": [
            {"kind": kind, "label": _kind_label(state, kind)}
            for h, kind in state["muted"]
            if h == handle
        ],
        "breakthrough_hit_rate": (
            round(len(acted) / len(delivered), 2) if delivered else None
        ),
        "status": status,
        "handler_verbs": handler_verbs(exclude=quick_ids),
        "owner_actions": [
            {
                "id": a["id"],
                "at": _iso(a["at"]),
                "verb": a["verb"],
                "verb_label": dom.VERB_LABELS.get(a["verb"], a["verb"]),
                "item_id": a.get("item_id"),
                "option_id": a.get("option_id"),
                "note": a.get("note") or "",
                "actor": a.get("actor", "owner"),
                "rule_id": a.get("rule_id"),
                "shadow": a.get("shadow", False),
            }
            for a in state.get("owner_actions", [])
            if a["handle"] == handle
        ][-10:],
        "thread_id": handlers[handle].get("thread_id"),
        "auto_applied": [
            log_view(log) for log in state["action_log"] if log["handle"] == handle
        ][-10:],
        "sends": [
            send_view(s, now) for s in state.get("sends", []) if s["handle"] == handle
        ][-20:],
    }


def log_view(log: dict) -> dict:
    view = dict(log)
    view["at"] = _iso(log["at"])
    view["decision_label"] = DECISION_LABELS.get(log["decision"], log["decision"])
    view["presence_label"] = MODE_LABELS.get(log.get("presence"), log.get("presence"))
    return view


def send_view(send: dict, now: datetime | None = None) -> dict:
    dispatch = dispatch_mod.view(send, now)
    for key in ("claimed_at", "claim_expires_at", "delivered_at"):
        dispatch[key] = _iso(dispatch[key])
    return {
        "id": send["id"],
        "at": _iso(send["at"]),
        "rule_id": send["rule_id"],
        "wait_id": send["wait_id"],
        "handle": send["handle"],
        "target": send["target"],
        "template": send["template"],
        "version": send["version"],
        "attempt": send["attempt"],
        "presence": send["presence"],
        "presence_label": MODE_LABELS.get(send["presence"], send["presence"]),
        "fact_hash": send.get("fact_hash"),
        "text": send["text"],
        "mode": send.get("mode", "active"),
        "outcome": send.get("outcome"),
        "outcome_label": OUTCOME_LABELS.get(send.get("outcome"), send.get("outcome")),
        "dispatch": dispatch,
    }


def rule_view(rule: dict, state: dict | None = None) -> dict:
    """A stored rule plus its composed When / Then sentences:
    the row speaks sentences with registry labels resolved,
    never raw codes (frame F3; critic C-01)."""
    rule = dom.normalize_rule(rule)
    state = state or {}
    match = rule.get("match") or {}
    parts = []
    if match.get("wait_class"):
        parts.append(f"class is {class_label(match['wait_class'])}")
    if match.get("status_code"):
        codes = match["status_code"]
        if isinstance(codes, list):
            parts.append(
                "status is " + " or ".join(status_label(state, c) for c in codes)
            )
        else:
            parts.append(f"status is {status_label(state, codes)}")
    if match.get("kind"):
        parts.append(f"kind is {_kind_label(state, match['kind'])}")
    if match.get("handle"):
        parts.append(f"handler is {match['handle']}")
    trigger = rule.get("trigger") or {}
    on = trigger.get("on", "on_enter")
    if on == "on_age":
        parts.append(f"after {trigger.get('after_minutes', '?')} min")
    elif on == "on_repeat":
        parts.append(f"on the {trigger.get('count', '?')}th arrival")
    elif on == "on_state_change":
        parts.append("when the state changes")
    elif on == "on_presence_enter":
        parts.append("when the scope is entered")
    if rule.get("where"):
        parts.append("+ conditions")
    if rule.get("requires"):
        parts.append("with all flags holding")
    when = ("Wait — " + " · ".join(parts)) if parts else "Any wait"
    action = rule["action"]
    verb = {
        "auto_apply": "Auto-apply the decision",
        "surface": "Surface it for the owner",
        "hold": "Hold it",
        "post": "Post",
        "post_and_apply": "Post, then auto-apply",
    }.get(action["type"], action["type"])
    then = verb
    if action.get("template"):
        then += f" · {action['template']}"
    guards = rule.get("guards") or {}
    guard_bits = []
    if guards.get("cooldown_minutes") is not None:
        guard_bits.append(f"cooldown {guards['cooldown_minutes']}m")
    if guards.get("max_posts") is not None:
        guard_bits.append(f"max posts {guards['max_posts']}")
    if guards.get("escalate_after") is not None:
        guard_bits.append(f"escalate after {guards['escalate_after']} → Main")
    if guard_bits:
        then += " · " + " · ".join(guard_bits)
    view = dict(rule)
    view["display_name"] = rule.get("name") or rule["id"].replace("-", " ").title()
    view["when_label"] = when
    view["then_label"] = then
    return view


def status_view(state: dict, handle: str, derived=None):
    """The handler's latest status record, classified.

    Groups ride verbatim from the post: a group the state
    did not call for is absent, never empty-filled.
    """
    record = state.get("handler_status", {}).get(handle)
    if record is None:
        return None
    view = dict(record)
    view["at"] = _iso(record["at"])
    if view.get("owner_waiting"):
        decl = view["owner_waiting"]
        view["owner_waiting"] = {
            "label": decl["label"],
            "commissioned_at": _iso(decl["commissioned_at"]),
            "declared_at": _iso(decl.get("declared_at") or decl["commissioned_at"]),
        }
    view["status_label"] = status_label(state, record["status_code"])
    view["provenance"] = record.get("provenance", "offer")
    view["provenance_label"] = PROVENANCE_LABELS.get(
        view["provenance"], view["provenance"]
    )
    if derived is not None:
        view["derived"] = derived
    view["need"] = dom.classify_need(record["status_code"], state.get("status_codes"))
    view["quick_verbs"] = quick_verbs_for_status(state, handle, record)
    if "tail" in view:
        view["tail"] = [
            {**entry, "kind_label": _kind_label(state, entry["kind"])}
            for entry in view["tail"]
        ]
    stamps = [v for v in state.get("verifications", []) if v["handle"] == handle]
    if stamps:
        latest = stamps[-1]
        view["verification"] = {
            "verdict": latest["verdict"],
            "at": _iso(latest["at"]),
            "note": latest.get("note") or "",
            "posted_by": latest.get("posted_by"),
        }
    return view


def build_sends(state: dict, handle: str | None = None, now=None) -> dict:
    sends = state.get("sends", [])
    if handle:
        sends = [s for s in sends if s["handle"] == handle]
    return {"contract": CONTRACT, "sends": [send_view(s, now) for s in sends][-50:]}


def build_registries(state: dict) -> dict:
    """The Registries screen + the rule editor's pickers:
    every vocabulary the declarative engine matches over."""
    return {
        "contract": CONTRACT,
        "status_codes": state.get("status_codes", []),
        "fields": [
            {**f, "label": class_label(f["name"])} for f in state.get("fields", [])
        ],
        "wait_classes": [
            {**c, "label": class_label(c["name"])}
            for c in state.get("wait_classes", [])
        ],
        "operators": [{"op": op, "label": dom.OP_LABELS[op]} for op in dom.OPS],
        "triggers": [
            {"on": key, "label": label} for key, label in dom.TRIGGER_LABELS.items()
        ],
        "actions": [
            {"type": key, "label": label} for key, label in dom.ACTION_LABELS.items()
        ],
        "templates": state.get("templates", []),
        "action_rules": state.get("action_rules", []),
        "item_kinds": [
            {
                **entry,
                "digest_owner": entry.get("digest_owner")
                or dom.STATUS_KIND_OWNERS.get(entry["kind"]),
                "digest_owner_label": DIGEST_OWNER_LABELS.get(
                    entry.get("digest_owner")
                    or dom.STATUS_KIND_OWNERS.get(entry["kind"]),
                    "—",
                ),
            }
            for entry in state.get("item_kinds", [])
        ],
        "handlers": [
            {
                "handle": h["handle"],
                "label": h["label"],
                "thread_id": h.get("thread_id"),
                **handler_presentation(h),
                "ui_surface": bool(h.get("ui_surface")),
                "retired": bool(h.get("retired")),
            }
            for h in state["handlers"]
        ],
    }
