# Review — owner-attention (superapp big-bang consolidation)

Findings first:

1. **The whole product is one process over one JSON dict.**
   `backend/apps/server.py` runs a stdlib `ThreadingHTTPServer`
   (port 8797) whose every request and both background loops
   load → mutate → save a single state dict
   (`backend/infra/store.py`: `JsonFileStore`, atomic `.tmp` +
   rename; `MemoryStore` seeded from demo data when
   `ATTENTION_DATA` is unset). There are no internal served
   shapes: the evaluator, the digest builder, the dispatch
   consumer, and the Today builder all read and write the same
   dict under one lock. The pipeline/app split the plan draws
   (§1) is real only at the `api/1` HTTP seam — consolidation
   must *introduce* the internal seams, not find them.
2. **Every registry attention owns is runtime state in that
   one untracked file.** Handlers, programmes, rules,
   templates, status codes, wait classes, item kinds, action
   rules — all live in `var/data/state.json` (gitignored with
   all of `var/`), written through the API
   (`backend/services/writes.py`), seeded from code defaults
   (`backend/domain/attention.py`) plus store `backfill()`.
   At inspection the live store carried 10 handlers, 3
   programme declarations, 39 sends, 52 items. There is no
   tracked live registry, no file form, and no seed/example
   for any of them; `backend/infra/sample_data.py` is a demo
   seed, not a backup. A transplant that moves code without
   this file moves an empty product.
3. **The evaluator is three things on three clocks, not
   one.** The staffing measure derives at Digest assembly
   (request time, `backend/services/staffing.py` +
   `staffing_rows.py`); continuation dispatch acts on the
   60-second tick (`backend/services/continuation.py`); its
   inputs are collected on a slow loop
   (`server.py:_capacity_loop`): panel capacity, worktree
   presence, lane-record checkpoints, programme contracts.
   Its five inputs — armed rows, status posts, runner run
   records, panel capacity, lane record files — come from
   four repos' territory.
4. **Dispatch is a ledger with four minters and one
   consumer, and the consumer's ordering is load-bearing.**
   Sends are minted by the wait-rule engine, owner verbs,
   handler actions, and the continuation pass — all through
   `engine.record_send` into the one ledger. The in-service
   consumer (`dispatch_consumer.py`) *settles* outstanding
   bridge records before claiming new ones, acks only on
   the bridge fulfillment's `submission_message_id`, and
   stamps a suppressed send's late fulfillment as fact
   rather than resurrecting it. The suppress verb the
   earlier gap named **exists in the tree** (route, CLI verb,
   and internal uses).
5. **From this side, the runner contact is two read seams,
   not attribution only.** The evaluator reads the runner's
   detached run records straight off its filesystem
   (`backend/infra/run_records.py`, default
   `../colab-runner/results/detached`) and the panel's
   served state (`backend/infra/panel_client.py`,
   `/api/state/records|specs`, port 8793). The join between
   run-record `caller` strings and attention topics is a
   prefix-naming convention (`staffing._attribute`), not a
   shared registry — exactly the seam §4.1 exists to close.

## 1. Verification

- `git rev-parse HEAD` =
  `24ae5bc245b1eeeef32284603bfe3d14931a9fa8` — equal to the
  pin. Branch `main`.
- `git status --porcelain` is empty: the tree is clean.
  (`var/` is gitignored wholesale, so the live state below
  is overlay by construction, not dirt.)
- Read-only throughout: file reads, `git log`, grep, and
  one structural probe of the live state file (counts and
  key names only). No checkout, no tests, no server started.

## 2. Anatomy

- **Entry point.** `python -m backend.apps.server`
  (stdlib only, layers apps → services → infra/domain →
  foundation per `AGENTS.md`). Every request runs under one
  lock shared with the tick, and begins by evaluating waits
  and action rules before routing (`server.py:145-153`).
  Routes (`api/1`): reads `/health`, `/api/v1/glance`,
  `/api/v1/today`, `/api/v1/digest`, `/api/v1/handlers/<h>`,
  `/api/v1/registries`, `/api/v1/programmes`,
  `/api/v1/sends`, `/api/v1/sends/undispatched`,
  `/api/v1/rules`; writes for presence, item/handler
  actions, sends claim/ack/**suppress**, vocab registries,
  rules, handlers, programmes; agent seam
  `/api/v1/agent/{items,items/<id>/resolve,status,waits,
  dispatch-failures,verifications}`. The `connector/cli.py`
  CLI (post item/status/wait, poll, resolve, dispatch
  list/claim/ack/fail/suppress, verify status) drives the
  same seam.
- **The tick** (`server.py:_tick_loop`, 60 s): presence
  expiry flip, tail promotion
  (`ingest.promote_tail_items`), armed-row ingest
  (`programmes.ingest_armed`), push-fact clearing
  (`facts.clear_resolved`), wait evaluation, action rules,
  continuation pass, dispatch-consumer pass; saves when
  anything moved. A failed tick never kills the serve.
- **The slow loop** (`server.py:_capacity_loop`, every
  max(60 s, `capacity_collect_minutes` = 5 min)): capacity
  collection (`staffing.collect_capacity` → panel +
  run records), worktree snapshot (`worktrees.collect`),
  lane-record snapshot (`records.collect`), programme
  contract sync (`contracts.sync`).
- **State stores** — all keys of the one dict
  (`store.empty_state`): `handlers`, `programmes`
  (post-backfill; not in `empty_state`), `items`, `waits`,
  `sends`, `presence` + `presence_seen`, `handler_status`,
  `armed_rows`, `rules`, `action_rules`, `status_codes`,
  `fields`, `wait_classes`, `templates`, `item_kinds`,
  `muted`, `allowlist`, `action_log`, `owner_actions`,
  `tap_counts`, `pings`, `owner_directed`,
  `dispatch_failures`, `verifications`, `staffing_rows`
  (escalation memory), `continuation`, `idle_watch`,
  `capacity_snapshot`/`capacity_error`,
  `worktree_snapshot`, `record_snapshot`, `source_health`.
  File-side stores: `var/armed/*.json` (the workbench drop,
  §6), `var/connector/bridge-token` (the bridge caller
  token, read per call, never stored in state).
- **Served shapes.** `model.build_glance`: presence view,
  clock + next digest window, `decision_count` (owner-
  actionable live items), per-handler needs-decision dots
  (active mode only), next due (suppressed when away),
  breakthrough items (listed when away). `model.build_today`:
  five bands in fixed order — breakthrough, due_today,
  needs_decision, waiting, fyi — **every band in every
  presence mode** (the queue is never presence-filtered),
  plus a sixth band, "Decided — awaiting fulfillment",
  when decided items stand. `digest.build_digest`:
  per-status-kind sections (owner-placed kinds only),
  programme cards (slug, label, rule text, staffing band,
  cadence, escalation, handles), owner-blocked stalls, the
  staffing object, topic-collapsed lane states, and the
  parked-plans band pulled live from the workbench.
  `facts.derive_push_facts` measures every open push item
  against its repo (HEAD, ahead/behind vs `origin/main`,
  dirty) at serve time and rewrites superseded titles from
  the measurement.
- **Deploy plumbing.** `deploy/DEPLOY.md` contracts:
  build (`init_venv.py`) → publish (copy/sync backend +
  frontend, drift-stated) → verify in target (`GET
  /health`); deploy carries no gate by ruling.
  `ops/install-unit.sh` renders the systemd unit from the
  settings seam; `ops/serve.sh` starts/stops (delegating
  to systemctl when the unit exists); `ops/watchdog.sh` +
  `ops/stackdump.py` are the survival kit the scheduler
  review saw referenced as external contracts. Frontend
  is static, served by the same process (`frontend/
  app.js`, no build step). Gate: `python3 check.py`
  (ruff, policy scanners, pytest) per `AGENTS.md`.
- **Settings seam.** Only `backend/foundation/settings.py`
  reads the environment (`ATTENTION_*`); defaults let a
  fresh clone run. Sibling addresses are settings:
  `wb_url` :8792, `bridge_url` :8796, `panel_url` :8793,
  `run_records_dir` pointing into the runner repo,
  `armed_dir` = own `var/armed`.

## 3. The decision machinery

- **Verdict at the tap** (`actions.apply_item_action`,
  spec §1.13): the verb is validated against the *served*
  verb set for that item (`model.verbs_for` — derived from
  kind, provenance, wait class, state; hard-stop classes
  never offer `approve_rule`), the decision is recorded on
  the item (`{verb, at, option_id, note, send_id}`) and,
  through `wait_id`, on the wait (`owner_approved` /
  `owner_denied`, `decided_at`, `owner_note`), and only
  then is the send written. Delivery never gates the
  decision. Replays are guarded twice: an
  `idempotency_key` short-circuits, and a repeated tap on
  the standing decision records and sends nothing
  (2026-11-12 amendment). Changing a *fulfilled* decision
  is refused — it is a new item.
- **Queue semantics.** A decision verb sets
  `triage = "done"`: the card leaves the open queue into
  the Today band "Decided — awaiting fulfillment"
  (`fulfillment.decided_items`: states queued / sent /
  recorded). Fulfillment is derived, never assumed
  (`fulfillment.derive`): for send-backed decisions, from
  the send ledger (delivered → fulfilled; a recorded
  dispatch failure → failed); for `push_needed`, from the
  scripted fact measurement (repo ahead = 0 → fulfilled;
  repo gone → failed). Past
  `fulfillment_stall_minutes` (120) unfulfilled reads
  **stalled**. Failed and stalled items *return to the
  decision queue* (`fulfillment.returned_items`) with
  `decision_history` carrying each prior verdict and its
  outcome — the history rides on the item's face
  (`model.item_view`).
- **The wait side.** Waits are decided by the declarative
  engine (`engine.evaluate_waits`): hard-stop classes are
  always surfaced, never auto-applied; rules match over
  poster fields plus server-derived values (age, repeat
  count, presence, handler status); dedupe keys on a fact
  hash of the wait's content. A surfaced wait becomes
  exactly one owner item (§1.2 de-duplication). A terminal
  status post from the owning thread resolves its pending
  waits — an ack alone never does (`ingest.post_status`).
- **Reply routing (Decision 1, in code).** The `reply`
  verb sends the verdict template to the item's own
  handle, and — unless the handle is `main` — a second
  send, template `reply`, target `main`, rule
  `owner:reply-copy`: direct to the owning thread, main
  copied (`actions.py`, reply branch). All sends,
  including owner verbs, go through the one ledger
  (`engine.record_send`).
- **Presence.** `state["presence"]` = `{mode, expires_at,
  expectation}`, modes active / focus / away. Expiry
  resolves **at read time** (`model.effective_mode`: an
  expired non-active mode serves as `active`) and the tick
  also flips it in state. The glance is presence-shaped
  (dots only when active, breakthrough listed when away,
  next-due withheld when away); Today is not filtered at
  all (§2). Rule scope reads presence (`focus_scope =
  "away"`: focus counts as away for auto-apply scope).
- **Repetition proposes rules.** Counted taps per
  handler + class + verb surface a `rule_proposal` item
  at the threshold; `rule_it` / make-rule promote to
  action rules — shadow for every verb except wait
  approvals, which go active and are refused outright
  for hard-stop classes.

## 4. Evaluation — the staffing/stall evaluator

- **What it measures.** `staffing.build_staffing` derives
  rows at Digest assembly from: the capacity snapshot
  (live High-RAM sessions from the panel, running runs
  per session from run records, idle-since per session),
  run-record caller attribution (longest-prefix match of
  `caller` against topic/handle names; child workers =
  running callers that are not the topic or its lane
  handles), status posts (`handler_status`), armed rows,
  worktree and record snapshots, owner-waiting
  declarations, and undelivered supervision sends.
- **Row classes** (`staffing_rows.KIND_LABELS`):
  understaffed (< 2 workers or < 2 sessions used, while
  ≥ 2 live sessions; zero-worker and coordinator-without-
  children called out), fleet_idle, record_gap,
  idle_unlanded, no_successor, phantom_stop (a
  BLOCKED-OWNER claim citing no owner message — priced
  with frozen minutes, addressed to main),
  blocked_uncited, blocked_unverified (cited basis main
  has not stamped via `verifications` past one check
  cycle), unrouted_defect (a workhorse defect with no
  routing on its post), serial_plan (declared independent
  steps outnumber fielded lanes — measured at adoption),
  owner_waiting / owner_waiting_unanswered (past one
  check cycle), armed_unposted, unlanded_claim,
  unarmed_work, steer_undeliverable.
- **Cadence rule.** The cadence is per-programme
  (`cadence_minutes` on the declaration) else the 15-minute
  service default. Two missed intervals is the recurring
  bound: an armed row older than 2× cadence with no status
  post naming its todo is `armed_unposted`
  (`staffing_rows._armed_rows`); a lane record whose
  latest conforming `progress-checkpoint:` line is older
  than 2× cadence is a `record_gap` (`_record_rows`); the
  idle detector fires when no signal (checkpoint, worktree,
  post, armed status) has moved for two intervals
  (`continuation._idle_triggers`).
- **Only a measure clears.** Rows are re-derived from
  current evidence at every assembly; there is no ack
  path in the evaluator at all. The only memory is
  `state["staffing_rows"]` — first-seen stamps used for
  stall duration and escalation timing; a row the measure
  no longer raises disappears and its stamp is deleted.
- **Escalation.** A row escalates to `main` when its age
  passes the programme's `escalation_hours` (default 1 h);
  phantom_stop and steer_undeliverable escalate
  immediately. Owner-waiting rows are addressed to main
  from the first cycle past cadence.
- **Worktree presence.** `worktrees.collect` measures
  every declared programme's `worktree_roots` (git tip,
  dirty, landed = HEAD is ancestor of main). A terminal
  claim (DONE/CLOSED) beside unlanded trees is an
  `unlanded_claim` row — the claim is reported against
  the tree, not taken; standing trees with no armed row
  and no live lane are `unarmed_work`.
- **Continuation (the evaluator acting).**
  `continuation.run_pass` on the tick converts trigger
  rows (record_gap, unarmed_work, no_successor,
  blocked_uncited, blocked_unverified), stalled
  fulfillments, and idle programmes into `continuation`
  sends through the ledger, repeating on the programme's
  cadence until the measure clears; a prior undelivered
  ping blocks a twin mint; void blocked claims also
  raise defect items. Pings to retired handlers are
  never minted.
- **What it consumes.** Armed rows (§6), status posts,
  programme declarations, panel capacity + specs,
  run records, worktree/record snapshots, the send
  ledger and failure records, workbench derivations
  (todo counts and plan-modified stamps, via
  `digest._wb_topics` + `derive.derive_for`).

## 5. Dispatch — the in-service dispatch consumer

- **The ledger.** One `sends` list in state. A send:
  `{id (sNNNN), at, rule_id, wait_id, handle, target,
  template, version, attempt, presence, text, fact_hash,
  mode (active|shadow), outcome, dispatch{…}}`. Shadow
  sends are never dispatchable. Owner verbs, rule posts,
  continuation pings, and handler actions all mint here
  and nowhere else.
- **Lifecycle** (`backend/services/dispatch.py`):
  undispatched → claimed (one attributed consumer,
  15-minute lease from `dispatch_claim_minutes`,
  attempts incremented; expiry applied **at read time**,
  no sweeper) → delivered, only via `ack` by the claiming
  consumer before expiry **carrying the chat surface's
  reference** (`delivery_ref`). Routes and CLI both expose
  claim / ack / **suppress**.
- **The suppress verb is present.** `dispatch.suppress`
  (route `POST /api/v1/sends/<id>/suppress`, CLI
  `dispatch suppress`): retires a send to terminal
  not-dispatchable with a mandatory reason on the record;
  a delivered send cannot be suppressed. The consumer
  itself suppresses on bridge-retired records and on
  attempts exhausted.
- **Target resolution.** At mint, `engine` resolves the
  target: template audience `main` → `main`; else the
  handler's `thread_id`, else the handle; a rule's
  `escalate_after` guard retargets to `main`. At delivery,
  `dispatch_consumer._resolve_target` maps the send's
  target through the handler registry to its `thread_id`,
  passes a bare UUID through as a chat id, else records
  the failure "No thread is registered for this send's
  target."
- **The consumer pass** (`dispatch_consumer.run_pass`,
  consumer name `attention-service`, on the tick):
  **settle first** — for every send with an outstanding
  `bridge_request_id`, fetch the bridge record: `done`
  with a `submission_message_id` → ack with that
  reference (a send suppressed while outstanding is
  stamped delivered as fact, never resurrected); `queued`
  → re-claim if the lease lapsed, wait; `missing` /
  failed → record the failure, release the claim (a
  reason containing "retired" → suppress, terminal).
  **Then claim + enqueue**: cap 10 per pass
  (`dispatch_pass_cap`), max 6 attempts
  (`dispatch_max_attempts`, then parked + suppressed with
  the reason on the record).
- **The bridge hop** (`backend/infra/bridge_client.py`):
  `POST /tools/chat_send` on the scheduler's harness
  connector (:8796) with envelope
  **`attn-<send-id>-a<attempts>`** — the bridge dedupes
  per caller + envelope, so retries cannot double-post —
  and `meta` carried as record data: `{source:
  "owner-attention", send_id, template, target, rule_id,
  sha256(text)}`. Fulfillment is read back via
  `GET /tools/result/<request_id>` (404 → `missing`).
  The caller token is read from
  `var/connector/bridge-token` on every call and never
  enters state; no token → the consumer quietly does
  nothing (sends stay undispatched).
- **Failures are records, never acks.**
  `dispatch_failures` entries `{send_id, consumer,
  reason, at}`, deduplicated to one per hour per send +
  reason (the pass retries every minute); an undelivered
  failure against an understaffed topic surfaces as a
  `steer_undeliverable` staffing row addressed to main.

## 6. Cross-cutting contracts designed locally

- **The handler registry.** `state["handlers"]`:
  `{handle, label, color_slot, icon, thread_id,
  ui_surface, retired}` — handle → thread is the routing
  half; programme membership is *not* on the handler (it
  lives on the programme declaration's `handles` list,
  §below). Written only via `POST /api/v1/handlers`
  (`writes.register_handler`: upsert, omitted fields
  preserved from the existing entry). Read by everything:
  target resolution, labels/colors on every served view,
  retired filtering. **Untracked and unseeded**: the live
  registry exists only inside `var/data/state.json`
  (10 handlers at inspection: lane handles, `main`,
  `calendar`, `mail`); the tracked `sample_data.py` seed
  is a demo specimen with a different, smaller set. No
  file form exists — the registry has never lived outside
  the store.
- **The programme registry** (the supervision directory).
  `state["programmes"]`, written via `POST
  /api/v1/programmes` (`writes.upsert_programme`):
  `{slug, label, handles[], cadence_minutes,
  staffing_band{min,max}, escalation_hours, venue
  (colab|none), rule_text, settled[], commissions[],
  worktree_roots[], record_locations[], contract_path,
  idle_classes[], wb_projects[], retired}`. Cadence,
  band, escalation, and venue are declarations, never
  evaluator constants (the repo's `AGENTS.md`
  spec-sync block). Two fields are *sourced*:
  `contracts.sync` refreshes `rule_text` and
  `cadence_minutes` from the wb-carried goal contract
  file at `contract_path` (the §1.11/§4.11 contract —
  parsed from its `- Key: value` lines) on the slow loop.
- **The armed-row consumption contract.**
  `programmes.ingest_armed` globs
  `settings.armed_dir/*.json` (default the repo's own
  `var/armed/`; the workbench writes there cross-repo)
  on every tick. Join keys: `(project, todo)`. A row must
  carry `project` and `todo` or it is skipped; rows whose
  `source.source_class == "fixture"` **never supervise**
  (skipped at ingest). Rows appear by existing and
  retire by disappearing; `ingested_at` is preserved
  across syncs; the full row is kept under
  `armed_rows[].row`. The evaluator reads `armed_at`,
  `cadence_minutes` (default 15), `status`, `title` from
  the row — the consumer half of the workbench review's
  written shape, field-for-field as written there
  (`armed_at, bundle, cadence, cadence_minutes, handle,
  programme, project, source{writer, project, todo,
  source_class}, status, title, todo` — verified against
  a live row).
- **Status-post ingestion.** `POST /api/v1/agent/status`
  → `ingest.post_status`: handle must be registered;
  the grouped form is validated (a group the state does
  not call for is absent, never empty-filled); `refs`
  are **references only** — `{project, plan, todo_ids,
  steps_open, steps_independent}`, no todo state is
  accepted or stored; `owner_waiting` is a sticky
  declaration (label + commissioned_at) surviving later
  posts until an explicit null or a terminal status
  clears it. Items post via `POST /api/v1/agent/items`
  keyed `(handle, source_ref)`; decision posts must
  carry their options or are refused; defect routing,
  when present, is shape-validated (`{workhorse, thread,
  at, evidence}`).
- **Vocabulary registries.** Status codes, fields, wait
  classes, templates, item kinds, action rules — all
  state-resident, owner-writable at runtime
  (`/api/v1/vocab/*`, `/api/v1/rules`), seeded from
  `domain/attention.py` defaults with `backfill()` for
  late-arriving seeds. The status-code registry carries
  the task-mode vocabulary (WORKING, CONTINUE, REVIEW,
  DONE, CLOSED, PARKED, BLOCKED-OWNER, BLOCKED-HARD)
  with per-code `need` and `terminal` semantics.
  Hard-stop wait classes are named in code
  (`HARD_STOP_CLASSES`) and are not editable through
  the write surface.
- **Seed/example pattern — the weak sibling.** Settings
  are env-only (no config file is read; `.gitignore`
  names a `config.json` nothing reads). There is no
  tracked example for the store, the handlers, or the
  programmes; `examples/registry/` holds two specimens
  in the *scheduler's* registry format (watchdog driver,
  file registry) — starter residue, not attention
  contracts. Against §4.4's pattern, attention is the
  repo with nothing to contribute and everything to gain.

## 7. Pipeline vs apps

- **Engine (pipeline-shaped).** The evaluator
  (staffing + staffing_rows + continuation), the
  dispatch consumer and ledger lifecycle, the wait-rule
  engine, fulfillment derivation, push-fact measurement
  (`facts.py`), the workbench classification/conflict
  derivation (`derive.py`), the four collectors
  (capacity, worktrees, records, contracts), ingest
  validation/classification/tier assignment, and the
  domain derivations (`domain/attention.py`: band,
  visibility, need, templates, rule legality — pure, no
  I/O, no clock).
- **Surface (app-shaped).** `model.py`'s builders —
  glance, Today, handler page, registries, sends — every
  label, verb list, and presence filter computed there,
  display-ready; the static frontend renders served
  shapes and does arithmetic only (`AGENTS.md` seam
  rule). `API.md` is the one declared backend/frontend
  seam.
- **The honest seam map.** Between engine and surface
  *inside* this repo there is no contract at all — direct
  function calls over the shared dict (`build_digest`
  calls `staffing.build_staffing` synchronously;
  `build_today` calls `fulfillment` derivations inline).
  The pipeline boundary the mega repo needs must be cut
  along these call sites: evaluator, dispatch, work
  record, and fact measurement as pipeline services;
  glance/Today/Digest/handlers as the attention app over
  their served shapes. Two derivations sit on the
  surface side of the line today but are engine in
  nature: `facts.derive_push_facts` (runs git against
  sibling repos during a GET) and `digest._parked_pull`
  (pulls workbench plans during Digest assembly) — both
  belong behind pipeline feeds in the target structure.

## 8. Overlaps with the other three, from this side

- **Scheduler.** (a) *Delivery substrate*: attention
  owns the send ledger and consumer; the actual delivery
  rides the scheduler's harness connector bridge
  (`/tools/chat_send`, `/tools/result/<id>`, :8796,
  token caller `attention-dispatch`) and then the
  scheduler-side bridge queue/wake/drain machinery the
  scheduler review describes. Two queues in series, two
  records of one send (the ledger entry and the bridge
  record, joined by `bridge_request_id`). (b) *Routing
  knowledge duplicated*: the destination chat is
  resolved here from the handler registry's `thread_id`,
  and again scheduler-side from
  `bodies/bridge-wake-owners.yaml` when the wake minter
  works the bridged record. (c) *Wake territory*: the
  scheduler outbox mints pings (agent-due / escalation /
  report); attention mints its own continuation and
  supervision sends through its ledger instead — the
  same functional territory, two minters, as the
  scheduler review found from its side. (d) *The
  healthcheck*: the scheduler's untracked
  `jobs/owner-attention-healthcheck.yaml` probes this
  service; from this side the contract is the `/health`
  route it answers (`{status, contract, environment,
  last_stackdump_at}`). (e) The survival contracts
  (watchdog ladder, stackdump) live in `ops/` here in
  the same named form the scheduler review saw
  referenced externally.
- **Workbench.** (a) *Armed rows*: producer there,
  consumer here — confirmed field-for-field (§6),
  including the fixture exclusion both sides honor.
  (b) *Classification endpoint*: `derive.derive_for`
  pulls the workbench's `/api/projects/<p>/todos` at
  read time for every status post carrying refs and
  serves disagreements (posted working / all todos
  done, etc.) as conflict data — the consumer side of
  the endpoint the workbench review describes; posted
  refs are never resolved into stored todo state.
  (c) *Digest pulls*: parked plans, parked counts, and
  newest-plan-modified stamps come from live workbench
  reads at Digest assembly (`wb_client.fetch_projects/
  fetch_plans`). (d) *Goal contracts*: programme
  declarations source rule text and cadence from
  wb-carried GOAL contract files (`contracts.py`) —
  attention's registry already defers part of its truth
  to the work record. (e) *Territory*: Today's bands
  and the workbench Home/Board both present "what needs
  the owner"; the shared store rule (owner-waiting tail
  entries promote to queue items, §3) means the queue
  and the counts read the same items the digest reads —
  the duplication is in derivation, not in records.
  (f) *Status vocabulary*: attention's registry (§6)
  is a runtime-extensible copy of the vocabulary §4.6
  consolidates; the checkpoint line format its record
  rows parse (`records.py`) is the workbench's format.
- **Runner.** Read-only, but concrete (refining the
  runner review's "attribution-level only", which was
  written from the runner side): the evaluator reads
  detached run records directly from the runner's
  results directory and capacity/specs from the panel's
  served API (§4, Finding 5). Nothing here writes to
  the runner. The caller-attribution join is a naming
  convention over the runner's caller strings — the
  two registries (§4.1's runner callers and attention's
  topics) have never shared a key.

## 9. Amendment input for plan §9

1. **Handle registry → §4.1: confirmed, with a form
   delta.** The registry is exactly what §9 expects —
   the shell's programme/lane directory and the
   dispatch target source. But it has **no file form**:
   it is rows in the single state store, API-written,
   unseeded in tracked code. §4.1's merged contract
   needs an explicit store-migration + seed/export step
   for it, or the directory is lost in transit.
   **Second delta**: the *programme* registry (§6) is
   a separate registry in the same store and is the
   supervision directory proper (cadence, band,
   escalation, venue, roots, contract sourcing). §9
   names only the handle registry; the amendment must
   carry the programme registry into §4.1 (with its
   contract-sourced fields reconciled against §4.11's
   goal-record ownership, which is where its
   `contract_path` truth already lives).
2. **Dispatch over the §4.5 substrate: confirmed, with
   two contract deltas.** (a) *Settle-first ordering
   and the suppressed-but-fulfilled edge* (§5) are part
   of the consumer contract, not implementation
   detail — a merged consumer that enqueues first, or
   resurrects suppressed sends, reintroduces the
   twin-send class the 2026-11-12 cures removed.
   (b) *The failure record is contract*: deduped
   failure records and their surfacing as staffing rows
   (§5) ride with the substrate. (c) §4.5 should name
   the **ledger + minting surface** (`record_send` and
   its four producer classes) as the pipeline contract
   attention expresses over — not only the consumer —
   since owner verbs and continuation mint above the
   substrate, not beside it.
3. **Evaluator as pipeline: confirmed, with an input
   delta.** §9.3 describes the evaluator as "the
   consumer side of §4.3 (the evaluator that reads what
   the workbench writes)". The code reads **five**
   inputs: armed rows, status posts, programme
   declarations, runner run records + panel capacity,
   and lane record/worktree snapshots (§4). The
   amendment should name the snapshot contracts
   (capacity, worktree, record, armed) as pipeline
   feeds, and the evaluator's one piece of state —
   first-seen/escalation memory (`staffing_rows`) — as
   pipeline-owned. Note also the evaluator's split
   personality (§2, Finding 3): measure-at-assembly,
   act-on-tick, collect-on-slow-loop; the pipeline
   shape must keep the three clocks distinct.
4. **Today/Digest as app surfaces: confirmed, with
   two deltas.** (a) *Presence asymmetry is
   contractual*: the glance is presence-filtered, the
   queue never is (§3). §9.3's "one status surface"
   and stage D5's glance + Today widget must preserve
   the asymmetry, not unify it away. (b) *Digest is
   not a pure surface today*: it pulls workbench plans
   live at assembly and feeds staffing evidence from
   the same pull (§7). In the target structure that
   pull is a work-record pipeline feed; if the
   amendment leaves it in the app, the app keeps a
   private workbench client and the overlap in §8
   survives consolidation. (c) The **status
   vocabulary registry is owner-extensible at
   runtime** (§6); §4.6's fixed pipeline contract
   must either give the `/vocab` write surface a
   pipeline home or name the extensibility a
   retirement — the review cannot settle which.
5. **Presence and the glance model (§9.3): confirmed.**
   One model, two consumers (launcher widget + app),
   read-time expiry (§3) — no delta beyond the
   asymmetry in 4(a).

## 10. Preserve list

Nothing below is approximated, renamed, or "improved"
in transit:

- **The state store's discipline**: one JSON-shaped
  state, written atomically (`.tmp` sibling + rename);
  registry seeds appended when absent, never overwritten
  (`backfill`). The store's datetime decode heuristic
  (ISO strings restored on load) is a format coupling —
  carried or deliberately replaced, never drifted into.
- **Send record + dispatch subrecord shapes** (§5),
  including `mode`/`outcome` (shadow sends never
  dispatch) and the id scheme (`sNNNN`; waits `wNNNN`;
  owner actions `oaNNNN`; items `handle:source_ref`).
- **Envelope form** `attn-<send-id>-a<attempts>` and
  the bridge meta shape (framing as record data, text
  digest included).
- **Delivered-only-on-reference**: no ack without the
  claiming consumer, a live claim, and the fulfillment's
  submission reference; claim lease 15 minutes, expiry
  at read time; failure records are never acks.
- **Suppress semantics**: terminal, reasoned, refused
  on a delivered send; a suppressed send's late
  fulfillment is stamped as fact, never resurrected.
- **Queue semantics** (§3): verdict recorded at the tap;
  the decided band; fulfillment states (queued / sent /
  recorded / fulfilled / failed / stalled at 120
  minutes); failed/stalled return to the queue with
  decision history on the item's face; replay guards.
- **Reply routing**: direct to the owning thread, main
  copied (`owner:reply-copy`) — Decision 1.
- **Presence semantics**: modes, expectation text, and
  expiry resolved at read time; the glance/Today
  presence asymmetry.
- **The wait record** and its fact-hash dedupe; a
  surfaced wait becomes exactly one item; terminal
  status resolves waits, acks never do.
- **Armed-row file shape, `(project, todo)` join, and
  the fixture exclusion** (consumer half of §4.3).
- **Status-post form**: grouped form with absent-not-
  empty groups; refs as references only; sticky
  owner-waiting declarations.
- **Programme declaration fields** (§6), including
  contract-sourced `rule_text`/`cadence_minutes`.
- **Staffing row kinds, labels, and escalation-memory
  semantics**: first-seen stamps, per-programme
  escalation bound, only a fresh measure clears.
- **Push-fact measurement**: the five fact states
  (current / superseded / pushed / gone /
  unverifiable), measured titles, and tick self-clearing
  on pushed/gone.
- **Vocabulary registry contents as data**: rules,
  templates (with versions), status codes, classes,
  kinds, and action rules the owner has written at
  runtime are records, not code — they migrate as data.

## 11. Risks and unknowns

- **Overlay capture is existential here (§3 of the
  plan).** The live handlers, programmes, rules,
  templates, vocab additions, presence, and queue all
  exist only in `var/data/state.json`. At inspection:
  10 handlers, 3 programmes, 39 sends, 52 items, and
  presence `away` with an expectation set — migrate the
  file verbatim or the product restarts empty and the
  owner's runtime-written rules are gone.
- **`var/` is not all product state.** `var/xfer/`
  carries probe scripts and tarballs (working debris
  from venue-side test loops); `var/storyboard-build/`
  and `var/venv/` are build state. Capture must
  distinguish data (`var/data`, `var/armed`,
  `var/connector`) from debris, or the mega repo
  inherits the debris as if it were records.
- **Single-lock assumptions.** The code's correctness
  leans on one process, one lock, load→mutate→save.
  Any pipeline/app process split introduces concurrency
  the derivations were never written against (e.g. the
  tick and a request both evaluating waits).
- **Paths out of the repo are data.** `run_records_dir`,
  programme `worktree_roots`, `record_locations`, and
  `contract_path` values point into sibling repos and
  goal workspaces; they live in settings and registry
  rows, so a repo move silently re-points or breaks
  the evaluator's ground truth until they are re-based.
- **The bridge token is a file, not a registry entry.**
  `var/connector/bridge-token` is the caller credential
  for the scheduler bridge; §4.1's registry merge must
  carry the token-caller nature (hash-only scheduler-
  side, raw token only in this untracked file) without
  absorbing the raw value into any tracked or stored
  form.
- **Unknown: the frontend's contract drift.** The
  frontend was inspected only as a served static shell
  for this review; whether `frontend/app.js` derives
  anything beyond arithmetic over `api/1` shapes was
  not verified line-by-line.
- **Unknown: scheduler-side bridge behavior.** The
  bridge record lifecycle (queue → drain → fulfillment)
  is taken from this repo's client contract and the
  scheduler review; the two were consistent at every
  point checked, but the drain's own records were not
  re-inspected here.
