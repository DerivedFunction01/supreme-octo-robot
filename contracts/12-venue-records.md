# 12 — Venue records and placement

**Canonical owner:** the pipeline venue layer — it writes
and reads the records; the panel and the evaluator consume
its served projections, never the files directly. (Plan
§4.12.)

**The contract in one line:** the venue layer's records say
what a session is, what a run did, where work is placed,
and what it cost — in shapes frozen here, that no consumer
re-derives.

## Lease records (RUN1)

Schema: `schemas/lease-record.schema.json`; fixture:
`fixtures/lease-record.json` (a pre-venue-migration
specimen record). One record per session, at
`var/lease-<session>.json`, written by the lease core
(`pipeline/venue/sync/lease/core/records.py`) with the
staged-sibling atomic write: a sibling temp file, then
rename over — a crash mid-write cannot tear the record.
Readers read records exactly as written. Core fields are
stamped at acquire (session, shape, `shape_spec`, rate
snapshot, acquired / deadline / last-used, live jobs,
budget at acquire); lifecycle stamps further fields on the
paths that earn them (extension, renewal, spend). Spend
and orphan derivation and the panel all parse this one
shape.

- **Session-evidence projection:** on every lease-record
  save, `write_session_evidence` refreshes
  `var/session-evidence-<session>.json` — a verbatim
  projection of deadline, acquired_at, shape, spec, caller,
  and venue (schema:
  `schemas/session-evidence.schema.json`; fixture:
  `fixtures/session-evidence.json`) — so orphan derivation
  keeps an evidenced deadline if the record itself is lost.
- **Venue key:** every record carries a `venue` key,
  stamped at write time; session identity is
  venue-qualified. Legacy records are stamped `venue:
  colab` by a one-time migration (§10.3) — no read-time
  default exists in any reader. The lease schema requires
  `budget_at_acquire` exactly on records carrying `venue`
  — i.e. records written after the venue migration (an
  `allOf` if/then) — and the pre-migration specimen fixture
  validates as the legacy record it is.

## Run records (RUN2)

Schema: `schemas/run-record.schema.json`; fixture:
`fixtures/run-record.json`. One record per run at
`results/runs/<run_id>.json`, born `{run_id, job, shape,
state: starting, started_at, resumed}` at launch; fields
accrue over the run's life. Run records carry the `venue`
key with the lease records' (above).

- **Terminal states are exactly three:** `complete`,
  `failed`, `orphaned`.
- **Exactly one `run-terminal` event:** a terminal
  transition appends exactly one `run-terminal` event to
  `var/ui-outbox.jsonl`, guarded by the record's
  `terminal_event_state` stamp — a re-poll or a second
  terminal path appends nothing.
- Stale detached run records collect on the reap cycle;
  collected records carry a `collector` stamp and stand
  terminal.

## Placement (RUN4)

- **No pin in the run/gate funnel.** Nothing in the launch
  or gate path may name a session.
- **Latest-deadline adoption:** `acquire`'s adoption pool
  sorts live records at the requested shape — the caller's
  own leases first, unattributed next, non-degraded before
  degraded, latest deadline as the last sort key — and
  adopts from the head of that order.
- **Pins are adoption-only:** a `--prefer-session` pin
  names a lease to adopt; it cannot combine with create,
  and it refuses on shape mismatch or a dead /
  past-deadline record. (Synchronous attaches are a
  separate claim system; caller attribution semantics
  whole are contract 01.)

## Spend attribution (RUN4)

Spend is counted **from the repo's own lease segments,
never from account-balance deltas**. A completed segment
is journaled to `var/lease-spend-journal.jsonl` at the
record's rate snapshot — one line per segment:
`{session, shape, start, end, rate}` plus `caller` when
the record carries one — appended at every seam that ends
a session's assignment under a record; a failed journal
write never breaks the lifecycle action it records. Live
records contribute their running segment. The attributed
total is the fold of the journal plus live segments
(`pipeline/venue/sync/lease/core/spend.py`).

## Snapshot-bundle lineage (RUN5)

Schema: `schemas/bundle-manifest.schema.json`; fixture:
`fixtures/bundle-manifest.json` (field form verbatim from
`pipeline/venue/sync/make_snapshot_bundle.sh`; values are a
specimen — no live bundle was copied).

- **Origin lineage only:** the snapshot commit's parent is
  the **current origin tip** and its tree is the tree being
  shipped — never a bundle on the local lineage, which
  cannot fast-forward a fresh origin clone.
- **Recorded and verified:** the manifest beside the
  bundle records its path, byte size, and SHA-256, the
  snapshot commit, the parent origin tip, and the tree;
  size + SHA-256 are recorded before transfer and verified
  after (the chunked transfer verifies per-part and
  whole-file hashes as well).
- **Applied ff-only:** the recorded apply route is fetch
  the snapshot commit, then `git merge --ff-only` — a
  non-fast-forward apply refuses.

## Venue events

The venue event record serves one message string —
`{at, kind, tone, message, venue}`. The split entry shape
the kit's shared timeline row renders (a compact date
token, a time, a headline, a kind badge, and a meta line,
with a drawer behind it) is the venue layer's one
derivation (`pipeline/venue/sync/venue_events.py` — date
token and time from the record's own timestamp, headline
the message verbatim, meta/entity only what the record
serves), and the served shape is frozen in
`schemas/venue-event.schema.json`. The record itself is
unchanged by the derivation; consumers do not re-derive
the split.

## Related contracts

The liveness entries the lease core renders ride contract
02; the caller registry that placement consults rides
contract 01; lease and repos config ride contract 04.

## Preserve clauses carried

RUN1, RUN2, RUN4, RUN5 — whole.
