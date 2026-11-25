# Workhorse superapp — consolidation plan

The four workhorses — scheduler, workbench, venue
runner, owner-attention — run consolidated in this repo:
a pipeline layer of engines bound by explicit contracts,
with four apps over it as views of one integrated
frontend. This document is the consolidation's governing
record: the decisions it was formed under, the target
structure as built, the preserve list, the contract
consolidations with their canonical owners, and the
owner's ruled decisions. It states the present; the
formation's step-by-step execution record is not carried
here. Source reviews: `docs/review/`. Overlay capture:
`docs/overlay/`.

Decisions first:

- **One integration pass, not a verbatim copy.** The
  reviews prove a copy loses the running system: the
  scheduler's deployed fleet was an untracked overlay its
  pinned tree lacked, the runner's live registries
  existed only on the machine, and the workbench's
  cross-repo write contracts are the real seams. The
  consolidation therefore ran overlay capture and
  contract consolidation before any tree moved.
- **The pipeline/apps line mostly ratifies splits the
  code already drew.** The scheduler was already engines
  under a server with a consumer viewer; the workbench
  was already one mutation path under a consuming
  surface; the runner panel already rendered only the
  lease core's served portions. The plan formalized those
  boundaries as pipeline contracts and moved the engines
  behind them.
- **Three platform services existed nowhere and were
  built, not found:** an automatic gate runner, a
  deployment/release record, and state-store backup
  (§5). A fourth — the unified state writer — generalizes
  the write discipline every workhorse had grown its own
  workaround for (§4.15).
- **Attention is designed into the structure.** Its
  registries had no file form and its pipeline/app split
  existed only at its HTTP boundary; §8 records the
  outcomes its integration settled.
- **Four decisions were genuinely the owner's** (§9) —
  everything else in this plan is settled by the rulings
  or the reviews. All four stand ruled.

**Scope fence:** only the four workhorses are members.
Other repos are clients of the four and kit consumers in
their own homes — no part of this structure touches them.

**Parallelization ruling (standing):** backend and
frontend work split in parallel over landed contracts;
plan numbering is not a dependency. Serial exceptions,
each with its named shared state: the contract freeze
itself (every lane consumes the contracts it writes);
the kit token source (one writer — all surfaces consume
its generated CSS); the scheduler state cutover
(single-writer — one engine against one registry/state
at a time; no lane ever runs a second engine against
live state); and the attention amendment ahead of the
dispatch finalization (attention is a dispatch consumer
and a status-surface owner; freezing either without its
delta reopens both).

## 1. Target structure

```
supreme-octo-robot/
  contracts/     the pipeline contracts of §4, as documents + schemas + fixtures
  pipeline/
    scheduling/  registry, catalog/adoption/drift, schedule math, engine, executor
    dispatch/    outbox + bridge queue + wake minter + messages/outbox (one substrate)
    venue/       lease core, run records, transport, gate policy, adapters/
      adapters/colab/   the Colab adapter
      adapters/local/   the local-machine adapter
    workrecord/  registry store, plans/bundles, progress derivation, arming writers
    evaluation/  classification feed, doctor, progress reporting
    attention/   evaluator, dispatch consumer, decision machinery, presence
    registry/    the one caller + routing registry
    gate/        the shared gate legs; the root check.py composes them
    platform/    ops service, unified state writer, harness connector,
                 gate runner, release record, backup, survival services
  apps/
    scheduler/   viewer client + host bridge binding over pipeline /api/v1 shapes
    workbench/   viewer sections/components over work-record served shapes
    runner/      panel over venue served portions
    attention/   Today/Digest/glance over evaluation + dispatch shapes
  artifact/      the one integrated frontend — the four apps as views
                 of a single client on the unified kit
  docs/          this plan, the reviews, the overlay capture record
```

- **Pipeline layer** carries the engines the four repos
  ran, plus the platform services, bound by the explicit
  contracts of §4. Backends do the work; apps consume
  served shapes.
- **The four apps** keep their domains and derivations.
  Each app's frontend is a consumer of pipeline-served
  shapes; each app's host bridge binding is an app-side
  deploy adapter over the loopback contract, not pipeline
  code. The frontend target is one integrated app
  (`docs/rulings.md` §1): a single shell on the unified
  kit, the four apps as views of the one client.
- **The kit's home is the spec-driven starter**: the
  Workhorse Kit v1 — the token source, the generator and
  its `--wb-*` naming map, the status table, the
  primitives — lives there. This repo consumes the kit as
  every other repo does; `kit/` here is a vendored copy,
  never edited directly. Adding a look stays a few file
  edits in the kit's home.
- **The original repos are archived as they are** now
  that this repo carries their work. colab-runner is
  explicitly untouched: the generic venue core lives here
  alongside it, and the Colab adapter replaces its use.

**Canonical owners** — because this is one superapp,
cross-cutting parts are unified under a single owner
rather than left as per-repo contracts (§4 names the
owner per entry):

| Contract / concern | Canonical owner |
|---|---|
| Caller + routing registry | pipeline registry |
| Machine-entry writer contract | pipeline scheduling engine |
| Registry entry format | pipeline scheduling engine |
| Supervision arming contracts | pipeline work-record service |
| Seed/example config pattern | pipeline platform config contract |
| Dispatch substrate | pipeline dispatch |
| Status vocabulary — semantics | pipeline |
| Status table — presentation | Workhorse Kit |
| Classified-catalog axes | pipeline scheduling engine |
| Spec/supervision generic text | spec-driven starter |
| Viewer shell + bridge adapter | Workhorse Kit (app-shell contract) |
| Portability/denylist seam | pipeline gate |
| Goal records and goal-owned machinery | pipeline work-record service |
| Venue records + placement | pipeline venue layer |
| Engine firing semantics | pipeline scheduling engine |
| Unified state writer | pipeline platform |
| Gate, denylist, and venv bootstrap | pipeline gate |
| Path derivation | per-package paths modules (§4.17); scanner: pipeline gate |

What each app retains as its own: **workbench** — todo/
plan/bundle records and board surfaces; **scheduler
app** — job entries authored by operators and the viewer;
**runner app** — lease panel surfaces; **attention
app** — Today/Digest surfaces and its decision queue
presentation.

## 2. Preserve list (hard constraints, consolidated from the reviews)

Nothing below is approximated, renamed, or "improved" in
transit; a change to any item is a separate ruling, not a
consolidation side effect. Per-system detail lives in the
reviews (`docs/review/`); the contracts (`contracts/`)
carry the operative clauses.

**Work record (workbench review):**
- File-todo format and id scheme: bundle layout
  (`.plans/<date>-<slug>/todos/*.md`, `finished/`), front
  matter (`id`, `title`, `status`, `created`, `updated`,
  `progress_check`, `progress_armed`; id regex
  `^t-[0-9A-HJKMNP-TV-Z]+$`; statuses
  `todo|doing|blocked|done`), unknown fields preserved
  losslessly, and the `progress-checkpoint: <ISO-8601> —
  <text>` body-line format with the 2-missed-intervals
  stall verdict.
- Registry unified schema, `registry.json` export shape,
  and the "data never migrates" rule: each project's
  registry DB stays in its owning repo; the mega repo
  inherits tooling, not data.
- The manifest (`workbench.yaml`) format, including its
  `catalog_*` classification fields.
- The two stores stay two stores: registry DB vs
  `.plans/` bundles are not conflated, and the
  registry-DB todo table stays link-only ("steps are
  never copied here").

**Arming contracts (workbench review):**
- The scheduler-entry YAML the harness writes per armed
  todo: filename `wb-progress-<project>-<todo-id>.yaml`,
  written through the one writer path (no migration
  stamp — presence in the store is admission),
  classified-catalog block, machine-form source stamp,
  `${WS}` anchors, delete-on-terminal.
- The attention armed-row JSON: filename
  `wb-armed-<project-slug>-<todo-id-lowercase>.json`, the
  row shape as written (handle = todo id, no guessed
  lane), atomic `.tmp` + rename, delete-on-terminal,
  whole-directory reconciliation.

**Scheduler (scheduler review):**
- Job ids (filename stem = entry id), the strict
  registry YAML subset and field semantics
  (unknown-field quarantine, secret-shape refusal), owner
  values (`goal:<slug>` / `none` + reason), and both
  `source` stamp forms.
- Catalog version 1, adoption rendering, the
  setup-coverage rule, drift semantics with its named
  volatile fields; classification evidence and the
  scripted/agent boundary; admission semantics — in the
  target, an entry fires iff its status is active and it
  stands in the pipeline registry store, whose one
  mutation path is the writer path; presence through
  that path is admission. The migration field family
  (`migrated`, `migrated_at`, `migration_note`,
  `proof_pending`) does not exist in the target format.
- Engine firing semantics: consume-before-run,
  missed-point collapse with counts, no self-overlap,
  last-good registry on parse failure, fail-safe halt on
  corrupt state, schema → restart → entries ordering (or
  a deliberate, named replacement).
- Ledger format: canonical sorted-key JSON per event,
  the event-kind vocabulary, the SQLite schema/indexes,
  JSONL export byte format with SHA-256 verification,
  import only into an empty store.
- Outbox ping shape, ids, states, coalescing by job +
  kind, wake-window discipline, explicit ack,
  void-on-entry-removal.
- HTTP routes and payload shapes for `/health`,
  `/pings`, `/ops`, `/api/v1`, `/tools`; ops error
  names/status mapping and staged-write semantics; the
  pinned `GIT_SSH_COMMAND` pair rule.
- Connector scopes, token-hash-only caller registry,
  fresh-read-per-call, ledgering of refusals, envelope
  idempotency, and the no-authority boundary (no tool
  approves, pushes, acquires a lease, or writes a
  calendar).
- Bridge record shape and the target-resolution rule:
  the destination chat is data inside a record; the wake
  address is a separate routing decision (drain home for
  `chat_send`).
- Body refs and ack-after-work discipline; the
  watchdog/keeper contract (external driver, presence
  before health, render-when-invalid, one ladder attempt
  per episode, health as the verdict); portability
  anchors (`${REPO}`/`${WS}`/`${HOME}`) and the
  no-machine-literals rule for tracked files.

**Runner (runner review):**
- Lease record JSON shape, per-session file naming
  (`var/lease-<session>.json`), the staged-sibling atomic
  write, and the `session-evidence-` projection.
- Run record shape, the three terminal states
  (`complete | failed | orphaned`), and the exactly-one
  `run-terminal` outbox event.
- Caller attribution semantics in full: flag over env,
  registry validation with machinery constants, lane
  suffixes, presented-but-unregistered refusal, absent =
  unattributed, `active` = detached-only, the claims
  journal.
- Placement: latest-deadline adoption, adoption-only
  pins, no pin in the run/gate funnel. Spend counted from
  the repo's own lease segments, never from
  account-balance deltas.
- Snapshot-bundle lineage: built on the origin lineage,
  size + SHA-256 recorded and verified, applied
  fast-forward-only.
- The seed/example config pattern itself: tracked
  fictional examples, untracked live files, gitignore
  entries that document why each live file is local.

**Attention (attention review):**
- The state store's discipline: one JSON-shaped state,
  written atomically (`.tmp` sibling + rename); registry
  seeds appended when absent, never overwritten
  (backfill). The store's datetime decode heuristic (ISO
  strings restored on load) is a format coupling —
  carried or deliberately replaced, never drifted into.
- Decision machinery: the verdict is recorded at the
  tap, validated against the served verb set; the decided
  card leaves the open queue into the "Decided —
  awaiting fulfillment" band (states queued / sent /
  recorded); fulfillment is derived, never assumed — from
  the send ledger for send-backed decisions, from the
  scripted push-fact measurement for push items;
  unfulfilled past 120 minutes reads stalled; failed and
  stalled items return to the decision queue with
  `decision_history` on the item's face; replay guards
  (idempotency key; a repeated tap on a standing decision
  sends nothing); a fulfilled decision is never changed —
  it is a new item.
- Reply routing: direct to the owning thread, main copied
  (`owner:reply-copy`) — Decision 1.
- Presence semantics: modes (active / focus / away) and
  expectation text, expiry resolved at read time; the
  glance / Today presence asymmetry (glance
  presence-filtered, the decision queue never).
- Send record + dispatch subrecord shapes, including
  `mode` / `outcome` (shadow sends never dispatch) and
  the id schemes (`sNNNN`; waits `wNNNN`; owner actions
  `oaNNNN`; items `handle:source_ref`). Envelope form
  `attn-<send-id>-a<attempts>` and the bridge meta shape.
- Delivered-only-on-reference: no ack without the
  claiming consumer, a live claim (15-minute lease,
  expiry at read time), and the fulfillment's submission
  reference; failure records are never acks.
- Suppress semantics: terminal, reasoned, refused on a
  delivered send; a suppressed send's late fulfillment is
  stamped as fact, never resurrected.
- The wait record and its fact-hash dedupe; a surfaced
  wait becomes exactly one item; a terminal status post
  resolves waits, an ack alone never does.
- The armed-row consumer half: file shape, `(project,
  todo)` join, fixture-class rows never supervise.
- Status-post form: grouped form with absent-not-empty
  groups; refs as references only; sticky `owner_waiting`
  declarations.
- Programme declaration fields, including
  contract-sourced `rule_text` / `cadence_minutes`.
- Staffing row kinds, labels, and escalation-memory
  semantics: first-seen stamps, per-programme escalation
  bound, only a fresh measure clears.
- Push-fact measurement: the five fact states (current /
  superseded / pushed / gone / unverifiable), measured
  titles, tick self-clearing on pushed/gone.
- Vocabulary registry contents as data: rules, templates
  (with versions), status codes, classes, kinds, and
  action rules the owner has written at runtime are
  records, not code — they migrate as data.

**Status vocabulary (all reviews):** the ruled entry
vocabulary (canonical / implemented / deferred /
unexplored / hard-gate / abandoned — changes only via a
mutation carrying a ruling note) and its token status
table (14 named statuses with hue, per-mode text, glyph,
description) are one contract in two files; both halves
move together or not at all.

## 3. Overlay capture — before any tree moves

The pinned trees were not the deployed systems. Each
repo got an overlay census and capture, read-only
against the source, with the captured material classified
(promote to tracked / live config under the seed/example
pattern / data, migrated verbatim / runtime state, not
carried / credential, reference only / debris, excluded).
The capture record — per-repo inventories, the
classification outcomes, and the standing findings —
lives in `docs/overlay/`. Two of its verdicts bind the
structure: the scheduler's captured registry validates
complete with the overlay applied where the bare pin
quarantines one entry, and attention's store migrates
verbatim or the product restarts empty.

## 4. Registry and contract consolidations

One entry per consolidation. All land as pipeline-layer
contracts in `contracts/`; `contracts/traceability.md`
traces every §2 preserve item to a contract clause.

1. **Caller + routing registry** — one pipeline contract
   (contract 01). Instances: the runner's caller registry,
   the scheduler connector's caller registry, and two
   caller→chat routing tables (the scheduler's wake-owners
   config and the runner's notify-routes). The merged
   contract keeps the three natures distinct — thread
   callers (operator-written), machinery callers (code
   constants), token callers (hash-only) — and the
   seed/example pattern intact. Attention's handler
   registry and programme registry join it (§8): neither
   had a file form — both were API-written rows in the one
   untracked store — so the contract carries an explicit
   store-migration + seed/export step, and the registries
   now have the seed/export form they never had. The
   programme registry (cadence, band, escalation, venue,
   roots) is the supervision directory; its
   contract-sourced fields (`rule_text`,
   `cadence_minutes`) are owned by the goal record (§4.11)
   and the registry is its directory projection.
   **Canonical owner:** the pipeline registry
   (`pipeline/registry`) — one directory for callers,
   handles, programmes, and caller→chat routing; all four
   apps consume it, none keeps a local copy.
2. **Machine-entry writer contract** — the scheduler
   registry has two machine writers: the workbench harness
   (`wb-progress-*`, machine-form source stamp) and the
   runner lease core (`colab-liveness-*`, entry deleted in
   the same call that deletes the lease record). One
   contract class for machine-rendered entries: stamp
   form, lifecycle owned by the writer, drift counted
   separately per writer. Machine renders are admitted by
   the writer-path write itself, as every entry is — there
   is no born-admitted exception and no migration stamp.
   **Canonical owner:** the pipeline scheduling engine —
   it owns the registry the entries land in; the workbench
   harness and the runner lease core are its two
   registered writers.
3. **Supervision arming contracts** — the workbench's two
   write-contracts (scheduler entries; attention armed
   rows, §2) are the pipeline's arming contract:
   doing-transition arms, terminal retires, sync failure
   never fails the todo write, fixture-class writers never
   write live. **Canonical owner:** the pipeline — the
   work-record service arms and retires; the workbench app
   owns the todo record, the pipeline owns the arm/retire
   act and both projections.
4. **Seed/example config pattern** — one platform config
   contract (contract 04) from the runner's five configs,
   the scheduler's config example, and the workbench's
   config + env examples: tracked fictional examples,
   untracked live files, precedence env > live > defaults
   with per-key source reporting. The contract fixes the
   one drift the reviews caught: the scheduler example's
   timezone default disagreed with its code default — one
   source names the default. The scheduler file registry
   homes under this pattern: the manifest is a live config
   under the seed/example pattern, and its check is an
   internal loop of the pipeline platform services, not a
   registry entry. **Canonical owner:** the pipeline
   platform config contract — each app keeps its own live
   config file; the pattern, precedence, and
   source-reporting are pipeline-owned.
5. **Dispatch substrate** — scheduler outbox + bridge
   queue + wake minter, and the workbench messages store +
   outbox + notify, merge into one pipeline dispatch
   contract (contract 05): ping kinds and lifecycle,
   coalescing, explicit ack, envelope idempotency,
   delivery audit in the ledger. Attention's dispatch
   expresses over this substrate (§8), with three clauses
   of contract rank: settle-first ordering (outstanding
   bridge records settle before new claims/enqueues) and
   the suppressed-but-fulfilled edge; the deduped failure
   record rides with the substrate; and the contract names
   the ledger + `record_send` minting surface with its
   four producer classes (wait-rule engine, owner verbs,
   handler actions, continuation) — not only the consumer.
   **Canonical owner:** the pipeline dispatch — the
   scheduler's outbox/bridge/wake substrate is the
   surviving base; the workbench message outbox retires
   into it; attention's dispatch expresses over it.
6. **Status vocabulary contract** — the SPEC vocabulary +
   the token status table + the scheduler's centralized
   outcome labels + the task-mode status vocabulary: one
   pipeline contract (contract 06), served ready; apps
   render, never re-derive. The vocabulary registry is
   owner-extensible at runtime in attention; under this
   entry's ruling the write surface homes in the pipeline:
   vocabulary edits are pipeline registry writes and apps
   stay render-only. **Canonical owner:** the pipeline for
   the semantics, served ready; the presentation form (the
   token status table) is owned by the kit.
7. **Classified-catalog contract** — the axes
   (origin/generality/use_case) are defined once (contract
   07), consumed by all four: the scheduler catalog, the
   workbench manifest template + validation, the arming
   writers' renders. **Canonical owner:** the pipeline
   scheduling engine — the catalog owner; the workbench
   manifest consumes its axes.
8. **Spec/supervision kit** — the repos' spec-sync blocks
   and the workbench context restatements of SPEC
   material: this repo carries the synced block once; the
   starter remains the canonical home of the generic text;
   the context restatements retire into pointers at the
   one text. **Canonical owner:** the spec-driven starter
   — canonical home of the generic text; this repo owns
   only its synced block.
9. **Viewer shell + bridge adapter contract** — four
   separate shells (workbench server + TS bridge + client,
   scheduler viewer's three-tree deploy, runner panel,
   attention's viewer) share one pattern: repo source →
   runtime mirror → Library artifact, a host bridge
   binding seam, bridge-down kept distinct from
   server-down. One app-shell contract (contract 09); each
   app's served shapes stay its own. **Canonical owner:**
   the Workhorse Kit / app-shell contract — kit-owned;
   each app owns its served shapes.
10. **Portability/denylist seam** — the scheduler's
    portability scanner and the runner's untracked
    denylist are one gate component class: tracked
    scanner, untracked personal-literal denylist, never
    the reverse. It lands in the gate (§4.16), not as a
    per-repo script. **Canonical owner:** the pipeline
    gate — one gate component; denylists stay untracked
    per deployment.
11. **Goal records and goal-owned machinery** — a goal
    is not a Muse system: there is no Muse-side registry
    to sync with, and no part of this structure reads or
    writes one. What a goal mechanically is, is a record
    plus its ping: a work record carrying the goal
    contract block (Objective / Complete when / Blocked
    only when / Continuation — the stall-prevention
    mechanism, riding the work record), created by wb for
    code-focused work or app-side for non-code purposes,
    and a ping or reminder armed as a scheduler entry.
    The merged contract (contract 11): the goal record is
    the top level of the work record (goal → bundles/plans
    → todos → arms); the contract block is a field of the
    record, not a file header that can diverge; the
    workspace (GOAL.md, files/, hidden_files/) is a
    projection of the record; goal-owned schedules are
    pipeline scheduling entries armed by the record itself,
    surviving any single app's registry; measurement is
    the one evaluator over the one store; continuation
    dispatch rides the one dispatch substrate (§4.5). The
    decoupling is load-bearing: stall prevention was
    hostage to a registry whose entries could vanish with
    their owner; in this structure the record and the job
    are the two homes, both pipeline surfaces, and there
    is nowhere else for a goal's terms to live.
    **Canonical owner:** the pipeline work-record service.
12. **Venue records and placement** — the runner's record
    shapes had no consolidation partner and freeze as the
    venue layer's own contract (contract 12): the lease
    record (shape, per-session naming, staged-sibling
    atomic write, the `session-evidence-` projection), the
    run record (shape, the three terminal states,
    exactly-one `run-terminal` outbox event), placement
    (latest-deadline adoption, adoption-only pins, no pin
    in the run/gate funnel) with spend counted from the
    repo's own lease segments, and snapshot-bundle lineage
    (built on the origin lineage, size + SHA-256 recorded
    and verified, applied fast-forward-only).
    **Canonical owner:** the pipeline venue layer — it
    writes and reads the records; the panel and the
    evaluator consume its served projections, never the
    files directly.
13. **Engine semantics** — the scheduler engine's firing
    semantics freeze as contract 13: consume-before-run,
    missed-point collapse with counts, no self-overlap,
    dispatch in entry-id order, last-good registry on
    parse failure, fail-safe halt on corrupt state, and
    the schema → restart → entries ordering (or a
    deliberate, named replacement). The migrated-only
    firing clause is NOT carried: in the target an entry
    fires iff its status is `active` and it stands in the
    pipeline registry store, which has exactly one
    mutation path (contract 02's writer path); presence
    in the store through that path is admission, and there
    is no directory-drop path for a flag to guard.
    Admission evidence (validation counts, proof outcome)
    is recorded as events in the dispatch/ledger store,
    not as fields on the entry. A change to any clause is
    a ruling, not a migration detail. **Canonical owner:**
    the pipeline scheduling engine — the contract's only
    implementer; every consumer of fired work reads its
    effects through the ledger (§4.5) and the entry format
    (§4.14).
14. **Registry entry format** — the scheduler job-entry
    format itself (contract 14): one file per job at
    `jobs/<id>.yaml`; the filename stem is the job id and
    an internal `id` field must match it; the strict
    registry YAML subset (nested maps by two-space
    indentation, scalar lists only, no anchors, flow maps,
    multiline strings, or lists of maps); unknown fields
    invalid and quarantined, secret-shaped values refused;
    the entry field forms as the schema of record defines
    them, including both `source` stamp forms — and NOT
    the migration field family (§2): the target format
    drops it, because in a repo built whole a field no
    entry lacks discriminates nothing, and its one real
    function, guarding admission, is carried by the single
    mutation path (§4.2). The `source` stamp is
    provenance, not a migration field, and stays. §4.2's
    two registered writers write this format, §4.7's
    catalog classifies it (the `catalog` block is one of
    its fields), §4.13's engine fires from it. A change to
    the format is a ruling, not a migration detail.
    **Canonical owner:** the pipeline scheduling engine —
    it owns the registry the entries land in and the
    validator that enforces the format.
15. **Unified state writer** — this machine denies writes
    in waves (the write-denial flap: `open('w')` denied
    from agent-class processes, `fsync` denied, a truncate
    that lands before the denial destroys the file;
    rename-over never denied, long-lived server processes
    never denied). Each workhorse grew its own workaround:
    the scheduler's `/ops` delegation, the workbench's
    synchronous file drops into sibling repos, the
    attention store's in-process atomic write, the
    runner's staged-sibling record writes. In one app the
    distribution is the defect: one unified writer in the
    pipeline platform (contract 15) performs every
    pipeline store write, every app state write, and every
    app-level file edit, through one atomicity protocol
    (stage to a fresh sibling, read-back verify,
    rename-over; no process ever opens a target for
    truncate-write), with every mutation attributed to a
    contract 01 caller and ledgered as an `op` event
    (contract 05). The operation set is the `/ops` set
    generalized (write, patch, cas-update, delete; `exec`
    stays contract 04's clause), the failure semantics are
    contract 04's closed error table reused whole, and
    compare-and-swap rides the stamps the served shapes
    already carry. Scope stops at this machine:
    venue-session files write locally there, other
    programmes' repos are never write targets, and
    developer shell writes are not app writes.
    **Canonical owner:** the pipeline platform — the
    scheduler `/ops` implementation is its base; every
    other store's writer re-points at it.
16. **Gate, denylist, and venv bootstrap** — per-repo
    check files are drift, and shared checks have one
    home. The shared legs consolidate into one gate
    package in the pipeline layer (`pipeline/gate`): the
    line cap (one enumeration), the portability/denylist
    component (§4.10's component, completed here — **one
    untracked denylist per deployment** feeds it; per-repo
    denylists retire), ruff format/lint, the policy
    scanners, the test-isolation state hash, and
    **AST-based test targeting** — an AST dependency
    lineage from changed files to the tests that exercise
    them, `--explain`-able — which is what lets a mega
    repo run a change-aware gate instead of every suite on
    every change. The venv bootstrap consolidates the same
    way: one `find_uv` and one builder, parameterized by
    per-package config. What stays per-package is a
    **declaration**, not a script: each package names the
    shared legs it runs plus its own legs. One root check
    at the repo root (`check.py`) composes the set for a
    package, a pathspec, or the union tree. The per-package
    check files retire when the composed gate proves
    parity — no shims. **Canonical owner:** the pipeline
    gate — the gate runner (§5) executes this gate and
    records verdicts against tree SHAs; it does not invoke
    four drifting files. Proof burden: verdict parity —
    the composed gate reproduces each package's gate
    verdict on the current tree, red where red, green
    where green.
17. **Path discipline.** Path derivation has one home
    per package: a foundation paths module at the package
    root (anchored on the package's own file spine) plus
    per-area resolver modules where the package's size
    warrants, and every consumer importing its paths from
    them — no module writes its own root arithmetic, and
    no path component is written as a fresh literal where
    a paths-module value covers it. Module-relative
    resource reads (a file reading its own sibling asset)
    are the one declared exception form. The pipeline gate
    owns the enforcement: a paths-discipline scanner leg
    fails fresh root/path arithmetic outside the paths
    modules. **Canonical owner:** each package owns its
    paths modules; the pipeline gate owns the scanner.
    Proof burden: a resolved-path census per package,
    identical before and after any re-pointing, with the
    package suite green at its count — the same
    result-preserving standard as every other
    consolidation here.

## 5. Platform services

The services that exist nowhere in the source repos live
in `pipeline/platform` (the gate runner executes the
pipeline gate of §4.16):

- **Automatic gate runner.** Runs a repo's gate on its
  venue automatically at the points the pipeline already
  knows — formation, landing, stage deploy — and records
  the verdict against the tree SHA. For the shared legs
  the gates themselves consolidated first (§4.16): the
  service runs the one composed gate, and the per-repo
  check files retired at the consolidation.
- **Deployment/release record.** Every deploy writes an
  entry (repo, commit, artifact, stage, time, result)
  into a pipeline store, tying artifact ↔ repo commit ↔
  stage; each app's deploy path refuses to report success
  without its entry, and a drift check with no entry reads
  as undeployed, not as deployed.
- **State-store backup.** Scheduled, integrity-verified
  snapshots of the stores that had no backup story — the
  ledger (via its own export + SHA-256), outbox, next-due,
  live config, bridge records, per-project registry DBs,
  the venue state, and the live registries of §4.1 — to a
  home outside the repos, proven by restore drills: one
  store of each class restored into a scratch home and
  read back by its own pipeline module.
- **Unified state writer.** §4.15's service: one wrapper
  performs every pipeline store write, app state write,
  and app-level file edit on this machine through the
  stage-verify-rename protocol, caller-attributed and
  ledgered, so the write-denial flap is this service's
  problem and no other component's. Its proof is the
  flap drill: under an injected denial, every refused or
  interrupted write leaves its target byte-identical to
  its pre-state, a writer killed mid-stage leaves no torn
  target, a stale-stamp cas-update is refused whole, and
  the ledger carries every attempt with its caller and
  result.
- **Survival services (homed here, not built new).** The
  watchdog/keeper ladder, the stackdump watchdog, and the
  file-registry check are platform services whose
  contracts freeze in contract 04; their registry-entry
  forms retire into internal loops of the platform
  services, and their external registrations are
  platform-owned.

## 6. Venue keying and the runner extraction

The runner genericizes by extraction; the colab-runner
repo is not edited. The outcomes:

- **Venue key on records.** Lease records, run records,
  and every served panel portion carry a `venue` key;
  session identity is venue-qualified so a second venue's
  names cannot collide with Colab's. Legacy records —
  every record written before the key existed — were
  stamped `venue: colab` in a one-time migration (§9,
  decision 3): no read-time default exists in the reader.
- **Funnel dispatch.** The adapter seam is the funnel
  callable the lease core receives by injection:
  extraction puts a per-venue dispatch behind that
  callable, plus a per-venue shape catalog (replacing
  help-text parsing for new venues; the Colab catalog
  keeps its parser) and a per-venue stop/exec verb set.
  The lease core does not change shape.
- **Colab payload stays with the adapter.** The bridge
  (hash-signed command queue), endpoint host-grammar
  shape reading, snippets, probes, and the repo's own job
  manifests are Colab-adapter material, never core. The
  OAuth token guard is adapter-side auth at the funnel.
- **Panel venue-keyed.** Served portions carry venue; the
  panel renders the mixed fleet as one fleet with venue
  named on every record — anything that cannot name its
  venue is a defect.
- **Registries re-homed.** The caller registry leads
  (§4.1); lease config and the repos registry follow under
  the §4.4 config contract, their untracked-live nature
  intact. The liveness-entry generator is a pipeline
  writer under §4.2, writing into the pipeline's own
  scheduler registry.

The fleet today is local machines and Colab sessions as
peers under this layer (`pipeline/venue/adapters/local/`,
`pipeline/venue/adapters/colab/`).

## 7. The integrated frontend

The four app frontends build against the frozen contracts
first — each against a stateful mock adapter behind its
data seam: every storyboarded control works end-to-end
against the mock store (state changes, flows, validation),
never a static frame; mock payloads are generated from the
contracts' schemas and fixtures and validated against the
schemas in the build. Each app's live landing then swaps
the mock adapter for the live one with no frontend
rewrite. Deploys carry no built-in gate — gating is the
caller's step — and each deploy writes its release-record
entry (§5).

The result is the one integrated app of `docs/rulings.md`
§1: a single shell on the extracted kit, re-tokened on
Workhorse Kit v1, with the scheduler app over pipeline
`/api/v1` shapes, the workbench app over work-record
feeds, the runner app over venue-keyed portions, the
attention app (glance, Today, unified triage) over
evaluation + dispatch shapes, and unified Settings —
the four apps as views of the one client in `artifact/`,
never four separate frontends.

## 8. Attention — integration outcomes

Attention's integration settled against §4 without
reopening a pipeline contract:

- **Structure — the split is cut, not found.** Attention
  was one process over a single JSON state dict; the
  evaluator, the digest builder, the dispatch consumer,
  and the Today builder read and wrote the same dict
  under one lock, and the pipeline/app split existed only
  at its HTTP boundary. The seams are cut along the
  review's call sites: evaluator, dispatch, work record,
  and fact measurement are pipeline services
  (`pipeline/attention`, `pipeline/evaluation`,
  `pipeline/dispatch`); glance, Today, Digest, and the
  handlers surface are the attention app over their
  served shapes. Two derivations that sat surface-side
  are engine in nature and live behind pipeline feeds:
  push-fact measurement and Digest's workbench pull.
- **Registry (§4.1): confirmed, with the form delta
  carried.** The handler registry is the shell's
  programme/lane directory and the dispatch target
  source; the programme registry is the supervision
  directory proper. Both had no file form; the merged
  contract's store-migration + seed/export step (§4.1)
  is how they landed, re-seeded from the overlay capture.
  The goal record owns the contract fields; the programme
  registry is its directory projection — declaration
  fields live in the registry, contract fields are
  sourced from the record, never duplicated.
- **Dispatch (§4.5): confirmed over the substrate, three
  contract additions.** Settle-first ordering and the
  suppressed-but-fulfilled edge are contract (§4.5); the
  deduped failure record rides with the substrate; the
  contract names the ledger + `record_send` minting
  surface with its four producer classes — owner verbs
  and continuation mint above the substrate, not beside
  it.
- **Evaluator as pipeline: confirmed, five inputs, three
  clocks.** The evaluator reads five inputs — armed rows,
  status posts, programme declarations, runner run
  records + panel capacity, and lane record/worktree
  snapshots. The snapshot contracts (capacity, worktree,
  record, armed) are pipeline feeds; the evaluator's one
  piece of state — first-seen/escalation memory — is
  pipeline-owned state. Its three clocks stay distinct:
  measure at Digest assembly, act on the tick
  (continuation), collect on the slow loop.
- **Today/Digest as surfaces: confirmed, asymmetry
  contractual, one relocation.** The presence asymmetry
  is contractual: the glance is presence-filtered; the
  decision queue never is. Digest's live workbench pull
  is a work-record pipeline feed; the attention app keeps
  no private workbench client.
- **Status vocabulary (§4.6): the `/vocab` write surface
  homes in the pipeline.** Vocabulary edits are pipeline
  registry writes; apps stay render-only. Hard-stop wait
  classes stay named in code and uneditable through the
  surface.
- **Decision machinery and presence/glance: confirmed as
  designed** — §2's attention preserve list carries them.

## 9. Decisions ruled by the owner

Short by design — only what the reviews could not settle
from the rulings. All four stand ruled; nothing in this
section remains open.

1. **`/ops` authentication posture.** The reviewed
   posture trusted a self-asserted `caller` string —
   attribution audited, not authenticated. **Ruled:
   harden to the `/tools` token model** — one pipeline
   change, every ops client issued a token; the one
   unauthenticated write/exec surface is closed.
2. **Retired-sweeper connector compatibility.** The
   connector served the retired approval sweeper's state
   file and nudge ledger at fixed workspace paths, with
   the retired schema inlined in scheduler code. **Ruled:
   retire** — the tools and the inlined schema leave with
   the scheduling move; the records stay on disk, unread
   by the pipeline.
3. **Legacy lease/run records' venue.** Every existing
   record lacked a venue key. **Ruled: stamp them in a
   one-time migration** — records rewritten once, no
   read-time default to outlive its truth (§6).
4. **Kit distribution to non-bun stacks.** Token
   consumption was the bun generator only. **Ruled: one
   generator in the kit's home; the generated CSS ships
   as the distribution and consumers take it checked-in.**
   The owner's correction to the framing stands: the
   consolidated repo is one repo with one `package.json`
   and one frontend build — generation is a single build
   step the backends never perform, so no per-stack fork
   exists inside the superapp.

## 10. Risks that still bind

- **Pinned tree ≠ live system** (all reviews): any work
  that starts from a tracked tree alone silently loses a
  live overlay. The overlay capture (§3) and the
  clean-and-pushed discipline exist to make that
  impossible; a step that skips either has failed by
  definition.
- **Overlay drift:** the scheduler engine rescans its
  registry continuously, so overlay edits change the
  running system outside git history. Capture is a census
  with a timestamp, and a cutover re-censuses immediately
  before it runs; a mismatch pauses the cutover — it does
  not get absorbed.
- **Split-brain:** consume-before-run protects one
  engine, not two. The scheduler serve is single-writer
  by design; no second engine ever runs against its
  registry/state.
- **Consolidating the wrong pair of stores:** the
  workbench has two todo stores and a third projection
  (scheduler entries). §2 keeps them distinct; a merge of
  the wrong pair corrupts the work record.
- **External registrations are not in any repo:** reaper
  and notify hooks, the keeper, and the liveness duties
  live outside the trees being consolidated. They are
  recorded in the capture (§3) and re-homed explicitly; a
  missed registration is a silent loss of a duty,
  discovered late.
- **Sibling-layout seams:** the arming writers and
  several consumers locate each other by
  workspace-relative paths and must keep working for
  external adopting projects with the harness absent.
  Internalizing the seams must not break external
  adopters.
- **Catalog fragility carries over:** the Colab shape
  catalog is parsed from CLI help text and the shape
  vocabulary is Colab-denominated (CU rates, `gpu`/`tpu`/
  `high_mem`). §6 contains this inside the adapter;
  budget semantics across a mixed fleet remain
  venue-denominated until a second venue forces the
  question (proven when a second venue exists).
- **Three-tree UI drift:** repo source, runtime mirror,
  and hosted artifact can diverge independently. §4.9's
  shell contract plus §5's release record are the cure; a
  stage is "live" only on a served check, not on a deploy
  script's say-so.

## 11. Supersession outcomes

The consolidation's fold, stated as the present surface:

**Registries.** The one pipeline registry (§4.1) holds
what six stores held apart: the scheduler connector
caller registry, the runner caller registry, both
caller→chat routing tables, and attention's handler and
programme registries. Attention's rules registry folds
into the evaluator's rule set; its templates migrate as
data; its vocabulary registry folds into the §4.6
vocabulary contract. The armed-row file registry is
abolished as a file drop — arming is pipeline-internal
state. The workbench per-project registry DBs stay in
their owning projects (data never migrates, §2); the
workbench server-local registry cache is abolished — no
cross-process cache registry exists in one app. The
runner's repos registry is the venue layer's repo set.
The scheduler file registry is homed under the platform
config pattern (§4.4): the manifest rides the
seed/example pattern and its check is a platform survival
loop, not a registry entry. **Survivors, transformed not
superseded:** the scheduler job registry is the pipeline
scheduling registry; the work-record stores are the one
work-record store's two halves (§2); lease/run records
are the venue-keyed store; attention's send ledger is
the dispatch ledger. The registry surface is four
stores: the directory registry, the scheduling registry,
the work-record store, and the venue store.

**Write paths.** Five mechanisms fold into the one
writer (§4.15): the scheduler `/ops` service as a
standalone per-repo service (its implementation survives
as the writer's base — the mechanism that retires is the
per-repo delegation form, not the code); the workbench's
cross-repo file drops (the arming act itself survives
under §4.3); the attention state store's in-process
writer; the runner lease core's record-writer helpers
(contract 12's shapes survive; the writer code folds);
and every per-app atomic-write helper, replaced by
wrapper calls under contract 15.

**Crons and jobs.** Of the scheduler registry's entries
at formation: the two machine-entry families
(`wb-progress-*`, `colab-liveness-*`) are not registry
entries in the target — arming and venue health are
internal pipeline acts; the cross-app watch/maintenance
jobs that existed only because the apps were separate
processes (per-app healthchecks, the per-app doctor,
file-registry check, stale-mockup cleanup, transient
restore, extend guard, store prune) are internal
health/maintenance loops of the pipeline services; the
dispatch pair (wake minter, drain) are pipeline dispatch
internals; the deployment self-watch jobs fold into the
platform services of §5. The client-work jobs migrate as
ordinary jobs, unchanged in substance. **The Muse cron
layer, as a class:** no harness motion lives in Muse
crons in this structure — every harness watch is a
pipeline scheduling entry armed by a record (§4.11
decoupling). Runtime system jobs (feed pulses, the
deterministic doctor) are not harness machinery and are
out of scope.
