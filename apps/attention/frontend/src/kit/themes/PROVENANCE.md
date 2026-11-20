# Vendored kit — provenance

Vendored verbatim 2026-11-13 from the Workhorse Kit v1 home
(the spec-driven-starter repo's `workhorse-kit/` directory):

- `themes/` — the generated CSS distribution (`index.css`,
  `fonts.css`, `olive.css`, `teal.css`), byte-identical to the
  kit home at vendoring time, with the bundled fonts from the
  kit's `assets/fonts/` alongside under `../assets/fonts/`.

Per plan §10.4: one generator in the kit's home; the generated
CSS ships as the distribution and consumers take it checked-in.
These copies are never edited by hand — a kit change is made
in the kit's home and re-vendored. At S8 integration the
parent folds this app into the superapp's one frontend build,
where the kit is consumed once for the whole shell.

Components and lib are NOT vendored: the app consumes them
from the kit's home through the `@workhorse/kit` alias
(vite.config.ts + tsconfig paths), including the kit's
AppShell. (An earlier stage build vendored byte-identical
copies under `../components/` + `../lib/`; the AppShell
re-point deleted them — the alias is the standing form, the
same consumption the runner and workbench apps use.)

Re-vendored 2026-11-13 (kit pass): `index.css`, `olive.css`,
and `teal.css` regenerated in the kit's home and re-vendored
byte-identical — `index.css` no longer imports a `katex.css`
(gap K2, closed in the kit: the kit ships no math component
or KaTeX fonts, so the import is removed there), and the
palettes carry the new `--wb-accent-soft` semantic token
(gap K3). The empty `katex.css` stand-in this directory
carried so the old verbatim `index.css` would resolve is
deleted; the vendored set is now exactly the kit's
generated distribution. `fonts.css` and the fonts are
unchanged.
