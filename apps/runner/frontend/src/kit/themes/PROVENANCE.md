# Vendored kit theme CSS — provenance

Vendored verbatim from the Workhorse Kit v1 home,
`${WS}/spec-driven-starter/workhorse-kit/themes/`
(`index.css`, `fonts.css`, `olive.css`, `teal.css`), with the
bundled fonts from `../assets/fonts/` alongside, per plan
§10.4: one generator in the kit's home; the generated CSS
ships as the distribution and consumers take it checked-in.
These copies are never edited by hand — a token change is
made in the kit's home and re-vendored. Refreshed
(shell unification): the copies were verified byte-identical
to the kit home at the refresh.

The kit's components and lib are NOT vendored here: the app
imports them from the kit home through the `@workhorse/kit/*`
alias (see `vite.config.ts` / `tsconfig.json`). Only this
generated CSS distribution (and its fonts) is taken
checked-in. An earlier build carried copied components under
`src/kit/components/` and `src/kit/lib/`; the copies were
verified byte-identical to the kit originals and removed.

Re-vendored (kit pass part 2): `index.css`,
`olive.css`, and `teal.css` regenerated in the kit's home
and re-vendored byte-identical — `index.css` no longer
imports a `katex.css` (gap K2, closed in the kit: the
generated themes carry no KaTeX import; the kit's Math
component carries its own KaTeX assets, imported by the
component itself, and this app does not adopt Math in this
round), and the palettes carry the `--wb-accent-soft`
semantic token (gap K3). The empty `katex.css` stand-in
this directory carried so the old verbatim `index.css`
would resolve is deleted; the vendored set is now exactly
the kit's generated distribution. `fonts.css` and the
fonts are unchanged.
