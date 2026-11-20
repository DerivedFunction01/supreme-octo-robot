"""Pipeline dispatch: the one substrate (plan §4.5,
contract 05).

One substrate mints, coalesces, wakes, delivers, and
audits every ping and send in the harness — no second
minter, no second queue, no ack without the work done.
Its parts:

- `ledger` — the audit ledger (SQLite store, canonical
  JSONL export), carried from the pinned scheduler; the
  send ledger's records live in it by reference at the
  consumer (see `sends`).
- `outbox` — durable pings: coalescing, wake windows,
  explicit ack-after-work, void-on-entry-removal.
- `stateio` — the atomic state I/O discipline the stores
  share (temp file + rename, fsync; a malformed file is a
  StateError, never a silent default).
- `bridge` — the connector bridge queue: one JSON record
  per bridged call, envelope idempotency at the boundary.
- `wake` — the wake minter: one wake ping per queued
  bridge item, plus the bridge-drain episode escalation.
- `sends` — the send ledger lifecycle (contract 05's
  attention clauses): minting only through `record_send`,
  claim on a bounded lease, delivery only by the claiming
  consumer's ack carrying a submission reference,
  reasoned terminal suppress, deduped failure records.
- `messages` + `notify` — the workbench message store
  and its watcher outbox, retired into this substrate at
  S6: the message lifecycle's transitions into `sent`
  write their outbox rows here, and notify targets are
  the substrate's wake-up half (a wake, not the record).

Landed at the consolidation's step S6 from the scheduler
pin (outbox/bridge/wake/ledger — the surviving base) and
the workbench pin (messages/notify), with the send
lifecycle ported from the attention pin's dispatch
service. Stdlib only; paths derive from callers, never
from this package's location, except the platform-writer
load in `bridge` (the mega repo's path seam).
"""
