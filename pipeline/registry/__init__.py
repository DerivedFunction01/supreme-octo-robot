"""Pipeline registry: the one caller + routing registry
(plan §4.1, contract 01).

Every actor the harness can name — thread caller, machinery
caller, token caller, attention handle, programme — resolves
in this one store, in one of three caller natures that are
never blurred. All four apps consume it; none keeps a local
copy. The store, seed and config parts live at the package
root; the caller natures and routing live in `callers/`,
the attention-facing parts in `attention/`, and the
card-watch seam in `cards/`. Its parts:

- `store` — the merged registry store itself: one live JSON
  file (untracked, seeded under contract 04's seed/example
  pattern) holding the thread-caller file form, the
  token-caller map, the routing tables, and the handler /
  programme directory rows. Writes ride the unified writer
  (contract 15).
- `callers` — the thread/machinery claim semantics (RUN3,
  carried whole from the runner's pinned registry code): a
  presented-but-unregistered claim is refused, an absent
  claim is unattributed, callers marked `active` are
  detached-only, attaches journal to the claims journal.
- `tokens` — the token-caller nature (SCH7): hashes only,
  read fresh from the store on every authentication, scopes
  from the closed set; a missing or malformed registry
  means no callers and every call refused.
- `routing` — the caller→chat tables the wake minter and
  the liveness escalation resolve against (SCH8's table
  half): bridge-wake owners, notify routes, and the
  restart-reconcile owners table with its own grammar.
- `directory` — attention's handler + programme registries
  (§9.1): the shell's programme/lane directory and the
  supervision directory proper, in the seed/export form
  contract 01 gives them at this step.
- `seed` — the seed/export step: the live store is seeded
  from the S1 overlay capture only, never from the tracked
  examples; export writes the per-form files back out.
- `config` — this package's own settings under the unified
  config contract (§4.4): env > live > defaults, with
  per-key source reporting.
- `attstore` — retired here: the migrated attention state
  store (contract 01's annex) re-homed to the attention
  package (`attention/infra/attstore.py`, commission 12);
  its seed data and its suite moved with it.

Landed at the consolidation's step S7 from the runner pin
(caller semantics), the scheduler pin (connector registry,
routing tables), and the attention pin (handler/programme
registries, the state store). Stdlib only; paths derive
from callers, never from this package's location, except
the platform-writer load (the mega repo's path seam).
"""
