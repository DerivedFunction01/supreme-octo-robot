"""Read-model sections: the per-section builders (glance,
today, handler, sends, registries) — split from
model.py; attention.services.reads.model re-exports
this surface.
"""

from __future__ import annotations

from datetime import datetime

from attention.domain import attention as dom
from attention.services.dispatch import dispatch as dispatch_mod
from attention.services.waits import facts as facts_mod
from attention.services.waits import fulfillment
from attention.settings import Settings

from .items import _live_items, item_view
from .labels import (
    BAND_LABELS,
    BAND_ORDER,
    CONTRACT,
    DECISION_LABELS,
    DIGEST_OWNER_LABELS,
    MODE_LABELS,
    OUTCOME_LABELS,
    PROVENANCE_LABELS,
    _iso,
    _kind_label,
    class_label,
    digest_windows,
    effective_mode,
    handler_map,
    handler_order,
    handler_presentation,
    presence_view,
    status_label,
)
from .verbs import handler_verbs, quick_verbs_for_status


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
