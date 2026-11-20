"""The card-watch source seam (card-owner plan, Step 1
fan-out: the source lane).

One behavior: turn bridged runtime permission reads into
normalized card DTOs, behind an interface every later step
can fake. Pending cards come only from the bridged
`permissions_list` read; resolutions come only from the
bridged `permissions_history` read (the Step 1 bridge
extension). There is no direct in-process runtime API and
none is invented here: the transport is injected, and in
production it is the scheduling connector client
(`ops/bridge/connector_client.Client`), whose contract this
adapter mirrors — a call returns the tool's result dict,
returns an undrained marker when the request is still
queued at the poll deadline, or raises an enumerable error
carrying a `.name`.

Source-stale is an enumerable result, never an exception
and never an empty snapshot: a read that fails, fails
fulfillment, or goes undrained yields `SourceStale` and
the caller records a non-run, leaving watcher state
untouched. A snapshot whose records do not carry the
whitelist shape is likewise stale (`malformed`) rather
than partial — a partial snapshot read as complete could
silently miss a card, and no card is ever dropped quietly.

Normalization is a whitelist, applied here and nowhere
else: a card DTO carries only `approval_id`, the runtime
purpose and scope text, the request and expiry times, and
the origin (a chat id or a cron/job id). Raw tool
arguments and command payloads from the runtime record
are dropped at this boundary and never enter a wait, a
summary, or the digest.

Disappearance is not resolution: this seam manufactures
no outcome. `history` returns `Resolved` only from a
history record's own outcome stamp, `Unresolved` from the
record's explicit unresolved answer, and `SourceStale`
from everything else.

The DTO field set is the plan's (rulings: normalization
whitelist, wait linkage); if the spine's Step 1 freeze
lands a different shape, the frozen shape wins and this
module changes to match — the seam (result taxonomy,
staleness, whitelist discipline) is the contract either
way.
"""

from dataclasses import dataclass

LIST_TOOL = "permissions_list"
HISTORY_TOOL = "permissions_history"

STALE_UNDRAINED = "undrained"
STALE_TRANSPORT = "transport"
STALE_MALFORMED = "malformed"


@dataclass(frozen=True)
class CardDTO:
    """One pending permission card, whitelist fields only."""

    approval_id: str
    purpose: str
    scope: str
    requested_at: str
    expires_at: str | None
    origin_kind: str  # "chat" | "cron" | "unknown"
    origin_id: str

    def as_dict(self):
        return {
            "approval_id": self.approval_id,
            "purpose": self.purpose,
            "scope": self.scope,
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "origin_kind": self.origin_kind,
            "origin_id": self.origin_id,
        }


@dataclass(frozen=True)
class Snapshot:
    """A good pending snapshot: every observed card."""

    cards: tuple
    taken_at: str


@dataclass(frozen=True)
class SourceStale:
    """An enumerable non-run: the source did not answer.

    `reason` is one of the STALE_* constants; `detail`
    carries the transport error name or the malformed
    shape's description. Never a card list."""

    reason: str
    detail: str = ""


@dataclass(frozen=True)
class Resolved:
    """An authoritative outcome, from a history record only."""

    approval_id: str
    outcome: str  # "approved" | "denied" | "expired" | other terminal
    decided_at: str


@dataclass(frozen=True)
class Unresolved:
    """The history source answered: no outcome stamped yet."""

    approval_id: str


def _text(raw, key):
    value = raw.get(key)
    return value if isinstance(value, str) else ""


def normalize_card(raw):
    """One raw pending record -> CardDTO, or None when the
    record carries no approval_id (the snapshot is then
    malformed at the call site, never silently partial)."""
    if not isinstance(raw, dict):
        return None
    approval_id = raw.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        return None
    if isinstance(raw.get("origin_chat_id"), str) and raw["origin_chat_id"]:
        origin_kind, origin_id = "chat", raw["origin_chat_id"]
    elif isinstance(raw.get("origin_job_id"), str) and raw["origin_job_id"]:
        origin_kind, origin_id = "cron", raw["origin_job_id"]
    else:
        origin_kind, origin_id = "unknown", ""
    expires = raw.get("expires_at")
    return CardDTO(
        approval_id=approval_id,
        purpose=_text(raw, "purpose"),
        scope=_text(raw, "scope"),
        requested_at=_text(raw, "requested_at"),
        expires_at=expires if isinstance(expires, str) and expires else None,
        origin_kind=origin_kind,
        origin_id=origin_id,
    )


def _records_of(result):
    """The pending record list out of a fulfilled list
    result, or None when the shape is not the contract's:
    a dict carrying the records under `pending` (the form
    the bridge bodies fulfill, contract 05's card-watch
    source section), a bare list, or a dict carrying them
    under `cards`."""
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("pending", "cards"):
            if isinstance(result.get(key), list):
                return result[key]
    return None


class BridgeCardSource:
    """The production source: bridged reads over an
    injected connector-client-shaped transport.

    `transport.call(tool, args)` mirrors the connector
    client: a result dict, an `{"undrained": True, ...}`
    marker, or an exception carrying `.name`. `clock` is a
    zero-arg callable returning the pass's ISO timestamp,
    injected so tests never read a wall clock."""

    def __init__(self, transport, clock):
        self._transport = transport
        self._clock = clock

    def _call(self, tool, args):
        """-> (result, None) | (None, SourceStale)."""
        try:
            result = self._transport.call(tool, args)
        except Exception as exc:  # enumerable transport failure
            return None, SourceStale(
                STALE_TRANSPORT, str(getattr(exc, "name", type(exc).__name__)))
        if isinstance(result, dict) and result.get("undrained"):
            return None, SourceStale(STALE_UNDRAINED, tool)
        if isinstance(result, dict) and result.get("shadow"):
            # A tokenless client performed nothing; that is
            # an unperformed read, not an empty queue.
            return None, SourceStale(STALE_TRANSPORT, "shadow")
        return result, None

    def pending_snapshot(self):
        """-> Snapshot | SourceStale."""
        result, stale = self._call(LIST_TOOL, {})
        if stale is not None:
            return stale
        records = _records_of(result)
        if records is None:
            return SourceStale(STALE_MALFORMED, "list result shape")
        cards = []
        for raw in records:
            card = normalize_card(raw)
            if card is None:
                return SourceStale(STALE_MALFORMED, "card without approval_id")
            cards.append(card)
        return Snapshot(cards=tuple(cards), taken_at=self._clock())

    def history(self, approval_id):
        """-> Resolved | Unresolved | SourceStale."""
        result, stale = self._call(HISTORY_TOOL, {"approval_id": approval_id})
        if stale is not None:
            return stale
        if not isinstance(result, dict):
            return SourceStale(STALE_MALFORMED, "history result shape")
        outcome = result.get("outcome")
        if result.get("status") == "unresolved" or not outcome:
            return Unresolved(approval_id)
        if not isinstance(outcome, str):
            return SourceStale(STALE_MALFORMED, "history outcome shape")
        return Resolved(
            approval_id=approval_id,
            outcome=outcome.strip().lower(),
            decided_at=_text(result, "decided_at"),
        )
