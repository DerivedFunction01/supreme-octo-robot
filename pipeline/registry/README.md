# pipeline/registry — the caller + routing registry

One store for every actor the harness can name: thread
callers, machinery callers, token callers, attention
handles, programmes — and the caller→chat routing tables
they resolve against. All four apps consume it; none
keeps a local copy.

- **Landed (S7):** the merged registry store
  (`store.py`) with the three caller natures distinct —
  thread callers (operator-written rows), machinery
  callers (code constants, never listed), token callers
  (hash-only) — plus the routing tables (bridge-wake
  owners, notify routes, restart-reconcile owners) and
  the handler/programme directory in its new seed/export
  form. Claim semantics (`callers/callers.py`, RUN3
  whole), token authentication (`callers/tokens.py`,
  SCH7 whole), routing resolution (`callers/routing.py`),
  directory upserts (`attention/directory.py`), the
  seed/export step (`seed.py`), and this package's config
  under the unified contract (`config.py`). The migrated
  attention state store formerly homed here re-homed to
  the attention package (`attention/infra/attstore.py`,
  commission 12).
- **The live store** is `var/registry.json` (untracked,
  `.gitignore`d): seeded from the S1 overlay capture for
  this consolidation (`python3 -m registry.seed
  seed-capture --holding ../../docs/overlay/holding
  --to var/registry.json`, run from `pipeline/`); a fresh
  deployment seeds from the tracked fictional examples
  (`seed-examples --fixtures ../../contracts/fixtures`).
- **State of the consumers:** the in-tree consumers keep
  their pinned read paths until their own steps re-point
  them (the scheduling connector reads its live config's
  connector block; the venue claim seams read the runner
  registry form) — the merged store is seeded from the
  same captures and census-proven to agree with every
  one of them (tests/test_census.py). Consumer re-pointing
  rides S8 (apps as consumers) and S11 (cutover).
- **Governed by:** contracts 01 (this registry), 04
  (config pattern), 07 (catalog axes — consumed from the
  scheduling registry's one definition), 15 (the writer
  every save rides).
- **Tests:** `python3 -m unittest discover -s tests -t ..`
  from this directory. (The attstore suite — including its
  pinned-loader leg under `ATTENTION_PIN_ROOT` — moved
  with the store to the attention package's tests.)
