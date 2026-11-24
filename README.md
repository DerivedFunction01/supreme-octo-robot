# supreme-octo-robot — the workhorse superapp

One repo for the four workhorses — scheduler, workbench,
runner (Colab lease core + panel), owner-attention — as a
pipeline layer with four apps over it.

**Governing document:** `docs/2026-11-12/consolidation-plan.md`
(the big-bang consolidation plan: decisions, target
structure §1, preserve list §2, overlay capture §3,
contracts §4, execution steps §5, platform services §6,
venue extraction §7, stage deploys §8, attention amendment
§9, owner rulings §10, supersession ledger §12). Source
reviews: `docs/review/`.

**Status:** step S0 landed — the eleven pipeline contracts
are frozen in `contracts/` (documents + schemas + fixtures,
with the §2 traceability index), and the directory skeleton
below exists as READMEs only. No code has moved; integration
steps S1–S11 execute per the plan, behind gate G1.

```
contracts/     the pipeline contracts of §4 (frozen at S0)
pipeline/      the engines, bound by the contracts
  scheduling/  registry, catalog/adoption/drift, schedule math, engine, executor
  dispatch/    outbox + bridge queue + wake minter + messages/outbox (one substrate)
  venue/       lease core, run records, transport, gate policy, adapters/
    adapters/colab/   the extracted Colab adapter
  workrecord/  registry store, plans/bundles, progress derivation, arming writers
  evaluation/  classification feed, doctor, progress reporting
  platform/    ops service, harness connector, gate runner, release record,
               backup, watchdog/stackdump/file-registry survival services
apps/          the four consumers of pipeline-served shapes
  scheduler/   viewer client + host bridge binding over /api/v1 shapes
  workbench/   viewer sections/components over work-record served shapes
  runner/      panel over venue served portions
  attention/   Today/Digest/glance over evaluation + dispatch shapes
docs/          the plan, the reviews, stage records
```

The kit (Workhorse Kit v1) does **not** live here — its home
is the spec-driven starter; this repo consumes it as every
other repo does. The original repos archive as they are once
this repo carries their work; colab-runner is explicitly
untouched (the venue core is extracted alongside it).
