# Scheduler app — frontend (stage D2, mock-first; S8 live adapter)

The scheduler app's five storyboarded surfaces (Overview, Jobs,
Job detail, Pings, Ledger) as a working TypeScript + React app,
per plan §8's mock-first amendment: the S0 contracts are frozen,
so the frontend begins now against a **stateful mock adapter**
behind the app's data seam. Every storyboarded control works
end-to-end against the mock store — run-now walks the engine's
states, suspend/resume move the entry's status, ping
acknowledge moves the record. S8 adds the **live adapter**
(`src/live/`, HTTP over the pipeline's `/api/v1`, contract 09)
behind the same seam with no frontend rewrite: the
integration entry mounts the mock by default (the demo
persona) and the live adapter under `?adapter=live`
(`?api=<base-url>` overrides the same-origin default). On
live data the shell stays read-only per contract 09 — the
action verbs refuse (gap G8; contract 09's S8 dispositions
record every gap's outcome).

## Run

```
npm install
npm run dev          # standalone preview on the mock adapter
npm run build        # tsc --noEmit + vite build
npm run check-schemas  # mock payloads vs the frozen contracts
npm run exercise       # drive every control in jsdom, asserted
npm run check-live     # the live adapter vs the pipeline-served payloads
npm run gen-seeds      # regenerate src/mock/seed-entries.json
```

## Layout

- `src/api.ts` — the seam: the `SchedulerApi` interface every
  surface renders from and acts through.
- `src/types.ts` — contract 09's served shapes (job view,
  detail, run view, pings, ledger, overview) over contract
  14's entry form. Storyboard-required fields the contracts
  do not freeze are marked GAP in place, each with its S8
  disposition.
- `src/live/` — the live adapter (S8): a snapshot-cache
  `SchedulerApi` over the pipeline's `/api/v1`, projecting
  the moved server's payloads into the app's view types.
- `src/contract-data.ts` — the contract tables both adapters
  serve (contract 09 amendment's classification + the
  evidence-backed entry config blocks) until the pipeline
  serves them itself.
- `src/mock/` — the mock adapter: `seeds.ts` (the fleet of
  record: 26 entries generated from the S1 overlay capture +
  contract fixtures, deterministic outcome plans, cadence
  math) and `mock-adapter.ts` (the store, a contract-13
  engine — consume-before-run, catchup collapse, no
  self-overlap — and the contract-09 view projections; every
  label is computed here, server-side, per contract 06).
- `src/views/`, `src/components/` — the five surfaces and the
  shell, composed from Workhorse Kit v1: primitives imported
  from the kit's home in the spec-driven starter (the
  `@workhorse/kit` alias in `vite.config.ts`), generated
  theme CSS vendored checked-in under `src/kit/` per plan
  §10.4 (see `src/kit/PROVENANCE.md`).
- `src/Preview.tsx` — the standalone preview entry (desk
  frame + the app). Not part of the app: integration mounts
  `<App api={...}>` in the superapp shell instead, on the
  adapter its query string selects.
- `tools/` — `gen-seeds.py` (seed generation + contract-14
  validation), `check-schemas.ts` (payload validation),
  `exercise-ui.tsx` (control exercise), `check-live.ts`
  (adapter-contract tests for the live adapter),
  `live/` (the served-payload diff harness: `dump_served.py`
  captures both servers' payloads over the S1-capture
  fixture store, `diff_served.py` prints the verdict;
  `payloads-*.json` are the kept captures), `tsconfig.json`
  (runtime path mappings for the tool runner).

Icons are Lucide only (`lucide-react`).

## Mock discipline

Mock payloads are generated from the contracts' schemas and
fixtures — the seed jobs are the real fleet's entries, the
seed pings and ledger lines ride the frozen schemas — and
`npm run check-schemas` validates everything the mock serves
(seeded and runtime-generated alike) against
`contracts/schemas/*.json` plus contract 09/14 structural
checks. Anything a surface needed that the contracts do not
freeze was built only where the approved storyboard requires
it and is recorded as a named gap with its S8 disposition —
never silently invented. The live side's evidence is the
served-payload diff (`tools/live/`): the pipeline server's
payloads diff EMPTY against the pinned app's over the same
fixture store, except the dispositioned plan-amendment-3
removals.
