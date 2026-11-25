# supreme-octo-robot — the workhorse superapp

One repo for the four workhorses — scheduler, workbench,
venue runner, owner-attention — consolidated into a
pipeline layer with four apps over it. The four run from
this repo: the scheduler serve runs from
`pipeline/scheduling` (systemd `workhorse.service`), and
the venue fleet — local machines and Colab sessions as
peers — runs under `pipeline/venue`.

**Governing document:** `docs/consolidation-plan.md` —
the consolidation's decisions, target structure,
preserve list, contract consolidations with their
canonical owners, and the owner's ruled decisions.
Source reviews of the four original systems:
`docs/review/`. Standing owner rulings for the app:
`docs/rulings.md`. Supervision rules:
`docs/supervision-rules.md` (the generic text; its
canonical home is the spec-driven starter, this repo
carries the synced text).

```
contracts/     the pipeline contracts (documents + schemas + fixtures,
               with the traceability index)
pipeline/      the engines, bound by the contracts
  scheduling/  registry, catalog/adoption/drift, schedule math, engine, executor
  dispatch/    outbox + bridge queue + wake minter + messages/outbox (one substrate)
  venue/       lease core, run records, transport, gate policy, adapters/
    adapters/colab/   the Colab adapter
    adapters/local/   the local-machine adapter
  workrecord/  registry store, plans/bundles, progress derivation, arming writers
  evaluation/  classification feed, doctor, progress reporting
  attention/   evaluator, dispatch consumer, decision machinery, presence
  registry/    the one caller + routing registry all four apps consume
  gate/        the shared gate legs the root check.py composes
  platform/    ops service, unified state writer, harness connector,
               gate runner, release record, backup, survival services
apps/          the four consumers of pipeline-served shapes
  scheduler/   viewer client + host bridge binding over /api/v1 shapes
  workbench/   viewer sections/components over work-record served shapes
  runner/      panel over venue served portions
  attention/   Today/Digest/glance over evaluation + dispatch shapes
artifact/      the one integrated frontend: the four apps as views
               of a single client on the unified kit
docs/          the plan, the reviews, the overlay capture record
```

**The gate** is `check.py` at the repo root: ruff format
and lint, the policy scanners, and pytest, composed from
per-package declarations in `pipeline/gate`. It is
change-aware by default — a pathspec runs the affected
packages with AST-targeted tests; `--all` forces the
full suite.

The kit lives here: `kit/` is this repo's own UI kit and
its source of truth (see `kit/PROVENANCE.md`); it was
forked from the spec-driven starter's kit, which remains
that repo's own. The original repos
are archived as they are; colab-runner is explicitly
untouched — the venue core lives here alongside it, and
the Colab adapter replaces its use.
