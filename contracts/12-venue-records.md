# 12 — Venue records and placement

**Canonical owner:** the pipeline venue layer — it writes
and reads the records; the panel and the evaluator consume
its served projections, never the files directly. (Plan
§4.12, added by amendment; the S0 evidence
schemas for these records are adopted here and stop being
evidence owned by no clause.)

**The contract in one line:** the venue layer's records say
what a session is, what a run did, where work is placed,
and what it cost — in shapes frozen here, that no consumer
re-derives.

## Lease records (RUN1)

Schema: `schemas/lease-record.schema.json`; fixture:
`fixtures/lease-record.json` (the pinned tests' specimen
record). One record per session, at
`var/lease-<session>.json`, written by the lease core
(`sync/lease/records.py`) with the staged-sibling atomic
write: a sibling temp file, then rename over — a crash
mid-write cannot tear the record. Readers read records
exactly as written. Core fields are stamped at acquire
(session, shape, `shape_spec`, rate snapshot, acquired /
deadline / last-used, live jobs, budget at acquire);
lifecycle stamps further fields on the paths that earn them
(extension, renewal, spend). Spend and orphan derivation
and the panel all parse this one shape.

- **Session-evidence projection:** on every lease-record
  save, `write_session_evidence` refreshes
  `var/session-evidence-<session>.json` — a verbatim
  projection of deadline, acquired_at, shape, spec, caller
  (schema: `schemas/session-evidence.schema.json`; fixture:
  `fixtures/session-evidence.json`) — so orphan derivation
  keeps an evidenced deadline if the record itself is lost.
- **Venue key (S5):** records gain a `venue` key from the
  first extracted write (plan §7 V1); session identity
  becomes venue-qualified. Legacy records carry no key and
  are **stamped** `venue: colab` in S5's one-time migration
  (§10.3) — no read-time default exists in any reader.

## Run records (RUN2)

Schema: `schemas/run-record.schema.json`; fixture:
`fixtures/run-record.json` (the pinned specimen). One
record per run at `results/runs/<run_id>.json`, born
`{run_id, job, shape, state: starting, started_at,
resumed}` at launch; fields accrue over the run's life.

- **Terminal states are exactly three:** `complete`,
  `failed`, `orphaned`.
- **Exactly one `run-terminal` event:** a terminal
  transition appends exactly one `run-terminal` event to
  `var/ui-outbox.jsonl`, guarded by the record's
  `terminal_event_state` stamp — a re-poll or a second
  terminal path appends nothing.
- The venue key lands on run records with the lease
  records' (above).

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
(`sync/lease/spend.py` at the pin).

## Snapshot-bundle lineage (RUN5)

Schema: `schemas/bundle-manifest.schema.json`; fixture:
`fixtures/bundle-manifest.json` (field form verbatim from
`sync/make_snapshot_bundle.sh` at the pin; values are a
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

## Migration notes

S5 executes plan §7 against this contract: the venue core
is extracted alongside the untouched colab-runner repo
(D4), records gain venue keys from the first extracted
write, and the legacy stock is stamped once (§10.3). The
liveness entries the lease core renders ride contract 02;
the caller registry that placement consults rides
contract 01; lease and repos config ride contract 04.

## Preserve clauses carried

RUN1, RUN2, RUN4, RUN5 — whole.

## Findings from the frontend build

Two defects recorded by the runner frontend lane, both
dispositioned as S5 inputs:

1. The session-evidence schema is closed with no `venue`
   field, while §7/D2 require every record venue-keyed. The
   frontend's seed evidence omits the key (schema-faithful)
   and its projection names the venue. S5 amends the schema
   when it stamps the legacy records. **Disposition (S5):
   amended.** The schema gains a required
   `venue` property; the fixture carries `venue: colab`;
   `write_session_evidence` projects the record's venue, and
   the §10.3 migration stamps the legacy evidence files with
   the records they project.
2. This contract's lease-record fixture fails its own
   schema: the schema requires `budget_at_acquire`; the
   pinned specimen does not carry it. The frontend's
   validation reports it as a known-fail, not counted
   against its own payloads. S5 dispositions it in the
   same amendment pass — the schema corrected to the
   specimen, or the field's requirement scoped to records
   written after the venue migration. **Disposition (S5):
   the requirement is scoped, as the second
   option names.** The code stamps `budget_at_acquire` at
   every acquire and adoption (the acquire field shape), so
   the schema now requires it exactly on records carrying
   `venue` — i.e. records written after the venue migration
   (an `allOf` if/then) — and the pre-migration specimen
   fixture validates as the legacy record it is. The lease
   schema also gains the `venue` property itself, and the
   run-record schema gains `venue` as a required key (its
   fixture carries the stamp).
3. Reconciliation addendum: upstream commit
   `8e9cb9b` ("Standing collector: stale detached runs
   collect on the reap cycle") now collects stale detached
   run records in the live runner — of 2,084 records at the
   reconciliation snapshot, 0 remain in `polling` (3 at
   S1) and 25 carry `collector: "collector-sweep"`, all
   terminal. S5 ports that mechanism (plan §0 baseline
   note); the hygiene remainder is unchanged and still
   S5's: 3 records that do not parse and 1 record in the
   `completed` state outside the three terminal states
   named above.
4. Event entry-shape extension (LogRow build):
   the venue event record serves one message string —
   `{at, kind, tone, message, venue}` — while the kit's
   shared timeline row (LogRow, timeline-component study
   Variant B) renders a split entry: a compact date token,
   a time, a headline, a kind badge, and a meta line, with
   a drawer behind it. The runner frontend's adapter now
   serves that split as a projection (`EventView`) derived
   from the record — the record itself is unchanged. The
   drawer shows only servable fields, as frame B3 of the
   study draws it: the full message verbatim, the facts
   Time / Kind / Venue, and a lease routing row resolved
   from the lease the message names. `contracts/schemas/`
   carries no event schema; the frontend's mock validation
   pins the record shape locally (mirroring its types)
   until one is frozen. When the live adapter lands, the
   served event shape should carry the split natively
   rather than each consumer re-deriving it — disposition:
   S5/S8 input, with this finding as the shape of record.
   **S5 half dispositioned:** the split is now
   the venue layer's one derivation
   (`pipeline/venue/sync/venue_events.py` — date token and
   time from the record's own timestamp, headline the
   message verbatim, meta/entity only what the record
   serves), and the served shape is frozen in
   `schemas/venue-event.schema.json`. The S8 half remains:
   the live adapter serves this shape to the frontend,
   retiring the frontend's projection.
