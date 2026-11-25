# pipeline/dispatch

The one dispatch substrate (contract 05): the
scheduler's outbox, bridge queue, and wake minter as
the surviving base; the workbench message store and
its watcher outbox retired into it; the send-ledger
lifecycle expressed over it. One substrate mints,
coalesces, wakes, delivers, and audits every ping and
send in the harness — no second minter, no second
queue, no ack without the work done.

## Modules

- `ledger.py` — the audit ledger: SQLite store
  (state file `scheduler.db` under the caller's state
  dir), canonical sorted-key JSON records, JSONL export
  with SHA-256 verification, import only into an empty
  store.
- `outbox.py` — durable pings (`state/outbox.json`):
  coalescing by pending job id + kind, wake windows,
  explicit ack-after-work, void-on-entry-removal.
- `stateio.py` — the atomic state I/O discipline the
  stores share (temp file + rename, flush, fsync;
  malformed state is a StateError, never a silent
  default). The scheduling engine's own state reads
  use it from here.
- `bridge.py` — the connector bridge queue: one JSON
  record per bridged call, envelope idempotency
  ((caller, envelope_id) find-or-enqueue), poll and
  fulfill. Records are written through the platform
  writer's staged-write protocol (contract 15). The
  scheduler's connector module keeps the tool surface
  (auth, scopes, direct tools) over this queue.
- `wake.py` — the wake minter: one wake ping per queued
  bridge item (detail carries identity only, never
  text), target resolution from the routing data it is
  handed, and the bridge-drain episode escalation. The
  scheduler's bridge-wake ops script remains the entry:
  it parses the owners config (the registry YAML subset
  is the scheduling package's) and hands the minter the
  resolved owners table and drain home.
- `sends.py` — the send ledger lifecycle (contract
  05's attention clauses): minting only through
  `record_send` (four producer classes), shadow sends
  never dispatchable, claim on a bounded lease with
  read-time expiry, delivery only via the claiming
  consumer's ack carrying a submission reference,
  reasoned terminal suppress, the
  suppressed-but-fulfilled edge stamped as fact,
  failure records deduped to one per hour per
  send + reason, attempts exhaustion parked +
  suppressed. It operates on the ledger as a list of
  send dicts; the attention service's dispatch
  (`pipeline/attention/services/dispatch/`) applies
  the same lifecycle over the attention state store.
- `messages/` + `notify.py` — the workbench message
  store (SQLite, its own schema lineage) and its
  watcher outbox: every transition into `sent` writes
  an outbox row in the same transaction; consumers
  poll `list_outbox` with their own checkpoints;
  notify targets (webhook / command) are the wake-up
  half — a wake, not the record. The doctor posts its
  digest through `dispatch.messages` from here.

## Consumers

- The scheduling server and `bin/sched`: engine, API,
  connector tool surface, and the ops entries import
  the substrate as the top-level `dispatch` package
  (the server package's `__init__` puts the pipeline
  root on sys.path — the mega repo's path seam).
- The evaluation doctor: posts its digest through
  `dispatch.messages` (the messages DB path stays a
  workbench-service state seam, `WB_MESSAGES_DB_PATH`).

## Gate

`python3 check.py dispatch` from the repo root — the
800-line cap over this package plus the substrate test
suite (`tests/`: the message-store suites, the send
lifecycle, the bridge round-trip, and the outbox
parity sequence), composed from this package's
`gate.json` declaration. The scheduling suite
exercises the same modules through the server surface.

- **Governed by:** contract 05 (pings, bridge queue,
  sends, decision machinery, waits), contract 01
  (routing tables and token callers), contract 03
  (the status posts and continuation triggers that
  feed it), contract 15 (the staged-write protocol
  the bridge queue writes through).
- The retired sweeper's connector tools do **not**
  live here — they retired with the sweeper.
