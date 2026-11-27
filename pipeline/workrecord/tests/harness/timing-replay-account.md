# Replay account — timing-ledger Step 5 over 2026-11-26-wall-clock-reduction

Findings first. The trace stands end to end for five of the plan's
eight steps: plan-file estimate → transition events reconstructed
from named records → report figure, with every reconstructed
instant at its source's own precision and marked as backfilled.
Three steps (1, 7, 8) render no measured span — the surviving
record bounds their completion but not their start, and the
report's honest absence is the correct rendering, not a gap in
the replay. One read-side defect was found and cured: over the
store's real shape the report could not read this plan's file at
all (below). The harness is `test_timing_replay.py` beside this
account; it rebuilds the store in a tmp project and asserts every
figure stated here.

## The backfill form

A reconstructed transition is a record in the ledger's own shape
(`at`, `actor`, `verb`, `field`, `old`, `new`) plus two keys:
`backfilled: true` and `source` naming the evidence the instant
was reconstructed from. Precision follows the source exactly:

- a landing record's `landed_at` — microsecond precision, as
  recorded;
- a run record's `finished_at`, a git commit's committer instant
  — second precision, as recorded;
- the front-matter `created:` stamp — date-only, so the create
  line's instant is day-grain (`2026-11-26T00:00:00+00:00`) and
  its source says so;
- a todo file's mtime — the write that recorded its done state,
  rendered at second grain.

A `doing` line is placed only where a recorded instant bounds
the step's work independently of its completion (in practice:
the step's first build commit). Where no independent bound
survives, no doing line is reconstructed — a span needs two
bounds, and one bound is not a span. A `done` line's `old` is
the last recorded status (`doing` where a doing line stands,
else `todo`), so no line claims a state the record never held.
No blocked line is reconstructed for any step: no step's record
carries a blocked episode, so blocked renders a measured 0m on
every span — "none recorded", not "none occurred".

## What the report shows

| step | est | actual | span bounds (evidence) |
|---|---|---|---|
| 1 — Inventory the four sources | 1h | — (no span) | done 16:21:48Z, todo-file mtime |
| 2 — No-verdict gate fires | 40m | 3m | git c4d33a12 18:33:04Z → landing record 99133339344e, landed 18:36:12.526154Z |
| 3 — Union gate dispatch default | 45m | 2h32m | git 38a57d82 16:49:24Z (contract half) → landing record e46a5d437c74, landed 19:21:31.045447Z |
| 4 — In-fire double run | 20m | 10m | git 3d2be92d 16:34:34Z → run record plancheck-gate-20261126T164424Z, finished 16:44:55Z |
| 5 — Landing record | 40m | 17m | git cd973e01 17:04:56Z → landing record 99cd586f1737, landed 17:22:03.944307Z |
| 6 — plan-check formations | 35m | 1h37m | git 30cf0449 16:24:35Z → landing record c27c2c92c2ef (precision cure), landed 18:01:05.2578Z |
| 7 — Overlap analysis | 35m | — (no span) | done 19:29:19Z, todo-file mtime |
| 8 — Spec transfer | 30m | — (no span) | done 19:30:38Z, git 6cbf16b6 (the sync landing) |

Wall-clock (est): ruled 5h05m, serial sum 5h05m — every step is
priced, and no step declares a position, so the ruled form
prices all eight in the serial band. Wall-clock (actual): ruled
4h39m, serial sum 4h39m, over the five measured steps, with 3
steps excluded as unmeasured. Steps 2–6 render their backfill
marks with sources; step 2's editor set reads [local-compute,
workhorse-successor-v] — the build was the local-compute seat's,
the landing this seat's, exactly as its landing record states.
The price book over the replay store is honest absence: no todo
of this pre-ledger plan carries a minted est or fan-out
position, so the book has no priced items — its grain begins
with plans minted after the ledger.

Two cautions the figures carry. The spans are bounds from
recorded evidence, not partitions of the day: the seat worked
steps interleaved (step 3's contract half landed while steps 4–6
were in flight), so spans overlap in time and each is a lower
bound on its step's true span — authoring before a step's first
commit is unrecorded everywhere. And step 3's 2h32m and step 6's
1h37m against 45m/35m estimates are real overruns of the recorded
form: step 3's backstop needed a re-formation and two gate
cures; step 6's span runs to its precision cure's landing, an
hour and a half after its first gate green — the cure is part of the
step's landing sequence, as the plan's closing account records
it ("landed d02055a with precision cure c27c2c9").

## Where the figures agree with the plan's own records

- Every landing record's `landed_at` is its step's report end,
  asserted for steps 2, 3, 5, 6.
- Step 5's landing record prices its own phases —
  formation→gate 13.6m, gate→landed 1.8m, formation→landed
  15.5m — and the todo body states the same figures; the
  report's 17.13m step span contains them, opening 1m40s before
  the record's formation (the writer commit precedes the first
  gate fire) and closing at the same landed instant.
- Step 2's record (1 fire, formation→landed 0.8m) sits inside
  its 3.14m span the same way.
- Step 3's real-fire proof (union-gate-20261126T192204Z,
  ran-green naming both constituents) started 33s after the
  step's landed_at — post-landing verification of the landed
  form, correctly outside the span, as its todo body records.
- Step 4's span brackets its verification pair: the red-path
  fire (plancheck-gate-20261126T163502Z, 16:35:02Z) inside it,
  the green-path fire's finish as its close. A third fire in
  the step's record (164038Z, transport-dead at mkdir) moved
  no bound.
- measurement.md itself prices the baseline corpus (the
  programme window 2026-11-24→26), not this plan's steps, so
  the two records overlap at exactly one point: step 1.
  measurement.md is step 1's deliverable, and the report shows
  step 1 priced (1h) with no measured span — its completion
  instant (the todo write at 16:21:48Z, a minute after
  measurement.md's own write at 16:21:04Z) is the only step-1
  instant the record holds. The baseline's driven-landing
  median (15.7m formation→landing over the window's merges)
  and this plan's landing-record phases are different
  populations and are not conflated.

## The 170m total the report does not reproduce

The plan header states "Total: 170m". The report's est
wall-clock is 305m. Both are correct readings of different
declared structure: 170m is the critical path over the plan's
requires graph — 60 (step 1) + 45 (the longest of steps 2–6,
which all require only step 1) + 35 (step 7) + 30 (step 8). The
ledger's ruled form prices declared fan-out *positions*; this
plan's blocks predate the position grammar (they declare
fan-out lane lists, not positions), no todo carries a minted
position, and so every step prices in the serial band and ruled
== serial sum. Reproducing the 170m form from the ledger
requires position declarations — the carrying the timing plan's
Step 3 built into the mint for plans adopted after it. The gap
is named here rather than closed by inventing positions for a
plan that never declared them.

## Where the evidence ran out

- Steps 1 and 7 — spans. Step 1 ran as five record-family
  lanes whose only surviving instants are the deliverable's
  write (16:21:04Z) and the todo's done write (16:21:48Z).
  Step 7's deliverable (overlap.md) was last written 19:21:46Z
  and its todo recorded done at 19:29:19Z; no start instant
  survives for either step.
- Step 8 — a span. Its two recorded instants, the starter
  commit (19:30:22Z) and this repo's sync commit (19:30:38Z),
  are one bound 16 seconds apart, not two; the transfer's
  authoring time is unrecorded.
- Every step — authoring time before its first commit, and
  any worktree: no step's record names the worktree it ran
  in, so the worktree field renders absence throughout.
- Blocked time — no step's record carries a blocked episode;
  the waits between steps are inter-step and were never
  recorded as blocked status on any todo.

## The read-side cure

`lib/plans/timing.py`, `plan_timing`: the report read a plan's
text only from its bundle's own `plan.md`. This plan's store —
and every bundle in the workrecord project — is the split form:
a bundle directory holding only todos, the plan file in a
different tree (the seat's plan dir), joined only by the todos'
`plan:` front-matter. Over the real store the report therefore
rendered every step's estimate and title as absence despite the
plan file existing and being named by all eight todos. The cure
reads the plan through the todos' shared ref when the bundle
carries no plan file of its own: the todos must agree on the
one ref (a trailing `#fragment` is stripped — it locates a
section, never a different plan), relative refs resolve
against the plans dir, and disagreement or a missing file
keeps the honest absence. The harness proves both sides: the
replay store (plan file present, in its own tree) renders
titles and estimates through the ref; the same store with the
plan file missing renders them as absence while its spans
still measure. The module docstring records the join and the
backfill form this step defined.

## Fixture fidelity notes

The harness embeds the evidence as constants (the serve tree is
never mutated, and the test touches only tmp dirs): the todos'
front-matter and completion-note bodies verbatim, the plan's
step headings, wb-step blocks, and closing est lines verbatim.
Elided, and named: the plan steps' prose bodies (the report
reads none of it) and the annotation on step 1's closing est
line after its first clause. The todo copies' `plan:` refs name
the fixture's own plan file — in the serve tree they name the
repo-root plan file by absolute path; the copy's ref names the
file it points at, in the same split geometry. Git commits are
cited by their current-tree SHAs; the todo bodies record
pre-strip SHAs for the same commits (the 2026-11-27 history
rewrite), with subjects and instants identical.
