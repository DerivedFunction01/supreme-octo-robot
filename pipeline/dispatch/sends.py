"""The send ledger (contract 05 — attention's clauses,
plan §9.2).

Attention's sends list is the dispatch ledger (plan §12,
survivor). A recorded send is undispatched until one
attributed consumer claims it; delivery exists only as
that consumer's ack, carrying the fulfillment's
submission reference. Failure records are never acks.

- **Minting is only through `record_send`.** Four
  producer classes mint: the wait-rule engine, owner
  verbs, handler actions, and the continuation pass —
  owner verbs and continuation mint above the substrate,
  not beside it. Producers compose the text (template
  rendering is theirs); the substrate records the send
  with its id scheme (ATT5: `sNNNN`).
- **Shadow sends are never dispatchable** (ATT5): a
  `mode: shadow` send records and never claims.
- **Claim (ATT6):** one attributed consumer on a
  15-minute lease (the lease length is the caller's
  setting, passed in); expiry is applied at read time —
  no sweeper. Attempts count at claim.
- **Settle-first ordering (§9.2a) is the consumer's
  contract, supported here:** `stamp_late_fulfillment`
  records a suppressed send's late fulfillment as fact —
  it never resurrects the send.
- **Suppress (ATT7):** terminal, reasoned (a mandatory
  reason on the record), refused on a delivered send.
  Attempts exhausted → parked + suppressed with the
  reason on the record (`park_exhausted`).
- **Failure records (§9.2b):** deduplicated to one per
  hour per send + reason.

The lifecycle functions operate on the ledger as a list
of send dicts (the store's shape at S6; the attention
state store's writer re-point and the list's migration
into this repo's stores land at S7). Timestamps are
datetimes at this surface; the storing consumer
serializes.

Ported at S6 from the attention pin's dispatch service
(backend/services/dispatch.py + the consumer's failure
and late-fulfillment clauses), semantics unchanged.
"""
from datetime import timedelta

CLAIM_MINUTES_DEFAULT = 15
MAX_ATTEMPTS_DEFAULT = 6
_FAILURE_GAP = timedelta(hours=1)

LABELS = {
    "undispatched": "Undispatched",
    "claimed": "Claimed",
    "delivered": "Delivered",
    "not_dispatchable": "Not dispatchable",
}


class SendError(Exception):
    """A refused lifecycle act: `name` is the refusal
    class (conflict / validation / not_found), `detail`
    the human line."""

    def __init__(self, name, detail=""):
        super().__init__(detail or name)
        self.name = name
        self.detail = detail or name


def blank_dispatch():
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


def state_of(send, now=None):
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


def view(send, now=None):
    """The dispatch object the send view serves."""
    dispatch = {**blank_dispatch(), **(send.get("dispatch") or {})}
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


def _new_send_id(sends):
    top = 0
    for send in sends:
        sid = send.get("id") or ""
        if sid.startswith("s") and sid[1:].isdigit():
            top = max(top, int(sid[1:]))
    return f"s{top + 1:04d}"


def record_send(sends, *, producer, template, version, text,
                handle, target, now, rule_id=None, wait_id=None,
                fact_hash=None, mode="active", presence="active",
                attempt=1):
    """Mint one send into the ledger — the only minting
    surface. `producer` names the producer class
    (wait-rule engine, owner verb, handler action,
    continuation) and is carried on the record for audit.
    A shadow-mode send is recorded with outcome `shadow`
    and can never be claimed."""
    if mode not in ("active", "shadow"):
        raise SendError("validation", f"bad send mode {mode!r}")
    send = {
        "id": _new_send_id(sends),
        "at": now,
        "rule_id": rule_id,
        "wait_id": wait_id,
        "handle": handle,
        "target": target,
        "template": template,
        "version": version,
        "attempt": attempt,
        "presence": presence,
        "text": text,
        "fact_hash": fact_hash,
        "mode": mode,
        "outcome": "shadow" if mode == "shadow" else "recorded",
        "producer": producer,
        "dispatch": blank_dispatch(),
    }
    sends.append(send)
    return send


def _find(sends, send_id):
    for send in sends:
        if send["id"] == send_id:
            return send
    raise SendError("not_found", "No such send.")


def _consumer(consumer):
    if not isinstance(consumer, str) or not consumer.strip():
        raise SendError("validation", "consumer is required")
    return consumer.strip()


def undispatched(sends, now):
    """Claimable sends in ledger order (the drain order)."""
    return [s for s in sends if state_of(s, now) == "undispatched"]


def claim(sends, send_id, consumer, now,
          claim_minutes=CLAIM_MINUTES_DEFAULT):
    """Claim one send for a bounded lease. Re-claiming by
    the same consumer inside its lease is a no-op return;
    an expired claim is claimable again (expiry applied
    at read time)."""
    consumer = _consumer(consumer)
    send = _find(sends, send_id)
    current = state_of(send, now)
    if current == "not_dispatchable":
        raise SendError(
            "validation", "shadow sends are not dispatchable"
            if send.get("mode") == "shadow"
            else "that send is not dispatchable")
    if current == "delivered":
        raise SendError("conflict", "That send has already been delivered.")
    dispatch = {**blank_dispatch(), **(send.get("dispatch") or {})}
    if current == "claimed":
        if dispatch["consumer"] != consumer:
            raise SendError(
                "conflict", "That send is claimed by another consumer.")
        send["dispatch"] = dispatch
        return send
    dispatch.update(
        consumer=consumer,
        claimed_at=now,
        claim_expires_at=now + timedelta(minutes=claim_minutes),
        attempts=dispatch["attempts"] + 1,
    )
    send["dispatch"] = dispatch
    return send


def ack(sends, send_id, consumer, delivery_ref, now):
    """Record delivery: the claiming consumer, before
    expiry, with the fulfillment's submission reference.
    Failure records are never acks — there is no other
    path into `delivered_at`."""
    consumer = _consumer(consumer)
    if not isinstance(delivery_ref, str) or not delivery_ref.strip():
        raise SendError("validation", "delivery_ref is required")
    send = _find(sends, send_id)
    current = state_of(send, now)
    if current == "delivered":
        raise SendError("conflict", "That send has already been delivered.")
    if current != "claimed":
        raise SendError(
            "conflict", "That send holds no live claim to acknowledge.")
    dispatch = {**blank_dispatch(), **(send.get("dispatch") or {})}
    if dispatch["consumer"] != consumer:
        raise SendError(
            "conflict", "That send is claimed by another consumer.")
    dispatch.update(delivered_at=now, delivery_ref=delivery_ref.strip())
    send["dispatch"] = dispatch
    return send


def suppress(sends, send_id, reason, now):
    """Retire a moot send to a terminal not-dispatchable
    state, with its reason on the record. A delivered
    send's history is never rewritten."""
    send = _find(sends, send_id)
    if state_of(send, now) == "delivered":
        raise SendError(
            "conflict", "A delivered send cannot be suppressed.")
    if not isinstance(reason, str) or not reason.strip():
        raise SendError("validation", "a reason is required")
    dispatch = send.setdefault("dispatch", blank_dispatch())
    dispatch["suppressed_at"] = now
    dispatch["suppressed_reason"] = reason.strip()
    return send


def stamp_late_fulfillment(sends, send_id, delivery_ref, now):
    """The suppressed-but-fulfilled edge (§9.2a): a send
    suppressed while its bridge record was outstanding
    was fulfilled anyway. Stamp the delivery as fact —
    delivered_at + the reference land on the record,
    alongside the suppressed reason, which stays. Never
    resurrect: the send is terminal either way (state_of
    reads the stamped delivery, as in the source), is
    never claimable or re-queued, and no second
    fulfillment can land on it."""
    send = _find(sends, send_id)
    dispatch = send.setdefault("dispatch", blank_dispatch())
    if dispatch.get("suppressed_at") is None:
        raise SendError(
            "conflict", "that send is not suppressed; ack is its path")
    dispatch["delivered_at"] = now
    dispatch["delivery_ref"] = delivery_ref
    return send


def release_claim(sends, send_id):
    """Drop the claim and the bridge link after a
    terminal bridge failure; attempts stay counted."""
    send = _find(sends, send_id)
    dispatch = send.get("dispatch") or {}
    dispatch.update(
        consumer=None,
        claimed_at=None,
        claim_expires_at=None,
        bridge_request_id=None,
        envelope_id=None,
    )
    send["dispatch"] = dispatch
    return send


def park_exhausted(sends, send_id, now,
                   max_attempts=MAX_ATTEMPTS_DEFAULT):
    """Attempts exhausted without a fulfillment: park the
    send and suppress it with the reason on the record.
    Returns True when this call parked it."""
    send = _find(sends, send_id)
    dispatch = send.get("dispatch") or {}
    if (dispatch.get("attempts") or 0) < max_attempts:
        return False
    release_claim(sends, send_id)
    suppress(sends, send_id,
             "Delivery attempts exhausted without a fulfillment.", now)
    return True


def record_failure(failures, send_id, consumer, reason, now):
    """Record a delivery failure, at most once an hour
    per send + reason (§9.2b). Returns the record, or
    None when this failure is a duplicate inside the
    window. A failure record is never an ack."""
    for failure in failures:
        at = failure.get("at")
        if (
            failure.get("send_id") == send_id
            and failure.get("reason") == reason
            and at is not None
            and now - at < _FAILURE_GAP
        ):
            return None
    record = {"send_id": send_id, "consumer": consumer,
              "reason": reason, "at": now}
    failures.append(record)
    return record


def bridge_envelope(send):
    """The bridge envelope form for a claimed send
    (contract 05): `attn-<send-id>-a<attempts>`."""
    dispatch = send.get("dispatch") or {}
    return f"attn-{send['id']}-a{dispatch.get('attempts') or 0}"
