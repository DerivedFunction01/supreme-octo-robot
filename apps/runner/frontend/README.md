# Runner app — frontend

The Runner panel over venue served portions: a Vite/React
app (package `runner-frontend`) whose data seam carries
three adapters — a stateful mock adapter for the standalone
preview, a live adapter over the venue surface for the
integration entry, and a relay adapter (the live adapter's
behaviour over the shell's action channel) when the shell
frame injects its transport. Every storyboarded control
works end-to-end against the mock store — acquire / renew /
release / adopt / exec / probe change state, and every view
re-derives from the store.

## Run it

```
npm install
npm run dev          # or: npm run build && npm run preview
npm run validate:mocks   # seed payloads vs contracts/schemas/*.json
npm run typecheck
```

The standalone preview entry (`index.html` → `src/main.tsx`)
runs the whole app on the mock adapter. A harness strip above
the app chrome (not part of the app) carries the preview-only
controls: the lease-server reachability switch that drives the
Degraded frame. The integration entry (`integration.html` →
`src/integration.tsx`) selects the live or relay adapter;
`?adapter=mock` keeps the mock available there.

## Layout

- `src/venue/` — the seam. `types.ts` (contract 12 record
  shapes + served projections), `adapter.ts` + `adapter/`
  (the `VenueAdapter` interface and `MockVenueAdapter`
  against an in-memory store, seeded from `seed/*.json`),
  `live-adapter.ts` + `live-adapter/`, `relay-adapter.ts`,
  and `index.ts` (the one adapter instance + React hook,
  selecting relay, then live, then mock).
- `src/views/` — Leases, Lease detail, New lease, Orphans,
  Events, Budget, and Access, plus `GrantCard`; Degraded is
  rendered by Leases when the adapter reports the server
  unreachable. There is no Settings destination: appearance
  lives in the shell's unified Settings.
- `src/components/` — `ui.tsx`: the storyboard chrome
  components (GroupedList, Row, LogRow, StatusChip,
  PickerChips, Dialog, NoticeRow). The AppShell itself is
  imported from the kit (`@workhorse/kit`).
- `src/kit/` — the kit's generated theme CSS and fonts,
  vendored checked-in with provenance
  (`themes/PROVENANCE.md`). Never edited here; a missing
  capability is a kit gap, reported — not forked. The kit's
  components and lib are consumed from the repo's `kit/`
  home through the `@workhorse/kit` alias, not copied here.
- `scripts/` — `validate-mocks.mjs` (schema verdicts),
  `smoke-adapter.mjs` (headless exercise of every verb),
  and live/relay/api-base smoke scripts.

## Venue discipline

Every record and served projection is venue-keyed; the UI
renders the venue rather than assuming it. Seed leases,
events, and runs carry `venue: colab`, and the served specs
seed also names a `local` shape/venue. Session evidence is
no exception: its schema is closed
(`additionalProperties: false`) and `venue` is one of its
required fields, so seed evidence carries it like every
other record.
