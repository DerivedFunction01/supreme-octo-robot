# Vendored Workhorse Kit v1 — generated CSS distribution

Per plan §10.4 (owner ruling): one generator in the
kit's home; the generated CSS ships as the distribution and
consumers take it checked-in. The kit's home is
the spec-driven-starter repo's `workhorse-kit/` (extracted
from workbench-viewer at pin `b0b9cc5`, plan step S2).

Vendored here (SHA-256 verified at vendor time; the hashes
match the vendored files as they stand):

| File | SHA-256 (first 16) |
|---|---|
| `themes/index.css` | `d3fafa66ad9cc40d` |
| `themes/fonts.css` | `4e0b27f09ed0974e` |
| `themes/olive.css` | `083de26e24426594` |
| `themes/teal.css` | `31b303d2f54575f5` |
| `assets/fonts/inter-var.woff2` | `3100e775e8616cd2` |
| `assets/fonts/plex-mono-400.woff2` | `08949f728dc52d52` |
| `assets/fonts/plex-mono-500.woff2` | `01d285447409c8a5` |
| `assets/fonts/plex-mono-600.woff2` | `0d1f0b8d0722224e` |

Generation note: this vendored set is an earlier kit
generation than this repo's repo-root `kit/`. `fonts.css`
and the font files match the repo-root kit's copies;
`themes/index.css`, `themes/olive.css`, and
`themes/teal.css` differ from the repo-root kit's current
themes (which also carry a `highlight.css` this vendored
set does not).

Notes:

- `themes/index.css` **is** vendored whole, the Workbench
  pattern: this app's `src/index.css` keeps its own
  `@import "tailwindcss"` first and imports the vendored
  file after it; the file's own tailwind import resolves to
  the same Tailwind v4 setup. The vendored file is the only
  copy of what it carries — the `:root` scale block
  (`--wb-space-*`, `--wb-radius-*`, `--wb-font-*`, sizes,
  motion, chart colors) and the `[data-density]` tail
  block; no reproduction of it is kept in `src/index.css`.
  The vendored `index.css` carries no `./katex.css` import
  (gap K2, closed in the kit: the generated themes carry
  no KaTeX import; the kit's Math component carries its
  own KaTeX assets under the kit's `assets/`).
- The palettes carry the `--wb-accent-soft` semantic
  token (gap K3).
- `fonts.css` references `../assets/fonts/*.woff2`; the vendored
  layout preserves that relative path (`themes/` beside
  `assets/fonts/`).
- Kit **components** are not copied: the app imports them
  from this repo's repo-root `kit/` through the
  `@workhorse/kit` alias (see `vite.config.ts`). Only the
  CSS — the ruled checked-in distribution — is vendored.
- Never edit the vendored files here. A new look is edited in
  the kit's home and re-vendored; needing to edit a consumer is
  a defect against the kit.
