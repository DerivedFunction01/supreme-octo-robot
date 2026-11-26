"""RETIRED (attention fold): the service's
own dispatch consumer. The tick no longer runs it —
sends are born settled retired in the waits engine and
nothing is claimable or enqueueable — and this module
stays in tree only as the record of the retired §1.12
consumer: it claimed the ledger's sends on the tick,
delivered through the bridge, acked only on the
fulfillment's submission reference; failures were
recorded, never acknowledged.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from attention.infra import bridge_client
from attention.services.dispatch import dispatch
from attention.services.writes import writes
from attention.settings import Settings

_FAILURE_GAP = timedelta(hours=1)


def _meta(send: dict) -> dict:
    """The delivery framing, carried as record data: who
    sent this, under which rule, and the text's digest —
    never as directions inside the payload text."""
    return {
        "source": "owner-attention",
        "send_id": send["id"],
        "template": send.get("template"),
        "target": send.get("target"),
        "rule_id": send.get("rule_id"),
        "sha256": hashlib.sha256(send["text"].encode()).hexdigest(),
    }


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _resolve_target(state: dict, send: dict) -> str | None:
    """The target chat from the registry, or None."""
    target = send.get("target")
    if not target:
        return None
    handlers = {h["handle"]: h for h in state.get("handlers", [])}
    if target in handlers:
        return handlers[target].get("thread_id")
    if _UUID.match(target):
        return target
    return None


def _record_failure(
    state: dict, send_id: str, consumer: str, reason: str, now: datetime
) -> None:
    """Record a delivery failure, at most once an hour
    per send and reason (the pass retries every minute)."""
    for failure in state.get("dispatch_failures") or []:
        if (
            failure.get("send_id") == send_id
            and failure.get("reason") == reason
            and isinstance(failure.get("at"), datetime)
            and now - failure["at"] < _FAILURE_GAP
        ):
            return
    writes.record_dispatch_failure(
        state, {"send_id": send_id, "consumer": consumer, "reason": reason}, now
    )


def _release(send: dict) -> None:
    """Drop the claim and the bridge link after a
    terminal bridge failure; attempts stay counted."""
    record = send.get("dispatch") or {}
    record.update(
        consumer=None,
        claimed_at=None,
        claim_expires_at=None,
        bridge_request_id=None,
        envelope_id=None,
    )
    send["dispatch"] = record


def _claim(state: dict, send: dict, settings: Settings, now: datetime) -> None:
    dispatch.claim(
        state, send["id"], {"consumer": settings.dispatch_consumer}, settings, now
    )


def _settle(state: dict, settings: Settings, send: dict, now: datetime, bridge) -> str:
    """Act on one send's outstanding bridge record:
    acked, failed, waiting, or unavailable."""
    consumer = settings.dispatch_consumer
    record = send.get("dispatch") or {}
    try:
        result = bridge.fetch_result(settings, record["bridge_request_id"])
    except bridge.BridgeUnavailable:
        return "unavailable"
    if result is None:
        return "unavailable"
    status = result["status"]
    if status == "queued":
        if dispatch.state_of(send, now) == "undispatched":
            _claim(state, send, settings, now)
        return "waiting"
    if status == "done":
        reference = (result.get("result") or {}).get("submission_message_id")
        if reference:
            current = dispatch.state_of(send, now)
            if current == "not_dispatchable":
                # Suppressed while its record was outstanding
                # and fulfilled anyway: stamp the delivery as
                # fact; never resurrect, never poison the pass.
                record = send.setdefault("dispatch", {})
                record["delivered_at"] = now
                record["delivery_ref"] = reference
                return "acked"
            holder = (send.get("dispatch") or {}).get("consumer")
            if current == "claimed" and holder != consumer:
                return "waiting"
            if current != "claimed":
                _claim(state, send, settings, now)
            dispatch.ack(
                state,
                send["id"],
                {"consumer": consumer, "delivery_ref": reference},
                now,
            )
            return "acked"
        reason = "Bridge fulfillment carried no submission reference."
    elif status == "missing":
        reason = "The bridge record for this send no longer exists."
    else:
        reason = result.get("error") or "Bridge fulfillment failed."
    _record_failure(state, send["id"], consumer, reason, now)
    if "retired" in reason.lower():
        # A retirement at the bridge is terminal: the send is
        # never released back into the queue to be re-enqueued.
        dispatch.suppress(
            state, send["id"], {"reason": f"Retired at the bridge: {reason}"}, now
        )
        return "failed"
    _release(send)
    return "failed"


def run_pass(
    state: dict, settings: Settings, now: datetime, bridge=bridge_client
) -> tuple[dict, bool]:
    """One consumer pass: settle outstanding bridge
    records, then claim and enqueue new sends."""
    summary = {"acked": 0, "failed": 0, "enqueued": 0, "waiting": 0}
    changed = False
    failed_this_pass: set = set()
    for send in state.get("sends", []):
        record = send.get("dispatch") or {}
        if not record.get("bridge_request_id"):
            continue
        if dispatch.state_of(send, now) == "delivered":
            continue
        outcome = _settle(state, settings, send, now, bridge)
        if outcome in summary:
            summary[outcome] += 1
        if outcome == "failed":
            failed_this_pass.add(send["id"])
        if outcome != "unavailable":
            changed = True
    for send in dispatch.undispatched(state, now):
        if summary["enqueued"] >= settings.dispatch_pass_cap:
            break
        if send["id"] in failed_this_pass:
            continue
        if (send.get("dispatch") or {}).get("bridge_request_id"):
            continue
        attempts = (send.get("dispatch") or {}).get("attempts") or 0
        if attempts >= settings.dispatch_max_attempts:
            _record_failure(
                state,
                send["id"],
                settings.dispatch_consumer,
                "Delivery attempts exhausted without a fulfillment; "
                "the send is parked.",
                now,
            )
            dispatch.suppress(
                state,
                send["id"],
                {"reason": "Delivery attempts exhausted without a fulfillment."},
                now,
            )
            changed = True
            continue
        chat_id = _resolve_target(state, send)
        if chat_id is None:
            _record_failure(
                state,
                send["id"],
                settings.dispatch_consumer,
                "No thread is registered for this send's target.",
                now,
            )
            changed = True
            continue
        _claim(state, send, settings, now)
        changed = True
        envelope = f"attn-{send['id']}-a{send['dispatch']['attempts']}"
        try:
            queued = bridge.enqueue_chat_send(
                settings, chat_id, send["text"], envelope, meta=_meta(send)
            )
        except bridge.BridgeUnavailable:
            queued = None
        if queued is None:
            continue
        send["dispatch"]["bridge_request_id"] = queued["request_id"]
        send["dispatch"]["envelope_id"] = envelope
        summary["enqueued"] += 1
    return summary, changed
