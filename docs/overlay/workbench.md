# Overlay inventory — workbench-viewer

Nothing was held for this repo. Its overlay classes are
inventoried in place: registry data never migrates, live
config carries tracked specimens, and runtime state is
not carried.

**Manifest census.** The harness's own sweep, run
read-only against the workspace, returned 11 canonical
projects, 241 manifest roots, 0 errors — the verification
that the consolidated tooling reads every adopting
project where it lives. The census is a snapshot, not a
constant: one project's fold (its worktrees and exports
under one canonical slug) grows as worktrees are created.

**Registry stores stay in place.** Each project's
registry DB (the unified schema: `entries`, `history`,
`todos`, `todo_events`) and its `registry.json` export
remain in the owning project; all 11 read cleanly from
the mega-repo side at capture. The two registries this
repo writes into siblings — the scheduler `wb-progress-*`
entries and attention's armed rows — are captured in
those repos' inventories.

**Live config, inventoried not held.** `config.json`
(only `file_editing_enabled` and `port` — the specimen
and defaults carry the contract) and `viewer.env`, each
with a tracked specimen (`config.example.json`,
`viewer.env.example`).

**Runtime state, not carried.** The `state/` population:
health/link/repair records, the server lock, the
messages store, the server-local repos-registry cache,
doctor findings, edit and repos history logs, and
edit-backups. Two backups are secret-bearing by name —
inventoried by reference only, never copied, never read.
The portability denylist sat in `state/` — live config
by nature, runtime by location; it is named here so the
class is not lost: a denylist is provisioned material,
never tracked content.

**Templates ride the tree** (tracked): the manifest,
staging, and choice-kit templates — not overlay, no
capture action.
