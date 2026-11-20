# pipeline/scheduling

The scheduling engine: registry parser/validator and entry
schema, the classified catalog with adoption and drift,
schedule math, the engine, and the scripted executor.

- **Landed:** step S3 (2026-11-13) — the scheduler pin
  `cf910ce` tree moved here whole (server package, `bin/sched`,
  tests, `ops/`, `tools/`, examples, the registry) plus the
  S1 overlay capture (24 entries, 14 bodies, 5 member
  scripts, the file-registry manifest under `registry/`).
  The moved registry censuses 26 entries, matching the live
  census; the pinned suite passes against the moved tree.
- **Target semantics, per the S0 contracts:** the registry
  entry format is contract 14's — the migration field family
  does not exist here (amendment 3), and presence through
  the one writer path is admission; the engine fires on
  contract 13's semantics (the migrated-only clause is not
  carried); the `/api/v1` views serve contract 09's shapes
  (no migration fields). The ledger and outbox modules ride
  this package as the dispatch substrate's surviving base —
  their consolidation is step S6.
- **Governed by:** contracts 02, 07, 13, 14 (registry,
  catalog, engine, format), contract 04 (its live config),
  contract 09 (served views).
- **Single-writer at cutover:** one engine against one
  registry/state at a time (plan §0, serial exception 3;
  the S11 cutover stops the old engine before this one
  starts). Nothing here is running yet — the original
  scheduler serves until the freeze.
