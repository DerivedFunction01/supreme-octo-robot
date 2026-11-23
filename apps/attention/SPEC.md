# Owner-attention — SPEC

The attention system's product spec in this repo: the
staffing-supervision row catalogue, the owner-action
surface, the decision queue's semantics, and the Digest's
form. The pipeline derivations these surfaces present are
contracts 03 (the evaluator), 05 (the send ledger and
decision machinery), and 06 (the vocabulary); the generic
supervision rules are stated in the shared spec
(spec-driven-starter, `docs/supervision-rules.md`). This
file carries the product-specific substance: the row
families the evaluator serves, what a decision means, and
the Digest's ruled form. Drawn from the
original owner-attention spec (§1.11 (a)–(l) and §1.13)
and the owner's flow rulings.

## 1. Staffing supervision — the row families

Staffing is measured against live venue capacity and
surfaced repeatedly until it is staffed. An
acknowledgement never clears a row; only a later measure
showing the programme staffed does. The evaluator serves
one row per finding, in these families:

- **Child-worker counts** — a programme's workers are
  counted split by attribution: runs by the programme's
  own coordinator callers, and child workers run by every
  other caller attributed to it. A coordinator fielding
  no child workers while its programme has parallel work
  is the defect in its pure form.
- **Fleet-idle** — a live session carrying no runs while
  any programme is understaffed, or while runs queue on
  another session, is a fleet-level row of its own.
- **Idle-unlanded** — work done in the record while the
  status stays non-terminal: idle with unlanded work,
  carrying the minutes since the last activity evidence.
- **No-successor** — a programme done (or its referenced
  plan derived done) while its project holds approved
  unstarted plans and it fields no workers, until a
  successor is staffed or the programme closes.
- **Record-gap** — no lane is called idle from its record
  alone: the measure cross-checks run records and the
  work record's stamps on its referenced plans first.
  Work moving under a frozen record is a missing-record
  defect carrying the checkpoint gap — the age of the
  lane's newest status post against the armed 15-minute
  checkpoint cadence.
- **Timed escalation** — a row starts in the lane's
  hands; still unstaffed after one hour it escalates to
  main and stays escalated until a measure shows the
  programme staffed.
- **Dispatch-failure actuation** — a supervision steer
  that cannot reach an agent able to act is itself a
  defect after one failed cycle (`attn dispatch fail`);
  a delivery failure for an understaffed topic's thread
  surfaces as a `steer_undeliverable` row to main.
- **Priced evidence** — every row serves its measured
  sentence: active workers, child workers, per-session
  run counts, idle-session minutes while any queue
  waits, and the checkpoint gap.
- **Phantom stop** — a blocked or stand-down state whose
  basis is a claimed owner instruction must cite the
  owner's actual message (blockers carry a citation of
  thread and time). An uncited claim is a defect, not a
  state, priced with the frozen duration.
- **Blocked-supervision** — a cited claim is verified
  against the verifications store (`attn verify
  status`); an unverifiable claim is void on detection
  and the lane resumes under its standing authorization.
  The rows are `blocked_uncited` and
  `blocked_unverified`. Blocked is a supervised state,
  not an exit from the ping set.
- **Unrouted defect** — a defect in one of the shared
  workhorse systems (scheduler, workbench/harness, the
  lease runner) is notified to its owning thread with a
  fix commission at diagnosis (`attn post item
  --workhorse/--notify-thread/--evidence`). A defect
  visible in a lane's record with no routed notification
  is an unrouted-defect row, escalating on the timed
  pattern and clearing when the notification exists, not
  when it is acked.
- **Stall pricing** — every stall-class row carries its
  stall duration (`stall_minutes`, measured from when
  supervision first saw the row) alongside the measured
  size of the work it interrupts (`jobs_run`, the
  workers fielded, and `expected_minutes` where a plan
  states one — unstated serves an honest null, never a
  guess).
- **Serial plan** — an adopted plan whose remaining
  steps are contract-independent and which fields fewer
  lanes than it has independent steps is an understaffing
  row at adoption time, read from the declared
  `steps_open` / `steps_independent` against live lanes;
  a plan with no declaration draws no row rather than a
  guessed one. (Serving plan step structure from the
  work record is the durable gap this family waits on.)
- **Owner-waiting** — a deliverable the owner
  commissioned and asked for by name is tracked apart
  from the lane queue, under an owner-waiting
  declaration (name + commission time) that a terminal
  status clears. Unstaffed one check cycle past
  commission, it is a defect row to main from the first
  digest; a status ask about one is priority traffic.

## 2. The owner-action surface (§1.13)

One owner-action endpoint replaces triage. Items carry
poster-attached options and a backend-served verb list
that the frontend renders verbatim; the endpoint records
the tap's verdict on the item — and, through its wait,
on the wait it stands for — immediately. Actions are
recorded on the item and in the handler's served action
log. Approving a wait creates its action rule active —
the one promotion that does not land in shadow — and is
refused absolutely on hard-stop classes, which can be
approved once, never ruled. Any other verb may be
promoted to a rule by a deliberate make-rule tap, and
every such promotion lands in shadow (the shadow-first
discipline). The seed rules evaluate as patterns: R1, a
defect item clears when its subject reaches a terminal
state; R2, a stale status draws a ping; R3, a
performance clearance is served as for-information, not
as a decision. The evaluated rule records themselves
stay engine data.

Reply routing is direct to the owning thread, with main
copied — there is no main triage step.

## 3. Queue semantics — decision is not fulfillment

(Owner rulings.)

- A decision and its fulfillment are separate events.
  The tap records the verdict at once; the card then
  moves to a visible **decided-awaiting-fulfillment**
  state carrying the pick, the time, and the fulfillment
  state, read from the send ledger or the act's own
  record.
- Fulfillment is verified, never assumed. A failed or
  stalled fulfillment returns the item to the queue with
  its history on its face.
- The decision is changeable while unfulfilled; after
  fulfillment, a change is a new item.
- Acting on a fulfilled item is refused (409).
- The decided band serves under `decided_count`; the
  stall bound for a decided item is 120 minutes;
  `decision_history` rides on the item's face.

## 4. Digest form

(Owner rulings.)

- The Digest is **live cards, generated and stamped on
  open**: each card carries its `generated_at` stamp,
  and its facts are measured at render time.
- The form is a social-app-style feed: a composer at the
  head, scoped by programme; one continuous stream of
  programme posts; an action row closing each post;
  replies open in place under the post they answer.
- There is **no reply box inside a post**. The earlier
  dashboard form — cards with an in-card reply box — was
  rejected and is not a variant.
