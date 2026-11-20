"""The permission-card watcher core (card-owner plan,
Steps 2–4: reconciliation and the orphan self-poster,
resolution watching, resumption verification).

One behavior: keep attention state's `permission_card`
waits in step with the runtime's permission cards. Each
pass takes a pending snapshot through the card source
(`registry.cards.cardsource`, the Step 1 seam), reconciles it
against the `card_watch` ledger in attention state, posts
exactly one wait per observed card, watches each card to
an authoritative resolution, and — after an approval —
verifies the blocked work actually resumed before
closing anything.

The discipline, all load-bearing:

- **Outcomes come from history records only** (contract
  05, card-watch source section). A card disappearing
  from the pending list is not a resolution: with no
  history outcome the card is `resolution_unconfirmed`
  and its wait stays open. No attention-side decision,
  send delivery, or acknowledgement ever stamps an
  outcome here.
- **Source-stale is a non-run.** A snapshot that fails,
  fails fulfillment, or goes undrained leaves the store
  untouched — the pass returns before state is even
  loaded, and never reads as zero cards.
- **The watcher never resolves a card.** It holds no
  approve or deny capability and writes no runtime
  decision; it surfaces, stamps, escalates, and
  verifies. The wait it posts is the pinned ingestion
  shape (`decision: pending`, hard-stop class
  `permission_card`, idempotency key
  `permission-card:<approval_id>`), extended only by the
  `card` provenance subrecord.
- **Approval opens verification, not closure.** An
  approved card closes only on measured movement after
  the decision time — by default a newer handler status
  post in attention state; a probe can be injected for
  the work-record sources. A delivered send or an
  acknowledgement is not movement.
- **Escalation is stamped here, sent by the cadence
  lane.** The spine records `escalated_at` / `notify_due`
  facts at the standing bounds (expiry: immediately;
  stalled approval: one hour); wiring those stamps into
  sends is Step 5's half of the plan.

State shape (frozen at Step 1, recorded in contract 05):
the `card_watch` ledger maps `approval_id` to an entry
carrying the origin mapping, the linked wait and item
ids, first-seen / last-seen-pending stamps, expiry, the
entry state (`pending` | `resolution_unconfirmed` |
`verifying` | `closed`), the history-stamped outcome
and decision time, the close kind, and the nudge,
escalation, and redrive stamps.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from dispatch import sends as _sends

from . import cardsource

UTC = timezone.utc

POSTER = "card-watch"
WAIT_CLASS = "permission_card"
IDEMPOTENCY_PREFIX = "permission-card:"
MAIN_HANDLE = "main"

# Standing supervision timings (the plan introduces no
# new values): the checkpoint cadence is 15 minutes, so
# two intervals is 30; the staffing escalation bound is
# one hour.
REDRIVE_AFTER = timedelta(minutes=30)
ESCALATE_AFTER = timedelta(minutes=60)

STATE_PENDING = "pending"
STATE_UNCONFIRMED = "resolution_unconfirmed"
STATE_VERIFYING = "verifying"
STATE_CLOSED = "closed"

CLOSE_DENIED = "denied"
CLOSE_EXPIRED = "expired"
CLOSE_OTHER = "other"
CLOSE_VERIFIED = "verified_resumed"

PASS_COMPLETE = "complete"
PASS_SOURCE_STALE = "source_stale"
PASS_PARTIAL_HISTORY = "partial_history"

# Outcomes the history vocabulary names as terminal
# closures of their own kind; any other stamped outcome
# is terminal-other. `approved` is not a closure at all.
_NAMED_CLOSES = {"denied": CLOSE_DENIED, "expired": CLOSE_EXPIRED}


@dataclass(frozen=True)
class PassResult:
    """One pass's enumerable outcome (the cadence entry's
    exit alphabet names these kinds). `detail` carries
    the stale reason or the partial-history card id."""

    kind: str
    detail: str = ""


# ------------------------------------------------------------ time

def _as_dt(value):
    """Normalize a state value to an aware datetime.

    State mixes datetimes (the store's own stamps) with
    ISO strings (the card DTO's served stamps, which the
    store's decode heuristic restores to datetimes on
    load anyway); every comparison goes through here."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _as_dt_strict(value):
    """The strict sibling of `_as_dt`: the same
    normalization, but a malformed stamp raises instead of
    serving None (the scheduling card watch's adapter
    contract — its core takes an aware datetime, and a bad
    clock stamp there is a hard error, not an unknown)."""
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


# ------------------------------------------------------------ waits

def _new_wait_id(waits):
    """The pinned id algorithm (ATT5: `wNNNN`, minted
    from the persisted waits so a restart never reissues
    an id already in state)."""
    top = 0
    for wait in waits:
        wid = str(wait.get("id", ""))
        if wid.startswith("w") and wid[1:].isdigit():
            top = max(top, int(wid[1:]))
    return f"w{top + 1:04d}"


def _fact_hash(wait):
    """The pinned fact hash: the wait's content facts,
    never its decision state (the engine dedupes on it)."""
    facts = {
        key: wait.get(key)
        for key in (
            "summary", "status_code", "kind", "wait_class",
            "program_approved", "reversible", "in_budget",
            "only_blocker",
        )
    }
    blob = json.dumps(facts, sort_keys=True, default=str).encode()
    return hashlib.sha1(blob).hexdigest()[:12]


def _summary_for(dto):
    parts = [dto.purpose or "Permission card"]
    if dto.scope:
        parts.append(dto.scope)
    return " — ".join(parts)


def _map_origin(state, dto):
    """(handle, origin_kind): a chat origin matching a
    registered handler's thread posts under that handler;
    a cron origin, an unknown origin, or an unmatched
    chat posts under main as an orphan — never dropped,
    never under an invented handle."""
    if dto.origin_kind == "chat" and dto.origin_id:
        for handler in state.get("handlers", []):
            if handler.get("thread_id") == dto.origin_id \
                    and handler.get("handle") \
                    and not handler.get("retired"):
                return handler["handle"], "chat"
    return MAIN_HANDLE, "orphan"


def _post_wait(state, entry, dto, now):
    """Post the card's wait in the pinned ingestion
    shape, idempotent on the card's key: a standing wait
    with the same key is returned, never duplicated."""
    key = IDEMPOTENCY_PREFIX + dto.approval_id
    for wait in state["waits"]:
        if wait.get("idempotency_key") == key:
            return wait
    wait = {
        "id": _new_wait_id(state["waits"]),
        "handle": entry["handle"],
        "posted_by": POSTER,
        "wait_class": WAIT_CLASS,
        "summary": _summary_for(dto),
        "status_code": None,
        "kind": None,
        "program_approved": False,
        "reversible": False,
        "in_budget": False,
        "only_blocker": False,
        "idempotency_key": key,
        "posted_at": now,
        "decision": "pending",
        "rule_id": None,
        "decided_at": None,
        "evaluated": False,
        "last_fact_hash": None,
        "card": {
            "approval_id": dto.approval_id,
            "purpose": dto.purpose,
            "scope": dto.scope,
            "requested_at": dto.requested_at,
            "expires_at": dto.expires_at,
            "origin_kind": entry["origin_kind"],
            "origin_id": dto.origin_id,
            "outcome": None,
            "decided_at": None,
        },
    }
    wait["fact_hash"] = _fact_hash(wait)
    state["waits"].append(wait)
    return wait


def _find_wait(state, wait_id):
    for wait in state.get("waits", []):
        if wait.get("id") == wait_id:
            return wait
    return None


def _linked_item(state, wait_id):
    """The owner item the attention surface derived from
    this wait, when one exists in state."""
    if not wait_id:
        return None
    for item in state.get("items", []):
        if item.get("wait_id") == wait_id:
            return item
    return None


def _close(state, entry, wait, now, close_kind, verification=None):
    """Close as a stored fact: the wait's decision lands
    as `resolved` with the pass stamp, and a linked item
    is marked done on its own record — the self-clearing
    pattern, never a render mask."""
    if wait is not None and wait.get("decision") in (
            "pending", "surfaced"):
        wait["decision"] = "resolved"
        wait["decided_at"] = now
    item = _linked_item(state, entry.get("wait_id"))
    if item is not None:
        entry["item_id"] = item["id"]
        item["triage"] = "done"
    entry["state"] = STATE_CLOSED
    entry["closed_at"] = now
    entry["close_kind"] = close_kind
    if verification is not None:
        entry["verification"] = verification


# ------------------------------------------------------------ movement

def _handler_status_movement(state, entry):
    """The default movement measure: a handler status
    post newer than the approval's decision time. A
    terminal code is completion; any newer post is
    movement. Orphan cards have no lane record to
    measure — their verification rides an injected probe
    or stands unavailable."""
    if entry.get("origin_kind") == "orphan":
        return None
    record = (state.get("handler_status") or {}).get(
        entry.get("handle")) or {}
    at = _as_dt(record.get("at"))
    decided = _as_dt(entry.get("outcome_decided_at"))
    if at is None or decided is None or at <= decided:
        return None
    terminal = {
        code.get("code")
        for code in state.get("status_codes", [])
        if code.get("terminal")
    }
    if record.get("status_code") in terminal:
        return f"terminal_status:{record.get('status_code')}"
    return "status_post"


# ------------------------------------------------------------ redrive

def _mint_redrive(state, entry, wait, now, attempt):
    """Mint the continuation redrive through the one
    minting surface (producer class continuation,
    template `continuation`), ledgered on the entry by
    the caller so no twin is minted while it stands."""
    template = next(
        (t for t in state.get("templates", [])
         if t.get("kind") == "continuation"),
        None,
    )
    version = (template or {}).get("version", 1)
    text_template = (template or {}).get(
        "text", "Continue — {summary} {detail}")
    card = (wait or {}).get("card") or {}
    summary = (
        "Permission card approved, the blocked work has "
        f"not moved: {card.get('purpose') or entry['approval_id']}"
    )
    detail = (
        f"The card was approved at "
        f"{entry.get('outcome_decided_at')}; no movement "
        "has been measured since. Resume the blocked "
        "work, or post the status that shows it resumed."
    )
    text = text_template.replace("{summary}", summary) \
        .replace("{detail}", detail)
    handler = next(
        (h for h in state.get("handlers", [])
         if h.get("handle") == entry["handle"]),
        {},
    )
    target = handler.get("thread_id") or entry.get("origin_id") \
        or entry["handle"]
    send = _sends.record_send(
        state["sends"],
        producer="continuation",
        template="continuation",
        version=version,
        text=text,
        handle=entry["handle"],
        target=target,
        now=now,
        wait_id=entry.get("wait_id"),
        attempt=attempt,
    )
    entry["redrive_send_id"] = send["id"]
    entry["redrive_minted_at"] = now
    entry["redrive_attempts"] = attempt
    return send


def _verify(state, entry, wait, now, probe):
    """Step 4: an approved card closes only on measured
    movement. Past two cadence intervals without any, a
    mapped card is re-driven (no twin while a prior send
    stands undelivered or suppressed; a delivered send
    earns a repeat on the same bound) and the row
    escalates at one hour; an orphan card escalates as
    verification-unavailable instead of closing."""
    decided = _as_dt(entry.get("outcome_decided_at"))
    if decided is None:
        return False
    evidence = probe(state, entry)
    if evidence is not None:
        entry["movement"] = evidence
        _close(state, entry, wait, now, CLOSE_VERIFIED,
               verification="verified")
        return True
    if now < decided + REDRIVE_AFTER:
        return False
    changed = False
    if entry.get("origin_kind") == "orphan":
        if entry.get("verification") != "verification_unavailable":
            entry["verification"] = "verification_unavailable"
            changed = True
        # No lane exists to redrive: the escalation is
        # the act at this bound, not a later one.
        if entry.get("escalated_at") is None:
            entry["escalated_at"] = now
            changed = True
    else:
        prior = next(
            (s for s in state.get("sends", [])
             if s.get("id") == entry.get("redrive_send_id")),
            None,
        )
        if prior is None:
            _mint_redrive(state, entry, wait, now, 1)
            changed = True
        elif _sends.state_of(prior, now) == "delivered":
            minted = _as_dt(entry.get("redrive_minted_at"))
            if minted is not None and now >= minted + REDRIVE_AFTER:
                _mint_redrive(state, entry, wait, now,
                              (entry.get("redrive_attempts") or 1) + 1)
                changed = True
    if now >= decided + ESCALATE_AFTER \
            and entry.get("escalated_at") is None:
        entry["escalated_at"] = now
        changed = True
    return changed


# ------------------------------------------------------------ resolution

def _apply_outcome(state, entry, wait, resolved, now, probe):
    """Stamp a history outcome — the only outcome source
    there is. Approval moves the card to verifying (and
    verification runs in this same pass); every other
    stamped outcome closes the wait as a stored fact."""
    entry["outcome"] = resolved.outcome
    entry["outcome_decided_at"] = resolved.decided_at
    if wait is not None and isinstance(wait.get("card"), dict):
        wait["card"]["outcome"] = resolved.outcome
        wait["card"]["decided_at"] = resolved.decided_at
    if resolved.outcome == "approved":
        entry["state"] = STATE_VERIFYING
        _verify(state, entry, wait, now, probe)
        return
    close_kind = _NAMED_CLOSES.get(resolved.outcome, CLOSE_OTHER)
    if entry.get("origin_kind") == "chat":
        # The originating lane is known; the outcome
        # notification send is the cadence lane's wiring
        # over this stamp (no template in the registry
        # speaks for a runtime outcome today).
        entry["notify_due"] = True
    _close(state, entry, wait, now, close_kind)


# ------------------------------------------------------------ the pass

def run_pass(store, source, now, movement_probe=None):
    """One watcher pass over the store and the source.

    `store` is an AttentionStateStore (load_state /
    save_state); `source` is a card source
    (`pending_snapshot` / `history`, per cardsource);
    `now` is the pass's aware datetime — every stamp the
    pass writes derives from it, never from a wall clock
    read inside the pass. `movement_probe(state, entry)`
    may replace the default status-post measure."""
    probe = movement_probe or _handler_status_movement
    snapshot = source.pending_snapshot()
    if isinstance(snapshot, cardsource.SourceStale):
        # A non-run: state is not loaded, not saved, and
        # never read as zero cards.
        return PassResult(
            PASS_SOURCE_STALE,
            f"{snapshot.reason}:{snapshot.detail}")
    state = store.load_state()
    ledger = state.setdefault("card_watch", {})
    dirty = False
    partial = ""

    # Reconcile the snapshot: one wait per card, mapped
    # lane or orphan alike.
    seen = set()
    for dto in snapshot.cards:
        seen.add(dto.approval_id)
        entry = ledger.get(dto.approval_id)
        if entry is None:
            handle, origin_kind = _map_origin(state, dto)
            entry = {
                "approval_id": dto.approval_id,
                "handle": handle,
                "origin_kind": origin_kind,
                "origin_id": dto.origin_id,
                "wait_id": None,
                "item_id": None,
                "first_seen_at": now,
                "last_seen_pending_at": now,
                "requested_at": dto.requested_at,
                "expires_at": dto.expires_at,
                "state": STATE_PENDING,
                "outcome": None,
                "outcome_decided_at": None,
                "closed_at": None,
                "close_kind": None,
                "expired_unresolved_at": None,
                "last_nudged_at": None,
                "escalated_at": None,
                "notify_due": False,
                "verification": None,
                "movement": None,
                "redrive_send_id": None,
                "redrive_minted_at": None,
                "redrive_attempts": 0,
            }
            ledger[dto.approval_id] = entry
            entry["wait_id"] = _post_wait(state, entry, dto, now)["id"]
            dirty = True
        elif entry["state"] != STATE_CLOSED:
            entry["last_seen_pending_at"] = now
            if entry["state"] == STATE_UNCONFIRMED:
                entry["state"] = STATE_PENDING
            dirty = True
        item = _linked_item(state, entry.get("wait_id"))
        if item is not None and entry.get("item_id") != item["id"]:
            entry["item_id"] = item["id"]
            dirty = True

    # Resolution watching, then verification.
    for entry in ledger.values():
        if entry["state"] == STATE_CLOSED:
            continue
        wait = _find_wait(state, entry.get("wait_id"))
        if entry["state"] == STATE_VERIFYING:
            if _verify(state, entry, wait, now, probe):
                dirty = True
            continue
        result = source.history(entry["approval_id"])
        if isinstance(result, cardsource.SourceStale):
            partial = entry["approval_id"]
            continue
        if isinstance(result, cardsource.Resolved):
            _apply_outcome(state, entry, wait, result, now, probe)
            dirty = True
            continue
        # Unresolved: absence from pending with no
        # outcome is unconfirmed, never a closure; a
        # card still listed past its own expiry is
        # expired-unresolved and escalated, not closed.
        if entry["approval_id"] not in seen \
                and entry["state"] == STATE_PENDING:
            entry["state"] = STATE_UNCONFIRMED
            dirty = True
        if entry["approval_id"] in seen:
            expires = _as_dt(entry.get("expires_at"))
            if expires is not None and now > expires \
                    and entry.get("expired_unresolved_at") is None:
                entry["expired_unresolved_at"] = now
                if entry.get("escalated_at") is None:
                    entry["escalated_at"] = now
                dirty = True

    if dirty:
        store.save_state(state)
    if partial:
        return PassResult(PASS_PARTIAL_HISTORY, partial)
    return PassResult(PASS_COMPLETE)
