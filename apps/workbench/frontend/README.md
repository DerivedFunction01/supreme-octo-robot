# Workbench app — frontend (superapp stage D3, mock-first)

The workbench surface of the workhorse superapp, built ahead of
the pipeline stages on the frozen S0 contracts. Every control
works against a **stateful mock adapter**; at S8 the live
adapter replaces it behind the same seam with no frontend
rewrite.

## Run

```sh
npm install
npm run dev        # dev server (port 8799)
npm run build      # tsc --noEmit && vite build
npm run preview    # serves the production build (port 8799)
npm run validate:mocks   # contract checks over the mock store
npm run smoke:render     # server-render every section, desktop + phone forms
```

The standalone preview runs the whole app on the mock adapter —
that is the point of the mock-first amendment: the frontend is
exercisable end-to-end before the pipeline exists.

## Shape of the code

- `src/lib/seam.ts` — the `WorkbenchAdapter` interface. Every
  section reads and mutates through it, never around it.
- `src/lib/mockAdapter.ts` — the mock store (stateful,
  versioned, subscribable). `src/lib/store.tsx` holds the one
  instance; **that export is the only line that changes at S8.**
- `src/lib/arming.ts` — pure contract-03 machinery: the armed
  predicate, the armed-row render (schema-shaped, checked
  field-identical against the S0 fixture), the progress-entry
  render (target form — no `migrated` stamp family), the
  stall derivation (2 missed intervals), checkpoint lines.
- `src/lib/seed.ts` — invented programme content in the pinned
  served shapes for the census's 11 canonical projects. The
  live workbench state stores were never read or copied.
- `src/sections/` — the storyboard's 20 frames, in order.
- `src/components/Shell.tsx` — **standalone-preview chrome
  only.** Per the owner's one-shell ruling (2026-11-13) the
  kit's AppShell replaces it at integration; the sections do
  not depend on it beyond navigation context. It does engage
  the kit's `useIsPhone` seam for its phone presentation.

## Kit consumption

- React primitives: imported from the kit's vendored home in
  this repo (`kit/` at the repo root; source of truth the
  spec-driven starter — see `kit/PROVENANCE.md`) through
  the `@kit` alias in `vite.config.ts` / `tsconfig.json` —
  never copied per-app. React is aliased to this app's
  `node_modules` so the kit resolves one React instance; the
  same aliases appear in `scripts/render-smoke.mjs`.
- Generated theme CSS: vendored checked-in under `src/kit/`
  per plan §10.4, byte-identical to the kit home (SHA-256 in
  `src/kit/PROVENANCE.md`). One local addition: a stub
  `themes/katex.css` so the vendored `index.css`'s import
  resolves — the kit home carries no `katex.css`. Declared in
  the lane report as the lane's only local kit modification.
- Tailwind v4 does not auto-detect the kit outside the app
  tree, so `src/app.css` names the kit's `components/` and
  `lib/` as `@source`s explicitly.

## Checks

- `validate:mocks` — 34 checks: seeded/rendered armed rows
  validate against `contracts/schemas/armed-row.schema.json`;
  the rendered row is field-identical to
  `contracts/fixtures/armed-row.json`; status posts validate
  against `status-post.schema.json`; the progress entry runs
  `wb progress-check <id>` and carries no `migrated` family;
  arming flows (doing arms, done/blocked retire, off disarms,
  re-arm), stall derivation, the 15-minute default, the opt-out;
  todo-id scheme; guarded-save CAS (config gate, sha match,
  stale-sha refusal, dataset refusal); goal-record owner_waiting
  clearing and ping disarm.
- `smoke:render` — 27 cases mounting every section (desktop
  harness + phone harness with the ≤480px seam engaged),
  asserting storyboard marker content.
