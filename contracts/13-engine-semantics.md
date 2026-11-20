# 13 — Engine semantics

**Canonical owner:** the pipeline scheduling engine — the
engine is this contract's only implementer; every consumer
of fired work reads its effects through the ledger
(contract 05) and the entry format (contract 14). (Plan
§4.13, added by the 2026-11-13 amendment.)

**The contract in one line:** the engine fires each due
point exactly once, in order, or fails safe and says so in
the ledger — it never duplicates a run and never fires on
doubt.

The semantics below are the pinned engine's
(`server/engine.py` at the pin; its EC-1–EC-11 set). The
engine rescans the registry every tick and fires what is
due under them:

- **Consume-before-run (EC-4):** a fired grid point is
  consumed — `next_due` advanced and persisted — **before**
  the run starts, so a crash or a backward clock jump can
  delay a run but never duplicate one.
- **Missed-point collapse (EC-1):** missed points collapse
  to the latest; the collapse count is ledgered (`catchup`
  event carrying the count). Advance returns the latest
  missed point, the collapsed count, and the new next due
  as one computation (`server/schedule.py`).
- **No self-overlap:** an entry still running at its point
  skips the point; the skip is ledgered
  (`skipped_overlap`).
- **Same-tick order and isolation:** entries due on the
  same tick are dispatched in entry-id order, each
  execution in its own thread, so one long job cannot
  block the cadence of the others.
- **Last-good registry (EC-9):** a registry that fails to
  parse keeps the last-good registry running and escalates
  **once per distinct error** — a broken edit degrades to
  the last working fleet, never to silence or to a storm.
- **Fail-safe halt (EC-10):** corrupt durable state means
  **no firing at all**. Doubt stops the engine; it does
  not improvise a partial fleet.
- **Firing is status + presence (amendment 3,
  2026-11-13):** the engine fires an entry iff its status
  is `active` and it stands in the pipeline registry
  store. The store has exactly one mutation path —
  contract 02's writer path (validate under contract
  14's format, server-context proof for hand-authored
  entries) — so presence in the store through that path
  IS admission; there is no directory-drop path for a
  flag to guard. The pinned engine's migrated-only clause
  (fire only `migrated: true` entries) is deliberately
  NOT carried: the migration field family does not exist
  in the target format (contract 14). Admission evidence
  — validation counts, proof outcome — is recorded as
  events in the dispatch/ledger store (contract 05), not
  as fields on the entry. This bullet is the firing
  clause's deliberate, named replacement, recorded as a
  ruling, not a migration detail.
- **Schema → restart → entries ordering:** a registry
  schema change lands as code and is committed → the
  server restarts onto the new schema → only then may
  entries use the new fields. The format half of this
  ordering is contract 14's; the engine never meets an
  entry field it predates.
- **Single instance:** one engine runs against one
  registry and one state store (the single-instance lock
  at startup); the cutover discipline that depends on it
  is plan §5's serial exception 3 — no step runs a second
  engine against live state.

## Migration notes

S3 moves the engine behind this contract into
`pipeline/scheduling/`. A change to any clause above is a
ruling, not a migration detail: the §2 preserve item
permits deliberate, named replacements, and amendment 3
(2026-11-13) is the firing clause's — recorded in the
bullet above and in `contracts/traceability.md`. The
ordering clause's replacement allowance stands as
written, and the rest carry as written.

## Preserve clauses carried

SCH3 — whole.
