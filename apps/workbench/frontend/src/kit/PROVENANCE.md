# Vendored Workhorse Kit v1 — generated CSS distribution

Vendored per consolidation plan §10.4: one generator in the kit's
home; the generated CSS ships as the distribution; consumers take
it checked-in and never regenerate it.

- **Source:** this repo's `kit/themes/` (the superapp's own
  Workhorse Kit since the fork at the starter's kit
  consolidation; originally extracted from workbench-viewer
  at pin `b0b9cc5`, plan step S2), plus `assets/fonts/` from
  the same home. Hashes below recomputed at the fork's
  `--ui-*` re-point.
- **Vendored:** byte-identical copies (SHA-256 verified
  at vendor time):
  - `themes/index.css` — `1419e8fab647c4b7af7a9744a005f5cee9e1db4c45e95384f4d85ac746576431`
  - `themes/fonts.css` — `4e0b27f09ed0974ebf25831ac9dd9c54606fd7e09befe1d60d60b3592f416db7`
  - `themes/olive.css` — `50d0fae52d96c340263360ebc6b6673ad5c908c63f8ea7aeffd65beb230aca5f`
  - `themes/teal.css` — `b80883ffaa3da9d7c55c4d503249f01e29f8f960e25a6c9512d9d56b72cfa1ba`
  - `assets/fonts/*.woff2` — Inter variable; IBM Plex Mono 400/500/600
    (paths preserved: `fonts.css` references `../assets/fonts/`).
- **Re-vendored (kit pass part 2):** `themes/index.css`,
  `themes/olive.css`, and `themes/teal.css` regenerated in the
  kit's home and re-vendored byte-identical (hashes above) —
  `index.css` no longer imports a `katex.css` (gap K2, closed in
  the kit: the generated themes carry no KaTeX import; the kit's
  Math component carries its own KaTeX assets, imported by the
  component itself, and this app does not adopt Math in this
  round), and the palettes carry the `--ui-accent-soft`
  semantic token (gap K3). The consumer-side `themes/katex.css`
  stub this directory carried so the old vendored `index.css`
  import would resolve is deleted; the vendored set is now
  exactly the kit's generated distribution. (`themes/katex.css`
  was NOT part of the kit distribution: the S2 extraction
  carried no `katex.css`, and the stub styled nothing.)
- The kit's React primitives are **not** copied: the app imports
  them from the kit's home via the `@kit` path alias
  (`vite.config.ts` / `tsconfig.json`), so there is exactly one
  source for them.
