# Vendored kit — provenance

Vendored from the Workhorse Kit v1 home
(the spec-driven-starter repo's `workhorse-kit/` directory):

- `themes/` — the generated CSS distribution (`index.css`,
  `fonts.css`, `olive.css`, `teal.css`), with the bundled
  fonts from the kit's `assets/fonts/` alongside under
  `../assets/fonts/`.

Per plan §10.4: one generator in the kit's home; the generated
CSS ships as the distribution and consumers take it checked-in.
These copies are never edited by hand — a kit change is made
in the kit's home and re-vendored.

Generation note: this vendored set is an earlier kit
generation than this repo's repo-root `kit/`. `fonts.css`
and the font files match the repo-root kit's copies;
`index.css`, `olive.css`, and `teal.css` differ from the
repo-root kit's current themes (which also carry a
`highlight.css` this vendored set does not). The vendored
`index.css` carries no `katex.css` import (gap K2, closed:
the generated themes carry no KaTeX import — the kit's Math
component vendors its own KaTeX assets under the kit's
`assets/` and imports them itself), and the palettes carry
the `--wb-accent-soft` semantic token (gap K3). No
`katex.css` stand-in is carried.

Components and lib are NOT vendored: the app consumes them
from this repo's repo-root `kit/` through the
`@workhorse/kit` alias (vite.config.ts + tsconfig paths),
including the kit's AppShell — the same consumption the
runner and scheduler apps use. This app remains a per-app
Vite/React frontend; the integrated client in `artifact/`
consumes the kit separately, from the same repo-root home.
