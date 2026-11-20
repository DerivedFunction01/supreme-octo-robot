"""The send-ledger dispatch lifecycle (spec §1.12).

A recorded send is undispatched until one attributed
consumer claims it; delivery exists only as that
consumer's ack, carrying the chat surface's reference.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from attention.errors import Conflict, NotFound, Validation
from attention.settings import Settings

LABELS = {
    "undispatched": "Undispatched",
    "claimed": "Claimed",
    "delivered": "Delivered",
    "not_dispatchable": "Not dispatchable",
}


def _blank() -> dict:
    return {
        "consumer": None,
        "claimed_at": None,
        "claim_expires_at": None,
        "delivered_at": None,
        "delivery_ref": None,
        "attempts": 0,
        "bridge_request_id": None,
        "envelope_id": None,
        "suppressed_at": None,
        "suppressed_reason": None,
    }


def state_of(send: dict, now: datetime | None = None) -> str:
    """The send's current dispatch state, with expiry
    applied at read time rather than by a sweeper."""
    if send.get("mode") == "shadow" or send.get("outcome") == "shadow":
        return "not_dispatchable"
    dispatch = send.get("dispatch") or {}
    if dispatch.get("delivered_at") is not None:
        return "delivered"
    if dispatch.get("suppressed_at") is not None:
        return "not_dispatchable"
    expires = dispatch.get("claim_expires_at")
    if dispatch.get("claimed_at") is not None and (
        now is None or expires is None or expires > now
    ):
        return "claimed"
    return "undispatched"


def view(send: dict, now: datetime | None = None) -> dict:
    """The dispatch object the send view serves."""
    dispatch = {**_blank(), **(send.get("dispatch") or {})}
    state = state_of(send, now)
    return {
        "state": state,
        "state_label": LABELS[state],
        "consumer": dispatch["consumer"],
        "claimed_at": dispatch["claimed_at"],
        "claim_expires_at": dispatch["claim_expires_at"],
        "delivered_at": dispatch["delivered_at"],
        "delivery_ref": dispatch["delivery_ref"],
        "attempts": dispatch["attempts"],
        "bridge_request_id": dispatch["bridge_request_id"],
        "envelope_id": dispatch["envelope_id"],
        "suppressed_at": dispatch["suppressed_at"],
        "suppressed_reason": dispatch["suppressed_reason"],
    }


def suppress(state: dict, send_id: str, payload: dict, now: datetime):
    """Retire a moot send to a terminal not-dispatchable
    state, with its reason on the record. A delivered
    send's history is never rewritten."""
    send = _find(state, send_id)
    if state_of(send, now) == "delivered":
        raise Conflict("A delivered send cannot be suppressed.")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise Validation(
            "Suppression failed validation.",
            [{"field": "reason", "message": "a reason is required"}],
        )
    dispatch = send.setdefault("dispatch", _blank())
    dispatch["suppressed_at"] = now
    dispatch["suppressed_reason"] = reason.strip()
    return send


def undispatched(state: dict, now: datetime) -> list:
    """Claimable sends in ledger order (the drain order)."""
    return [s for s in state.get("sends", []) if state_of(s, now) == "undispatched"]


def _find(state: dict, send_id: str) -> dict:
    for send in state.get("sends", []):
        if send["id"] == send_id:
            return send
    raise NotFound("No such send.")


def _consumer(payload: dict) -> str:
    consumer = payload.get("consumer")
    if not isinstance(consumer, str) or not consumer.strip():
        raise Validation(
            "Dispatch failed validation.",
            [{"field": "consumer", "message": "is required"}],
        )
    return consumer.strip()


def claim(state: dict, send_id: str, payload: dict, settings: Settings, now: datetime):
    """Claim one send for a bounded lease."""
    consumer = _consumer(payload)
    send = _find(state, send_id)
    current = state_of(send, now)
    if current == "not_dispatchable":
        raise Validation(
            "Dispatch failed validation.",
            [{"field": "send", "message": "shadow sends are not dispatchable"}],
        )
    if current == "delivered":
        raise Conflict("That send has already been delivered.")
    dispatch = {**_blank(), **(send.get("dispatch") or {})}
    if current == "claimed":
        if dispatch["consumer"] != consumer:
            raise Conflict("That send is claimed by another consumer.")
        send["dispatch"] = dispatch
        return send
    dispatch.update(
        consumer=consumer,
        claimed_at=now,
        claim_expires_at=now + timedelta(minutes=settings.dispatch_claim_minutes),
        attempts=dispatch["attempts"] + 1,
    )
    send["dispatch"] = dispatch
    return send


def ack(state: dict, send_id: str, payload: dict, now: datetime):
    """Record delivery: the claiming consumer, before
    expiry, with the chat surface's reference."""
    consumer = _consumer(payload)
    reference = payload.get("delivery_ref")
    if not isinstance(reference, str) or not reference.strip():
        raise Validation(
            "Dispatch failed validation.",
            [{"field": "delivery_ref", "message": "is required"}],
        )
    send = _find(state, send_id)
    current = state_of(send, now)
    if current == "delivered":
        raise Conflict("That send has already been delivered.")
    if current != "claimed":
        raise Conflict("That send holds no live claim to acknowledge.")
    dispatch = {**_blank(), **(send.get("dispatch") or {})}
    if dispatch["consumer"] != consumer:
        raise Conflict("That send is claimed by another consumer.")
    dispatch.update(delivered_at=now, delivery_ref=reference.strip())
    send["dispatch"] = dispatch
    return send
