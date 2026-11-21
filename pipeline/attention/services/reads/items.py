"""Read-model items: the item view and the open-item sets
— split from model.py; attention.services.reads.model
re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from attention.domain import attention as dom
from attention.services.waits import facts as facts_mod
from attention.services.waits import fulfillment
from attention.settings import Settings

from .labels import (
    PROVENANCE_LABELS,
    TIER_LABELS,
    _iso,
    _kind_label,
    digest_windows,
    handler_map,
    handler_presentation,
)
from .verbs import item_staleness, verbs_for


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
