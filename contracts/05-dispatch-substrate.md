# 05 — Dispatch substrate

**Canonical owner:** the pipeline dispatch — the scheduler's
outbox/bridge/wake substrate is the surviving base; the
workbench message outbox retires into it; attention's
dispatch expresses over it. The implementation homes in
`pipeline/dispatch/`.

**The contract in one line:** one substrate mints, coalesces,
wakes, delivers, and audits every ping and send in the
harness — no second minter, no second queue, no ack without
the work done.

## Stores

- **Outbox** — `state/outbox.json` is the cross-process
  source of truth; every public operation reloads it first
  (the server, the CLI, drills, and the wake minter all
  write through the one class). Writes use the atomic state
  I/O discipline (temp file + rename, flush, fsync).
- **Bridge queue** — one JSON record per bridged call under
  `state/connector-bridge/`.
- **Send ledger** — attention's `sends` list is the
  dispatch ledger (the survivor). Minting is only
  through `record_send`.
- **Audit ledger** — the scheduler ledger records the whole
  lifecycle (event kinds below). Its format: canonical
  sorted-key JSON per event (the stored record reproduces
  the JSONL export line byte-for-byte), SQLite store with
  the schema/indexes, JSONL export with SHA-256
  verification, import only into an empty store (SCH4 —
  the export/store discipline and the dispatch-audit kinds
  are carried here; the full kind vocabulary spans the
  engine/ops/connector producers, see `traceability.md`).
  Fixture: `fixtures/ledger-events.jsonl` (lines produced
  by the Ledger/Outbox themselves). Schema:
  `schemas/ledger-event.schema.json`. Kind vocabulary:
  `run`, `agent_due`, `catchup`, `skipped_overlap`,
  `ping_created`, `ping_coalesced`, `ping_woken`,
  `ping_acked`, `ping_voided`, `ack_noop`, `entry_removed`,
  `registry_error`, `state_error`, `ledger_pruned`, `op`,
  `connector`.

## Pings (SCH5)

Schema: `schemas/outbox-ping.schema.json`; fixture:
`fixtures/outbox-ping.json` (a record created by the
Outbox). Rules:

- Kinds: `agent-due`, `escalation`, `report`. Ids are 12 hex
  chars from a UUID.
- **Coalescing by pending job id + ping kind:** a later due
  updates `due`, increments `coalesced_count`, replaces
  detail if supplied, and ledgers `ping_coalesced`.
- **Wake-window discipline:** a pending ping is wakeable if
  never woken or last woken at least one ack-timeout window
  ago (default 3600 s).
- **Explicit ack, ack-after-work:** reading or listing never
  acknowledges; the keeper acks only after the work is done;
  acking an already-acked or void ping is a ledgered no-op.
- **Void-on-entry-removal:** deleting a registry entry voids
  its pending pings.
- The keeper is external by design (it survives server
  crashes): it polls wakeable pings, wakes the agent
  surface, and acks after work — the wake half of the
  keeper contract; its survival half is contract 04's.

## The bridge queue (SCH8)

Schema: `schemas/bridge-record.schema.json`; fixture:
`fixtures/bridge-record.json` (the test suite's
planted-record form, with its envelope id).

- **Envelope idempotency:** `envelope_id` is 1–128 chars
  from `[A-Za-z0-9._-]`; a second enqueue with the same
  `(caller, envelope_id)` returns the existing record with
  `deduped: true` — a transport retry can never double-send
  a `chat_send`.
- **Target resolution:** the destination chat is **data
  inside a record**; the wake address is a **separate
  routing decision** — for `chat_send` a configured drain
  home wins, otherwise the record's own `args.chat_id`; for
  read tools, the requesting caller's owning thread from
  the owners table (contract 01). No honest target → the
  item stays queued and reports `UNRESOLVED`; targets are
  never guessed.
- **The wake minter** plants at most one pending wake ping
  per queued item (job id `bridge-wake-<request_id>`, kind
  `agent-due`, detail exactly `{request_id, tool, caller,
  target_chat}` — never the item's text). Idempotence needs
  no minter state: a pending ping suppresses a second mint;
  a record that leaves `queued` is never re-minted; a ping
  acked while its record is still queued is re-minted next
  pass, because **fulfillment — not the mint — is the
  lock**. A pass finding ≥1 resolvable queued item and no
  pending `bridge-drain` ping plants one episode-escalation
  ping; an unresolved-only queue never escalates. The drain
  executor acks its ping only when its final poll finds the
  queue empty — that ack closes the episode and re-arms the
  minter.
- **Bodies are refs, never payloads (SCH9's dispatch
  half):** pings and records carry `body_ref` and identity
  only; the instructional content lives behind the ref.

## Sends — attention's clauses

Schema: `schemas/attention-send.schema.json`; fixture:
`fixtures/attention-send.json` (the dispatch tests'
constructor specimen). Id schemes (**ATT5**): sends
`sNNNN`; waits `wNNNN`; owner actions `oaNNNN`; items
`handle:source_ref`. The bridge envelope form is
`attn-<send-id>-a<attempts>`; the bridge meta rides as
record data: `{source: "owner-attention", send_id,
template, target, rule_id, sha256(text)}`.

- **Four producer classes, one minting surface:** the
  wait-rule engine, owner verbs, handler actions, and the
  continuation pass mint through `record_send` — owner
  verbs and continuation mint **above** the substrate, not
  beside it. Shadow sends (`mode: shadow`) are
  never dispatchable (**ATT5**).
- **Settle-first ordering:** the consumer settles
  outstanding bridge records before claiming or enqueueing
  new sends. A merged consumer that enqueues first
  reintroduces the twin-send class — this ordering is contract, not implementation
  detail.
- **Claim and delivered-only-on-reference (ATT6):** a send
  is claimed by one attributed consumer on a 15-minute
  lease, expiry applied **at read time** (no sweeper);
  delivery happens only via ack by the claiming consumer,
  before expiry, **carrying the fulfillment's submission
  reference**. Failure records are never acks.
- **Suppress (ATT7):** terminal, reasoned (a mandatory
  reason on the record), **refused on a delivered send**.
  A suppressed send's late fulfillment is **stamped as
  fact, never resurrected** (the suppressed-but-
  fulfilled edge). Attempts exhausted → parked + suppressed
  with the reason on the record.
- **Failure records:** deduplicated to one per hour
  per send + reason; an undelivered failure against an
  understaffed topic surfaces as a `steer_undeliverable`
  staffing row (contract 03).

## Decision machinery

- **Verdict at the tap (ATT2):** the verb is validated
  against the *served* verb set for the item; the decision
  is recorded on the item (`{verb, at, option_id, note,
  send_id}`) and, through `wait_id`, on the wait — delivery
  never gates the decision.
- The decided card leaves the open queue into the
  **"Decided — awaiting fulfillment"** band (states queued
  / sent / recorded). **Fulfillment is derived, never
  assumed:** from the send ledger for send-backed decisions;
  from the scripted push-fact measurement (contract 03's
  fact feed) for `push_needed`. Unfulfilled past **120
  minutes** reads stalled; failed and stalled items
  **return to the decision queue** with `decision_history`
  on the item's face.
- **Replay guards:** an `idempotency_key` short-circuits; a
  repeated tap on a standing decision records and sends
  nothing; a **fulfilled decision is never changed** — it
  is a new item.
- **Reply routing (ATT3, Decision 1):** direct to the
  owning thread, main copied (`owner:reply-copy`) — unless
  the handle is `main`, which gets the single send.

## Waits (ATT8)

Schema: `schemas/attention-wait.schema.json`; fixture:
`fixtures/attention-wait.json` (the demo seed's wait, same
shape as live rows). The wait-rule engine dedupes on a
**fact hash** of the wait's content; a surfaced wait
becomes **exactly one** owner item; hard-stop classes are
always surfaced, never auto-applied. A **terminal status
post** resolves its waits (contract 03); an ack alone
never does.

## What this contract does NOT carry

The retired sweeper's connector tools (`sweeper_state_read`,
`sweeper_state_write`, `nudge_append`) and their inlined
schema are retired; they are not part of this
substrate. The retired records stay on disk, unread by the
pipeline.

## Preserve clauses carried

SCH5, SCH8, SCH4 (ledger format — see the audit-ledger
note above), SCH9's body-ref + ack-after-work half, ATT2,
ATT3, ATT5, ATT6, ATT7, ATT8.

## Owner items and templates

- **Owner-item schema:** `schemas/owner-item.schema.json`
  is part of the schema set, written from the frontend's
  `OwnerItem` shape (this contract's decision semantics in
  field form). The frontend's `validate:mocks` runs
  items.json through the schema (its structural
  cross-checks — id scheme, wait/handler/send resolution,
  verb vocabulary — remain). Specimen fixture:
  `fixtures/owner-item.json`.
- **Templates fixture:** `fixtures/attention-templates.json`
  carries 19 rows, including the `decision-reply` row
  (audience `chat`, slots `[summary]`, text
  `{summary}` — the producer composes the full reply
  line, per the decision machinery above).
- **The consumer surface:** pings (outbox), the bridge
  queue, the wake minter, the send ledger lifecycle, and
  the message store's watcher outbox are one substrate
  under `pipeline/dispatch/`. Settle-first
  ordering and the suppressed-but-fulfilled edge are
  substrate semantics (`dispatch.sends`), not consumer
  folklore.

## Card-watch source

The permission-card watcher's source contract
(implementation: `pipeline/registry/cards/`). Two
bridged reads, both `read` scope, both fulfilled by the
home-side bridge executor; neither carries any authority
— listing and lookup only, never approve or deny.

- **Card DTO:** `approval_id`, `purpose`,
  `scope`, `requested_at`, `expires_at` (nullable), and
  origin as `origin_kind` (`chat` | `cron` | `unknown`)
  with `origin_id`. This is the whole whitelist: raw tool
  arguments and command payloads from a runtime record
  are dropped at normalization and never enter a wait, a
  summary, or the digest.
- **Pending snapshot:** a `permissions_list` call (no
  args); the fulfilled result carries the records under
  `pending`, exactly as the runtime listing gives them
  (the bridge bodies' form). A record without an
  `approval_id` makes the snapshot malformed, never
  partial.
- **Resolution lookup:** a `permissions_history` call
  with args `{approval_id}`; the fulfilled result is the
  resolved record `{approval_id, outcome, decided_at}`
  when the runtime's resolved-record lookup holds an
  outcome, or the explicit unresolved answer
  `{approval_id, status: "unresolved"}` when it does
  not. Envelope idempotency covers both reads: a retry
  returns the existing record instead of queueing a
  twin.
- **Outcome vocabulary:** `approved` opens resumption
  verification; `denied` and `expired` are terminal; any
  other stamped outcome is terminal-other. An outcome
  exists only as a history record's stamp — a card's
  disappearance from the pending list is never an
  outcome, and no attention-side decision, send
  delivery, or acknowledgement stamps one.
- **Source-stale semantics:** a read that fails, fails
  fulfillment, goes undrained past its poll bound,
  returns a shadow (unperformed) result, or answers in a
  shape outside this contract is source-stale: the pass
  is an enumerable non-run, watcher state is untouched,
  and the snapshot never reads as zero cards. A drained,
  fulfilled empty list is a real answer — zero cards
  observed.
- **Watcher state shape:** provenance rides a
  `card` subrecord on the posted wait (schema:
  `schemas/attention-wait.schema.json`) — the DTO fields
  with `origin_kind` as mapped (`chat` for a registered
  handler's card, `orphan` otherwise), plus `outcome`
  and `decided_at` stamped at resolution — and a
  `card_watch` ledger in attention state keyed by
  `approval_id`: handle and origin mapping, linked wait
  and item ids, first-seen / last-seen-pending stamps,
  expiry, state (`pending` | `resolution_unconfirmed` |
  `verifying` | `closed`), the history-stamped outcome
  and decision time, close kind (`denied` | `expired` |
  `other` | `verified_resumed`), nudge and escalation
  stamps, and the redrive linkage.
