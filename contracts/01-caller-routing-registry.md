# 01 — Caller + routing registry

**Canonical owner:** the pipeline registry — one directory for
callers, handles, programmes, and caller→chat routing. All
four apps consume it; none keeps a local copy. The
implementation homes in `pipeline/registry/`.

**The contract in one line:** every actor the harness can name
— thread caller, machinery caller, token caller, attention
handle, programme — resolves in this one registry, in one of
three natures that are never blurred.

## Parties

- **Producers:** operators (thread-caller rows, routing
  tables — operator-written only; no code writes them), the
  code itself (machinery constants), the owner's mint verb
  (token callers), attention's API writers (handlers,
  programmes; their tracked seed/export form is the
  registry's `seed.py`).
- **Consumers:** the runner's wrapper seams (claim
  validation), the scheduler connector (authentication), the
  bridge-wake minter and the runner's liveness escalation
  (routing), attention's dispatch (target resolution) and
  evaluator (programme declarations), the shell (the
  programme/lane directory).

## The three caller natures

1. **Thread callers** — operator-written rows in a registry
   file: `{callers: [ids], active: [ids]}` (schema:
   `schemas/caller-registry.schema.json`; fixture:
   `fixtures/callers.example.json`, the tracked fictional
   seed). Semantics, carried whole from the runner
   (**RUN3**): a claim is `--caller` on Python entry points or
   `$COLAB_CALLER` for bash wrappers and drivers, **flag over
   env**; a claim may carry **one lane suffix** (`base:lane`)
   validated against its registered base; a
   **presented-but-unregistered claim is refused** at claim
   time; an **absent claim is unattributed**, never an error;
   registry validation is machinery ∪ local file, and a
   missing or malformed file yields the machinery set alone
   (fail-closed for thread claims, never a crash); callers in
   `active` are **detached-only** — the sync gate refuses
   their synchronous attaches outright; attaches are journaled
   to the **claims journal** (`var/caller-claims.jsonl`).
2. **Machinery callers** — code constants, never listed in any
   file: `panel`, `standing`, `test`, `lease`. A missing local
   registry never breaks the panel or the duties.
3. **Token callers** — the connector's registry: each caller
   maps to `{token_sha256, scopes}` (schema:
   `schemas/caller-registry.schema.json`, second form).
   **Hashes only** server-side; the registry is **read fresh
   from the live config on every call** (mint/revoke needs no
   restart); a missing/malformed registry means no callers
   and every call refused; raw tokens are printed once at
   mint and never stored in any tracked or stored form —
   attention's bridge token stays a raw-token live-config
   file on the client side only (docs/review/review-attention.md §11).
   Scopes: `read`, `write-state`, `send`, `bridge`, `exec` —
   `bridge` is home-side only, never issued to a venue caller.
   **`exec` denotes delegated execution:**
   it is the scope the `/ops` surface's `exec` op requires,
   while that surface's `write`/`patch` ops require
   `write-state` (contract 04's mapping). `exec` is
   likewise home-side only, never issued to a venue caller:
   it hands its holder arbitrary command execution in the
   server process, and mapping `exec` onto `write-state`
   instead would have handed that to every state-writing
   token — a widening, not a hardening. `/ops` requests
   authenticate through this same registry (read fresh per
   call), and the request's `caller` field must equal the
   authenticated caller — the self-asserted string survives
   only as the audit label, never as an authentication
   input. Every
   call, including refusals and authentication failures
   (caller `unknown`), is ledgered (contract 05's ledger).
   The boundary is absolute (**SCH7**): no tool approves a
   permission, pushes, acquires a lease, or writes a
   calendar.

## Handles and programmes

Attention's two registries join this contract: handlers and
programmes are API-written rows in the one untracked state
store, and the registry's seed/export step
(`pipeline/registry/seed.py`) gives them a tracked
seed/export form — `handlers.json` and `programmes.json`
on export.

- **Handler registry** — `{handle, label, color_slot, icon,
  thread_id, ui_surface, retired}` (schema:
  `schemas/attention-handler.schema.json`; fixture:
  `fixtures/attention-handler.json`, the demo seed's first
  row — the live registry's rows share this shape). Written by upsert;
  omitted fields are preserved from the existing entry.
  Handle → thread is the dispatch routing half; programme
  membership is not on the handler.
- **Programme registry** — the supervision directory proper:
  `{slug, label, handles[], cadence_minutes,
  staffing_band{min, max}, escalation_hours, venue,
  rule_text, settled[], commissions[], worktree_roots[],
  record_locations[], contract_path, idle_classes[],
  wb_projects[], retired}` (schema:
  `schemas/attention-programme.schema.json`; fixture:
  `fixtures/attention-programme.json`, the tests'
  upsert payload). Cadence, band, escalation, and venue are
  declarations, never evaluator constants (**ATT11**). Two
  fields are **contract-sourced**: `rule_text` and
  `cadence_minutes` are refreshed from the goal record at
  `contract_path` — the goal record owns them (contract 11)
  and the registry row is their directory projection, never
  a duplicate source.
- **Store seeding + seed/export:** the merged registry's
  live store is seeded, never hand-copied
  (`pipeline/registry/seed.py`): `seed-capture` builds it
  from the consolidation capture, `seed-examples` builds it
  from the tracked fictional examples in `fixtures/`, and
  `export` writes it back out in the per-form files.
  Live registries are re-seeded from the capture only,
  never from the tracked examples.
- **Store discipline (ATT1):** the store these registries
  live in keeps its discipline — one
  JSON-shaped state written atomically (`.tmp` sibling +
  rename); registry seeds appended when absent, never
  overwritten (`backfill`); and its datetime decode
  heuristic (ISO strings restored on load) is a format
  coupling — carried or deliberately replaced, never
  drifted into.

## Routing tables

Two caller→chat tables fold into this registry:

- **Bridge-wake owners** — `{version, owners: {<caller>:
  {chat}}, drain?: {chat}}` (fixture:
  `fixtures/bridge-wake-owners.example.yaml`, the test
  suite's specimen). Config is separate from job bodies.
- **Notify routes** — `{main, routes: {<caller>: <chat>}}`
  (fixture: `fixtures/notify-routes.example.json`).
  Machinery and unknown callers fall back to `main`.

The resolution rule itself (destination chat is data inside
a record; the wake address is a separate routing decision)
is contract 05's; this registry is the table it resolves
against (**SCH8**'s table half).

## Preserve clauses carried

RUN3 (caller attribution semantics, whole), SCH7 (token
registry discipline + no-authority boundary), ATT11
(programme declaration fields + contract-sourced fields),
SCH8 (routing tables; the rule rides 05).

## Store form

The registry is one store with the three natures distinct
and the seed/example pattern intact (contract 04). Venue
claims: no caller or routing row carries a venue key;
programme rows carry a `venue` declaration, which is a
different field and stays.
