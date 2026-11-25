# Scheduler app — frontend

The scheduler app's five storyboarded surfaces (Overview,
Jobs, Job detail, Pings, Ledger) as a TypeScript + React
app (package `scheduler-frontend` in the gate; the npm
package name is `workhorse-scheduler-frontend`). Two
adapters sit behind the app's data seam: a **stateful mock
adapter** and a **live adapter** (`src/live/`, HTTP over
the pipeline's `/api/v1`, contract 09). Every storyboarded
control works end-to-end against the mock store — run-now
walks the engine's states, suspend/resume move the entry's
status, ping acknowledge moves the record. The integration
entry mounts the mock by default (the demo persona) and
the live adapter under `?adapter=live` (`?api=<base-url>`
overrides the same-origin default). On live data the shell
stays read-only per contract 09 — the action verbs refuse
(gap G8).

## Run

```
npm install
npm run dev          # standalone preview on the mock adapter
npm run build        # tsc --noEmit + vite build + truncation check
npm run check-schemas  # mock payloads vs the frozen contracts
npm run exercise       # drive every control in jsdom, asserted
npm run check-live     # the live adapter vs the pipeline-served payloads
npm run gen-seeds      # regenerate src/mock/seed-entries.json
```

## Layout

- `src/api.ts` — the seam: the `SchedulerApi` interface
  every surface renders from and acts through.
- `src/types.ts` — contract 09's served shapes (job view,
  detail, run view, pings, ledger, overview) over contract
  14's entry form. Storyboard-required fields the contracts
  do not freeze are marked GAP in place.
- `src/live/` — the live adapter: a snapshot-cache
  `SchedulerApi` over the pipeline's `/api/v1`, projecting
  the pipeline server's payloads into the app's view types.
- `src/contract-data.ts` — the mock adapter's seed form of
  the two knob-bearing entries' config blocks only. The
  classification table no longer lives here: the pipeline
  serves audience/family/open_in on every job view
  (`pipeline/scheduling/server/serving/classification.py`) and the
  live adapter reads the served fields; the mock's copy of
  the fleet classification lives in `src/mock/seeds.ts`.
- `src/mock/` — the mock adapter: `seeds.ts` (26 entries
  in `seed-entries.json`, generated from the overlay
  capture + contract fixtures, deterministic outcome
  plans, cadence math) and `mock-adapter.ts` (the store,
  a contract-13 engine — consume-before-run, catchup
  collapse, no self-overlap — and the contract-09 view
  projections; every label is computed here, server-side,
  per contract 06), plus `mock-config.ts` and
  `mock-views.ts`.
- `src/views/`, `src/components/` — the five surfaces (plus
  `BuiltInDetail`) and the shell, composed from the kit:
  primitives imported from the kit's vendored home in this
  repo (`kit/` at the repo root) through the
  `@workhorse/kit` alias in `vite.config.ts`, generated
  theme CSS vendored checked-in under `src/kit/` (see
  `src/kit/PROVENANCE.md`).
- `src/Preview.tsx` — the standalone preview entry (desk
  frame + the app). Not part of the app: integration mounts
  `<App api={...}>` in the superapp shell instead, on the
  adapter its query string selects.
- `tools/` — `gen-seeds.py` (seed generation + contract-14
  validation), `check-schemas.ts` (payload validation),
  `exercise-ui.tsx` + `exercise-harness.ts` +
  `exercise-phone.ts` (control exercise), `check-live.ts`
  (adapter-contract tests for the live adapter), `live/`
  (the served-payload diff harness: `dump_served.py`
  captures both servers' payloads over the fixture store,
  `diff_served.py` prints the verdict; `payloads-*.json`
  are the kept captures), `tsconfig.json` (runtime path
  mappings for the tool runner).

Icons are Lucide only (`lucide-react`).

## Mock discipline

Mock payloads are generated from the contracts' schemas
and fixtures — the seed jobs are the real fleet's entries,
the seed pings and ledger lines ride the frozen schemas —
and `npm run check-schemas` validates everything the mock
serves (seeded and runtime-generated alike) against
`contracts/schemas/*.json` plus contract 09/14 structural
checks. Anything a surface needed that the contracts do
not freeze was built only where the approved storyboard
requires it and is recorded as a named gap — never
silently invented. The live side's evidence is the
served-payload diff (`tools/live/`): the pipeline server's
payloads are diffed against the pinned app's over the same
fixture store, with the dispositioned removals as the only
accepted differences (see `tools/live/diff_served.py`).
