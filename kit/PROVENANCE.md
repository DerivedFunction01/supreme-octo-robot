# Workhorse Kit — this repo's own kit

This directory is the kit's home and its one source of truth.
It began as a vendored copy of the spec-driven starter's kit
so every app in this repo could resolve `@workhorse/kit`
from inside the repo; at the starter's kit consolidation
(the generic kit dropped, the starter's kit renamed to
`ui-kit/` with the `--ui-*` prefix) this copy was forked into
this repo's own kit: changes to the kit land here directly,
the CSS prefix is `--ui-*`, and no tree outside this repo is
its source. The vendoring snapshot history that preceded the
fork is in this file's git history.

Direction: each app eventually gets its own kit and its own
flavor, rather than borrowing from the spec or from a shared
home. Until an app splits its kit off, this shared kit serves
the four apps (scheduler, workbench, runner, attention) and
the integrated client, and a split is a deliberate act that
moves that app's components and tokens into its own home.

## Manifest

`manifest.json` (this directory) carries the sha256 of every
kit file. It is the form the drift check verifies against;
regenerate it in the same change as any kit edit.

## Discipline

Kit changes land here, in this repo, like any other code:
edit the kit, regenerate the themes with the kit's own
generator (`tools/gen-tokens.mjs`, byte-identical output),
pass the kit's contrast gate (`tools/verify-contrast.mjs`),
regenerate `manifest.json`, and refresh the per-app theme
copies under `apps/*/frontend/src/kit/` in the same change.
A kit file that disagrees with the manifest is drift — the
copy, not the manifest, is wrong.

## Drift check

`pipeline/platform/ops/kit_drift.py` verifies this tree
against `manifest.json`: every file added, removed, or
changed is named and the check exits non-zero. The rebuild's
step-5 publish pipeline calls this check; a drifted kit does
not publish.
