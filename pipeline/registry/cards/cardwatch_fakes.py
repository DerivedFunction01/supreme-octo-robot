"""The card-watch test seam (card-owner plan, Step 1):
the fake card source, the fake bridge transport, the fake
clock, and the specimen records every card-watch test
shares. Shipped as a package module, not buried in one
test file, so the spine's core tests, the cadence lane,
and the surfacing lane all fake the source the same way.

Everything here is deterministic: no wall clock, no
network, no live server. The specimens are fictional; the
pending specimens deliberately carry raw tool payloads
(a `command` and a `tool_params`) of the kind the runtime
record holds, so the whitelist pins have something real
to drop.

Specimen stamps are fixed ISO strings. `SEED_NOW` sits
after both pending specimens were requested and before
either expires.
"""

from . import cardsource

SEED_NOW = "2026-11-14T15:00:00Z"

# Raw pending records, in the shape the bridged list read
# fulfills: whitelist fields plus the raw payload fields
# normalization must drop.
RAW_CARD_CHAT = {
    "approval_id": "appr-fixture-001",
    "purpose": "Run a shell command on the home machine",
    "scope": "exec: git push origin main",
    "requested_at": "2026-11-14T14:41:00Z",
    "expires_at": "2026-11-14T16:41:00Z",
    "origin_chat_id": "chat-fixture-alpha",
    "command": "git -C fixture/repo push origin main",
    "tool_params": {"command": "git push origin main", "timeout": 60},
}

RAW_CARD_CRON = {
    "approval_id": "appr-fixture-002",
    "purpose": "Send an email from the agent mailbox",
    "scope": "send: mail.handoff",
    "requested_at": "2026-11-14T14:52:00Z",
    "expires_at": "2026-11-14T15:52:00Z",
    "origin_job_id": "job-fixture-nightly",
    "command": "send digest to the list",
    "tool_params": {"recipients": ["fixture@example.invalid"]},
}

RAW_PENDING = [RAW_CARD_CHAT, RAW_CARD_CRON]

# Raw history records, one per outcome path. The bridge
# fulfills `permissions_history` from the runtime's
# resolved-record lookup: a record with an outcome stamp,
# or the explicit unresolved answer.
RAW_HISTORY_APPROVED = {
    "approval_id": "appr-fixture-001",
    "outcome": "approved",
    "decided_at": "2026-11-14T15:03:00Z",
}
RAW_HISTORY_DENIED = {
    "approval_id": "appr-fixture-002",
    "outcome": "denied",
    "decided_at": "2026-11-14T15:04:00Z",
}
RAW_HISTORY_EXPIRED = {
    "approval_id": "appr-fixture-003",
    "outcome": "expired",
    "decided_at": "2026-11-14T15:05:00Z",
}
RAW_HISTORY_UNRESOLVED = {
    "approval_id": "appr-fixture-001",
    "status": "unresolved",
}


class FakeClock:
    """A settable clock: callable returning the current
    ISO stamp; tests move it explicitly, never by waiting."""

    def __init__(self, now=SEED_NOW):
        self.now = now

    def __call__(self):
        return self.now

    def set(self, now):
        self.now = now


class FakeTransportError(Exception):
    """The fake transport's enumerable failure, carrying a
    `.name` exactly as the connector client's error does."""

    def __init__(self, name, detail=""):
        super().__init__(detail or name)
        self.name = name
        self.detail = detail or name


class FakeBridgeTransport:
    """A scripted stand-in for the connector client.

    Outcomes are queued per tool: a result dict is
    returned, the UNDRAINED marker is returned, or an
    exception instance is raised. Every call is recorded
    in `calls` as (tool, args). An unscripted call raises
    a transport error named `unscripted` — a test that
    reaches the bridge without scripting it fails loudly,
    never silently."""

    UNDRAINED = object()

    def __init__(self):
        self._queues = {}
        self.calls = []

    def script(self, tool, *outcomes):
        self._queues.setdefault(tool, []).extend(outcomes)
        return self

    def call(self, tool, args, envelope_id=None):
        self.calls.append((tool, args))
        queue = self._queues.get(tool) or []
        if not queue:
            raise FakeTransportError("unscripted", tool)
        outcome = queue.pop(0)
        if outcome is self.UNDRAINED:
            return {"undrained": True, "tool": tool,
                    "request_id": "req-fixture"}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeCardSource:
    """The fake card source: the same interface as
    BridgeCardSource, fed from in-memory specimens.

    `pending` holds raw records (normalized through the
    real whitelist, so a specimen edit exercises the same
    path as production); `history_records` maps approval
    ids to raw history records (absent id = the explicit
    unresolved answer). Setting `stale` to a SourceStale
    makes every read return it — the source-stale seam
    sibling lanes test against."""

    def __init__(self, clock, pending=(), history_records=None, stale=None):
        self._clock = clock
        self._pending = list(pending)
        self._history = dict(history_records or {})
        self.stale = stale

    def pending_snapshot(self):
        if self.stale is not None:
            return self.stale
        cards = tuple(cardsource.normalize_card(raw) for raw in self._pending)
        return cardsource.Snapshot(cards=cards, taken_at=self._clock())

    def history(self, approval_id):
        if self.stale is not None:
            return self.stale
        raw = self._history.get(approval_id)
        if raw is None or raw.get("status") == "unresolved" \
                or not raw.get("outcome"):
            return cardsource.Unresolved(approval_id)
        return cardsource.Resolved(
            approval_id=approval_id,
            outcome=str(raw["outcome"]).strip().lower(),
            decided_at=raw.get("decided_at") or "",
        )
