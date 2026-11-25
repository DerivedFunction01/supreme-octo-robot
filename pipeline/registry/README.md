# pipeline/registry — the caller + routing registry

One store for every actor the harness can name: thread
callers, machinery callers, token callers, attention
handles, programmes — and the caller→chat routing tables
they resolve against. All four apps consume it; none
keeps a local copy.

- The merged registry store
  (`store.py`) holds the three caller natures distinct —
  thread callers (operator-written rows), machinery
  callers (code constants, never listed), token callers
  (hash-only) — plus the routing tables (bridge-wake
  owners, notify routes, restart-reconcile owners) and
  the handler/programme directory. Claim semantics
  (`callers/callers.py`), token authentication
  (`callers/tokens.py`), routing resolution
  (`callers/routing.py`), directory upserts
  (`attention/directory.py`), the seed/export step
  (`seed.py`), and this package's config under the
  unified contract (`config.py`). The card-watch
  registry (`cards/`: the card source and the watcher)
  names the permission-card surface the mega card-watch
  owner holds. The attention state store is not here —
  it lives in the attention package
  (`attention/infra/attstore.py`).
- **The live store** is `var/registry.json` (untracked,
  `.gitignore`d), standing seeded in the deployment. A
  fresh deployment seeds from the tracked fictional
  examples (`python3 -m registry.seed
  seed-examples --fixtures ../../contracts/fixtures
  --to var/registry.json`, run from `pipeline/`). The
  `seed-capture` route rebuilds a store from a
  consolidation capture directory
  (`--holding DIR`); the capture itself is not carried
  in this tree.
- **State of the consumers:** the in-tree consumers
  read through their own seams (the scheduling
  connector reads its live config's
  connector block; the venue claim seams read the runner
  registry form) — the merged store is census-proven to
  agree with every
  one of them (tests/test_census.py).
- **Governed by:** contracts 01 (this registry), 04
  (config pattern), 07 (catalog axes — consumed from the
  scheduling registry's one definition), 15 (the writer
  every save rides).
- **Tests:** `python3 -m unittest discover -s tests -t ..`
  from this directory. (The attstore suite — including its
  pinned-loader leg under `ATTENTION_PIN_ROOT` — lives
  with the store in the attention package's tests.)
