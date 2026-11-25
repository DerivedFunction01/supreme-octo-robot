# Vendored kit theme CSS — provenance

Vendored from the Workhorse Kit v1 home, the
spec-driven-starter repo's `workhorse-kit/themes/`
(`index.css`, `fonts.css`, `olive.css`, `teal.css`), with the
bundled fonts from `../assets/fonts/` alongside, per plan
§10.4: one generator in the kit's home; the generated CSS
ships as the distribution and consumers take it checked-in.
These copies are never edited by hand — a token change is
made in the kit's home and re-vendored.

Generation note: this vendored set is an earlier kit
generation than this repo's repo-root `kit/`. `fonts.css`
and the font files match the repo-root kit's copies;
`index.css`, `olive.css`, and `teal.css` differ from the
repo-root kit's current themes (which also carry a
`highlight.css` this vendored set does not). The vendored
`index.css` carries no `katex.css` import (gap K2, closed:
the generated themes carry no KaTeX import; the kit's Math
component carries its own KaTeX assets, imported by the
component itself), and the palettes carry the
`--wb-accent-soft` semantic token (gap K3). No `katex.css`
stand-in is carried.

The kit's components and lib are NOT vendored here: the app
imports them from this repo's repo-root `kit/` through the
`@workhorse/kit/*` alias (see `vite.config.ts` /
`tsconfig.json`). Only this generated CSS distribution (and
its fonts) is taken checked-in.
