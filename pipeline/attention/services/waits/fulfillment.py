"""Decision fulfillment: the verdict is recorded at
the tap; fulfillment is a separate, verified event —
read from the send ledger for sends and from the
scripted fact measurement for pushes, never assumed."""

from __future__ import annotations

from datetime import datetime

from attention.domain import attention as dom
from attention.services.dispatch import dispatch
from attention.settings import Settings

LABELS = {
    "queued": "Decided — waiting to send",
    "sent": "Decided — sent, awaiting the act",
    "recorded": "Decided — recorded",
    "fulfilled": "Decided — fulfilled",
    "failed": "Fulfillment failed — back in your queue",
    "stalled": "Fulfillment stalled — back in your queue",
}
OPEN_STATES = ("queued", "sent", "recorded")
RETURNED_STATES = ("failed", "stalled")


def _send_state(item: dict, state: dict, decision: dict, now: datetime) -> str:
    send = next(
        (s for s in state.get("sends", []) if s["id"] == decision.get("send_id")),
        None,
    )
    if send is None:
        return "recorded"
    failures = [
        f for f in state.get("dispatch_failures", []) if f.get("send_id") == send["id"]
    ]
    current = dispatch.state_of(send, now)
    if current == "delivered":
        return "fulfilled"
    if failures:
        return "failed"
    if current == "not_dispatchable":
        return "recorded"
    return "sent" if current == "claimed" else "queued"


def derive(
    item: dict,
    state: dict,
    now: datetime,
    settings: Settings,
    fact: dict | None = None,
) -> dict | None:
    """The item's fulfillment view, or None when the
    item carries no recorded decision."""
    decision = item.get("decision")
    if not decision:
        return None
    if decision.get("fulfillment") == "fulfilled":
        return {
            "state": "fulfilled",
            "label": LABELS["fulfilled"],
            "verb": decision["verb"],
            "verb_label": dom.VERB_LABELS.get(decision["verb"], decision["verb"]),
            "at": decision["at"],
            "option_id": decision.get("option_id"),
            "send_id": decision.get("send_id"),
            "evidence": decision.get("evidence"),
        }
    if item["kind"] == "push_needed":
        fact_state = (fact or {}).get("state")
        if fact_state == "pushed":
            current = "fulfilled"
        elif fact_state == "gone":
            current = "failed"
        else:
            current = "queued"
        label = (
            "Decided — awaiting the push" if current == "queued" else LABELS[current]
        )
    else:
        current = _send_state(item, state, decision, now)
        label = LABELS[current]
        if current in OPEN_STATES:
            age = (now - decision["at"]).total_seconds() / 60
            if age > settings.fulfillment_stall_minutes:
                current, label = "stalled", LABELS["stalled"]
    return {
        "state": current,
        "label": label,
        "verb": decision["verb"],
        "verb_label": dom.VERB_LABELS.get(decision["verb"], decision["verb"]),
        "at": decision["at"],
        "option_id": decision.get("option_id"),
        "send_id": decision.get("send_id"),
    }


def returned_items(
    state: dict, now: datetime, settings: Settings, facts: dict | None = None
) -> list:
    """Decided items whose fulfillment failed or
    stalled: they stand in the decision queue again,
    with their history on their face."""
    out = []
    for item in state["items"]:
        if item["triage"] != "done" or not item.get("decision"):
            continue
        view = derive(item, state, now, settings, (facts or {}).get(item["id"]))
        if view and view["state"] in RETURNED_STATES:
            out.append(item)
    return out


def decided_items(
    state: dict, now: datetime, settings: Settings, facts: dict | None = None
) -> list:
    """Decided items still awaiting fulfillment: out
    of the decision queue, visible in their own band."""
    out = []
    for item in state["items"]:
        if item["triage"] != "done" or not item.get("decision"):
            continue
        view = derive(item, state, now, settings, (facts or {}).get(item["id"]))
        if view and view["state"] in OPEN_STATES:
            out.append(item)
    return out
