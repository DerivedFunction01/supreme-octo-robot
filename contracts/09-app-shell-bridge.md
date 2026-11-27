# 09 — App shell + bridge adapter

**Canonical owner:** the Workhorse Kit / app-shell contract
— kit-owned; each app owns its served shapes. (Plan §4.9;
presence asymmetry annexed from §9.4.)

**The contract in one line:** one shell pattern for all
four apps — repo source → runtime mirror → Library
artifact, over a host bridge binding seam — while every
app's served payload shapes stay its own.

## The pattern

- **Three trees, one truth:** repo source is canonical; the
  runtime mirror is a drift-guarded sync of it; the hosted
  artifact is published from the mirror. A stage is "live"
  only on a served check, not on a deploy script's say-so
  (plan §11). Every deploy writes its release-record entry
  (plan §6).
- **Host bridge binding seam:** the app-side server binds
  the host's privileged contracts at publish time
  (`definePrivilegedContracts` / `definePrivilegedHandlers`,
  in the artifact server's privileged module); a different
  host substitutes its own binding at that seam. The
  binding is an app-side deploy adapter over the loopback
  contract — never pipeline code.
- **Bridge-down ≠ server-down:** a bridge transport error
  is surfaced as a bridge error, distinct from any server
  state, never conflated (the scheduler viewer's raw-socket
  transport and its status-0 rule are the standing
  instance). A failed fetch keeps the last-good snapshot on
  screen, labeled with its age.
- **Read-only surfaces stay read-only:** ack, suspend, and
  admit live in the operator CLIs and chat, not in the
  shell. The one graduated shell verb is the guarded
  entry-config save (below).

## What each app keeps

Served shapes stay per-app: the scheduler app over pipeline
`/api/v1` shapes (frozen by the clause below), the
workbench app over work-record feeds (contract 03's
classification feed among them), the runner panel over the
venue layer's served portions, the attention app over its
`api/1` shapes. The scheduler live adapter
(`apps/scheduler/frontend/src/live/`) sits behind the
unchanged `SchedulerApi` seam; the integration entry
selects it with `?adapter=live` and the mock adapter
remains the default, for the demo persona.

## The scheduler app's `/api/v1` views (SCH6 — the `/api/v1` half)

The view set is served by
`pipeline/scheduling/server/serving/api.py` and routed by
`pipeline/scheduling/server/serving/http.py`:

- **`GET /api/v1/overview`** — `served_at`, `server_now`,
  server status / state error / registry errors, pid,
  uptime, last tick, running jobs, registry totals by kind
  and status, outbox depth by kind and aged count, 24 h
  totals (runs, failures, wakeups served, pings created),
  total expected wakes/day, the storage summary, and
  selected config values. The registry block also carries
  a `migrated` count equal to the registry total: the
  migration field family does not exist on entries
  (contract 14), so every entry in the store is an admitted
  entry and the count is the total.
- **`GET /api/v1/jobs` and `GET /api/v1/jobs/<id>`** — the
  job view: id, kind, status, suspend reason, owner,
  cadence object with its human `cadence_label`, timezone,
  next due instant + seconds-to-due, the last run view or
  the agent activity view, 24 h run/activity counts,
  failure streak, expected wakes/day, `report_when`, and
  the served classification (`audience` / `family` /
  `open_in`, below). The run view carries `ts`, `due`,
  `status`, `exit_code`, `label`, `matched_pattern`,
  `collapsed`, `error`, `stdout_tail`, `stderr_tail`; the
  agent activity view distinguishes pending / overdue past
  ack timeout / served / served · acked. Job detail adds
  title, timeout, ok exit codes, run/body/escalate_body,
  state paths, the full report block, classification,
  lifetime, `suspended_on`, `self_removal`, the `catalog`
  block projected to `{origin, generality, use_case}`, the
  entry's config view (below), and the recent-runs (50),
  recent-dues (50), and ping-history (20) windows. The job
  view carries no `migrated` field and detail carries no
  `migrated_at` or `proof_pending` — the migration field
  family does not exist in this format (contract 14).
  Schema: `schemas/job-view.schema.json`.
- **`GET /api/v1/pings`** — each pending ping plus
  `age_secs` and `overdue`, oldest first.
- **`GET /api/v1/pings/recent`** — the acked window
  (optional `?limit`, default 20): the most recently acked
  pings, newest ack first, as their outbox records. The
  window is built from the ledger's `ping_acked` events
  joined to the outbox store through its public `get` —
  the ledger is the only place ack order survives, since
  acked records leave `pending()` at ack time.
- **`GET /api/v1/ledger?limit=<1..500, default 50>`** —
  `{served_at, events}`, each event reduced to `ts`,
  `kind`, `job_id`, and a server-computed human `detail`.
- **`POST /api/v1/jobs/<id>/config`** — the one write on
  `/api/v1`: the guarded config save (below).

Every label in these views is server-computed — outcome
labels are centralized in the pipeline's `outcome_label()`
(`OK`, `Exit <n> · normal`, `Failed · exit <n>`,
`Timed out`, `Could not start`); the client derives
nothing beyond presentation and arithmetic over served
values.

Live-surface gaps, served honestly rather than filled:
the run view serves no duration or run-detail prose (the
live adapter serves both fields null and the run rows
render the served outcome label), and the overview serves
no notice field (the live adapter serves null). The
activity view is the pipeline's own projection (`{ts, due,
state, label, tone, acked_at, collapsed}`); the adapter
projects it into the app's form — state `acked` →
`served_acked`, the label verbatim, `since` = the served
ts, and `ping_id` joined from the served pending pings for
the same job ("" when none). The recent-dues window
carries `agent_due` records only; `skipped_overlap` dues
are run records and surface in the Ledger view.

## Presence — the asymmetry is contractual (ATT4, §9.4)

One presence model (schema:
`schemas/attention-presence.schema.json`; fixture:
`fixtures/attention-presence.json`), two consumers — the
launcher widget and the attention app. Modes active /
focus / away, with expectation text; expiry resolves **at
read time**. The **glance is presence-filtered** (needs-
decision dots only when active, breakthrough listed when
away, next-due withheld when away); **the decision queue
never is** — every Today band renders in every presence
mode. The asymmetry is preserved, not unified away.

## Kit distribution (§10.4 binding)

The kit's home is the spec-driven starter (plan §1); this
repo consumes the kit as every other repo does and never
forks a private copy. Per the owner's ruling: **one
generator in the kit's home; the generated CSS ships as the
distribution and consumers take it checked-in.** The
consolidated repo is one repo with one `package.json` and
one frontend build — generation is a single build step the
backends never perform, so no per-stack generator exists
inside the superapp (see `traceability.md`).

## Preserve clauses carried

ATT4 (presence semantics + the glance/Today asymmetry),
and SCH6's `/api/v1` half (the view set above). The shell
instances' remaining preserve items ride their app
contracts (traced in `traceability.md`).

## Served job classification + entry config

The classification is **served data** — the client renders
it and never derives it (contract 06's rule applied to a
new axis). Schema: `schemas/job-view.schema.json`. The
axis is served by `pipeline/scheduling/server/serving/
classification.py`, beside the registry it classifies:
fleet taxonomy ruled at the fleet level, not per-entry
authored data, so it does not ride the entry form
(contract 14 carries no classification fields for it). An
id the table does not list falls back to operator / null /
null.

### The classification axis

Every job view carries `audience`:

- **`operator`** — the operator's own jobs. The Jobs view
  renders them as full rows in the "Yours" group; the
  Overview's Status counts, its recent-jobs group, and
  the shell's Jobs badge count operator jobs only.
- **`builtin`** — the system's own machinery, rendered in
  the Jobs view's Built-in group as compact rows, and in
  the Overview as one summary row (the running count).
  A built-in's detail is **read-only** (status, last run,
  latest outcome, 24 h runs/failures, its config block
  when knob-bearing): no run-now, no enable/disable.

Built-ins split in two:

- **Family built-ins** serve `family`
  (`venue | arming | attention | workbench | dispatch`)
  and `open_in` (`runner | workbench | attention |
  dispatch`): they live under an app or pipeline service,
  their rows carry the family tag, and their detail
  carries the owning-service block and the "Open in"
  row, which posts the shell-bridge navigation intent
  (`{type: "workhorse:open", app, job_id}` to the parent
  shell — the `workhorse:*` postMessage convention the
  embedded apps already use).
- **Direct built-ins** serve `family: null` and
  `open_in: null`: they are the app's own machinery, the
  group placement is the whole statement — no family tag
  on the row, no "Open in" row on the detail.

### The fleet as classified

The table in `classification.py` (23 entries):

- Operator (3): `memory-index-watchdog`,
  `weekly-gmail-otp-cleanup`,
  `weekly-gmail-stale-jobs-cleanup`.
- Built-in · family Venue (7, open in Runner):
  `venue-extend-guard`, `venue-liveness-brisk-rocket-38`,
  `venue-liveness-cozy-pilot-61-r1794547171`,
  `venue-liveness-dawn-tower-93`,
  `colab-runner-transient-restore`, `colab-store-prune`,
  `venue-healthcheck`.
- Built-in · family Workbench (2, open in Workbench):
  `workbench-healthcheck`, `workbench-viewer-doctor`.
- Built-in · family Dispatch (2, open in Dispatch):
  `bridge-drain`, `bridge-wake`.
- Built-in · direct (9): `card-watch`,
  `file-registry-check`, `flap-watch`, `local-test-watch`,
  `restart-reconcile`, `stale-mockup-cleanup`,
  `storage-watch`, `vm-restart-detector`,
  `workhorse-healthcheck`.

Entries in the registry that the table does not list —
for example the pay-monitor and worktree-trim entries —
serve the fallback: operator / null / null.

### Entry config — knob-bearing entries expose their knobs

An entry whose executable takes real knobs carries a
**config block** in its entry form (schema
`job-view.schema.json` `$defs/configBlock`): knob
descriptors — key, label, type (`integer | number`),
unit, current value, allowed range — plus any declared
cross-knob constraints. Job detail serves the block
with the store's version stamp (`$defs/configView`);
an entry with no real knobs serves `config: null` and
renders no config form — honest absence, never an
empty form.

The block rides the entry record in map form (`config:
{version, knobs: {<key>: {…}}, constraints: {<name>:
{…}}}`), because the registry's YAML subset has no lists
of maps; `api.job_detail` projects it to the schema's
array-form `configView`, version stamp included. The
stamp's home is the block's own `version` field. The
registry validator owns the block's shape (knob fields,
type, range at rest, constraint references, constraints
satisfied at rest).

Semantics (the catalog pattern with no export step):

- The store is the source: the block rides the entry
  record; edits write back through the one writer path;
  the engine reads the values **at fire time** from the
  same record.
- A save presents the version it loaded. A stale save
  (the store's version has moved) is refused with
  contract 04's `no_match` and nothing is applied.
- The writer validates type, range, and the block's
  declared constraints **before** applying: a violation
  is refused whole (`bad_request`) — never half-applied,
  never ledgered.
- Every applied knob change appends one ledger event
  (contract 05): kind `op`, `op: "config"`, the entry,
  the knob, old → new — visible in the Ledger view like
  every other op.

The save is `POST /api/v1/jobs/<id>/config` with body
`{version, values, caller?}`: writer-validated (unknown
knob, wrong type, fraction for an integer knob, or
out-of-range refuses the whole save `bad_request`, entry
byte-identical), constraint re-checked against the merged
values, stale-stamp refusal as `no_match` (presented
version ≠ the record's, or the entry file moved under
the save — the platform writer's CAS discipline at this
surface), unknown job `not_found`, knobless entry
`bad_request`. An applied save rewrites only the entry's
`config:` region (every other byte preserved) through
the platform writer's staged write, bumps the stamp only
when a value actually changed, and ledgers one `op`
event per changed knob (`op: config`, with knob, label,
old, new, unit). Refusals are never ledgered. The live
adapter wires `saveConfig` to this route; `runNow`,
`setJobEnabled`, and `ackPing` refuse in the live adapter
under the read-only rule — no verb beyond the config save
is graduated. (The outbox HTTP surface's
`POST /pings/<id>/ack` is the operator CLI's route; the
read-only rule governs the shell, not the route.)

Knob-bearing entries: `storage-watch` — the home
free-space tiers (low 50 GB, critical 45 GB, with the
declared constraint critical < low) — and
`memory-index-watchdog` — the topic thresholds its check
script takes as parameters (per-file cap 40960 bytes,
per-topic set register 12800 bytes). The catalog example
for storage-watch carries the block too, so adoption
renders it; `config` is drift-volatile beside `source` —
its values and stamp move by design on every ledgered
save. Examined and carrying **no** config block:
`flap-watch` (neither its entry nor its script states a
probe-interval or denial-threshold parameter — detection
is per-arm canary verdicts; its only interval is the
entry cadence) and `bridge-drain` (its body takes no
batch or window knobs — it works the whole queue; its
only timing parameter is the entry's hourly backstop
cadence, already served as the cadence).

### Fire-time seam

A config knob may carry `env`: the name of the
environment variable the fired script actually reads.
The field is part of the block's schema of record
(`pipeline/scheduling/server/registry.py`: validated as a
variable name, beside the knob's other fields) and of its
serving contract (`configblocks.view_of` serves the name
beside the value; the guarded save's block rewrite
preserves it). The value travels in the knob's own unit —
the script owns the interpretation of its variable. The
engine carries no per-job table: the mapping is data on
the knob, not code per job.

The engine rescans the registry every tick, and the
executor builds the fired process's environment from the
entry as it stands at fire time (`registry.config_env`,
applied over the inherited environment by
`executor._build_env`): every knob declaring `env` sets
that variable to its saved value. A config saved since
the last fire therefore governs the next one — no
restart, no other act. An entry with no block, or a block
whose knobs declare no `env`, fires with exactly the
environment it fired with before the seam existed.

The two wired consumers: `storage-watch`'s knobs declare
`STORAGE_WATCH_HOME_LOW_GB` / `STORAGE_WATCH_HOME_CRIT_GB`;
`pipeline/scheduling/ops/watches/storage_watch.py` reads
its home tiers from those variables when present (in GB)
and falls back to its compiled constants (50 / 45 GB)
when absent — its previous behavior, labels included; its
/tmp tiers are not knobs and do not move.
`memory-index-watchdog`'s knobs declare
`SCHEDULER_TOPIC_FILE_MAX_BYTES` /
`SCHEDULER_TOPIC_PER_FILE_BYTES`; its check script
(`pipeline/scheduling/ops/watches/memory_watchdog_check.sh`)
takes exactly those as env parameters, so the record side
is the whole wiring — the script is unchanged. The
catalog example for storage-watch carries the same
declarations (config stays drift-volatile beside source).
