# Overlay capture — record

Before any tree moved in the consolidation, each source
repo got an overlay census and capture, read-only against
the source: the pinned trees were not the deployed
systems, and a copy from the pins alone would have lost
the scheduler's fleet, the runner's registries, the
workbench's runtime state, and attention's whole store.
The capture's classification is the discipline that
survives: every captured item is one of **promote to
tracked**, **live config** (the seed/example pattern:
tracked fictional example, untracked live file),
**data** (migrates verbatim, as data), **runtime state**
(not carried; re-seeded or left in place), **credential —
reference only** (named by path and nature, never copied,
never hashed), or **debris** (named as excluded).

Per-repo inventories: [scheduler](scheduler.md) ·
[workbench](workbench.md) · [runner](runner.md) ·
[attention](attention.md). The held copies the capture
made were consumed by the consolidation's steps; nothing
is held now.

## Outcomes

- **Scheduler.** The captured registry validates complete
  with the overlay applied (26 valid entries, 0 invalid)
  where the bare pin quarantines one entry: only
  `bridge-drain` is load-quarantined on the bare pin (its
  body file does not exist there); `bridge-wake`
  validates, because the loader never checks its wake
  body or routing config — it is operationally incomplete
  on the bare pin, not quarantined. The captured fleet —
  job entries, bodies, routing config, member scripts —
  runs from `pipeline/scheduling`.
- **Workbench.** Nothing was held: registry data never
  migrates. The harness sweep's census (11 canonical
  projects, 241 manifest roots, 0 errors) verified the
  mega repo's tooling reads every project's registry DB
  in place; the DBs and their `registry.json` exports
  stay in their owning projects.
- **Runner.** The six live configs ride the seed/example
  pattern into `pipeline/venue/config/`; runtime state
  (lease records, run records, detached outputs) was
  inventoried by count only and re-seeded deliberately,
  never copied blind. The auth-transient mirror is
  reference-only, permanently.
- **Attention.** The capture was existential: every
  registry attention owns lived only in the one untracked
  store (`var/data/state.json`). The store migrated
  verbatim as data; the pipeline registry gives those
  registries the seed/export form they never had
  (`pipeline/attention` carries the seeds). The captured
  store loads through the pinned code's own store path
  with every registry count identical raw vs loaded.

## Standing findings

1. **Credentials sit in working trees.** The scheduler's
   overlay held a raw connector token in a plaintext env
   file outside the hash-only registry. It was verified a
   redundant copy of the live token, read by nothing, and
   removed; no copy of the value exists in the capture.
   The class stands: credentials are inventoried by
   reference only, and a raw token in a tree is a defect
   wherever it is found.
2. **Record hygiene is the venue layer's.** The runner's
   run-record store carried records outside the three
   ruled terminal states (`complete | failed | orphaned`)
   and a small number of unparseable records at capture.
   The states are contract; the residue is the venue
   layer's to keep clean.
3. **External registrations are not in any repo.** The
   runner's reaper and notify hooks live in the runtime's
   hook system; the consolidation re-homes such
   registrations explicitly, because a capture of trees
   alone silently loses them.
