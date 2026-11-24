# 03 — Supervision arming contracts

**Canonical owner:** the pipeline — the work-record service
arms and retires; the workbench app owns the todo record, the
pipeline owns the arm/retire act and both projections. (Plan
§4.3; evaluator feeds annexed from §9.3.)

**The contract in one line:** a todo's doing transition arms
two projections (a scheduler entry, an attention armed row)
and its terminal transition retires both — and a sync failure
never fails the todo write.

## The arming act

- Both writers run at the end of the harness's todo writers
  (the one mutation path, so CLI and server writes arm
  identically). Armed predicate: a cadence in
  `progress_check` (not the opt-out value), not at a stop
  status (`done|blocked`), not in an archived bundle.
  Writers arm a doing todo at the 15-minute default when it
  declares no cadence.
- **Sync failure never fails the todo write:** the outcome
  rides the writer's result dict (`progress_entry` /
  `attention_row`); persistent divergence is the doctor's
  surface, not a write error. The doctor's admission
  check is presence-in-store through the writer path —
  an armed todo whose entry is absent from the registry
  store is the divergence it surfaces; there is no
  never-admitted field state to key on (the pinned
  doctor keys on `migrated` being false; amendment 3
  replaces that key).
- **Sibling seams retained:** the writers locate the
  scheduler registry and the armed directory by
  workspace-relative seams (`WB_SCHEDULER_JOBS_DIR`,
  `WB_ATTENTION_ARMED_DIR`); an absent sibling is a silent
  no-op, because external adopting projects must keep
  building with the harness absent. In the target structure
  the same writers write to the pipeline's own registry and
  armed directory through this contract.
- **Fixture-class writers never write live:** a project
  under a temp root is scratch — its syncs no-op against the
  live registry/armed dir, and its renders carry the
  `fixture` source class wherever they do land.

## Projection 1 — the scheduler entry (ARM1)

One entry per armed todo, `wb-progress-<project>-<todo-name>.yaml`
in the registry (entry form: contract 14; fixture:
`fixtures/scheduler-entry-wb-progress.yaml`). Written
through contract 02's writer path — presence in the
registry store is the entry's admission (amendment 3:
no `migrated` / `migrated_at` fields exist
in the target format; the pinned writer's stamp of the
todo's arming date does not carry), classified-catalog block
(origin machine / generality deployment-specific / use_case
work-tracking), machine-form source stamp, `${WS}` anchors
throughout, argv runs `wb progress-check <id>` at the todo's
cadence (exit 0 = on track / disarmed / gone; exit 3 =
stalled, the stall line rides the failure ping). Deleted on
terminal, disarm, or archive.

## Projection 2 — the armed row (ARM2)

One JSON file per armed todo:
`wb-armed-<project-slug>-<todo-name>.json` (a todo's name
is its slug id — lowercase by rule, contract 11 WR1).
Shape: `schemas/armed-row.schema.json`; fixture:
`fixtures/armed-row.json` (the pinned writer's own output
from the pinned tests' fixture todo). `handle` is the todo
name — harness todos record no posting lane and the writer
refuses to guess one. Sorted keys, indent 2, atomic `.tmp` +
`os.replace`; deleted on terminal, disarm, or archive;
`sync_all` reconciles the whole directory against the swept
armed set.

## The consumer half (ATT9)

The evaluator's ingest globs the armed directory every tick.
Join keys: `(project, todo)`. A row must carry `project` and
`todo` or it is skipped; rows whose
`source.source_class == "fixture"` **never supervise**.
Rows appear by existing and retire by disappearing;
`ingested_at` is preserved across syncs and the full row is
kept. The evaluator reads `armed_at`, `cadence_minutes`
(default 15), `status`, `title` from the row.

## Evaluator feeds (§9.3 annex)

The evaluator is a pipeline service reading **five** inputs,
not only the armed rows above:

1. armed rows (this contract),
2. status posts (below),
3. programme declarations (contract 01),
4. runner run records + panel capacity — at the pin these
   are two read seams: run records read from the runner's
   results directory, capacity/specs from the panel's served
   state; in the target structure both are pipeline feeds,
5. lane record / worktree snapshots.

The snapshot contracts — **capacity, worktree, record, and
armed snapshots** — are named pipeline feeds. The
evaluator's one piece of state, first-seen / escalation
memory (`staffing_rows`), is pipeline-owned state. Its
three clocks stay distinct and are preserved: **measure**
at Digest assembly, **act** on the 60-second tick
(continuation), **collect** on the slow loop.

**Cadence and stall rule (ATT12):** the cadence is
per-programme (`cadence_minutes` on the declaration) else
the 15-minute service default; **two missed intervals** is
the recurring bound — an armed row older than 2× cadence
with no status post naming its todo is `armed_unposted`; a
lane record whose latest conforming `progress-checkpoint:`
line is older than 2× cadence is a `record_gap`. Rows are
re-derived from current evidence at every assembly —
**only a fresh measure clears**; there is no ack path in
the evaluator. A row escalates to `main` when its age
passes the programme's `escalation_hours` (default 1 h);
`phantom_stop` and `steer_undeliverable` escalate
immediately. Staffing row kinds are a closed vocabulary at
the pin: understaffed, fleet_idle, record_gap,
idle_unlanded, no_successor, phantom_stop, blocked_uncited,
blocked_unverified, unrouted_defect, serial_plan,
owner_waiting, owner_waiting_unanswered, armed_unposted,
unlanded_claim, unarmed_work, steer_undeliverable — kinds
and labels migrate as vocabulary data (contract 06).

**Push-fact feed (ATT13):** push items are measured against
their repos (HEAD, ahead/behind vs `origin/main`, dirty) at
serve time; the five fact states are **current /
superseded / pushed / gone / unverifiable**; superseded
titles are rewritten from the measurement; the tick
self-clears on pushed/gone. In the target structure this
measurement is a pipeline feed, not a surface-side
derivation (§9.4), and contract 05's fulfillment derivation
consumes it for `push_needed` decisions.

**Workbench classification feed:** the work-record pipeline
serves, per project, every todo across the active bundles
with its status, raw `progress_check`, the opt-out derived
explicitly, arming stamp, last update, and the progress
derivation for the armed set (cadence, last activity,
missed checks, stall verdict) — served ready, so a consumer
judges escalations without parsing a todo file. A project
with no plans dir serves `available: false`. Deliberately
not served: whether a scheduler entry exists on disk — that
is the scheduling registry's own state, joined
consumer-side. Digest's parked-plans pull rides this same
feed family in the target structure; the attention app
keeps no private workbench client (§9.4).

## Status-post form (ATT10)

Schema: `schemas/status-post.schema.json`; fixture:
`fixtures/status-post.json` (the payload the pinned
connector CLI builds, from its pinned refs test). Rules:
the **grouped form** — a group the state does not call for
is **absent, never empty-filled**; **refs are references
only** (`{project, plan, todo_ids, steps_open,
steps_independent}` — no todo state is accepted or stored);
`owner_waiting` is a **sticky** declaration (label +
commissioned_at) surviving later posts until an explicit
null or a terminal status clears it; the poster must be a
registered handle (contract 01). A **terminal** status post
resolves the poster's pending waits; an ack alone never
does (contract 05).

## Preserve clauses carried

ARM1, ARM2, ATT9, ATT10, ATT12, ATT13, and WR1's
checkpoint-line + stall-verdict half (the line format's
record home is contract 11).
