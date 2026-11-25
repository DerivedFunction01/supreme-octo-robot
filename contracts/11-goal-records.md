# 11 — Goal records + work-record substrate

**Canonical owner:** the pipeline work-record service — the
goal record is the top-level work record; its workspace and
schedules are projections and entries armed by the record.
(Plan §4.11.)

**The contract in one line:** a goal is a record plus its
ping — a work record carrying the goal contract block, and
a reminder armed as a pipeline scheduling entry — and no
part of the target structure reads or writes any Muse-side
goal registry.

## The decoupling

Goals are decoupled from the Muse goal system entirely:
no part of the target structure reads or writes any
Muse-side goal registry. The contract's two homes are
pipeline surfaces: the work record and the scheduler job
definition — nowhere else.

## The goal record

- **Hierarchy:** goal → bundles/plans → todos → arms (the
  arms are contract 03's projections). The goal record is
  the top level of the work record.
- **The contract block is a field of the record**, not a
  file header that can diverge: **Objective / Complete
  when / Blocked only when / Continuation**. It is created
  by `wb` for code-focused work or app-side for non-code
  purposes.
- **The workspace is a projection:** `GOAL.md`, `files/`,
  and `hidden_files/` render from the record; the record
  is the truth when they disagree.
- **Goal-owned schedules are pipeline scheduling entries
  armed by the record itself** (entry form: contract 14,
  `owner: goal:<slug>`), surviving any single app's
  registry — a schedule's existence never depends on a
  registry outside the pipeline.
- **Measurement and continuation:** the one evaluator over
  the one store measures the record (contract 03's feeds);
  continuation dispatch rides the one dispatch substrate
  (contract 05).
- **Programme reconciliation:** the programme registry's
  contract-sourced fields (`rule_text`, `cadence_minutes`)
  are owned here — the registry row is their directory
  projection (contract 01, §9.1).

## The work-record substrate

§4.11 names the goal record the top level of **the work
record**; the store beneath it is carried here, in the
four preserve clauses no other §4 entry owns.

**File todos (WR1).** Bundle layout:
`.plans/<date>-<slug>/` holding an optional `plan.md` and a
`todos/` dir of one Markdown file per todo; `finished/`
holds archived bundles; legacy flat plans enumerate as
one-file bundles. Front matter (fixture:
`fixtures/file-todo.md`, written by the bundle writer):

| Field | Rule |
|---|---|
| `id` | required; the todo's name — a GitHub-like slug matching `^[a-z0-9]+(-[a-z0-9]+)*$`, 1–100 chars, unique across the project (the owner's naming ruling). Explicit at creation or derived from the title (slugified, suffixed `-2`, `-3`, … on collision). The todo's file is `<id>.md`. Pre-ruling records carry the retired generator's `t-[0-9A-HJKMNP-TV-Z]+` form until the rename pass migrates them; the parser accepts that form as a legacy id |
| `legacy_id` | written only by the rename pass: the record's pre-ruling `t-<token>` id, kept as data (the audit/reversibility join for anything that referenced it), never a lookup path |
| `title` | required |
| `status` | required; `todo\|doing\|blocked\|done` |
| `created`, `updated` | required |
| `progress_check` | cadence (`30m`/`2h` forms), `off` = opt-out, absent = writer arms at the 15-minute default on the doing move |
| `progress_armed` | the arming stamp |

Unknown fields are **preserved losslessly**; invalid files
surface flagged, never silently skipped. The body carries
the checkpoint line format —
`progress-checkpoint: <ISO-8601> — <text>` — whose
derivation (2 missed intervals = stall) is contract 03's.

**Registry store (WR2).** One SQLite DB per adopting
project at the path its manifest declares, schema unified
across every adopting repo (tables `entries`, `history`
— append-only audit/review log — `todos`, `todo_events`;
`PRAGMA user_version` migrations, WAL + busy_timeout, one
short `BEGIN IMMEDIATE` per mutation, per-row `version`
compare-and-swap). The `registry.json` export folds the DB
on every mutation; its shape is `{_generated{by, at,
warning}, project, entries, history, todos, todo_events}`,
serialized canonically (indent 2, sorted keys) and stamped
generated — never hand-edited. **Data never migrates:**
each project's registry DB stays in its owning repo; the
mega repo inherits tooling, not data.

> Noted tension, resolved by joint reading: §12 calls the
> per-project DBs "partitions of the one work-record
> store". Read together with §2's rule, the store is one
> **logical** store whose partitions remain **physically**
> in the owning repos — S4 inherits the tooling and the
> logical view, and moves no project's data. Flagged here
> so S4 does not have to re-derive it.

**Manifest (WR3).** `workbench.yaml` at a project root:
`name`, `slug`, `registry`, `plans`, `mockups`, `archive`,
plus the `catalog_*` classification fields (axes: contract
07). Fixture: `fixtures/workbench-manifest.yaml` (the
tracked template). Adoption is by placing the manifest;
the sweep finds adopters.

**Two stores stay two (WR4).** The registry DB and the
`.plans/` bundles are not conflated, and the registry-DB
todo table stays **link-only** — it may link to a
plan/step/entry; "steps are never copied here". The
scheduler entries and armed rows are projections of the
file todos (contracts 02/03), never a third store to merge.

## Preserve clauses carried

WR1, WR2, WR3, WR4 — and §4.11's own terms (the contract
block as a record field, the workspace as projection,
record-armed schedules, the decoupling).

## The goal-record store

`pipeline/workrecord/lib/writes/goals.py` in the
work-record service is the goal record's one home: one
JSON store of records (identity, project, contract block
as a record field, ping block, status posts in contract
03's wire form), every save riding the unified writer
through the work-record library's write seam, reads
fail-closed. The blocked-state gate below is enforced at
that writer: an uncited blocked post is refused, the
verifying party stamps verification as the post is
recorded, a terminal post clears owner-waiting and
retires the record's ping in the same call, and a retired
ping refuses re-arm. The record arms its own ping through
the progress schedules' writer path — one entry per armed
record in contract 14's form (`goal-ping-<slug>`, `owner:
goal:<slug>`, running `wb goal-check <slug>`) — and the
work-record server's goals feed
(`pipeline/workrecord/server/goals.py`) serves the store's
records. One form note: the entry carries no machine
source stamp (that stamp names a todo; a goal record has
none) — the registry's goal-owned entries are the
precedent, and the writer + lifecycle are stated in the
entry's classification and self-removal text.

## Blocked-state citation and verification

A status post asserting a blocked state (BLOCKED-OWNER /
BLOCKED-HARD) carries `basis_citation` (the owner's
message reference — thread + time) and `verification`
(verified-by + verified-at, stamped by the verifying
party). The wire home is the status post itself, with
contract 03's `blockers` group carrying the same pair in
its progress feeds. A blocked post without the pair is
invalid at the writer, not a renderable state in any app.
