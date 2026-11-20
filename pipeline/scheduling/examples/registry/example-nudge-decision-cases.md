# Sweeper nudge checker — worked decision cases

One worked case per rule in the checker's rule
modules (`ops/sweeper_nudge_check.py` and the
`ops/sweeper_nudge_*.py` family modules). Each case
states the records on
file (in brief) and the decision line the checker emits.
Every chat, repo, session, and workload below is fictional.

The governing principle: a send or escalation is keyed to the
fact set that justified it. The same facts again produce no
decision — a repeat requires new knowledge, and a threshold
crossing counts as new knowledge.

## Thread rules

**Case 1 — completion on record.** Classification for
chat-alpha is DONE.
→ `DECISION record-complete chat-alpha` (nothing is sent)

**Case 2 — thread closed out.** Classification for chat-beta
is CLOSED.
→ `DECISION record-closed chat-beta` (nothing is sent)

**Case 3 — quiet terms.** Classification is PARKED, or
BLOCKED-HARD.
→ No decision. A deliberate pause is not a stall, and the
deterministic tier never nudges a hard stop.

**Case 4 — blocked on the owner.** Classification is
BLOCKED-OWNER, outstanding work on record.
→ `ESCALATE chat-alpha: thread is classified BLOCKED-OWNER;
surfacing the owner's decision is agent work` — once per fact
set; a later classification or outstanding-work change is a
new fact set.

**Case 5 — awaiting review.** Classification is REVIEW.
→ `ESCALATE chat-alpha: thread is classified REVIEW;
presenting it for accept / reject / modify is agent work`

**Case 6 — unrecognized term.** Classification reads
"nearly-done", which is not a vocabulary term.
→ `ESCALATE chat-alpha: unrecognized status term
'nearly-done'; a term matches exactly or escalates, never
guessed`

**Case 7 — no status on record.** chat-alpha has
commissioned work outstanding and no classification.
→ `DECISION send status-request to chat-alpha` with the
code list from the templates file. Recorded once per fact
set; silence never reads as a status.

**Case 8 — plain idle stall.** Classification WORKING, last
activity 47 minutes ago, outstanding "finish the import
suite", no stall signature matches.
→ `DECISION send stall-nudge to chat-alpha`, trigger "quiet
47m with agent-clearable remainder".

**Case 9 — stall signature: dead coordinator after a
restart.** As case 8, except the host boot-time record is
later than the thread's last activity. **Implemented.**
→ `DECISION send stall-nudge to chat-alpha`, trigger
carrying the diagnosis: the host restarted after the
thread's last activity, so any coordinator or run it was
waiting on is dead — the thread is told to re-check what it
waited on and re-dispatch.

**Case 10 — stall signature: blank or errored state left
waiting.** A zero-byte record or an errored run is the last
thing on file for the thread's work. **Structured for, not
yet decidable:** those records are not kept in a shape the
checker can read today, so the signature is a placeholder
returning no match; the plain stall rule (case 8) still
applies.

**Case 11 — stall signature: progress schedule never
armed.** The thread's todo is in doing but no progress entry
was ever armed for it. **Structured for, not yet
decidable:** arming state lives in the todo bundles, which
the checker deliberately does not crawl; placeholder, no
match, as case 10.

**Case 12 — hard-stop words in the remainder.** Quiet past
the threshold, but the outstanding text names a push.
→ `ESCALATE chat-alpha: outstanding work names a possible
hard stop; classification is judgment, not enumerable`

**Case 13 — same facts, next pass.** Any send above, run
again 15 minutes later with no record changed.
→ No decision. Elapsed time alone is not knowledge.

## Venue rules

**Case 14 — idle venue, work waiting.** A High-RAM lease
record shows session reef-01 with no jobs in flight and no
open liveness finding, while a watched thread's outstanding
work names a gate run.
→ `DECISION send idleness-nudge` to the chat routed from
the lease's caller, naming the session and the waiting
work.

**Case 15 — idle venue, nothing waiting: profiling.** As
case 14, but no watched thread has compute work
outstanding, and the profile-target config lists
alpha-service's full suite with no baseline on record.
→ `DECISION send venue-ping` to alpha-service's owning
chat: sessions slot names reef-01, remainder slot reads
"profile the alpha-service full test suite and record the
baseline". Busy work always outranks profiling; a target
with a fresh baseline is skipped. Profiling is the
idle-work queue's third case: it fires only when no
adopted-plan or reconciliation case fires in the same
window (cases 25–28).

## Part B approval timing

Inputs are the approvals list in the sweeper state file
(id, first_seen, last_nudged, what, blocks, resolved_at,
resumed, owning chat). No list on record: the whole group
skips silently.

**Case 16 — new approval.** Entry pending, never surfaced.
→ `DECISION send approval-surface to main`: "Waiting on
you: restart the report service. Blocks: the nightly
export. Waiting since 14:05."

**Case 17 — still pending.** Entry surfaced before, last
nudged over 1h ago, current time inside the 09:00–21:30
owner-local window.
→ `DECISION send approval-surface to main` once more, with
the re-nudge fact set. Outside the window, or within 1h of
this tier's own last surface: no decision.

**Case 18 — resolved, no resumption.** resolved_at is 2h
old, resumed is not set, and the owning chat shows no
activity after the resolution.
→ `ESCALATE main: approval resolved but its owning chat
shows no activity within 60 minutes; verifying resumption
or re-driving the work is agent work`

## Git layer

Inputs are the repos in the git-layer config (fictional
here: alpha-service, beta-worker).

**Case 19 — ahead of upstream, first seen.** alpha-service
is 3 commits ahead of its upstream.
→ `DECISION send approval-surface to main`: "Waiting on
you: git sync for alpha-service (3 commits ahead of
upstream). Blocks: landed work in alpha-service awaiting
push. Waiting since <first sighting>." A push is the
owner's go, never scripted.

**Case 20 — ahead, aged.** The same ahead state is now
past the repo's 24h ahead threshold.
→ `DECISION send approval-surface to main` again — the
threshold crossing is a new fact set. An unchanged count
inside the threshold produces no repeat (case 13).

**Case 21 — dirty worktree, aged.** beta-worker's worktree
has had uncommitted changes for 30h against a 24h
threshold; beta-worker records no owning chat.
→ `DECISION send continue-standing-rule to main`: "Continue:
commit or discard the uncommitted work in beta-worker.
Standing rule: worktrees never age dirty past 24h. Proceed
without asking again."

**Case 22 — unmerged worktree, aging.** alpha-service has
a second worktree on branch fix-import whose head is not
merged into the main branch and whose latest commit is 2
days old.
→ `ESCALATE` with the facts (worktree, branch, commit age,
unmerged). Gate state and whether the follow-up is a defect
or an improvement are recorded nowhere, so landing is
escalated, never guessed.

**Case 23 — duplicate intent.** Within 72h, alpha-service
commits "repair import totals rounding" touching
totals.py, and beta-worker commits "repair import totals
rounding for exports" also touching totals.py: shared file
basename and subject-token overlap above 0.5, from
different repos, and the two diffs are different patches.
→ `ESCALATE main: possible duplicate intent` with both
commits and the shared files as evidence. Consolidation is
agent work; the checker never merges, rebases, or discards.
Refinement: every candidate pair is patch-checked (git
patch-id) before it can escalate. A pair whose patches are
identical is the same work — one branch replaying the
other's commit — and is suppressed as a per-pair escalation
(see case 24).

**Case 24 — branch replay rollup.** Within 72h, one branch
of alpha-service cherry-picks three of the main branch's
commits: three candidate pairs, each with an identical
patch-id.
→ One `ESCALATE main: branch replay` for the branch pair,
stating that the two branches share 3 commits with
identical patches and that one branch replays the other's
commits — fact-keyed on the branch pair and the patch set,
so a fourth replayed commit is a new fact set and
re-escalates with the updated count. Fewer than 3 identical
pairs on a branch pair fire nothing at all: a stray replay
or two is not a finding.

## Idle-work queue

The queue draws on the genuinely idle window — a live
High-RAM session idle with no compute work waiting (the
window of cases 14–15). Busy commissioned work always
outranks the whole queue: it fills the window before the
queue is reached. Inside the window the cases fire in
order, and a case fires only when no higher case fired
this cycle.

**Case 25 — adopted plan start.** The window is open and
the idle-plans config lists the alpha import rework as
unstarted, with a commissioning record on file (ruling,
2026-10-30).
→ `DECISION send continue-standing-rule` to the plan's
owning chat: "Continue: begin the alpha import rework in
a worktree. Standing rule: adopted plans begin when
capacity is idle; nothing builds from a wish — this
plan's commissioning is on record (ruling, 2026-10-30).
Proceed without asking again."

**Case 26 — unstarted plan, no commissioning record.**
The window is open and the idle-plans config lists the
beta report cleanup as unstarted, with no commissioning
record.
→ `ESCALATE` to the plan's owning chat, once per fact
set: the plan is recorded unstarted with nothing on file
showing it was ever adopted, so the checker never begins
it. Entries in state begun or dropped are ignored
entirely, commissioned or not.

**Case 27 — docs reconciliation.** The window is open,
no idle-plan case fires, and the reconciliation config
lists the alpha tracked docs with last_reconciled null
and the beta runbook at 2026-10-20 (19 days before the
check date) — null is the stalest record.
→ `DECISION send continue-standing-rule` to the alpha
docs' owning chat: "Continue: reconcile the alpha
service tracked docs against the records. Standing rule:
tracked docs state the present; reconcile when idle.
Proceed without asking again." One reconciliation send
per cycle: the beta runbook, also stale, waits for a
later window. A surface reconciled within 14 days fires
nothing.

**Case 28 — queue ordering.** The window is open and all
three cases have a candidate: an adopted unstarted plan,
a stale docs surface, and an unmeasured profile target.
→ Only the plan-start send fires; the reconciliation and
profiling candidates stay queued for a later window.
Remove the plan candidate and the reconciliation send
fires alone; remove both and profiling fires, as case
15.

## Statement rules

Two detection-only rules (owner ruling, 2026-11-08). They
state a condition through the escalation path; neither
sends anything to a thread, and neither concludes anything
beyond the statement. The long-running window is 1 hour —
a statement must land well inside one work block. The
contention persistence window is 30 minutes.

**Case 29 — long-running task.** A watched thread has
carried the outstanding text "finish the import suite"
for 75 minutes, with activity 5 minutes ago and
classification WORKING.
→ `ESCALATE <thread>`, once per fact set: "long-running
task: <thread> has had the same outstanding work for
1h15m while staying active: 'finish the import suite';
statement only — splitting or re-driving the work is
agent judgment." A later cycle with the same text and
the same first sighting states nothing new.

**Case 30 — long-running suppressed, stall owns.** The
same thread and text, but its last activity is 2 hours
old — quiet past the stall threshold.
→ No statement. Quiet threads belong to the stall rule,
which nudges or escalates with its own diagnosis; a
thread making no visible progress is a stall, not a
long-running task.

**Case 31 — long-running suppressed, deliberate state.**
The same thread and text past the window, but the
thread is classified PARKED (likewise BLOCKED-OWNER,
BLOCKED-HARD, REVIEW, DONE, or CLOSED).
→ No statement. Deliberate states and states another
rule already surfaces are never long-running findings.

**Case 32 — outstanding text changed inside the
window.** The text "finish the import suite" stood for
50 minutes, then changed to "repair the export totals"
20 minutes ago; the thread stayed active throughout.
→ No statement. The clock follows the text: a changed
text restarts the window, and the current text is only
20 minutes old.

**Case 33 — contention, persisted.** Both live High-RAM
sessions are busy — reef-01 with 2 jobs, reef-02 with
1 — a watched thread's outstanding names compute work
("run the gate suite"), no session is idle, and that
shape is unchanged for 35 minutes.
→ `ESCALATE main`, once per fact set: "compute
contention: every High-RAM session is busy — reef-01
(2 jobs), reef-02 (1 job) — while compute-bound work
waits and none is idle (shape unchanged for 35m): 'run
the gate suite'; statement only — routing the waiting
work is agent judgment."

**Case 34 — contention suppressed, idle session
exists.** As case 33, but reef-02's job list is empty.
→ No statement. An idle session exists, so the idleness
rule owns the case (case 14); contention is stated only
when the waiting work has nowhere to go.

**Case 35 — contention inside the persistence window.**
As case 33, but the shape is 10 minutes old.
→ No statement yet. A busy snapshot is a moment, not
contention: the statement fires when the same shape —
same busy sessions and job counts, same waiting work —
has persisted 30 minutes, and any change to the shape
restarts the clock.

## Venue-question rule

One send rule (owner ruling, 2026-11-08): work running on
a low-end venue is always questioned, and the question
carries the High-RAM situation as recorded. Justification
is the thread's to state; the checker only reads records.

**Case 36 — question fires on a low-end session with
jobs.** A lease record shows session dune-01 (shape cpu)
running run-101 and run-102; no High-RAM session is up.
→ `DECISION send venue-question` to the chat routed from
the lease's caller: "Venue check: work is running on
session dune-01 (cpu), a low-end venue: run-101, run-102.
High-RAM: none up. Standing rule: compute-bound work runs
on High-RAM. State the justification for this venue, or
move the work to High-RAM." The same records next cycle
ask nothing again.

**Case 37 — excepted session.** As case 36, but the
venue-exceptions config carries an entry matching the
lease's caller, its reason the recorded justification.
→ No decision. The exception is the justification on
record; there is nothing left to ask.

**Case 38 — low-end session idle.** As case 36, but the
job list is empty.
→ No decision. An idle low-end session runs no work; it
is the runner's business, not work on a low-end machine.

**Case 39 — High-RAM appears mid-run.** As case 36; two
cycles later a High-RAM lease shows session reef-01 idle
while dune-01's work runs on.
→ `DECISION send venue-question` again, the High-RAM slot
now reading "session reef-01 is idle". The fact set
changed — High-RAM capacity is up and unused — so the
question is asked again with the new fact, and the
follow-up clock restarts.

**Case 40 — question unanswered.** As case 36, and four
further cycles pass with the same records: same session,
same jobs, same High-RAM state.
→ `ESCALATE` to the session's chat, once per fact set:
the venue question is unanswered — the same work is
still on the low-end venue, no move and no justification
visible in the records. A justification stated in the
thread is read by the agent tier there; the checker
escalates only what the records show.

**Case 41 — the stall nudge text carries the diagnosis.**
As case 9: classification WORKING, last activity 47
minutes ago, the host boot record later than that
activity, outstanding "finish the import suite". The
stall-nudge template is v2: its diagnosis slot takes the
whole clause, composed from the recorded matches.
→ `DECISION send stall-nudge to chat-alpha`, text:
"Status check: quiet for 47m with commissioned work
outstanding: finish the import suite. Report what is done
and what remains; if the pause is on something
agent-clearable, continue now. Diagnosis: host restarted
at 16:50Z after this thread's last activity, so any
coordinator or run it was waiting on is dead — re-check
what it waited on and re-dispatch." With no signature
matched the diagnosis slot is empty and the delivered
text is the pre-v2 rendering, byte for byte.

## Grouped status reports

The status-request template is v3 (report-forms plan,
2026-11-08): a one-line code alone is not a status
report. The code line is the report's header and its
classification key; beneath it the thread reports in
its own state's form — the groups its state carries,
the rest omitted, never filled with "none". Case 42
shows the v2-era WORKING report; the per-state forms
and their classification are cases 46–49.

**Case 42 — a grouped report classifies by its code
line.** Asked for a status (case 7), chat-alpha replies:
the code line "STATUS: W", then one line per group —
done; ongoing; computed locally while High-RAM is up;
serial that should be parallel; stalling and why, and
what would speed it up; duplicate-intent consolidation;
docs state — each stated or marked none.
→ The sweeper records the term WORKING from the code
line, under the exact-match discipline. The groups are
the thread's own statement of its work, recorded with
the classification as its report — they are not checker
facts, and no rule recomputes them; the checker acts on
the classification and on the activity and outstanding
records, exactly as for any WORKING thread.

**Case 43 — a bare code is no report.** Asked for a
status, chat-alpha replies with only the code "W" and
nothing else.
→ The reply records term "unclassified" with the note
"bare code, no report", and is treated as no report:
the thread stands as unreported and is re-asked under
the status-request discipline (case 7). A lazy
one-line answer never satisfies a status request.

**Case 46 — a CLOSED report in its state's form.**
Asked for a status, chat-eta replies: the code line
"STATUS: CL", then two lines — done as one summary
line (the import suite landed and pushed; gate green)
and docs state (plan archived; memory updated).
→ The sweeper records CLOSED. Two lines is a complete
report: CLOSED's form carries done (summary) and docs
state, and nothing else exists to state. Brevity is
not bareness — a code alone is no report (case 43),
but a terminal report in its form is a report.

**Case 47 — a WORKING report missing doing groups is
partial.** Asked for a status, chat-alpha replies
"STATUS: W" with done and ongoing lines only — no
stalling line, no computed-locally or serial lines, no
docs state, while compute work is in flight.
→ The sweeper records WORKING with the note "partial
report: no stalling line, no computed-locally, no
serial-that-should-be-parallel, no docs state". A
partial report is a report — the term classifies and
the thread is not re-asked as unreported (contrast
case 43) — but the missing groups are named on the
record the next sweep judges against.

**Case 48 — a none-filled terminal report is a
report with a form note (D1).** Asked for a status,
chat-eta replies "STATUS: CL" in the v2-era shape:
all seven group lines present, five of them "none",
plus a done summary and a docs-state line.
→ The sweeper records CLOSED with the form note
"none-filled groups". Content over form: the padding
is forbidden by the string and noted on the record,
but the record does not punish it — the thread stands
reported, not re-asked.

**Case 49 — PARKED reported as stalling is a form
error.** Asked for a status, chat-beta — parked by
the owner's instruction on the last run — replies
"STATUS: P" with a stalling line: "stalling: waiting
on the venue session to return."
→ The sweeper records PARKED with the form note
"reported as stalling; parked is deliberate". Parked
never maps onto stalling: no stall nudge, no stall
clock. The classification follows the derived state —
parked by instruction, nothing doing — and the
missing groups (why parked, what resumes it) are what
a later request asks for.

## Workbench health (body step 12, scripted)

The body's old step-12 fetch is performed by the
scripted checker (rule check_workbench_health); the
body's duty is only to surface the escalation it
records.

**Case 44 — the viewer is down.** The checker's probe
of the viewer's health endpoint gets no response —
connection refused, on both of its attempts (a single
cold-connect timeout is retried once before it counts:
measured live, a fresh process's first connect can
stall past the timeout while the viewer is up).
→ `ESCALATE main`, once per outage: "workbench viewer
appears down: the health probe failed — no response
(connection refused) — at <time>; the threads' progress
schedules depend on the viewer." The outage's start is
the fact set: the next cycle, still refused, decides
nothing new.

**Case 45 — recovery records and re-arms.** After case
44's outage, the probe answers 200 with a parseable
body.
→ `DECISION record-recovered main`: the outage is
closed and its fact cleared, so a later outage
escalates as new knowledge. An ambiguous answer along
the way — a non-200 status, an unparseable body —
records a plain record decision instead: no escalation,
no outage fact; honest absence over a false alarm.

## Unarmed progress watch (stall signature, scripted)

The unarmed-progress stall signature (report-forms
plan Step 6, 2026-11-08) reads, for the stalled chat's
repo in the thread-repos config: todo files in active
bundles (front-matter status and progress_check), and
the registry's wb-progress entries. An interval counts
only as a registry entry; a chat with no config entry
is undecidable and the signature stays silent.

**Case 50 — an unarmed doing todo rides the stall
nudge as its diagnosis.** Chat-alpha has stalled
(case 41's shape, minus the restart). In chat-alpha's
repo, todo
t-EXAMPLE1 is doing, carries no progress_check field,
and has no wb-progress entry in the registry.
→ The stall nudge's diagnosis carries: "work in
flight with no progress watch armed: todo t-EXAMPLE1
is doing in alpha-service with no wb-progress entry
in the scheduler registry and no recorded opt-out —
arm its progress schedule, or record progress_check:
off in the todo if the watch is deliberately off."
The same holds when the front-matter claims a cadence
(progress_check: 15m) but no entry exists — a declared
watch that never landed is not a watch; the entry is
the interval.

**Case 51 — an armed todo is silent.** Same stall,
but t-EXAMPLE1 carries progress_check: 15m and its
wb-progress-alpha-t-example1.yaml entry sits in the
registry.
→ No unarmed line in the diagnosis. The watch exists
as a registry entry; missed pings from it are the
progress schedule's own stall evidence, not this
signature's.

**Case 52 — an opted-out todo is silent.** Same
stall; t-EXAMPLE1 is doing with progress_check: off
recorded in its front-matter and no registry entry.
→ No unarmed line. The opt-out is a recorded decision
(the harness's --no-progress shape), not a missing
watch; the signature distinguishes "deliberately off"
from "never armed" by that record alone.

## Frozen run records and escalation consumption (record rules, scripted)

The record rules (unstaffed-doing plan, 2026-11-09;
ops/sweeper_nudge_records.py) read other systems'
records as records: the runner's run records and the
scheduler ledger's wb-progress outcomes. A frozen
record's bound is its job manifest's timeout, capped
at 45 minutes — the owner's no-progress bound;
absent a manifest, the cap itself is the window.
Attribution is the
record's caller, resolved through the notify-routes
map to a chat the thread-repos config attributes and
the sweeper watches.

**Case 53 — a staffed, progressing todo is quiet.**
Todo t-EXAMPLE2's wb-progress job runs on cadence and
its recent runs exit 0 (on track); its pings, when any
fire, are followed by checkpoints that move the
todo's last activity.
→ No decision from the record rules. There is no
STALLED streak, and a streak whose last-activity stamp
moves is clearing by definition. Detection belongs to
the harness; this family consumes only its outcomes.

**Case 54 — a STALLED stream acked and cleared is
quiet.** Todo t-EXAMPLE3 stalls: three exit-3 runs,
three escalation pings created and acked. Then the
todo moves to done (or a checkpoint moves its last
activity and the runs return to exit 0).
→ No escalation. The streak is over or the condition
cleared; acked-but-cleared is the machinery working.
The escalation-consumption rule fires only while the
todo still reads doing with the last-activity stamp
unmoved across the whole streak.

**Case 55 — acked but uncleared at the bound
escalates to the owner.** Todo t-EXAMPLE4 (Step 4 —
Classification surface) in alpha-service has been
STALLED since 08:46Z: nine consecutive exit-3 runs,
nine escalation pings created and all nine acked,
the STALLED line's last-activity stamp identical at
both ends of the streak, and the todo still reads
doing in its front-matter.
→ `ESCALATE main`, once for that stall (fact set:
todo + stall start): "progress escalations are being
consumed without effect: todo t-EXAMPLE4 (Step 4 —
Classification surface) in alpha-service has been
STALLED since <stall start> (2h14m); 9 escalation
pings were acked and the condition has not cleared —
the todo is still doing and its last activity has
not moved (<stamp>). Staff the lane, re-dispatch the
continuation, or surface the block; an ack is not a
resolution." The next cycle with the same stall
decides nothing new; a cleared-and-restalled todo is
a new stall and a new fact set.

**Case 56 — a frozen run record draws the reconcile
nudge.** Chat-alpha's caller owns run record
alpha-gate-20261109T080000Z (job alpha-gate, manifest
timeout 3600s): state polling since 08:00Z, no resume
and no checkpoint pull after 08:05Z. At 10:30Z the
record's evidence is past its bound with no
reconcile evidence.
→ Send `record-reconcile` to chat-alpha, fact-keyed
on the record and its newest evidence stamp:
"Run record check: colab-run record
alpha-gate-20261109T080000Z (job alpha-gate) has been
polling for 2h30m with no reconcile evidence past
its evidence bound — a frozen record is not running
work. Reconcile it (colab-run --poll
alpha-gate-20261109T080000Z) or close it out; do not
treat it as still running." A record inside its
window, a terminal record, a record whose evidence
moved after the bound (a reconcile is working
it), and a record whose caller routes to no
attributed watched chat all decide nothing.

**Case 57 — an in-scope continuation on a record
finding is a continue (body-side).** Case 55's
escalation lands with the agent tier. The stalled
todo is Step 4 of an adopted plan; Steps 1–3 are
landed, Step 4's continuation is agent-clearable
inside the plan's approved scope, and nothing about
it is a hard stop.
→ The body says continue (Part A, the finding as its
named trigger): the owning thread is told to staff
and proceed with Step 4, recorded and reported after
the fact like any Part A continue — the finding's
thread is not classified plainly WORKING while the
finding stands. Where the continuation's scope is
unclear or the step is not agent-clearable, the body
instead surfaces the finding in the main chat
promptly; what it never does is ack the escalation
and move on — that consumption-without-effect is
the failure the rule exists to catch.

**Case 58 — a pending permission is never
grant-eligible (zero-agent Step 5).** Approvals
entry "card-7" is newly pending (a runtime
connection card for a reporting tool; blocks "the
nightly export"; first seen 12:05). The runtime
listing carries no program, scope, or reversibility
fields for it.
→ `DECISION send main approval-surface` with the
pending surface text — and nothing more. Grant
eligibility (the body's 5A/5B) is a property of a
chat-level wait inside an approved program, judged
by reading the waiting chat; a runtime permission
card is never grant-eligible and never escalates
as one — it surfaces, and the owner decides.

**Case 59 — a resolved-not-resumed escalation
carries the re-drive facts (zero-agent Step 5).**
Approvals entry "card-9" ("restart the report
service", blocks "the nightly export", owning chat
chat-delta, first seen 09:12) resolved at 10:04;
chat-delta shows no activity after the resolution,
and 60 minutes pass.
→ `DECISION escalate main approval-resume:card-9`:
the reason names the approval, its what and blocks,
the owning chat, the first-seen and resolved times,
and the no-activity finding — the full re-drive fact
set, so the escalation agent verifies resumption or
re-drives the blocked work from the escalation
alone, without re-reading the state file.
