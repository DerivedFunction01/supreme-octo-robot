# Vendored Workhorse Kit v1 — generated CSS distribution

Vendored per consolidation plan §10.4: one generator in the kit's
home; the generated CSS ships as the distribution; consumers take
it checked-in and never regenerate it.

- **Source:** `${WS}/spec-driven-starter/workhorse-kit/themes/`
  (Workhorse Kit v1, extracted from workbench-viewer at pin
  `b0b9cc5`, plan step S2), plus `assets/fonts/` from the same home.
- **Vendored:** 2026-11-13, byte-identical copies (SHA-256 verified
  at vendor time):
  - `themes/index.css` — `d3fafa66ad9cc40de4e5c896e8d1b0db59fed71ca1dc94542d00cfd49f9fb2ce`
  - `themes/fonts.css` — `4e0b27f09ed0974ebf25831ac9dd9c54606fd7e09befe1d60d60b3592f416db7`
  - `themes/olive.css` — `083de26e24426594c8553566dc3388938e50ce735c6296bb0991911c02a7f2e1`
  - `themes/teal.css` — `31b303d2f54575f548cc06c6ff9b5a85e8625454d7291db39adfa3645bd6f94a`
  - `assets/fonts/*.woff2` — Inter variable; IBM Plex Mono 400/500/600
    (paths preserved: `fonts.css` references `../assets/fonts/`).
- **Re-vendored 2026-11-13 (kit pass part 2):** `themes/index.css`,
  `themes/olive.css`, and `themes/teal.css` regenerated in the
  kit's home and re-vendored byte-identical (hashes above) —
  `index.css` no longer imports a `katex.css` (gap K2, closed in
  the kit: the generated themes carry no KaTeX import; the kit's
  Math component carries its own KaTeX assets, imported by the
  component itself, and this app does not adopt Math in this
  round), and the palettes carry the `--wb-accent-soft`
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
