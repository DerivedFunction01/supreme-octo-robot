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
  (plan §11). From P2 onward every deploy writes its
  release-record entry (plan §6) — until then stage deploys
  are recorded by hand in `docs/`.
- **Host bridge binding seam:** the app-side server binds
  the host's privileged contracts at publish time
  (`definePrivilegedContracts` / `definePrivilegedHandlers`);
  a different host substitutes its own binding at that seam.
  The binding is an app-side deploy adapter over the
  loopback contract — never pipeline code.
- **Bridge-down ≠ server-down:** a bridge transport error
  is surfaced as a bridge error, distinct from any server
  state, never conflated (the scheduler viewer's raw-socket
  transport and its status-0 rule are the standing
  instance). A failed fetch keeps the last-good snapshot on
  screen, labeled with its age.
- **Read-only surfaces stay read-only:** ack, suspend, and
  admit live in the operator CLIs and chat, not in the
  shell (the scheduler viewer's standing rule, generalized).

## What each app keeps

Served shapes stay per-app: the scheduler app over pipeline
`/api/v1` shapes (frozen by the clause below), the
workbench app over work-record feeds (contract 03's
classification feed among them), the runner panel over the
venue layer's served portions, the attention app over its
`api/1` shapes. S8's backend half is the adapter set that
keeps every §2 payload identical; this contract governs
the shell they render in.

## The scheduler app's `/api/v1` views (SCH6 — the `/api/v1` half)

The view set at the pin (`server/api.py`; the scheduler
review's route inventory) is frozen as served:

- **`GET /api/v1/overview`** — `served_at`, `server_now`,
  server status / state error / registry errors, pid,
  uptime, last tick, running jobs, registry totals by kind
  and status, outbox depth by kind
  and aged count, 24 h totals (runs, failures, wakeups
  served, pings created), total expected wakes/day, the
  storage summary, and selected config values.
- **`GET /api/v1/jobs` and `GET /api/v1/jobs/<id>`** — the
  job view: id, kind, status, suspend reason,
  owner, cadence object with its human `cadence_label`,
  timezone, next due instant + seconds-to-due, the last run
  view or the agent activity view, 24 h run/activity
  counts, failure streak, expected wakes/day, report mode.
  The run view carries `ts`, `due`, `status`, `exit_code`,
  `label`, `matched_pattern`, `collapsed`, `error`,
  `stdout_tail`, `stderr_tail`; the agent activity view
  distinguishes pending / overdue past ack timeout /
  served / served · acked. Job detail adds title, timeout,
  ok exit codes, run/body/escalate_body, state paths, the
  full report block, classification, lifetime, and the
  recent-runs (50), recent-dues (50), and ping-history
  (20) windows. (Amendment 3, 2026-11-13: the pinned
  views' `migrated` field and migrated count in the
  overview, and job detail's `migrated_at` and
  `proof_pending`, do not exist in the target — the
  migration field family is dropped from the format,
  contract 14.) (Amendment 2026-11-13: the job view
  also carries the served operator / built-in
  classification, and detail adds the entry's config
  block on knob-bearing entries — see the amendment
  section at the end of this contract; schema:
  `schemas/job-view.schema.json`.)
- **`GET /api/v1/pings`** — each pending ping plus
  `age_secs` and `overdue`, oldest first.
- **`GET /api/v1/ledger?limit=<1..500, default 50>`** —
  `{served_at, events}`, each event reduced to `ts`,
  `kind`, `job_id`, and a server-computed human `detail`.

Every label in these views is server-computed — outcome
labels are centralized in the pipeline's `outcome_label()`
(`OK`, `Exit <n> · normal`, `Failed · exit <n>`,
`Timed out`, `Could not start`); the client derives
nothing beyond presentation and arithmetic over served
values (the pattern section above). S8's done-evidence is
the empty served-payload diff for these routes against
the pinned app.

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
mode. Stage D5 preserves the asymmetry rather than
unifying it away.

## Kit distribution (§10.4 binding)

The kit's home is the spec-driven starter (plan §1); this
repo consumes the kit as every other repo does and never
forks a private copy. Per the owner's ruling: **one
generator in the kit's home; the generated CSS ships as the
distribution and consumers take it checked-in.** The
consolidated repo is one repo with one `package.json` and
one frontend build — generation is a single build step the
backends never perform, so no per-stack generator exists
inside the superapp (the workbench review's per-stack
question is superseded by this ruling; see
`traceability.md`).

## Preserve clauses carried

ATT4 (presence semantics + the glance/Today asymmetry),
and SCH6's `/api/v1` half (the view set above). The shell
instances' remaining preserve items ride their app
contracts (traced in `traceability.md`).

## Findings from the frontend build (2026-11-13)

Recorded by the scheduler frontend lane against the frozen
view set; all dispositioned as S8 inputs (the live adapter's
reconciliation), none fabricated around in the mock:

- G1/G2: the storyboard requires run duration and
  run-detail prose; the frozen run view carries neither.
- G3: the storyboard's overview notice field has no
  counterpart in the frozen overview view.
- G4: the ledger's caller sub-line is unservable from the
  frozen four-field event reduction.
- G5: the storyboard's Pings Recent (status-post) rows
  exceed the frozen pending-only pings view; the mock does
  not fabricate them.
- G6: storyboard waiting order vs the contract's
  oldest-first — implemented per contract.
- G7: activity-view fields are unfrozen beyond the four
  states.
- G8 (the named reconciliation): this contract's read-only
  rule (ack, suspend, and admit live in the operator CLIs
  and chat, not in the shell) vs the mock app's in-shell
  action verbs (run-now, enable/disable, acknowledge).
  The mock exercises the verbs to demonstrate the flows;
  the live S8 shell honors the read-only rule, and which
  verbs, if any, graduate into the shell is decided at
  S8, not assumed by the mock.

## Amendment — served job classification + entry config (2026-11-13)

Owner rulings of 2026-11-13 (the grouped Jobs treatment
approved from the jobs/built-ins mockup, then the taxonomy
refinement the same hour). The classification is **served
data** — the client renders it and never derives it
(contract 06's rule applied to a new axis). Schema:
`schemas/job-view.schema.json`.

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
  when knob-bearing): no run-now, no enable/disable. The
  G8 reconciliation is unaffected — at S8 the verbs'
  graduation is decided for operator jobs; built-ins
  never carry them.

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

### The fleet as classified (26 entries)

- Operator (6): `memory-index-watchdog`,
  `paywatch-lane-watchdog`,
  `paywatch-daily-scheduler`,
  `paywatch-deferral-retries`,
  `weekly-gmail-otp-cleanup`,
  `weekly-gmail-stale-jobs-cleanup`.
- Built-in · family Venue (6, open in Runner): the
  `colab-*` fleet — `colab-extend-guard`,
  `colab-liveness-brisk-rocket-38`,
  `colab-liveness-cozy-pilot-61-r1794547171`,
  `colab-liveness-dawn-tower-93`,
  `colab-runner-transient-restore`, `colab-store-prune`.
- Built-in · family Arming (2, open in Workbench):
  `wb-progress-programme-a-t-01k8r0000000000000000000b1`,
  `wb-progress-programme-b-t-01k8r0000000000000000000b2`.
- Built-in · family Attention (1, open in Attention):
  `owner-attention-healthcheck`.
- Built-in · family Workbench (2, open in Workbench):
  `workbench-viewer-doctor`,
  `workbench-viewer-healthcheck`.
- Built-in · family Dispatch (2, open in Dispatch):
  `bridge-drain`, `bridge-wake`.
- Built-in · direct (7): `file-registry-check`,
  `flap-watch`, `local-test-watch`, `restart-reconcile`,
  `stale-mockup-cleanup`, `storage-watch`,
  `vm-restart-detector`.

`storage-watch` is a **reclassification** (owner,
2026-11-13): it sat with the operator jobs in the
mockup; it watches the machine, not client work, so it
is a direct built-in. Counts in the served seed:
6 operator (5 enabled — `paywatch-lane-watchdog` stands
suspended), 20 built-in (13 family, 7 direct).

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

Knob-bearing at this stage (values from the entries'
own evidence, not invented): `storage-watch` — the
home free-space tiers (low 50 GB, critical 45 GB; the
live `ops/storage_watch.py` constants, the owner's
2026-11-11 retune), with the declared constraint
critical < low; `memory-index-watchdog` — the topic
thresholds its held check script takes as parameters
(per-file cap 40960 bytes, per-topic set register
12800 bytes). Examined and carrying **no** config
block: `flap-watch` (neither its entry nor its script
states a probe-interval or denial-threshold parameter —
detection is per-arm canary verdicts; its only interval
is the entry cadence) and `bridge-drain` (its body takes
no batch or window knobs — it works the whole queue;
its only timing parameter is the entry's hourly
backstop cadence, already served as the cadence).

## S8 dispositions — the live adapter (2026-11-13)

Recorded by the S8 backend lane (scheduler app). The
adapter lives at `apps/scheduler/frontend/src/live/`
behind the unchanged `SchedulerApi` seam; the integration
entry selects it with `?adapter=live` (the mock remains
the default, for the demo persona). Every disposition
rests on the served-payload diff
(`apps/scheduler/frontend/tools/live/`): over a fixture
store seeded from the S1 capture — the 26-entry merged
registry in its moved form, 36 seeded ledger events, 5
seeded pings, a pinned engine clock — the pipeline
server's `/api/v1` payloads diff **empty** against the
pinned scheduler app's (pin `cf910ce`) except 105 paths,
every one a plan-amendment-3 removal (job view +
detail-embedded `migrated` ×52, detail `migrated_at`
×26, `proof_pending` ×26, the overview registry migrated
count ×1), and one volatile path (overview `pid`, an
environment fact). Zero undispositioned diffs.

- **G1/G2 — dropped on the live surface, not frozen.**
  No run duration or run-detail prose is served; the
  live adapter serves both fields null and the run rows
  render the served outcome label. The fields remain in
  the app types for the mock's demo persona. Remaining
  home if a live duration is ever wanted: the pipeline
  run record + api (a duration would be recorded at run
  completion) — not scheduled.
- **G3 — not frozen; dropped on the live surface.** The
  overview serves no notice; the live adapter serves
  null. The mock keeps its flap notice in demo mode.
- **G4 — closed; no serving gap as built.** The feed
  serves the stored event records with the detail string
  computed over them — identical on both servers,
  diff-verified, caller included where the writer
  recorded it — and the view as built renders the frozen
  four-field reduction (the detail string is the
  headline; no caller sub-line was built). If a caller
  sub-line is wanted later, the feed already carries the
  field: a view change, not a serving gap.
- **G5 — open; remaining home: pipeline api.** No route
  serves an acked/recent pings window (both ping routes
  are pending-only; acked records live only in the
  outbox store). The live adapter serves the Recent
  group an empty list — its honest empty state — and
  fabricates nothing. A window route is a pipeline
  addition when wanted.
- **G6 — closed (ruled in the finding itself).** The
  contract's oldest-first stands; the adapter serves
  the server's order verbatim.
- **G7 — closed by projection.** The pipeline serves its
  own activity projection (`{ts, due, state, label,
  tone, acked_at, collapsed}`); the adapter projects it
  into the app's form — state `acked` → `served_acked`
  (the other three pass), the label **verbatim** (labels
  are served, contract 06: the server's "Ping pending" /
  "Past ack timeout" supersede the mock's phrasings),
  `since` = the served ts, and `ping_id` joined from the
  served pending pings for the same job ("" when none —
  the field is carried for the app's form; no view
  renders it). Nothing else is derived client-side.
- **G8 — decided: no verb graduates at S8.** The
  read-only rule stands for `runNow`, `setJobEnabled`,
  and `ackPing`: the amendment above fences built-ins
  from the verbs expressly, and nothing in the contracts
  graduates them for operator jobs either; the live
  adapter refuses all three with contract 04's
  `outside_scope`, refused before anything is staged
  (in the app envelope the name reads as it must:
  outside the shell's scope). `saveConfig` **is** the
  graduated verb — the amendment designs it end-to-end
  for the app — but its pipeline half does not exist
  (below), so the live adapter refuses it `not_found`
  until served. The mock continues to exercise all four
  verbs against its fake store for the demo persona.
  (The outbox HTTP surface's `POST /pings/<id>/ack` is
  the operator CLI's route; the read-only rule governs
  the shell, not the route.)

Named extras dispositioned at S8 (not G-numbered):

- **Classification serving — open; remaining home:
  pipeline api.** The amendment's axis is not served by
  `/api/v1`: the job view carries no `audience` /
  `family` / `open_in`. Until the server serves it, both
  adapters carry the amendment's frozen fleet table as
  contract data
  (`apps/scheduler/frontend/src/contract-data.ts`);
  unlisted ids fall back to operator / null / null (the
  mock's existing fallback). When the pipeline serves
  the axis, the adapter drops the table and passes the
  served fields through.
- **Config-block serving — open; remaining home:
  pipeline entry form (contract 14) + api + the one
  writer path.** No live entry carries a config block,
  so the live adapter serves `config: null` on every
  detail and `saveConfig` refuses (G8). The mock serves
  the two evidence-backed blocks (`storage-watch`,
  `memory-index-watchdog`) in demo mode.
- **Unserved detail fields — open; remaining home:
  pipeline api projections.** `suspended_on`,
  `self_removal`, and the `catalog` block are absent
  from the served detail; the live adapter serves them
  null (honest absence). The underlying data exists in
  the entry form / stores; serving them is additive
  when wanted.
- **Ping-history form — conformed.** Job detail's
  ping-history window serves the server's event rows
  (`{ts, kind, ping_id, ping_kind, detail}`) — the
  pinned behavior; the app conformed its rendering to
  the rows, and the mock projects the same rows from
  its ledger. The storyboard's record-based history
  (per-ping summary / state / coalesced count) is not
  served by `/api/v1`; remaining home: pipeline api, if
  ever wanted.
- **Recent-dues window scope — noted; pinned behavior.**
  The served window carries `agent_due` records only;
  `skipped_overlap` dues are run records and surface in
  the Ledger view. The live adapter adds only the
  pending row from the served `next_due`, mirroring the
  mock.
- **Activity-state coverage — noted.** Over the real
  fleet only `bridge-drain` is agent-kind, so only the
  `pending` activity state is exercisable end-to-end
  over served data; the overdue / served / served_acked
  branches are the same single projection function,
  code-diff-identical between the pinned and moved
  servers.

## Pipeline serving — the S8 remainders land (2026-11-13)

The four items the dispositions above named as open with
their remaining home in the pipeline now serve from the
pipeline side (`pipeline/scheduling/server/`). The live
adapter has not been re-pointed yet — that is the
follow-on — so the app still carries/refuses as recorded
above; what changed is that every refusal now has a real
target.

- **Classification serving — served.** The amendment's
  frozen fleet table (26 entries) lives pipeline-side in
  `server/classification.py`, beside the registry it
  classifies, and `api.job_view` joins
  `audience` / `family` / `open_in` onto every job view
  (list and detail alike). Home reasoning: the axis is
  fleet taxonomy ruled at the fleet level — it is not
  per-entry authored data, so it does not ride the entry
  form (contract 14 carries no classification fields for
  it); the app's `contract-data.ts` was the shape
  reference, never the source. An id the table does not
  list falls back to operator / null / null, the
  contract's own documented fallback.
- **Config blocks + the guarded save — served.** The
  block rides the entry record as the amendment ruled,
  in map form (`config: {version, knobs: {<key>: {…}},
  constraints: {<name>: {…}}}`), because the registry's
  YAML subset has no lists of maps; `api.job_detail`
  projects it to the schema's array-form `configView`
  (`contracts/schemas/job-view.schema.json`), version
  stamp included. The stamp's home is the block's own
  `version` field. The registry validator now owns the
  block's shape (knob fields, type, range at rest,
  constraint references, constraints satisfied at rest).
  The two evidence-backed blocks are backfilled at
  version 1: `storage-watch` (home low/critical tiers,
  50/45 GB, with the critical-below-low `lt` constraint)
  and `memory-index-watchdog` (topic file cap 40960,
  per-topic allowance 12800 bytes). `flap-watch` and
  `bridge-drain` carry none, as the amendment examined.
  The catalog example for storage-watch carries the
  block too, so adoption renders it; `config` is
  drift-volatile beside `source` — its values and stamp
  move by design on every ledgered save. The save is
  `POST /api/v1/jobs/<id>/config` with body `{version,
  values, caller?}`, the one graduated verb the G8
  disposition foresaw: writer-validated (unknown knob,
  wrong type, fraction for an integer knob, or
  out-of-range refuses the whole save `bad_request`,
  entry byte-identical), constraint re-checked against
  the merged values, stale-stamp refusal as `no_match`
  (presented version ≠ the record's, or the entry file
  moved under the save — the platform writer's CAS
  discipline at this surface), unknown job `not_found`,
  knobless entry `bad_request`. An applied save rewrites
  only the entry's `config:` region (every other byte
  preserved) through the platform writer's staged write,
  bumps the stamp only when a value actually changed,
  and ledgers one `op` event per changed knob (`op:
  config`, with knob, label, old, new, unit). Refusals
  are never ledgered.
- **G5 — served.** `GET /api/v1/pings/recent` (optional
  `?limit`, default 20) serves the acked window: the
  most recently acked pings, newest ack first, as their
  outbox records (acked records carry `acked_at`). The
  window is built from the ledger's `ping_acked` events
  joined to the outbox store through its public `get` —
  the ledger is the only place ack order survives, since
  acked records leave `pending()` at ack time.
- **Detail projections — served.** `api.job_detail`'s
  detail block gains `suspended_on`, `self_removal`, and
  `catalog` from the entry record, null where the entry
  carries none (honest absence, never back-filled).
  `catalog` projects to the view axis only — `{origin,
  generality, use_case}`; parameters and setup are
  adoption machinery, not view data.
- **Fire-time read — named, not wired.** The record is
  the engine's fire-time source (entries rescan every
  tick, so a saved value governs the next fire), but no
  knob→script consumption seam exists yet: the executor's
  only env seam is `run.env_names` passthrough from the
  server's own environment, `ops/storage_watch.py`'s
  thresholds are compiled constants, and
  `ops/memory_watchdog_check.sh`'s
  `SCHEDULER_TOPIC_FILE_MAX_BYTES` /
  `SCHEDULER_TOPIC_PER_FILE_BYTES` parameters have no
  mapping from the record. Wiring a per-script seam is
  its own change, deliberately not invented here.

Evidence: the pipeline scheduling suite runs 278 green
(248 at the S8 baseline + 30 new: classification table
and serving, registry block validation, view projection,
the save's apply/refuse matrix incl. byte-identical
refusals, HTTP route round-trips, G5 window, detail
projections, and a landed-registry pin). `bin/sched
validate` reads 26 valid / 0 invalid and `catalog-drift`
0 problems (storage-watch adopted-and-current). The
app-side harness re-run: the served-payload diff against
the pin is the 105 dispositioned amendment-3 removals +
the one volatile pid + **260 additions, every one a path
the pinned server does not carry** — `audience` /
`family` / `open_in` ×52 (list + detail) and
`suspended_on` / `self_removal` / `catalog` / `config`
×26 in the detail blocks. The harness fixture home is
built from the S1 capture, whose entries carry no config
blocks, so fixture details serve `config: null`
honestly; the blocks themselves are pinned against the
landed registry by the pipeline suite. `check-live`
still reads 61/0 — the adapter's mapped output is
unchanged until the re-point; two of its checks ("G5:
listRecentPings is empty on live data (no acked-window
route exists)", "saveConfig refuses not_found until the
pipeline serves config blocks") now describe expired
premises and flip with the follow-on.

Follow-on (the adapter re-point, separately
commissioned): drop the `contract-data.ts` fleet table
for the served axis, wire `saveConfig` to the POST
route and `listRecentPings` to the recent route, stop
hardcoding the three detail nulls, extend the diff
tool's dispositioned set with the 260 amendment-ordered
additions, and catch contract 14's field table up with
the `config` field (documented meanwhile in
`pipeline/scheduling/jobs/README.md`).

## Fire-time seam — landed (2026-11-13)

The pipeline-serving section above closed with the
fire-time read "named, not wired"; this section lands
it and supersedes that bullet. The seam is one optional
field, declared beside the block schema:

- **Declaration.** A config knob may carry `env`: the
  name of the environment variable the fired script
  actually reads. The field is part of the block's
  schema of record (`pipeline/scheduling/server/
  registry.py`: validated as a variable name, beside the
  knob's other fields) and of its serving contract
  (`configblocks.view_of` serves the name beside the
  value; the guarded save's block rewrite preserves it).
  The value travels in the knob's own unit — the script
  owns the interpretation of its variable. The engine
  carries no per-job table: the mapping is data on the
  knob, not code per job.
- **Resolution at fire time.** The engine rescans the
  registry every tick, and the executor builds the fired
  process's environment from the entry as it stands at
  fire time (`registry.config_env`, applied over the
  inherited environment by `executor._build_env`): every
  knob declaring `env` sets that variable to its saved
  value. A config saved since the last fire therefore
  governs the next one — no restart, no other act. An
  entry with no block, or a block whose knobs declare no
  `env`, fires with exactly the environment it fired
  with before the seam existed.
- **The two wired consumers.** `storage-watch`'s knobs
  declare `STORAGE_WATCH_HOME_LOW_GB` /
  `STORAGE_WATCH_HOME_CRIT_GB`; `ops/storage_watch.py`
  now reads its home tiers from those variables when
  present (in GB) and falls back to its compiled
  constants (50 / 45 GB) when absent — byte-for-byte its
  previous behavior, labels included; its /tmp tiers are
  not knobs and do not move. `memory-index-watchdog`'s
  knobs declare `SCHEDULER_TOPIC_FILE_MAX_BYTES` /
  `SCHEDULER_TOPIC_PER_FILE_BYTES`; its check script
  already took exactly those as env parameters, so the
  record side is the whole wiring — the script is
  unchanged. The catalog example for storage-watch
  carries the same declarations (config stays
  drift-volatile beside source).

Evidence: the pipeline scheduling suite runs 294 green
(278 at the pipeline-serving landing + 16 new in
`tests/test_firetime_seam.py`): the declaration's
validation (bad variable name refused at load), the
landed blocks resolving to the scripts' exact variables,
the resolver's empty mapping for blockless and
env-less entries, `_build_env` identity for a no-block
entry and config-wins precedence over an inherited
variable, the save rewrite preserving `env` with the
new value resolving, the storage watch's tier helper
(absent → the constant, garbage → the constant), and
two behavioral proofs — a free-space drop that is
silent under the compiled tiers reports LOW under the
saved tiers the engine delivers (the verdict flips at
the saved threshold and names it), and a real engine
fire of the real `storage_watch.py` where a config
saved between two fires of one engine instance makes
the second fire report CRITICAL at the saved tier, no
restart anywhere. `bin/sched validate` reads 26 valid
/ 0 invalid; `catalog-drift` 0 problems,
storage-watch adopted-and-current.
