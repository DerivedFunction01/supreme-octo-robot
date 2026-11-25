# Review — owner-attention (superapp consolidation)

Findings first:

1. **The whole product is one process over one JSON
   dict.** A stdlib HTTP server whose every request and
   both background loops load → mutate → save a single
   state dict (atomic `.tmp` + rename). There are no
   internal served shapes: the evaluator, the digest
   builder, the dispatch consumer, and the Today builder
   all read and write the same dict under one lock. The
   pipeline/app split is real only at the HTTP seam —
   consolidation must *introduce* the internal seams, not
   find them: evaluator, dispatch, work record, and fact
   measurement become pipeline services; glance, Today,
   Digest, and the handlers surface become the attention
   app over their served shapes.
2. **Every registry attention owns is runtime state in
   that one untracked file.** Handlers, programmes,
   rules, templates, status codes, wait classes, item
   kinds, action rules — all live in the single state
   store, written through the API, seeded from code
   defaults plus backfill. There is no tracked live
   registry, no file form, and no seed/example for any of
   them; the demo seed is not a backup. A transplant that
   moves code without this file moves an empty product
   (the overlay capture is existential here —
   `docs/overlay/attention.md`).
3. **The evaluator is three things on three clocks, not
   one.** The staffing measure derives at Digest assembly
   (request time); continuation dispatch acts on the
   60-second tick; its inputs are collected on a slow
   loop: panel capacity, worktree presence, lane-record
   checkpoints, programme contracts. Its five inputs —
   armed rows, status posts, runner run records, panel
   capacity, lane record files — come from four repos'
   territory. The pipeline shape keeps the three clocks
   distinct.
4. **Dispatch is a ledger with four minters and one
   consumer, and the consumer's ordering is
   load-bearing.** Sends are minted by the wait-rule
   engine, owner verbs, handler actions, and the
   continuation pass — all through the one `record_send`
   surface into the one ledger. The consumer *settles*
   outstanding bridge records before claiming new ones,
   acks only on the bridge fulfillment's submission
   reference, and stamps a suppressed send's late
   fulfillment as fact rather than resurrecting it.
5. **From this side, the runner contact is two read
   seams, not attribution only.** The evaluator reads the
   runner's detached run records straight off its
   filesystem and the panel's served state. The join
   between run-record `caller` strings and attention
   topics is a prefix-naming convention, not a shared
   registry — exactly the seam the merged caller/routing
   registry exists to close (plan §4.1).

## The decision machinery

- **Verdict at the tap.** The verb is validated against
  the *served* verb set for that item (derived from
  kind, provenance, wait class, state; hard-stop classes
  never offer an approve-rule verb), the decision is
  recorded on the item and, through its wait, on the
  wait — and only then is the send written. Delivery
  never gates the decision. Replays are guarded twice:
  an idempotency key short-circuits, and a repeated tap
  on the standing decision records and sends nothing.
  Changing a *fulfilled* decision is refused — it is a
  new item.
- **Queue semantics.** A decision verb moves the card
  out of the open queue into the "Decided — awaiting
  fulfillment" band (states queued / sent / recorded).
  Fulfillment is derived, never assumed: for send-backed
  decisions, from the send ledger (delivered →
  fulfilled; a recorded dispatch failure → failed); for
  push items, from the scripted fact measurement.
  Unfulfilled past 120 minutes reads **stalled**. Failed
  and stalled items *return to the decision queue* with
  `decision_history` carrying each prior verdict and its
  outcome — the history rides on the item's face.
- **The wait side.** Waits are decided by the
  declarative engine: hard-stop classes are always
  surfaced, never auto-applied; rules match over poster
  fields plus server-derived values (age, repeat count,
  presence, handler status); dedupe keys on a fact hash
  of the wait's content. A surfaced wait becomes exactly
  one owner item. A terminal status post from the owning
  thread resolves its pending waits — an ack alone never
  does.
- **Reply routing (Decision 1).** The reply verb sends
  the verdict to the item's own handle and — unless the
  handle is main — a copy to main: direct to the owning
  thread, main copied. All sends, including owner verbs,
  go through the one ledger.
- **Presence.** Modes active / focus / away, with
  expectation text; expiry resolves **at read time** and
  the tick also flips it in state. The glance is
  presence-shaped; Today is not filtered at all — the
  presence asymmetry is contractual: the glance is
  presence-filtered, the decision queue never is.
- **Repetition proposes rules.** Counted taps per
  handler + class + verb surface a rule proposal at the
  threshold; promotion lands rules in shadow for every
  verb except wait approvals, which go active and are
  refused outright for hard-stop classes.

## Evaluation — the staffing/stall evaluator

**What it measures.** Rows derive at Digest assembly
from: the capacity snapshot (live sessions, running runs
per session, idle-since), run-record caller attribution
(longest-prefix match of caller against topic/handle
names; child workers = running callers that are not the
topic or its lane handles), status posts, armed rows,
worktree and record snapshots, owner-waiting
declarations, and undelivered supervision sends.

**Row classes** include: understaffed, fleet-idle,
record-gap, idle-unlanded, no-successor, phantom-stop (a
blocked-owner claim citing no owner message — priced
with frozen minutes, addressed to main),
blocked-uncited, blocked-unverified, unrouted-defect,
serial-plan (declared independent steps outnumber
fielded lanes — measured at adoption), owner-waiting and
owner-waiting-unanswered, armed-unposted,
unlanded-claim, unarmed-work, steer-undeliverable.

**Cadence rule.** The cadence is per-programme else the
service default. Two missed intervals is the recurring
bound: an armed row with no status post naming its todo,
a lane record whose latest conforming checkpoint line is
stale, an idle detector with no signal moved — each
fires at two intervals.

**Only a measure clears.** Rows are re-derived from
current evidence at every assembly; there is no ack path
in the evaluator at all. The only memory is first-seen
stamps used for stall duration and escalation timing; a
row the measure no longer raises disappears and its
stamp is deleted. A row escalates to main when its age
passes the programme's escalation bound; phantom-stop
and steer-undeliverable escalate immediately;
owner-waiting rows are addressed to main from the first
cycle past cadence.

**Worktree presence.** Every declared programme's
worktree roots are measured (tip, dirty, landed = HEAD
is ancestor of main). A terminal claim beside unlanded
trees is an unlanded-claim row — the claim is reported
against the tree, not taken; standing trees with no
armed row and no live lane are unarmed-work.

**Continuation (the evaluator acting).** On the tick,
trigger rows, stalled fulfillments, and idle programmes
convert into continuation sends through the ledger,
repeating on the programme's cadence until the measure
clears; a prior undelivered ping blocks a twin mint;
void blocked claims also raise defect items. Pings to
retired handlers are never minted.

## Dispatch — the in-service dispatch consumer

- **The ledger.** One sends list. A send carries its id
  (`sNNNN`), rule, wait, handle, target, template and
  version, attempt, presence, text, fact hash, mode
  (active|shadow), outcome, and dispatch subrecord.
  Shadow sends are never dispatchable.
- **Lifecycle.** Undispatched → claimed (one attributed
  consumer, 15-minute lease, attempts incremented;
  expiry applied **at read time**, no sweeper) →
  delivered, only via ack by the claiming consumer
  before expiry **carrying the delivery reference**.
- **Suppress.** A first-class verb: retires a send to
  terminal not-dispatchable with a mandatory reason on
  the record; a delivered send cannot be suppressed. The
  consumer itself suppresses on bridge-retired records
  and on attempts exhausted.
- **Target resolution.** At mint: template audience main
  → main; else the handler's thread, else the handle; an
  escalate-after guard retargets to main. At delivery,
  the target maps through the handler registry to its
  thread; an unresolvable target records the failure —
  targets are never guessed.
- **The consumer pass.** **Settle first** — for every
  send with an outstanding bridge record, fetch it: done
  with a submission reference → ack with that reference
  (a send suppressed while outstanding is stamped
  delivered as fact, never resurrected); queued →
  re-claim if the lease lapsed, wait; missing/failed →
  record the failure, release the claim (a "retired"
  reason → suppress, terminal). **Then claim +
  enqueue**, capped per pass, attempts capped, then
  parked + suppressed with the reason on the record.
  Settle-first ordering and the suppressed-but-fulfilled
  edge are contract, not implementation detail: a merged
  consumer that enqueues first, or resurrects suppressed
  sends, reintroduces the twin-send class.
- **The bridge hop.** Delivery rides the scheduler's
  harness connector with envelope
  `attn-<send-id>-a<attempts>` — the bridge dedupes per
  caller + envelope, so retries cannot double-post — and
  framing carried as record data. The caller token is
  read from its file on every call and never enters
  state; no token → the consumer quietly does nothing.
- **Failures are records, never acks.** Failure entries
  deduplicate to one per hour per send + reason; an
  undelivered failure against an understaffed topic
  surfaces as a steer-undeliverable staffing row
  addressed to main.

## Cross-cutting contracts designed locally

- **The handler registry.** Handle → thread is the
  routing half; programme membership lives on the
  programme declaration's handles list, not on the
  handler. Written only through the API (upsert, omitted
  fields preserved). **Untracked and unseeded**: the live
  registry exists only inside the state store; the
  tracked demo seed is a different, smaller set. No file
  form exists — the registry has never lived outside the
  store. The merged contract therefore carries an
  explicit store-migration + seed/export step, or the
  directory is lost in transit.
- **The programme registry** (the supervision directory
  proper). Declarations carry slug, label, handles,
  cadence, staffing band, escalation bound, venue,
  worktree roots, record locations, contract path, and
  settled rulings. Cadence, band, escalation, and venue
  are declarations, never evaluator constants. Two
  fields are *sourced*: rule text and cadence refresh
  from the work-record-carried goal contract at the
  contract path — the goal record owns the contract
  fields, the programme registry is its directory
  projection.
- **The armed-row consumption contract.** Rows are
  globbed from the armed dir on every tick. Join keys:
  `(project, todo)`. A row must carry project and todo or
  it is skipped; fixture-class rows **never supervise**.
  Rows appear by existing and retire by disappearing;
  ingest stamps are preserved across syncs.
- **Status-post ingestion.** The grouped form is
  validated (a group the state does not call for is
  absent, never empty-filled); refs are **references
  only** — no todo state is accepted or stored;
  owner-waiting is a sticky declaration surviving later
  posts until an explicit clear or a terminal status.
  Decision posts must carry their options or are
  refused; defect routing, when present, is
  shape-validated.
- **Vocabulary registries.** Status codes, fields, wait
  classes, templates, item kinds, action rules — all
  state-resident, owner-writable at runtime, seeded from
  code defaults with backfill for late-arriving seeds.
  The status-code registry carries the task-mode
  vocabulary with per-code need and terminal semantics.
  Hard-stop wait classes are named in code and are not
  editable through the write surface. Under the
  consolidation the vocabulary write surface homes in
  the pipeline: vocabulary edits are pipeline registry
  writes and apps stay render-only (plan §4.6).
- **Seed/example pattern — the weak sibling.** Settings
  are env-only; there is no tracked example for the
  store, the handlers, or the programmes. Against the
  platform config pattern (plan §4.4), attention is the
  repo with nothing to contribute and everything to gain.

## Overlaps with the other three, from this side

- **Scheduler.** (a) *Delivery substrate*: attention
  owns the send ledger and consumer; delivery rides the
  scheduler's harness connector bridge and then the
  scheduler-side bridge queue/wake/drain machinery. Two
  queues in series, two records of one send, joined by
  the bridge request id. (b) *Routing knowledge
  duplicated*: the destination chat is resolved here
  from the handler registry, and again scheduler-side
  from its routing config when the wake minter works the
  bridged record. (c) *Wake territory*: the scheduler
  outbox mints pings; attention mints its own
  continuation and supervision sends through its ledger
  — the same functional territory, two minters.
  (d) *The healthcheck*: a scheduler job probes this
  service's health route. (e) The survival contracts
  (watchdog ladder, stackdump) live here in the same
  named form the scheduler review saw referenced
  externally.
- **Workbench.** (a) *Armed rows*: producer there,
  consumer here — confirmed field-for-field, including
  the fixture exclusion both sides honor.
  (b) *Classification feed*: pulled at read time for
  every status post carrying refs; disagreements are
  served as conflict data — posted refs are never
  resolved into stored todo state. (c) *Digest pulls*:
  parked plans and newest-plan-modified stamps come from
  live workbench reads at Digest assembly; in the target
  structure that pull is a work-record pipeline feed, or
  the app keeps a private workbench client and the
  overlap survives consolidation. (d) *Goal contracts*:
  programme declarations source rule text and cadence
  from work-record-carried contract files — attention's
  registry already defers part of its truth to the work
  record. (e) *Status vocabulary*: attention's registry
  is a runtime-extensible copy of the vocabulary the
  consolidation unifies; the checkpoint line format its
  record rows parse is the workbench's format.
- **Runner.** Read-only, but concrete: the evaluator
  reads detached run records directly from the runner's
  results directory and capacity/specs from the panel's
  served API. Nothing here writes to the runner. The
  caller-attribution join is a naming convention over the
  runner's caller strings — the two registries have
  never shared a key (Finding 5).

## Preserve exactly

Nothing below is approximated, renamed, or "improved"
in transit:

- **The state store's discipline**: one JSON-shaped
  state, written atomically (`.tmp` sibling + rename);
  registry seeds appended when absent, never overwritten
  (backfill). The store's datetime decode heuristic (ISO
  strings restored on load) is a format coupling —
  carried or deliberately replaced, never drifted into.
- **Send record + dispatch subrecord shapes**, including
  mode/outcome (shadow sends never dispatch) and the id
  schemes (sends `sNNNN`; waits `wNNNN`; owner actions
  `oaNNNN`; items `handle:source_ref`).
- **Envelope form** `attn-<send-id>-a<attempts>` and the
  bridge meta shape (framing as record data, text digest
  included).
- **Delivered-only-on-reference**: no ack without the
  claiming consumer, a live claim, and the fulfillment's
  submission reference; claim lease 15 minutes, expiry at
  read time; failure records are never acks.
- **Suppress semantics**: terminal, reasoned, refused on
  a delivered send; a suppressed send's late fulfillment
  is stamped as fact, never resurrected.
- **Queue semantics**: verdict recorded at the tap; the
  decided band; fulfillment states (queued / sent /
  recorded / fulfilled / failed / stalled at 120
  minutes); failed/stalled return to the queue with
  decision history on the item's face; replay guards.
- **Reply routing**: direct to the owning thread, main
  copied — Decision 1.
- **Presence semantics**: modes, expectation text, and
  expiry resolved at read time; the glance/Today
  presence asymmetry.
- **The wait record** and its fact-hash dedupe; a
  surfaced wait becomes exactly one item; a terminal
  status post resolves waits, an ack alone never does.
- **Armed-row file shape, `(project, todo)` join, and
  the fixture exclusion** (the consumer half of the
  arming contract).
- **Status-post form**: grouped form with absent-not-
  empty groups; refs as references only; sticky
  owner-waiting declarations.
- **Programme declaration fields**, including
  contract-sourced rule text and cadence.
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

## Risks the consolidation carries

- **Overlay capture is existential** (Finding 2): the
  live handlers, programmes, rules, templates, vocab
  additions, presence, and queue exist only in the one
  store — migrate the file verbatim or the product
  restarts empty and the owner's runtime-written rules
  are gone.
- **The store's debris is not product state.** Working
  and build debris sits beside the data in the same
  tree; capture distinguishes data from debris or the
  mega repo inherits the debris as if it were records.
- **Single-lock assumptions.** The code's correctness
  leans on one process, one lock, load→mutate→save. Any
  pipeline/app process split introduces concurrency the
  derivations were never written against.
- **Paths out of the repo are data.** Run-records dir,
  programme worktree roots, record locations, and
  contract paths point into sibling repos and goal
  workspaces; they live in settings and registry rows,
  so a repo move silently re-points or breaks the
  evaluator's ground truth until they are re-based.
- **The bridge token is a file, not a registry entry.**
  The registry merge carries the token-caller nature
  (hash-only scheduler-side, raw token only in the
  untracked file) without absorbing the raw value into
  any tracked or stored form.
