# Vendored Workhorse Kit — provenance and sync discipline

This directory is a **vendored copy** of the Workhorse Kit v1
(`@workhorse/kit`). It exists so every app in this repo resolves
the kit from inside the repo: a bare clone or a clean staged
formation has no sibling checkouts, and the previous tsconfig /
vite aliases pointed outside the repo, which failed there
(TS2307 on `@workhorse/kit/*`).

## Source of truth

The starter repo's `workhorse-kit/` directory (the
spec-driven-starter project) remains the kit's one source of
truth. Changes to the kit land there first; this copy is never
edited directly.

Vendoring snapshot:

- Source tree: the starter's `workhorse-kit/` (68 files,
  copied byte-for-byte; one re-sync carries
  the critic-confirmation cures F-2/F-3: a `notify` /
  `on-notify` solid-badge token pair in
  `tokens/tokens.json` (themes regenerated; the notify
  fill is the Okabe vermilion deepened to clear 4.5:1
  under white text), the contrast gate's Part 4
  (text-on-solid pairs) in `tools/verify-contrast.mjs`,
  and the Toggle focus guarantee — `wb-toggle` /
  `wb-toggle-track` hooks in `components/Toggle.tsx`
  plus the kit-owned `.wb-toggle` rule in the generated
  themes (see `tools/gen-tokens.mjs`), whose inset
  on-accent ring keeps the checked track's focus ring
  from camouflaging against its own accent fill; the
  F9b re-sync adds the two residues F9 named
  outside its scope: the Button press-shade token
  (`tokens/tokens.json`, themes regenerated) — Button's
  color-mix state steps run toward the per-mode
  press-shade (black in light modes, white in dark)
  instead of a fixed black, so the danger active state
  clears 4.5:1 in dark modes — with the contrast gate's
  Part 5 (button-state pairs, the mix constants
  mirrored as data) in `tools/verify-contrast.mjs`, and
  the Checkbox focus guarantee — the `wb-checkbox`
  hook in `components/Checkbox.tsx` plus the kit-owned
  `.wb-checkbox` rule in the generated themes (see
  `tools/gen-tokens.mjs`), whose inset white ring keeps
  the checked disc's accent focus ring from
  camouflaging against its status-done fill; the F11
  re-sync adds the `.wb-codeblock`
  focus rule in `themes/highlight.css` — the spliced
  code block is a scrollable region, rendered
  focusable by its consumer, and its focus indication
  is the kit's one ring (critic WB5-1); the F13
  re-sync adds the `.wb-prose a` rule
  in the generated themes (see `tools/gen-tokens.mjs`,
  beside the prose task-list rules): prose anchors
  take the accent colour plus an underline with a
  small offset, so a link inside a block of prose is
  never distinguished by colour alone (axe
  link-in-text-block; the reader-chrome form of the
  class measured serious on every PlanReader page);
  another re-sync adds the
  LogRow payload clamp: `lib/log-payload.ts` +
  `tools/verify-log-payload.mjs`, and the LogRow change
  itself; a further re-sync carries the
  contrast gate's Part 3 (text-on-tint pairs) with the
  finding-N-1 cure: status text tokens moved along their
  own scales in `tokens/tokens.json` (themes
  regenerated), and the mix-badge text step 78% -> 43%
  in `components/LogRow.tsx` + `components/AppShell.tsx`,
  mirrored in `tools/verify-contrast.mjs`).
  A Part 6 re-sync carries the
  starter's focus / boundary / overlay gate classes
  with the field-border role: `tokens/tokens.json`
  gains the role (themes regenerated),
  `tools/verify-contrast.mjs` gains Part 6 (gate at
  1,852 pairs) with the tree-scanned spend census, and
  every identifying border spend re-points from
  border-default / border-strong to field-border in
  `components/Checkbox.tsx`, `Fields.tsx`,
  `PaletteSelect.tsx`, `SegmentedControl.tsx`,
  `StateControls.tsx`, and `Toggle.tsx` — including
  the census's one provisional entry, the
  `components/Button.tsx` secondary edge, whose
  re-point the starter census carried as a NOTE owed
  by the D3D4 Button landing; it lands here. This
  formation is a union: it also carries two mega-side
  cures the starter takes as follow-ups — the D3D4
  Button label-wrap cure and the D5 `relative`
  containing-block hunks in `Toggle.tsx` /
  `SegmentedControl.tsx` — plus this formation's own
  census data in `tools/verify-contrast.mjs` (the
  Button classification the re-point retires into,
  and the Toggle needle the D5 hunk moves), so until
  those follow-ups land starter-side, the external
  drift leg names exactly `components/Button.tsx`,
  `components/Toggle.tsx`,
  `components/SegmentedControl.tsx`, and
  `tools/verify-contrast.mjs`.
- Starter repo HEAD at the last re-sync:
  `2a7eb22dcdcbada44e7f05ca820ed900aa4ff588` — the
  Part 6 commit, whose `workhorse-kit/` tree is this
  re-sync's source (the one later starter commit,
  56b11f7, touches scanners only); the manifest below
  remains the pin this repo verifies against.
- Regrouping cure applied locally (spec plan, Step 3): the starter's
  own folder-density cure, applied to this copy ahead of
  the next re-sync so both trees converge on the same
  layout. The 29 components now live in
  `components/controls/` (10), `components/display/` (12),
  and `components/shell/` (7), with every relative import
  re-pointed at the new leaf paths; KaTeX's 20 woff2 moved
  from `assets/fonts/` to `assets/fonts/katex/`; the
  1,219-line `assets/katex.css` split at its seams into
  `assets/katex-fonts.css` (@font-face), `assets/katex.css`,
  `assets/katex-sizing.css`, and `assets/katex-symbols.css`,
  imported in that order by `components/shell/Math.tsx`;
  and the contrast gate's census in
  `tools/verify-contrast.mjs` now scans `components/`
  recursively (census entry names remain basenames), its
  output unchanged. `manifest.json` was regenerated for
  the new tree. The re-sync narratives above name the
  paths as they stood when each re-sync landed.
- Contrast-gate decomposition carried locally
  (line-cap cure `b81a473`): the 1,178-line
  `tools/verify-contrast.mjs` split along its part seams
  into `tools/contrast/core.mjs` (tokens, colour math,
  resolvers), `tools/contrast/part6-pairs.mjs`, and
  `tools/contrast/census6.mjs`; the entry keeps the
  header record and Parts 1–5 and runs the parts in the
  original order, its output and exit code unchanged.
  The decomposition landed without its manifest carry;
  `manifest.json` is regenerated for the decomposed tree
  (74 files pinned).
- Docs-in-place strip carried locally: the comments and
  docs in this copy carry no date tags (the living-dates
  rule — living documents and comments state the present;
  the vendoring snapshot above keeps its attributions
  without their dates). The strip is owed at the source
  as well; until it lands there, the external drift leg
  names the stripped files. `manifest.json` is
  regenerated for the stripped tree (74 files pinned).

## Manifest

`manifest.json` (this directory) carries the sha256 of every
vendored file, generated at vendoring time. It is the form the
drift check verifies against.

## Sync discipline

A re-sync is a deliberate act, never a side effect:

1. Copy the starter's `workhorse-kit/` tree over this
   directory, verbatim (excluding any `node_modules` or build
   output the starter tree may later grow).
2. Regenerate `manifest.json` from the copied tree.
3. Update the vendoring snapshot note above (what the
   re-sync carries, and the starter HEAD if the kit has
   been committed there by then).
4. Run the drift check (below) — it must pass before the
   re-sync is landed.

Local edits to files in this directory are forbidden. If a
vendored file disagrees with the manifest and no re-sync is in
flight, the copy — not the manifest — is wrong.

## Drift check

`pipeline/platform/ops/kit_drift.py` verifies this tree two
ways:

- Internal: every file matches `manifest.json`; any file
  added, removed, or changed is named and the check exits
  non-zero.
- External (when a starter checkout is passed via
  `--starter <path>` or the `WORKHORSE_KIT_STARTER` env seam):
  every file also matches the starter's live `workhorse-kit/`
  tree, so a starter-side change that has not been re-synced
  is caught by name.

The publish prep (`pipeline/platform/ops/publish_prep.py`)
calls this check; a drifted kit does not publish.
