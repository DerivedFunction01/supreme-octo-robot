# Workbench app — frontend

The workbench surface of the workhorse superapp: a
Vite/React app (package `workbench-frontend`) over the
frozen contracts. Every control works against a **stateful
mock adapter** in the standalone preview; the integration
entry mounts the **live adapter** (`src/lib/liveAdapter/`)
behind the same seam, with `?adapter=mock` as the explicit
opt-out (`src/lib/store.tsx`).

## Run

```sh
npm install
npm run dev        # dev server (port 8799)
npm run build      # tsc --noEmit && vite build + truncation check
npm run preview    # serves the production build (port 8799)
npm run validate:mocks   # contract checks over the mock store
npm run smoke:render     # server-render every section, desktop + phone forms
npm run validate:live    # the live adapter against served feeds
npm run validate:relay   # the relay form of the live adapter
```

The standalone preview runs the whole app on the mock
adapter — the frontend is exercisable end-to-end without
the pipeline.

## Shape of the code

- `src/lib/seam.ts` — the `WorkbenchAdapter` interface.
  Every section reads and mutates through it, never
  around it.
- `src/lib/mockAdapter.ts` + `src/lib/mockAdapter/` — the
  mock store (stateful, versioned, subscribable).
  `src/lib/liveAdapter.ts` + `src/lib/liveAdapter/` — the
  live adapter over the pipeline's served feeds.
  `src/lib/store.tsx` holds the one instance and selects
  between them.
- `src/lib/arming.ts` — pure contract-03 machinery: the
  armed predicate, the armed-row render (schema-shaped,
  checked field-identical against the fixture), the
  progress-entry render (no `migrated` stamp family), the
  stall derivation (2 missed intervals), checkpoint lines.
- `src/lib/seed.ts` + `src/lib/seed/` — invented programme
  content in the pinned served shapes for the census's 11
  canonical projects. The live workbench state stores were
  never read or copied.
- `src/sections/` — the section components (Home, Overview,
  Goals, Mockups, Entries, Plans, Todos, Board, Inbox,
  TaskManager, the Code facet in `Repos.tsx`/`Explorer.tsx`,
  Editor, Settings, DatasetView, SegmentBlocks,
  MessageThreads).
- `src/components/Shell.tsx` — **standalone-preview chrome
  only.** The kit's AppShell replaces it at integration;
  the sections do not depend on it beyond navigation
  context. It does engage the kit's `useIsPhone` seam for
  its phone presentation.

## Kit consumption

- React primitives: imported from the kit's vendored home
  in this repo (`kit/` at the repo root; source of truth
  the spec-driven starter — see `kit/PROVENANCE.md`)
  through the `@kit` alias in `vite.config.ts` /
  `tsconfig.json` — never copied per-app. React is aliased
  to this app's `node_modules` so the kit resolves one
  React instance; the same aliases appear in
  `scripts/render-smoke.mjs`.
- Generated theme CSS: vendored checked-in under `src/kit/`,
  byte-identical to the kit home (SHA-256 in
  `src/kit/PROVENANCE.md`). The vendored `index.css` no
  longer imports a `katex.css` — the kit's generated themes
  carry no KaTeX import and the kit's Math component
  carries its own KaTeX assets — so no local stub exists;
  the vendored set is exactly the kit's generated
  distribution.
- Tailwind v4 does not auto-detect the kit outside the app
  tree, so `src/app.css` names the kit's `components/` and
  `lib/` as `@source`s explicitly.

## Checks

- `validate:mocks` — checks over the mock store, including:
  seeded/rendered armed rows validate against
  `contracts/schemas/armed-row.schema.json`; the rendered
  row is field-identical to
  `contracts/fixtures/armed-row.json`; status posts
  validate against `status-post.schema.json`; the progress
  entry runs `wb progress-check <id>` and carries no
  `migrated` family; arming flows (doing arms, done/blocked
  retire, off disarms, re-arm), stall derivation, the
  15-minute default, the opt-out; todo-id scheme;
  guarded-save CAS (config gate, sha match, stale-sha
  refusal, dataset refusal); goal-record owner_waiting
  clearing and ping disarm. (The check count grows with
  the script; `scripts/validate-mocks.mjs` is the count's
  source.)
- `smoke:render` — mounts every section through the
  desktop harness (`scripts/render-harness.tsx`) and the
  phone harness (`scripts/render-harness-phone.tsx`, the
  ≤480px seam engaged), asserting storyboard marker
  content in each case.
