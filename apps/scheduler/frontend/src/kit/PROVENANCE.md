# Vendored Workhorse Kit v1 — generated CSS distribution

Per plan §10.4 (owner ruling): one generator in the
kit's home; the generated CSS ships as the distribution and
consumers take it checked-in. The kit's home is this repo's `kit/` directory (the superapp's
own kit since the fork at the starter's kit consolidation;
originally extracted from workbench-viewer at pin `b0b9cc5`,
plan step S2). The hashes below are the current copies',
recomputed at the fork's `--ui-*` re-point.

Vendored here, byte-identical to the kit's `themes/` and
`assets/fonts/` (SHA-256 verified at vendor time):

| File | SHA-256 (first 16) |
|---|---|
| `themes/index.css` | `1419e8fab647c4b7` |
| `themes/fonts.css` | `4e0b27f09ed0974e` |
| `themes/olive.css` | `50d0fae52d96c340` |
| `themes/teal.css` | `b80883ffaa3da9d7` |
| `assets/fonts/inter-var.woff2` | `3100e775e8616cd2` |
| `assets/fonts/plex-mono-400.woff2` | `08949f728dc52d52` |
| `assets/fonts/plex-mono-500.woff2` | `01d285447409c8a5` |
| `assets/fonts/plex-mono-600.woff2` | `0d1f0b8d0722224e` |

Notes:

- `themes/index.css` **is** vendored whole (vendoring cure),
  the Workbench pattern: this app's `src/index.css`
  keeps its own `@import "tailwindcss"` first and imports the
  vendored file after it; the file's own tailwind import
  resolves to the same Tailwind v4 setup. It was originally
  skipped for that first-line import, and the app imported
  `fonts.css` / `olive.css` / `teal.css` directly instead —
  which silently dropped everything else the file carries:
  the `:root` scale block (`--ui-space-*`, `--ui-radius-*`,
  `--ui-font-*`, sizes, motion, chart colors) and the
  `[data-density]` tail block. The tail block spent a day
  reproduced verbatim in `src/index.css` as a
  stopgap; that reproduction is **deleted** — the vendored
  file's own copy is the only one, never both. (At first
  vendoring the kit's `index.css` also imported a `./katex.css`
  the kit did not ship — gap K2, closed in the kit:
  the import is removed there; it was never a reason this app
  needed, only a second reason to skip the file.)
- Re-vendored (kit pass): `olive.css` / `teal.css`
  regenerated in the kit's home for the `--ui-accent-soft`
  semantic token (gap K3) and re-vendored byte-identical;
  `fonts.css` and the font files are unchanged.
- `fonts.css` references `../assets/fonts/*.woff2`; the vendored
  layout preserves that relative path (`themes/` beside
  `assets/fonts/`).
- Kit **components** are not copied: the app imports them from
  the kit's home through the `@workhorse/kit` alias (see
  `vite.config.ts`), the same import-from-the-kit pattern as
  step S2's workbench consumer switch. Only the CSS — the ruled
  checked-in distribution — is vendored.
- Never edit the vendored files here. A new look is edited in
  the kit's home and re-vendored; needing to edit a consumer is
  a defect against the kit.
