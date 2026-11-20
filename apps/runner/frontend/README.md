# Runner app — frontend (stage D4, mock-first)

The Runner panel over venue served portions, built mock-first
under plan §8's amendment: the S0 contracts are frozen, so the
frontend runs now against a **stateful mock adapter** behind a
data seam. Every storyboarded control works end-to-end against
the mock store — acquire / renew / release / adopt / exec /
probe change state, and every view re-derives from the store.
At S8 the live adapter replaces the mock behind the same seam
(`src/venue/index.ts`) with no frontend rewrite.

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
Degraded frame.

## Layout

- `src/venue/` — the seam. `types.ts` (contract 12 record
  shapes + served projections), `adapter.ts` (`VenueAdapter`
  interface + `MockVenueAdapter`: the D1 verbs against an
  in-memory store, seeded from `seed/*.json`), `index.ts`
  (the one adapter instance + React hook).
- `src/views/` — the storyboard's 8 frames: Leases, Lease
  detail, New lease, Orphans, Events, Budget, Access, and
  Degraded (rendered by Leases when the adapter reports the
  server unreachable), plus the sidebar Settings appearance
  group.
- `src/components/` — the AppShell/sidebar/topbar and the
  storyboard chrome components (GroupedList, Row, LogRow,
  StatusChip, PickerChips, Dialog, NoticeRow) composed on
  Workhorse Kit v1 tokens.
- `src/kit/` — the extracted Workhorse Kit v1, consumed as
  ruled: components copied from the kit's home, theme CSS
  vendored checked-in with provenance (`themes/PROVENANCE.md`).
  Never edited here; a missing capability is a kit gap,
  reported — not forked.
- `scripts/` — `validate-mocks.mjs` (schema verdicts) and
  `smoke-adapter.mjs` (headless exercise of every verb).

## Venue discipline

Every record and served projection is venue-keyed (D2);
all seed data carries `venue: colab`, the only implemented
adapter (D1), and the UI renders the venue rather than
assuming it. One exception, recorded as a contract gap:
the frozen session-evidence schema is closed
(`additionalProperties: false`) and carries no venue field,
so seed evidence omits it and the projection names the venue.
