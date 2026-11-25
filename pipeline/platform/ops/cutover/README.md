# The cutover — topology and state of record

The S11 cutover consolidated the four original repos
(scheduler, workbench, attention, venue runner) into
this mega repo. It was executed as a freeze: the
originals halted, their state carried by the drivers
in this directory, and the consolidated serving
raised on the carried state. The drivers stand here
as the cutover's kit, with `freeze_record.example.json`
as the freeze record's shape and `preflight.py` as its
reader. This file states the topology and state the
cutover established — the standing facts the
consolidated tree runs under.

## Topology

- **Serving is the repo-root `run.py`** over the one
  platform serving core (`pipeline/platform/serving.py`):
  every pipeline CLI links in-process as a subcommand.
  Process boundaries follow coupling (owner ruling):
  three serving processes, one per unit —
  `serve` mounts the coupled scheduler + attention
  backends (ports 8796 / 8797) under
  `workhorse.service`; `serve-workbench` mounts the
  workbench (8792) under `workbench.service`;
  `serve-venue` mounts the lease panel (8793) under
  `venue.service`. Unit templates and their watchdog
  timers stand in `pipeline/platform/ops/`
  (`units-spec.json` is the render set); keeper and
  watchdog re-pointing names these units.
- **Two successors own the surfaces.** One frontend
  handler and one backend handler, each succeeding all
  four originals in its layer; the `@workhorse` digest
  route points at them. The four original threads are
  retired.
- **Card-watch owns permission-card watching** (OI-1):
  the mega card-watch owner holds it; no interim
  ownership exists.
- **The scheduler's owning seat is main** (OI-4): the
  scheduler workhorse has no separate live owning
  thread; its operation and verification run under
  main.

## State the cutover carried

- **Ledger and outbox**: the original scheduler's
  ledger was exported at the quiesce (SHA-256 + count),
  imported into the mega store proven empty, and
  re-export verified hash-equal; the bridge state and
  outbox carried with per-file hashes. The dispatch
  substrate (`pipeline/dispatch/`) is their home.
- **Registry**: the live scheduler registry was
  assembled into the mega registry by
  `assemble_registry.py` — past-migration provenance
  keys stripped under `--strip-provenance` (the
  pre-assembly snapshot preserves the values), every
  anchored argv target verified to exist, entry-
  referenced files that lived only in the original
  home provisioned into the mega scheduling home as
  untracked instance data and recorded per file in the
  assembly report. The two per-service healthcheck
  entries were replaced at the assembly by the one
  `workhorse-healthcheck` entry, covered by the
  platform ladder (`pipeline/platform/ops/healthcheck.py`
  + `watchdog.sh`).
- **Attention store**: migrated census-identical
  before and after on every carried key (handlers,
  items, sends, armed rows, programmes), loading
  through the mega
  `AttentionStateStore`; the programme declaration's
  locations re-based to the mega repo in the same act.
- **Work-record store**: migrated by
  `migrate_workrecord.py` — registry DB SHA-256 equal
  after copy, export entry counts equal, the migrated
  DB reading through the mega harness.
- **Todo slug rename**: every armed project's legacy-id
  todos were renamed to their title-derived slugs by
  the naming lane's driver (`lib.writes.todo_rename`,
  the `wb todo migrate-names` form): `legacy_id:` stored
  on each record as data only, corpus mentions
  rewritten, the scheduler entry and attention armed
  row deleted under the old name and re-created under
  the slug by the writers' own sync functions. History
  was not rewritten: historical legacy mentions in the
  attention store stand as written and join through
  `legacy_id`. One armed record was dispositioned in
  advance: the steampowernj programme todo (bundle
  `2026-11-12-steampowernj-programme`; legacy id
  `t-01M7860FNPKG0BN2RW0SCB9RWZ`) whose record is
  missing `created` — it renamed as-is, proven safe,
  and its `created` repair is a post-cutover act owned
  by the successor backend handler.
- **Venue state**: `var/`, run records, and the live
  configs (callers, lease, repos, notify-routes,
  transient, denylist) carried by `migrate_venue.py`,
  with the §10.3 binding stamp run on the target copy —
  legacy records stamped `venue: colab` once; no
  read-time default exists.
- **Live config and tokens**: the mega scheduling
  home's config was provisioned from the example with
  the carried owners/drain values merged
  (`provision_config.py`); caller tokens were minted
  by `mint_tokens.py` (the acting caller's first,
  server down; the rest against the standalone server
  whose health read status ok with `registry_count`
  equal to the assembled count — the degraded-carry
  check: a wrong-shaped carried state file degrades a
  raised server to a 200 with a non-ok status and an
  empty registry, and that read is a failed carry).
  Token material lands in client homes at 0600 and
  appears in no driver output.

## Standing facts the freeze established

- **Single-writer**: one engine against one
  registry/state at a time; the originals' services
  stay stopped.
- **The push was a cutover act**: the remade history
  pushed to origin on the generic remake gate passing
  (full-history scan at zero hits + the composed gate
  green on the remade history), the Library artifact
  republished from the remade tree first so the
  published surface hash-matches it.
- **Keepers re-armed at the mega homes**: the keeper
  hooks (scheduler keeper, lease reaper, lease notify,
  workbench outbox watcher) point at the consolidated
  homes and the three units; the gap-closure sweep's
  body carries mega discovery.
