# pipeline/scheduling

The scheduling engine: registry parser/validator and entry
schema, the classified catalog with adoption and drift,
schedule math, the engine, and the scripted executor.
It serves as the coupled process's scheduler half —
the repo-root `run.py serve` mounts it with the
attention backend under the one `workhorse.service`
unit; `bin/sched` is its operator CLI and
`bin/sched exec` / `write` / `patch` the ops route
other work rides.

- **Contents:** the server package, `bin/sched`, tests, `ops/`,
  `tools/`, examples, and the registry. The tracked
  registry (`jobs/`) carries 25 entries; job bodies are
  the live overlay (`bodies/`, untracked — a clean
  checkout carries none). The pinned suite passes
  against this tree.
- **Semantics, per the contracts:** the registry
  entry format is contract 14's — the migration field family
  does not exist here (amendment 3), and presence through
  the one writer path is admission; the engine fires on
  contract 13's semantics (the migrated-only clause is not
  carried); the `/api/v1` views serve contract 09's shapes
  (no migration fields). The ledger and outbox modules'
  home is the dispatch substrate
  (`pipeline/dispatch/`), which the server imports.
- **Governed by:** contracts 02, 07, 13, 14 (registry,
  catalog, engine, format), contract 04 (its live config),
  contract 09 (served views).
- **Single-writer:** one engine against one
  registry/state at a time.
