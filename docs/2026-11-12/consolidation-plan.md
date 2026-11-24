# Workhorse superapp — consolidation plan (big-bang integration)

Decisions first:

- **One integration pass (D5), not a verbatim copy (D4).** The three
  reviews prove a copy loses the running system: the scheduler's
  deployed fleet is an untracked overlay its pinned tree lacks, the
  runner's live registries exist only on this machine, and the
  workbench's cross-repo write contracts are the real seams. This
  plan therefore runs overlay capture (§3) and contract
  consolidation (§4) *before* any tree moves, and the integration
  pass executes only from clean, pushed source repos (gate G1, §5).
- **The pipeline/apps line mostly ratifies splits the code already
  draws (D6).** The scheduler is already engines under `server/`
  with a consumer viewer; the workbench is already one mutation path
  in `lib/` under a consuming surface; the runner panel already
  renders only the lease core's served portions. The plan formalizes
  those boundaries as pipeline contracts and moves the engines
  behind them.
- **Three platform services exist nowhere and are built, not
  found:** an automatic gate runner, a deployment/release record,
  and state-store backup (§6). Each is its own step with its own
  done-evidence; the integration does not close without them.
- **Attention is designed into the structure now and reviewed
  later.** Its tree was mid-build when the review pass ran. §9 is a
  hard insertion point: the attention review + plan delta land
  before the integration pass executes, and the dispatch and status
  consolidations are written so its surfaces slot in without
  rework.
- **Four decisions are genuinely the owner's** (§10) — everything
  else in this plan is settled by the rulings or the reviews. The
  `/ops` authentication posture is the largest: today the caller
  string is self-asserted, and the plan does not inherit that
  silently.

## 0. Header — pins and the lane-split ruling

Baseline pins (owner's pinned-commit rule; every lane names its
pin in its step, §5):

| Source | Pin |
|---|---|
| scheduler | `cf910ce6a2b1c696bb7bcdbc5c9fe49460cea779` |
| workbench-viewer | `b0b9cc58b2cf6f0231173e659b2f9d38d12bec8c` |
| colab-runner | `636033be98405bab396329728b5d386a3c90a168` |
| owner-attention | `7f13ae797ca068a258b53054dc34a4e0df9c7fa2` |
| mega repo | `supreme-octo-robot` (this repo; reviews in `docs/review/`) |

**Runner baseline advanced for S5 (reconciliation,
2026-11-13):** one post-pin commit exists on the runner —
`8e9cb9b34bccf3022dd29bde696d6a80f55142e3` ("Standing
collector: stale detached runs collect on the reap cycle"),
pushed, tree clean, G1 unaffected. S5 executes against that
commit (the pin above stands as the review/S0–S2 baseline);
the other three repos carry no post-pin fixes (scheduler's
one post-pin change, the `scheduler.env` removal, is already
carried as S1 finding 2). Full record:
`reconcile-originals-report.md` in the build's hidden files.

**Re-pinned 2026-11-12, late evening (owner's direction — the
four repos stabilized after the day's fixes).** The reviews
were executed at the original pins (scheduler `196a29d…`,
workbench `fd870ae…`, runner `a11cbb4…`, attention `24ae5bc…`)
and their evidence stands at those trees; §9 keeps attention's
review pin as its record, and any step naming a pin by
reference takes the table above. The table is the execution
baseline set. Movement since the review pins is the day's fix
traffic: scheduler 6 commits (restart-reconcile, bridge-send),
workbench 2 (progress-check verdict context, plan-ref
resolver), runner 8+ (channel verdict, contention, census),
attention 2 (stamp-collection timeout, workbench stamps in
the idle signature). Scheduler's tracked tree is clean at its
pin; three untracked live-overlay job entries sit outside the
commit (`colab-store-prune`, `owner-attention-healthcheck`,
`restart-reconcile`) — overlay, captured per §3, not part of
the pin. G1 at this re-pin: the runner is clean and pushed
(local == remote); workbench clean, 5 ahead; attention clean,
4 ahead; scheduler 9 ahead — pushes remain the owner's word.

Source reviews: `docs/review/2026-11-12/review-scheduler.md`,
`docs/review/2026-11-12/review-workbench.md`,
`docs/review/2026-11-12/review-runner.md`. Pack rulings: seed plan
D1–D6, §2b (kit + scope fence), §3, §4, §5.

**Parallelization ruling (owner: backend vs frontend lanes split
in parallel once work is code edits; plan numbering is not a
dependency).** After the contract freeze (step S0), work runs in
three lanes concurrently — **pipeline** (engines, stores,
contracts), **backend** (served shapes, app server adapters),
**frontend** (kit, shell, app surfaces) — split over the landed
contracts in `contracts/`. Serial exceptions, each with its named
shared state:

1. **S0 contract freeze is serial by design** — every lane
   consumes the contracts it writes; nothing parallel can start
   from unfrozen shapes.
2. **`tokens/tokens.json` has one writer** (frontend kit lane,
   step S2) — all surfaces consume its generated CSS; parallel
   edits to the token source would fork the kit.
3. **Scheduler state cutover is single-writer** (step S11) — one
   engine against one registry/state at a time; two engines
   double-fire (scheduler review §7). No lane runs a second
   engine against live state at any point in this plan.
4. **The §9 attention amendment precedes the dispatch
   finalization inside S6 and the cutover S11** — attention is a
   dispatch consumer and a status-surface owner; freezing either
   without its delta reopens both.

Everything else parallelizes: S3/S4/S5 run concurrently once S0
lands; the three app builds in S8 run concurrently once their
served shapes land; §6 platform services build concurrently with
S3–S8.

Scope fence (§2b) holds throughout: only the four workhorses are
members. Other repos are clients of the four and kit consumers in
their own homes (kit-adoption queue: pinehollow-v2,
programme-b, pinehollow v1 if still live) — no step in this
plan touches them.

## 1. Target structure

```
supreme-octo-robot/
  contracts/     the pipeline contracts of §4, as documents + schemas + fixtures
  pipeline/
    scheduling/  registry, catalog/adoption/drift, schedule math, engine, executor
    dispatch/    outbox + bridge queue + wake minter + messages/outbox (one substrate)
    venue/       lease core, run records, transport, gate policy, adapters/
      adapters/colab/   the extracted Colab adapter (funnel dispatch, bridge, snippets)
    workrecord/  registry store, plans/bundles, progress derivation, arming writers
    evaluation/  classification feed, doctor, progress reporting
    platform/    ops service, unified state writer, harness connector,
                 gate runner, release record, backup, watchdog/stackdump/
                 file-registry survival services
  apps/
    scheduler/   viewer client + host bridge binding over pipeline /api/v1 shapes
    workbench/   viewer sections/components over work-record served shapes
    runner/      panel over venue served portions
    attention/   Today/Digest/glance over evaluation + dispatch shapes (§9 delta)
  docs/          this plan, the reviews, stage records
```

- **Pipeline layer** carries the engines the four repos run today
  plus the three missing platform services, bound by the explicit
  contracts of §4. Backends do the work; apps consume served
  shapes — the programme-a rule applied to the harness itself (D6).
- **The four apps** keep their domains and derivations. Each app's
  frontend is a consumer of pipeline-served shapes; each app's
  host bridge binding is an app-side deploy adapter over the
  loopback contract, not pipeline code.
- **The kit's home is the spec-driven starter** (§2b ruling): the
  Workhorse Kit v1 — `tokens.json`, the generator and its
  `--wb-*` naming map, the status table, the primitives — lives
  there, extracted from the workbench in step S2. The mega repo
  consumes the kit as every other repo does; it does not fork a
  private copy. Adding a look stays a few file edits in the kit's
  home.
- **The original repos archive as they are** once the mega repo
  carries their work (D4). colab-runner is explicitly untouched:
  the generic venue core is extracted alongside it (§7).

**Canonical owners** — because this is one superapp, cross-cutting
parts are unified under a single owner rather than left as
per-repo contracts (§4 names the owner per entry):

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
| Portability/denylist seam | pipeline gate runner |
| Goal records and goal-owned machinery | pipeline work-record service |
| Venue records + placement | pipeline venue layer |
| Engine firing semantics | pipeline scheduling engine |
| Unified state writer | pipeline platform |
| Gate, denylist, and venv bootstrap | pipeline gate |
| Path derivation | per-package paths modules (§4.17); scanner: pipeline gate |

What each app retains as its own: **workbench** — todo/plan/
bundle records and board surfaces; **scheduler app** — job
entries authored by operators and the viewer; **runner app** —
lease panel surfaces; **attention app** — Today/Digest surfaces
and its decision queue presentation.

## 2. Preserve list (hard constraints, consolidated from the reviews)

Nothing below is approximated, renamed, or "improved" in transit;
a change to any item is a separate ruling, not a consolidation
side effect.

**Work record (workbench review §7):**
- File-todo format and id scheme: bundle layout
  (`.plans/<date>-<slug>/todos/*.md`, `finished/`), front matter
  (`id`, `title`, `status`, `created`, `updated`, `progress_check`,
  `progress_armed`; id regex `^t-[0-9A-HJKMNP-TV-Z]+$`; statuses
  `todo|doing|blocked|done`), unknown fields preserved losslessly,
  and the `progress-checkpoint: <ISO-8601> — <text>` body-line
  format with the 2-missed-intervals stall verdict.
- Registry unified schema, `registry.json` export shape, and the
  "data never migrates" rule: each project's registry DB stays in
  its owning repo; the mega repo inherits tooling, not data.
- The manifest (`workbench.yaml`) format, including its
  `catalog_*` classification fields.
- The two stores stay two stores: registry DB vs `.plans/`
  bundles are not conflated, and the registry-DB todo table stays
  link-only ("steps are never copied here").

**Arming contracts (workbench review §3):**
- The scheduler-entry YAML the harness writes per armed todo:
  filename `wb-progress-<project>-<todo-id>.yaml`, written
  through the one writer path (amendment 3, 2026-11-13: no
  `migrated` stamp — presence in the store is admission),
  classified-catalog block, machine-form
  source stamp, `${WS}` anchors, delete-on-terminal.
- The attention armed-row JSON: filename
  `wb-armed-<project-slug>-<todo-id-lowercase>.json`, the row
  shape as written (handle = todo id, no guessed lane), atomic
  `.tmp` + `os.replace`, delete-on-terminal, `sync_all`
  reconciliation.

**Scheduler (scheduler review §6):**
- Job ids (filename stem = entry id), the strict registry YAML
  subset and field semantics (unknown-field quarantine,
  secret-shape refusal), owner values (`goal:<slug>` / `none` +
  reason), and both `source` stamp forms.
- Catalog version 1, adoption rendering, the setup-coverage rule,
  drift semantics with its named volatile fields; classification
  evidence and the scripted/agent boundary; admission semantics
  (validate → server-context proof → admitted by the write
  itself) and the machine-writer exception (amendment 3,
  2026-11-13: the stamp step and the born-admitted exception
  are dropped from the target — the writer path is the one
  mutation path, and presence through it is admission).
- Engine firing semantics: consume-before-run, missed-point
  collapse with counts, no self-overlap, last-good registry on
  parse failure, fail-safe halt on corrupt state, only
  `migrated: true` entries fire, schema → restart → entries
  ordering (or a deliberate, named replacement). (Amended
  2026-11-13, amendment 3: the migrated-only firing clause is
  replaced — in the target an entry fires iff its status is
  active and it stands in the pipeline registry store, whose
  one mutation path is the writer path; presence through that
  path is admission. The `migrated` field family does not
  exist in the target format.)
- Ledger format: canonical sorted-key JSON per event, the
  event-kind vocabulary, the SQLite schema/indexes, JSONL export
  byte format with SHA-256 verification, import only into an
  empty store.
- Outbox ping shape, ids, states, coalescing by job+kind,
  wake-window discipline, explicit ack, void-on-entry-removal.
- HTTP routes and payload shapes for `/health`, `/pings`,
  `/ops`, `/api/v1`, `/tools`; ops error names/status mapping and
  staged-write semantics; the pinned `GIT_SSH_COMMAND` pair rule.
- Connector scopes, token-hash-only caller registry,
  fresh-read-per-call, ledgering of refusals, envelope
  idempotency, and the no-authority boundary (no tool approves,
  pushes, acquires a lease, or writes a calendar).
- Bridge record shape and the target-resolution rule: the
  destination chat is data inside a record; the wake address is a
  separate routing decision (drain home for `chat_send`).
- Body refs and ack-after-work discipline; the watchdog/keeper
  contract (external driver, presence before health,
  render-when-invalid, one ladder attempt per episode, health as
  the verdict); portability anchors (`${REPO}`/`${WS}`/`${HOME}`)
  and the no-machine-literals rule for tracked files.

**Runner (runner review §7):**
- Lease record JSON shape, per-session file naming
  (`var/lease-<session>.json`), the staged-sibling atomic write,
  and the `session-evidence-` projection.
- Run record shape, the three terminal states
  (`complete | failed | orphaned`), and the exactly-one
  `run-terminal` outbox event.
- Caller attribution semantics in full: flag over env, registry
  validation with machinery constants, lane suffixes,
  presented-but-unregistered refusal, absent = unattributed,
  `active` = detached-only, the claims journal.
- Placement: latest-deadline adoption, adoption-only pins, no pin
  in the run/gate funnel. Spend counted from the repo's own lease
  segments, never from account-balance deltas.
- Snapshot-bundle lineage: built on the origin lineage, size +
  SHA-256 recorded and verified, applied ff-only.
- The seed/example config pattern itself: tracked fictional
  examples, untracked live files, gitignore entries that document
  why each live file is local.

**Attention (attention review §10):**
- The state store's discipline: one JSON-shaped state, written
  atomically (`.tmp` sibling + rename); registry seeds appended
  when absent, never overwritten (`backfill`). The store's
  datetime decode heuristic (ISO strings restored on load) is a
  format coupling — carried or deliberately replaced, never
  drifted into.
- Decision machinery: the verdict is recorded at the tap,
  validated against the served verb set; the decided card leaves
  the open queue into the "Decided — awaiting fulfillment" band
  (states queued / sent / recorded); fulfillment is derived,
  never assumed — from the send ledger for send-backed decisions,
  from the scripted push-fact measurement for `push_needed`;
  unfulfilled past 120 minutes reads stalled; failed and stalled
  items return to the decision queue with `decision_history` on
  the item's face; replay guards (idempotency key, repeated tap
  on a standing decision sends nothing); a fulfilled decision is
  never changed — it is a new item.
- Reply routing: direct to the owning thread, main copied
  (`owner:reply-copy`) — Decision 1.
- Presence semantics: modes (active / focus / away) and
  expectation text, expiry resolved at read time; the glance /
  Today presence asymmetry (glance presence-filtered, the
  decision queue never).
- Send record + dispatch subrecord shapes, including `mode` /
  `outcome` (shadow sends never dispatch) and the id schemes
  (`sNNNN`; waits `wNNNN`; owner actions `oaNNNN`; items
  `handle:source_ref`). Envelope form
  `attn-<send-id>-a<attempts>` and the bridge meta shape.
- Delivered-only-on-reference: no ack without the claiming
  consumer, a live claim (15-minute lease, expiry at read time),
  and the fulfillment's submission reference; failure records
  are never acks.
- Suppress semantics: terminal, reasoned, refused on a
  delivered send; a suppressed send's late fulfillment is
  stamped as fact, never resurrected.
- The wait record and its fact-hash dedupe; a surfaced wait
  becomes exactly one item; a terminal status post resolves
  waits, an ack alone never does.
- The armed-row consumer half: file shape, `(project, todo)`
  join, fixture-class rows never supervise.
- Status-post form: grouped form with absent-not-empty groups;
  refs as references only; sticky `owner_waiting` declarations.
- Programme declaration fields, including contract-sourced
  `rule_text` / `cadence_minutes`.
- Staffing row kinds, labels, and escalation-memory semantics:
  first-seen stamps, per-programme escalation bound, only a
  fresh measure clears.
- Push-fact measurement: the five fact states (current /
  superseded / pushed / gone / unverifiable), measured titles,
  tick self-clearing on pushed/gone.
- Vocabulary registry contents as data: rules, templates (with
  versions), status codes, classes, kinds, and action rules the
  owner has written at runtime are records, not code — they
  migrate as data.

**Status vocabulary (all three reviews):** the ruled entry
vocabulary (SPEC §5.1: canonical / implemented / deferred /
unexplored / hard-gate / abandoned — changes only via a mutation
carrying a ruling note) and its token status table (14 named
statuses with hue, per-mode text, glyph, description) are one
contract in two files; both halves move together or not at all.

## 3. Overlay capture — before any tree moves

The pinned trees are not the deployed systems. Each repo gets an
overlay census and capture, read-only against the source, with
the captured material classified (promote to tracked / keep as
live config under the seed/example pattern / runtime state, not
carried). Capture output lands in this repo under
`docs/overlay/` (inventories) with the promotable files held for
the G1 gate; nothing here edits a source repo.

**Scheduler** (review §1, §2, §4): ~40 live `jobs/*.yaml` entries
beyond the two tracked bridge entries; all `bodies/` (12,
including `bridge-drain.md`, `bridge-wake-item.md`, and the
routing config `bridge-wake-owners.yaml` misfiled among them —
capture separates config from bodies); the file-registry
manifest `registry/file-registry.yaml`; live `config.json`
(connector caller registry, Git SSH path pair); the local-only
`.git/info/exclude` entries themselves, enumerated — the exclude
file is part of the inventory of what is hidden, and it does not
travel with the repo; member scripts that exist only in the
overlay; the untracked `jobs/owner-attention-healthcheck.yaml`
in the working tree. State (`state/` stores) is not carried;
ledger history moves only via the manual JSONL export, decided
at capture time and recorded.
*Done-evidence:* the captured registry + bodies validate on a
fresh tree; the captured overlay must not quarantine any
entry. (Evidence correction, 2026-11-13, from S1's fresh-tree
validation: the earlier wording — the pin alone quarantines
the two bridge entries — overstated the loader. On the bare
pin the loader quarantines only bridge-drain (1 valid, 1
invalid — its body file does not exist); bridge-wake
validates on the bare pin — its missing wake body and owners
config are runtime dependencies the loader never checks, so
it is operationally incomplete on the bare pin, not
quarantined. The captured overlay completes both: 26 valid,
0 invalid.)

**Workbench** (review §2, §5): per-project registry DBs and
`registry.json` exports stay in their owning repos by the
preserve rule — capture inventories them and verifies the mega
repo's tooling reads them in place; live `config.json` and
`viewer.env` (specimens tracked); untracked `state/` runtime
files inventoried, not carried; `workbench.yaml` manifests of all
adopting projects enumerated (the sweep's view of the world at
capture time); templates (`manifest/`, `staging/`, `choice-kit/`)
are tracked and ride the tree.

**Runner** (review §4, §8): the five untracked live configs —
`config/callers.json` (14 thread callers, 3 marked `active`),
`config/lease.json`, `config/repos.json`,
`config/notify-routes.json`, `config/denylist.txt` — plus
`config/transient.json` and the auth-transient mirror; `var/`
lease records and `results/runs/` run records (machine-local
state: inventoried, re-seeded deliberately at cutover, never
assumed to ride a tree copy); the two registrations that live
outside the repo — the reaper hook and the notify hook in the
runtime's hook system — recorded with their current definitions
so §5 can re-home them explicitly.

**Attention** (attention review §1, §2, §11): capture is
existential here. Every registry attention owns — handlers,
programmes, rules, templates, vocab — plus presence and the
queue live only in the one untracked store
`var/data/state.json` (at review: 10 handlers, 3 programmes,
39 sends, 52 items); no registry has a tracked seed or any
file form. If that file is lost, every registry it owns is
lost with it — the store migrates verbatim or the product
restarts empty. Capture distinguishes data from debris:
`var/data`, `var/armed` (the workbench's machine-written
rows), and `var/connector` (the bridge token — a raw-token
live-config file, carried as a secret, never absorbed into
any tracked or stored form) are data; `var/xfer`,
`var/storyboard-build`, and `var/venv` are working/build
debris and are not captured. Paths out of the repo are data
too — `run_records_dir` and programme `worktree_roots` /
`record_locations` / `contract_path` in settings and registry
rows — inventoried so the steps can re-base them instead of
silently breaking the evaluator's ground truth.
*Done-evidence:* the captured store loads against the pinned
code and its counts reconcile with a live count taken at
capture time.

## 4. Registry and contract consolidations

One entry per consolidation; each names its source evidence.
All land as pipeline-layer contracts in `contracts/` (step S0
writes them; step S7 implements the merged code).

1. **Caller + routing registry** — one pipeline contract.
   Instances: the runner's caller registry (untracked
   `config/callers.json` + tracked fictional example +
   machinery-caller code constants; runner review §4), the
   scheduler connector's caller registry (token hashes + scopes,
   inside live `config.json`; scheduler review §2), and two
   caller→chat routing tables — scheduler's
   `bodies/bridge-wake-owners.yaml` and the runner's
   `config/notify-routes.json` (scheduler review §5; runner
   review §4). The merged contract keeps the three natures
   distinct — thread callers (operator-written), machinery
   callers (code constants), token callers (hash-only) — and the
   seed/example pattern intact. Attention's handle registry
   joins this contract at §9; it is the shell's programme/lane
   directory (§2 of the seed plan). Attention's two registries
   carry a form delta (§9.1): neither has a file form —
   handlers and programmes are API-written rows in the one
   untracked store (`var/data/state.json`), unseeded in tracked
   code — so the merged contract adds an explicit
   store-migration + seed/export step (§9). The programme
   registry (cadence, band, escalation, venue, roots) joins as
   the supervision directory; its contract-sourced fields
   (`rule_text`, `cadence_minutes`) are owned by the goal
   record (§4.11) and the registry is its directory
   projection.
   **Canonical owner:** the pipeline registry — one directory
   for callers, handles, programmes, and caller→chat routing;
   all four apps consume it, none keeps a local copy.
2. **Machine-entry writer contract** — the scheduler registry
   has two machine writers today: the workbench harness
   (`wb-progress-*`, source stamp: writer/project/todo/
   source_class) and the runner lease core (`colab-liveness-*`,
   entry deleted in the same call that deletes the lease
   record). One contract class for machine-rendered entries:
   stamp form, lifecycle owned by the
   writer, drift counted separately per writer (scheduler
   review §2, §5; runner review §6). (Amendment 3,
   2026-11-13: the born-admitted exception is retired —
   machine renders are admitted by the writer-path write
   itself, as every entry is.)
   **Canonical owner:** the pipeline scheduling engine — it
   owns the registry the entries land in; the workbench
   harness and the runner lease core are its two registered
   writers.
3. **Supervision arming contracts** — the workbench's two
   write-contracts (scheduler entries; attention armed rows,
   §2 preserve list) become the pipeline's arming contract:
   doing-transition arms, terminal retires, sync failure never
   fails the todo write, fixture-class writers never write live
   (workbench review §3).
   **Canonical owner:** the pipeline — the work-record service
   arms and retires; the workbench app owns the todo record,
   the pipeline owns the arm/retire act and both projections.
4. **Seed/example config pattern** — one platform config
   contract from five runner configs, the scheduler's
   `config.example.json`, and the workbench's
   `config.example.json` + `viewer.env.example`: tracked
   fictional examples, untracked live files, precedence env >
   live > defaults with per-key source reporting (scheduler
   review §2). The contract fixes the one drift the review
   caught: `config.example.json` says timezone `UTC`, the code
   default is `America/New_York`. The scheduler file registry
   (`registry/file-registry.yaml` — live manifest untracked,
   tracked specimen under `examples/file-registry/`, checker
   contract v1) homes under this pattern (§12's unhomed
   store, closed at S0): the manifest is a live config under
   the seed/example pattern, and its check becomes an
   internal loop of the pipeline platform services, not a
   registry entry.
   **Canonical owner:** the pipeline platform config contract —
   each app keeps its own live config file; the pattern,
   precedence, and source-reporting are pipeline-owned.
5. **Dispatch substrate** — scheduler outbox + bridge queue +
   wake minter, and the workbench messages store + outbox +
   notify (a dispatch/digest mechanism built earlier and
   independently), merge into one pipeline dispatch contract:
   ping kinds and lifecycle, coalescing, explicit ack,
   envelope idempotency, delivery audit in the ledger
   (scheduler review §2, §6; workbench review §3, §6).
   Attention's dispatch expresses over this substrate at §9
   rather than beside it. Its consumer contract adds three
   clauses (§9.2): settle-first ordering (outstanding bridge
   records settle before new claims/enqueues) and the
   suppressed-but-fulfilled edge are contract, not
   implementation detail; the deduped failure record rides
   with the substrate; and the contract names the ledger +
   `record_send` minting surface with its four producer
   classes (wait-rule engine, owner verbs, handler actions,
   continuation) — not only the consumer.
   **Canonical owner:** the pipeline dispatch — the scheduler's
   outbox/bridge/wake substrate is the surviving base; the
   workbench message outbox retires into it; attention's
   dispatch expresses over it.
6. **Status vocabulary contract** — SPEC §5.1 + the token
   status table + the scheduler's centralized `outcome_label()`
   + the task-mode status vocabulary: one pipeline contract,
   served ready; apps render, never re-derive (workbench
   review §4; scheduler review §2). The vocabulary registry
   is owner-extensible at runtime in attention today (a
   `/vocab` write surface; attention review §6). Under this
   entry's ruling the write surface homes in the pipeline:
   vocabulary edits are pipeline registry writes and apps
   stay render-only — resolved here (§9.5), not a §10
   decision.
   **Canonical owner:** the pipeline for the semantics, served
   ready; the presentation form (the token status table) is
   owned by the kit.
7. **Classified-catalog contract** — the axes
   (origin/generality/use_case) are defined once per surface
   today: scheduler catalog, workbench manifest template +
   validation, the arming writers' renders, SPEC §17. One
   definition, consumed by all four (scheduler review §2;
   workbench review §5).
   **Canonical owner:** the pipeline scheduling engine — the
   catalog owner; the workbench manifest consumes its axes.
8. **Spec/supervision kit** — the four repos' spec-sync blocks
   (`<!-- spec-sync:supervision-rules -->` in scheduler,
   workbench, runner) and the workbench `context/` six-file
   restatement of SPEC material: the mega repo carries the
   synced block once; the starter remains the canonical home
   of the generic text; the `context/` restatements retire
   into pointers at the mega repo's SPEC (all three reviews
   §4/§5).
   **Canonical owner:** the spec-driven starter — canonical
   home of the generic text; the mega repo owns only its
   synced block and its own SPEC.
9. **Viewer shell + bridge adapter contract** — four separate
   shells (workbench Python server + TS bridge + client,
   scheduler viewer's three-tree deploy, runner panel,
   attention's viewer) share one pattern: repo source →
   runtime mirror → Library artifact, a host bridge binding
   seam, bridge-down kept distinct from server-down. One
   app-shell contract; each app's served shapes stay its own
   (scheduler review §2; workbench review §3, §6; runner
   review §2, §6).
   **Canonical owner:** the Workhorse Kit / app-shell contract
   — kit-owned; each app owns its served shapes.
10. **Portability/denylist seam** — the scheduler's
    `tools/portability_scan.py` and the runner's untracked
    denylist are one gate component class: tracked scanner,
    untracked personal-literal denylist, never the reverse
    (scheduler review §4; runner review §4). It lands in the
    gate runner (§6), not as a per-repo script.
    **Canonical owner:** the pipeline gate runner — one gate
    component; denylists stay untracked per deployment.
11. **Goal records and goal-owned machinery** — a goal is
    not a Muse system (owner, 2026-11-12): the Muse goal
    registry was a shell with no effect — the owner removed
    the goals outright — and what a goal mechanically is, is
    a record plus its ping: a work record carrying the goal
    contract block (Objective / Complete when / Blocked only
    when / Continuation — adopted 2026-11-12 as the
    stall-prevention mechanism, riding the work record),
    created by wb for code-focused work or app-side for
    non-code purposes, and a ping or reminder armed as a cron
    in the scheduler. Today that spans five homes with no
    single owner: the GOAL.md workspace on disk, the contract
    block inside it, the workbench progress-check measurement,
    attention's continuation dispatch, and goal-owned
    scheduler crons.
    The split is measured, not theoretical (2026-11-12): the
    registry listed 15 active goals while 11 of their
    workspaces did not exist on disk (registry/disk
    divergence); when the owner deleted the goals, the jobs
    they owned died with them — the greenfield progress watch
    and the programme-a staffing reminder ceased to exist — so
    stall prevention was hostage to its owner's existence.
    The merged contract: the goal record is the top level of
    the work record (goal → bundles/plans → todos → arms);
    the contract block is a field of the record, not a file
    header that can diverge; the workspace (GOAL.md, files/,
    hidden_files/) is a projection of the record; goal-owned
    schedules are pipeline scheduling entries armed by the
    record itself, surviving any single app's registry;
    measurement is the one evaluator over the one store;
    continuation dispatch rides the one dispatch substrate
    (§4.5). Decoupling (owner, 2026-11-12): there is no
    Muse-side registry to sync with — the consolidation
    decouples goals from the Muse goal system entirely, and
    no part of the target structure reads or writes it. This
    matches main's two-homes plan, whose two homes are
    scheduler job definitions and workbench records — both
    pipeline surfaces in the target structure, so the
    contract ends up living in the record and the job,
    nowhere else.
    **Canonical owner:** the pipeline work-record service
    (the goal record is the top-level work record; its
    workspace and schedules are projections and entries armed
    by the record).
12. **Venue records and placement** — the runner's record
    shapes had no consolidation partner (no other repo keeps
    venue state) and so froze nowhere in §4.1–§4.11; S0's
    traceability returned them untraced. This entry freezes
    them as the venue layer's own contract: the lease record
    (shape, per-session naming `var/lease-<session>.json`,
    staged-sibling atomic write, the `session-evidence-`
    projection), the run record (shape, the three terminal
    states `complete | failed | orphaned`, exactly-one
    `run-terminal` outbox event), placement (latest-deadline
    adoption, adoption-only pins, no pin in the run/gate
    funnel) with spend counted from the repo's own lease
    segments, and snapshot-bundle lineage (built on the
    origin lineage, size + SHA-256 recorded and verified,
    applied ff-only) (runner review §7, §8). §7's venue
    keying builds against this entry at S5; the §10.3 stamp
    migration rewrites the legacy records it governs.
    **Canonical owner:** the pipeline venue layer — it
    writes and reads the records; the panel and the
    evaluator consume its served projections, never the
    files directly.
13. **Engine semantics** — the scheduler engine's firing
    semantics are the harness's load-bearing behaviour and,
    like the venue records, froze nowhere in §4.1–§4.11;
    S0's traceability returned them untraced. This entry
    freezes them: consume-before-run, missed-point collapse
    with counts, no self-overlap, dispatch in entry-id
    order, last-good registry on parse failure, fail-safe
    halt on corrupt state, and the schema → restart → entries
    ordering (or a deliberate, named replacement) (scheduler
    review §6; the pinned engine's EC-1–EC-11 semantics).
    The pinned set's migrated-only firing clause is NOT
    carried (amendment 3, 2026-11-13): in the target an entry
    fires iff its status is `active` and it stands in the
    pipeline registry store, which has exactly one mutation
    path (contract 02's writer path — validate under §4.14's
    format, server-context proof for hand-authored entries);
    presence in the store through that path is admission, and
    there is no directory-drop path for a flag to guard.
    Admission evidence (validation counts, proof outcome) is
    recorded as events in the dispatch/ledger store, not as
    fields on the entry. S3 moves the engine behind this
    contract; a change to any clause is a ruling, not a
    migration detail.
    **Canonical owner:** the pipeline scheduling engine —
    the engine is the contract's only implementer; every
    consumer of fired work reads its effects through the
    ledger (§4.5) and the entry format (§4.14).
14. **Registry entry format** — the scheduler job-entry
    format itself: one file per job at `jobs/<id>.yaml`;
    the filename stem is the job id and an internal `id`
    field must match it; the strict registry YAML subset
    (nested maps by two-space indentation, scalar lists
    only, no anchors, flow maps, multiline strings, or
    lists of maps); unknown fields invalid and
    quarantined, secret-shaped values refused; and the
    entry field forms as the pinned schema of record
    defines them (`jobs/README.md` and
    `server/registry.py` at the scheduler pin), including
    both `source` stamp forms — and NOT the migration field
    family (`migrated`, `migrated_at`, `migration_note`,
    `proof_pending`): the pinned schema of record carries it,
    and the target format drops it (amendment 3, 2026-11-13;
    presence in the registry store through the one writer
    path is admission, §4.2) — and the format half of the
    schema → restart → entries ordering (scheduler review
    §6; §2's SCH1 item). §4.1–§4.13 flank it without
    owning it: §4.2's two registered writers write it,
    §4.7's catalog classifies it (the `catalog` block is
    one of its fields), §4.13's engine fires from it, and
    the job registry §12 names a survivor — the store
    that becomes the pipeline scheduling registry — is
    where it lives. S0 carried the format as contract
    02's shared substrate so S3 could move it whole; this
    entry gives it a contract of its own (contract 14).
    S3 moves the registry behind it; a change to the
    format is a ruling, not a migration detail.
    **Canonical owner:** the pipeline scheduling engine —
    it owns the registry the entries land in and the
    validator that enforces the format; every writer,
    reader, and the engine itself conforms to it.
15. **Unified state writer** — this machine denies writes
    in waves (the write-denial flap: `open('w')` denied
    from agent-class processes, `fsync` denied, a
    truncate that lands before the denial destroys the
    file; rename-over never denied, long-lived server
    processes never denied — probed 2026-11-08, standing
    since). Each workhorse grew its own workaround: the
    scheduler's `/ops` delegation (write/patch/exec
    performed by the never-denied server process, staged
    and ledgered; scheduler review §2, contract 04), the
    workbench's synchronous file drops into sibling
    repos (scheduler YAML, attention armed-row JSON —
    §4.3's write-contracts, executed as direct file
    writes), the attention store's in-process atomic
    write (§2, contract 01's annex), the runner's
    staged-sibling record writes (contract 12). In one
    app the distribution is the defect: none of the four
    workarounds is needed *as a per-app mechanism* once
    the writes have one home. This entry generalizes
    §4.2's principle — the registry store's exactly one
    mutation path — from one store to all state: one
    unified writer in the pipeline platform performs
    every pipeline store write, every app state write,
    and every app-level file edit, through one atomicity
    protocol (stage to a fresh sibling, read-back
    verify, rename-over; no process ever opens a target
    for truncate-write), with every mutation attributed
    to a contract 01 caller and ledgered as an `op`
    event (contract 05). The operation set is the
    `/ops` set generalized (write, patch, cas-update,
    delete; `exec` stays contract 04's clause), the
    failure semantics are contract 04's closed error
    table reused whole, and compare-and-swap rides the
    stamps the served shapes already carry (contract
    11's per-row `version`, contract 09's config-view
    version stamp, the workbench editor's sha guard).
    Scope stops at this machine: venue-session files
    write locally there, other programmes' repos are
    never write targets (§2b), and developer shell
    writes are not app writes. Frozen as contract 15.
    **Canonical owner:** the pipeline platform — the
    writer is a platform service (§6, P4); the scheduler
    `/ops` implementation is its base, moved at S3 (the
    surviving-base pattern, as §4.5 took the scheduler
    outbox); every other store's writer re-points at
    its own step (S4, S5, S7).
16. **Gate, denylist, and venv bootstrap** — each
    workhorse maintains its own check file, and the
    legs that are the same leg already diverge: the
    800-line cap exists three times (the scheduler's
    `check.sh` over `git ls-files`, the workbench's
    `tools/length.py` inside its nine-leg
    `tools/check.sh`, dispatch's package-scoped `find`
    variant — one rule, three enumerations); the
    portability scanner lives in the scheduler while
    the runner keeps a separate untracked denylist
    for the same literals, and the other repos keep
    theirs; `find_uv` is duplicated between the
    workbench and attention `init_venv.py` files;
    attention's `check.py` carries the ruff / scanner
    / targeted-pytest shape a fourth way. The owner's
    ruling (2026-11-13): per-repo check files are
    drift, and shared checks have one home. The
    shared legs consolidate into one gate package in
    the pipeline layer: the line cap (one
    enumeration), the portability/denylist component
    (§4.10's component, completed here — **one
    untracked denylist per deployment** feeds it;
    per-repo denylists retire), ruff format/lint, the
    policy scanners, the test-isolation state hash,
    and **AST-based test targeting** — the programme-a
    `check.py` mechanism (an AST dependency lineage
    from changed files to the tests that exercise
    them, `--explain`-able), which is what lets a
    mega repo doing many things at once run a
    change-aware gate instead of every suite on every
    change; attention's path-mirror targeting is the
    weaker variant it supersedes for Python packages.
    The venv bootstrap consolidates the same way:
    one `find_uv` and one builder, parameterized by
    per-package config (venv location, Python spec,
    requirements source). What stays per-package is
    a **declaration**, not a script: each package
    names the shared legs it runs plus its own legs
    (scheduling's validate/census, the frontend legs
    served by the app suites and the kit contrast
    gate, the runner's `colab-check` venue funnel).
    One root check at the repo root composes the set
    for a package, a step's pathspec, or the union
    tree. The per-package check files retire when
    the composed gate proves parity — no shims.
    **Canonical owner:** the pipeline gate — §6 P1's
    runner executes this gate and records verdicts
    against tree SHAs; it does not invoke four
    drifting files. Proof burden: verdict parity —
    the composed gate reproduces each landed
    package's current gate verdict on the current
    tree, red where red (the `bin/sched` line-cap
    finding stands until that file's decomposition
    lands), green where green.

    17. **Path discipline.** Path derivation has one
    home per package, in the programme-a form: a
    foundation paths module at the package root
    (anchored on the package's own file spine) plus
    per-area resolver modules where the package's
    size warrants, and every consumer importing its
    paths from them — no module writes its own root
    arithmetic, and no path component is written as
    a fresh literal where a paths-module value
    covers it. Module-relative resource reads (a
    file reading its own sibling asset) are the one
    declared exception form. The pipeline gate owns
    the enforcement: a paths-discipline scanner leg
    fails fresh root/path arithmetic outside the
    paths modules. **Canonical owner:** each package
    owns its paths modules; the pipeline gate owns
    the scanner. Proof burden: a resolved-path
    census per package, identical before and after
    the re-pointing, with the package suite green at
    its count — the same result-preserving standard
    as every other consolidation here. (Added by
    amendment 6.)

**Amendment (2026-11-13, owner's word):** entries 12 and
13 were added after S0's traceability
(`contracts/traceability.md`, findings F1–F3) returned five
§2 preserve items with no carrying clause (SCH3, RUN1,
RUN2, RUN4, RUN5) and two partial traces (SCH6, SCH9). §4
had thirteen entries from this amendment. The same pass
homed the partial halves in the existing contracts: the
`/ops` payload semantics and the watchdog/keeper contract
in contract 04 (the platform contract; the keeper's build
homes in §6's platform services), and the `/api/v1` view
shapes in contract 09. All 36 §2 preserve items now trace
to a contract clause.

**Amendment 2 (2026-11-13, owner's ruling):** entry 14
was added on contract 02's substrate note, which recorded
that §4 assigned the registry entry format no entry of
its own — §4.2 and §4.7 flanked it (the writers and the
catalog) while S3 was to move it as a shared substrate.
The owner ruled the format gets its own entry and
contract (contract 14), with the pipeline scheduling
engine as canonical owner. §4 has fourteen entries from
this amendment.

**Amendment 3 (2026-11-13, owner's ruling):** the
migration field family (`migrated`, `migrated_at`,
`migration_note`, `proof_pending`) does not exist in the
target registry entry format or its semantics (§4.2,
§4.13, §4.14 and §2 amended; contracts 02, 03, 07, 09,
13, 14). The basis, paraphrased from the ruling: in a new
repo built whole, a field no entry lacks discriminates
nothing — all 26 live entries carry `migrated: true`, and
the machine writers stamp it unconditionally at birth —
and its one real function, guarding admission, is carried
by the target's single mutation path: an entry stands in
the pipeline registry store only by being written through
contract 02's writer path (validate under §4.14's format,
server-context proof for hand-authored entries), so
presence is admission and there is no directory-drop path
for a flag to guard. Admission evidence rides the
dispatch/ledger store as events, not entry fields. The
`source` stamp is provenance, not a migration field, and
stays. The live scheduler keeps its fields untouched —
this binds the target format and semantics at S3.

**Amendment 4 (2026-11-13, owner's ruling):** entry 15
was added on the owner's word that the machine's
file-writing flaws are one component's problem in the
consolidated app: the per-workhorse workarounds the
flap forced (scheduler `/ops` routing around workbench
file truncation, runner lease-core record writers,
attention's in-process store writer, the workbench's
cross-repo drops) have no reason to survive as four
mechanisms when there is one app and one pipeline. The
amendment adds §4.15 + contract 15 (canonical owner:
the pipeline platform), the §1 owners-table row, §6's
P4 service, and the §12 write-path fold; §1's structure
line names the writer under `pipeline/platform/`. The
step re-pointings ride as clauses on the steps
themselves: S3 (the moved `/ops` service becomes the
wrapper's base implementation), S4 (the workbench
writers and the file editor's guarded saves), S5 (the
venue lease/run record writers), S7 (the attention
state store writer, at its store migration); S9
executes P4's done-evidence over the re-pointed set.
What the plan already said, extended rather than
restated: contract 04's ops clause froze the ancestor
(payload semantics, the staged write, the closed error
table) as one endpoint's contract; §4.2/contract 02
froze the one-mutation-path principle for one store;
contracts 01 (ATT1), 11 (per-row CAS), and 12
(staged-sibling record writes) froze per-store write
disciplines — §4.15 generalizes the principle and the
protocol across all of them, and contract 15 is the
one home for the operation set, the atomicity
protocol, and the failure semantics. No §2 preserve
item changes: the shapes and disciplines those items
preserve stand; only their writing mechanism gains a
single owner (§12 reconciles the retired mechanisms;
the count stays 36 of 36 — traceability, amendment 4).

**Amendment 5 (2026-11-13, owner's ruling):** entry 16
was added on the owner's word that per-repo check
files are drift — the shared legs (line cap,
portability, scanners), the denylist itself, the
venv bootstrap, and test targeting are one
component each, not one per workhorse. The amendment
adds §4.16 + the §1 owners-table row and sharpens
§6 P1 (below): for shared legs it supersedes P1's
original "replaces per-invocation gate calls, not
the gates themselves" — the gates consolidate first,
and the runner runs the one gate. Programme-a's
AST-targeted `check.py` is the named reference
mechanism for test selection. The consolidation is
staffed on the landed trees when ruled (scheduling,
dispatch, workrecord), shaped to receive the
runner's funnel declaration at S5's close and
attention's `check.py` legs at S7; its tree commits
separately, after the S4/S5/S6 batch, so step
attribution stays clean.

**Amendment 6 (2026-11-13, owner's direction):** entry
17 was added on the owner's word, from the programme-a
packaging thread: programme-a's `paths.py` discipline — one
resolver spine, no other place writing its own paths —
is what made its package-read change minimal, and the
mega repo does not have it (no paths module anywhere;
self-location idioms in ~160 files across pipeline/**;
the acute case proven the same day, when 22 hand-rolled
root derivations in the scheduling ops scripts blocked
that folder's regroup until a single paths module
replaced them). The amendment adds §4.17 + the §1
owners-table row. Execution is waved behind the
in-flight regroup/decomposition lanes: the ops tree's
paths module lands inside the ops regroup's first act;
the census and the quiet trees (scheduling server/cli,
platform, registry, dispatch, evaluation) proceed in
parallel; venue and workrecord follow when their
moving lanes land.

## 5. Execution steps

Dependency order. Each step names its lane, its pin, its inputs,
and the evidence that closes it. Steps S0–S2 and the §3 capture
are documents-and-kit work inside this repo and the starter —
they do not move source trees and do not wait on G1.

- **S0 — Contract freeze + repo skeleton.** Lane: pipeline.
  Pins: all three. Inputs: the three reviews, §4 of this plan.
  Writes `contracts/` (the fourteen §4 entries as documents +
  schemas + fixtures drawn from the pinned code) and the §1
  directory skeleton. *Done-evidence:* every §2 preserve item
  traces to a contract clause; each contract carries at least
  one fixture taken verbatim from a pinned tree (an armed row,
  a scheduler entry of each source form, a lease record, a run
  record, a ledger event line).
- **S1 — Overlay capture.** Lane: pipeline. Pins: all three.
  Executes §3. *Done-evidence:* the four census counts reconcile
  with the reviews (~40 scheduler live entries, 12 bodies, 5
  runner live configs, the workbench manifest census), and the
  captured scheduler overlay validates complete on a fresh
  tree (26 valid, 0 invalid) where the bare pin quarantines
  bridge-drain alone and leaves bridge-wake operationally
  incomplete (§3's evidence correction, 2026-11-13).
- **G1 — Clean-and-pushed gate (hard gate, no lane).** The
  integration steps S3 onward begin only from source repos that
  are clean and pushed: working tree empty and local HEAD equal
  to the live remote `main` HEAD, verified from the repos
  themselves. At the 2026-11-12 11:05 EST verification only the
  runner met this (workbench clean but 3 ahead; scheduler 3
  ahead plus one untracked file; attention dirty and 1 ahead).
  Pushes remain the owner's word — no step in this plan pushes
  a source repo. A lane whose source fails G1 does its
  read-only preparation and stops at the gate.
- **S2 — Kit extraction.** Lane: frontend. Pin: workbench
  `b0b9cc5…`. Inputs: `tokens/tokens.json`, `gen-tokens.mjs`
  naming map, the status table, bundled fonts, the 24 viewer
  primitives. Moves the kit to its home in the spec-driven
  starter as Workhorse Kit v1; the workbench becomes a consumer.
  *Done-evidence:* regeneration is byte-identical to the pinned
  checked-in CSS; the contrast gate passes both palettes × both
  modes reading the extracted `tokens.json`; stage deploy D1
  (§8) shows the shell on the extracted kit.
- **S3 — Scheduling pipeline.** Lane: pipeline. Pin: scheduler
  `cf910ce…` + S1 overlay. Moves registry/catalog/schedule/
  engine/executor, ledger, outbox, ops service, connector, and
  the survival services into `pipeline/scheduling/` +
  `pipeline/platform/`, behind the S0 contracts; the classified
  catalog and adoption service land whole. *Done-evidence:*
  the pinned test suite passes against the moved tree; a
  registry census over the captured overlay matches the live
  census; ledger export from the moved store byte-matches an
  export from the pinned store over the same events. The
  moved ops service lands as the unified writer's base
  implementation (§4.15): its write/patch perform through
  contract 15's protocol from this step on, and the
  per-repo `/ops` form does not survive as a standalone
  service.
- **S4 — Work-record pipeline.** Lane: pipeline. Pin:
  workbench `b0b9cc5…`. Moves `lib/registry/`, `lib/plans/`,
  bundle writers, progress derivation, both arming writers,
  sweep/manifest, doctor, and the repos/datasets/diffs
  derivation set into `pipeline/workrecord/` +
  `pipeline/evaluation/`. The two arming writers keep writing
  the §2 shapes — now to the pipeline's own registry and armed
  directory through the §4.3 contract, with the sibling seams
  retained for external adopters (their projects must keep
  building with the harness absent). *Done-evidence:* pinned
  harness tests pass; a doing transition in a fixture project
  produces byte-identical scheduler entry and armed row to the
  pinned writers, save the migration field family amendment 3
  drops from the target format (the entry's remaining bytes
  identical); the doctor runs clean over the swept set.
  Both arming writers and the file editor's guarded saves
  write through the unified writer (§4.15): the cross-repo
  file drop as a mechanism retires here — the writers
  address the pipeline's own stores, and the wrapper
  performs the writes.
- **S5 — Venue pipeline + venue keying.** Lane: pipeline. Pin:
  runner `636033b…`, advancing to `8e9cb9b…` per the §0
  baseline note (2026-11-13 reconciliation): the
  standing-collector commit is ported as part of this step —
  the venue layer gains standing collection of stale
  detached runs on the reap cycle rather than inventing a
  mechanism; the hygiene remainder from S1 finding 4 (3
  unparseable records, 1 `completed` record) is still
  dispositioned here. Executes §7: the venue core extracted
  alongside the untouched colab-runner repo, the funnel
  dispatch change, venue keys on records and portions.
  *Done-evidence:* §7's checklist, including the panel serving
  venue-keyed portions and legacy records carrying the
  migration's `venue: colab` stamp — no read-time default
  exists in the reader (§10.3, ruled). The venue lease/run
  record writers re-point to the unified writer (§4.15):
  contract 12's record shapes stand; their staged-sibling
  mechanism becomes the wrapper's protocol.
- **S6 — Dispatch consolidation.** Lane: pipeline. Pins:
  scheduler + workbench. Implements §4.5: one substrate under
  the scheduler's outbox semantics, the bridge queue and wake
  minter folded in, the workbench messages/outbox expressed
  over it. **The substrate's consumer surface freezes only
  with the §9 attention delta — landed (§9)** (serial
  exception 4).
  *Done-evidence:* wake/ack/coalesce behaviour over fixture
  pings matches the pinned scheduler's ledger event sequence;
  a bridge `chat_send` round-trips with envelope idempotency
  (a duplicate enqueue returns the existing record).
- **S7 — Registry consolidation implementation.** Lane:
  pipeline. Pins: all three. Implements §4.1/§4.4/§4.7: the
  caller+routing registry as one store with the three caller
  natures, the unified config contract, the single catalog
  axes definition. Live registries are re-seeded from the S1
  capture, never from the tracked examples. *Done-evidence:*
  every caller in the captured live registries validates
  against the merged registry (14 runner thread callers, the
  connector callers, both routing tables); an unregistered
  presented claim is refused, an absent claim unattributed —
  the pinned semantics, exercised. The attention state
  store's writer re-points to the unified writer (§4.15)
  as its store migrates under contract 01's seed/export
  step: ATT1's discipline (atomic write, backfill) becomes
  wrapper-mediated, and its in-process writer retires.
- **S8 — The apps.** Lanes: frontend + backend in parallel per
  app; the three apps concurrent. Pins: per-app source pins.
  Each app is rebuilt as a consumer: scheduler app over
  `/api/v1` shapes, workbench app over work-record feeds,
  runner panel over venue portions — all on the extracted kit
  and the one shell (launcher, sidebar/tab bar, unified
  Settings) per the surface inventory's treatments. Backend
  half: the served-shape adapters that keep every §2 payload
  identical. Frontend half: surfaces per the inventory, stage
  deployed per §8 as each lands. *Done-evidence per app:*
  served-payload diff against the pinned app is empty for the
  preserve-listed routes; the app's stage deploy is live and
  renders real data from the pipeline.
- **S9 — Platform services.** Lane: pipeline. Executes §6
  (P1–P4 below); runs concurrently with S3–S8 after S0.
- **S10 — Attention amendment.** Executes §9. Hard prerequisite
  for S6's freeze and for S11.
- **S11 — Integration pass and cutover.** Lane: pipeline, with
  frontend/backend verification. Pins: all four (attention pin
  from §9). The big bang lands as one pass: the four apps
  switch to the pipeline in this repo; the scheduler cutover
  is single-writer — the old engine stops, state stores hand
  over (ledger via verified export/import into the empty
  store; outbox and next-due by capture), the new engine
  starts alone against the registry. External registrations
  re-homed: keeper/watchdog, the runner's reaper and notify
  hooks, the liveness entries (now written by the pipeline's
  own venue core). *Done-evidence:* a full gate on the union
  tree; the live registry census, lease census, and work
  record census after cutover match the censuses taken
  immediately before; no source repo's engine is running.
  Only then do the original scheduler, workbench, and
  attention repos archive as they are; colab-runner stays
  untouched and in service as the Colab adapter's home repo
  until the extracted adapter replaces its use.

## 6. Platform services (built new — S9 sub-steps)

- **P1 — Automatic gate runner.** Seeds exist: the scheduler's
  `check.sh` shape (line cap, portability scan, validate,
  census, tests), the runner's `bin/colab-check` funnel
  (snapshot bundle, remote run, verdict + wall time), and the
  portability/denylist component (§4.10). The service runs a
  repo's gate on its venue automatically at the points the
  pipeline already knows — formation, landing, stage deploy —
  and records the verdict against the tree SHA. It replaces
  per-invocation gate calls, not the gates themselves.
  **As amended 2026-11-13 (§4.16):** for the shared legs
  the gates themselves consolidate first — the service
  runs the one pipeline gate composed from per-package
  declarations, and the per-repo check files retire at
  the consolidation, not at cutover.
  *Done-evidence:* one real gate of each of the three source
  repos executed by the service end-to-end, verdict recorded
  against the tree SHA, matching a manual run's verdict.
- **P2 — Deployment/release record.** Today every deploy is
  drift-guarded sync with no ledger (workbench review §7;
  scheduler and runner deploy plumbing likewise). The record
  ties artifact ↔ repo commit ↔ stage: every deploy in §8
  writes an entry (repo, commit, artifact, stage, time,
  result) into a pipeline store, and each app's deploy path
  refuses to report success without its entry. *Done-evidence:*
  the §8 stage deploys from P2's landing onward each carry a
  record entry that resolves to the exact deployed commit;
  a drift check with no entry reads as undeployed, not as
  deployed.
- **P3 — State-store backup.** The stores with no backup story
  today: scheduler ledger (manual export only), outbox,
  next-due, live config, bridge records; workbench per-project
  registry DBs and `messages.db`; runner `var/` and
  `results/runs/`; the live registries of §4.1. The service
  takes scheduled, integrity-verified snapshots (ledger via
  its own export + SHA-256; the rest as file snapshots with
  manifests) to a home outside the repos. *Done-evidence:* a
  restore drill — one store of each class restored into a
  scratch home and read back by its own pipeline module.
- **P4 — Unified state writer.** The ops service's mutation
  half, generalized (§4.15, contract 15): one wrapper
  performs every pipeline store write, app state write,
  and app-level file edit on this machine — write, patch,
  cas-update, delete through the stage-verify-rename
  protocol, registry-caller attributed, `op`-ledgered —
  so the write-denial flap is this service's problem and
  no other component's. Its base implementation is the
  scheduler's `/ops` service, moved at S3; the remaining
  writers re-point at S4/S5/S7, and this step closes the
  service over the re-pointed set. *Done-evidence:* a
  flap-simulation drill — under an injected denial (and
  repeated inside a live flap window where one offers),
  writes are attempted against one store of each
  re-pointed class (scheduling registry, work-record
  store, venue records, attention state store, an
  app-edited file): every refused or interrupted write
  leaves its target byte-identical to its pre-state
  (hash-verified), a writer killed mid-stage leaves no
  torn target, a stale-stamp cas-update is refused whole,
  and the ledger carries every attempt with its caller
  and result.
- **Survival services (not built new — homed here).** The
  watchdog/keeper ladder, the stackdump watchdog, and the
  file-registry check already exist scheduler-side; they are
  platform services whose contracts freeze in contract 04
  (§4.4, as amended 2026-11-13) and whose build home is this
  step: S9 lands them as pipeline platform services
  alongside P1–P4, their registry-entry forms retiring into
  internal loops (§12), and S11 re-homes their external
  registrations.

## 7. Venue keying and runner extraction (S5 detail)

The runner genericizes by extraction; the colab-runner repo is
not edited (D4). Steps in order:

- **V1 — Venue key on records.** Lease records, run records,
  and every served panel portion gain a `venue` key from the
  first extracted write; session identity becomes
  venue-qualified so a second venue's names cannot collide
  with Colab's (runner review §3, §8). Legacy records carry
  no key: how they read is owner decision §10.3 — S5 does not
  start until it is ruled, because a mixed fleet makes a wrong
  default expensive.
- **V2 — Funnel dispatch.** The adapter seam is the
  `sync/cli.py` `colab()` callable the core already receives
  by injection: extraction puts a per-venue dispatch behind
  that callable, plus a per-venue shape catalog (replacing
  help-text parsing for new venues; the Colab catalog keeps
  its parser) and a per-venue stop/exec verb set. The lease
  core does not change shape (runner review §3).
- **V3 — Colab payload stays with the adapter.** The bridge
  (hash-signed command queue at `/content/bridge`), endpoint
  host-grammar shape reading, `snippets/`, `probes/`, and the
  repo's own `jobs/` manifests are Colab-adapter material,
  never core (runner review §3, §7). The OAuth token guard is
  decided as adapter-side auth at the funnel.
- **V4 — Panel venue-keyed.** Served portions carry venue;
  the panel (apps/runner) renders the mixed fleet as one
  fleet with venue named on every record — anything that
  cannot name its venue is a defect (D2 binding rule).
- **V5 — Registries re-homed.** The caller registry leads
  (§4.1); lease config and repos registry follow under the
  §4.4 config contract, their untracked-live nature intact.
  The liveness-entry generator becomes a pipeline writer
  under §4.2, writing into the pipeline's own scheduler
  registry.

## 8. Stage-deploy map (artifact: Workhorse Superapp)

Stage 1 shell is already live. Each later stage deploys to the
Library as its frontend work lands, so the owner sees progress
per app, not at the end (owner ruling, 2026-11-12). Deploy
carries no built-in gate — gating is the caller's step, and
from P2 onward each deploy writes its release-record entry.

**Mock-first amendment (owner ruling, 2026-11-13):** the four app
frontends (D2–D5) begin now, ahead of the pipeline logic
(S3–S11), because the S0 contracts are frozen — contracts
complete, logic not required. Each frontend builds against a
stateful mock adapter behind its data seam: every storyboarded
control works end-to-end against the mock store (state changes,
flows, validation) — working in the mock sense, never a static
frame. Mock payloads are generated from the contracts' schemas
and fixtures and validated against the schemas in the build.
Each stage's S8 landing then swaps the mock adapter for the
live one with no frontend rewrite, and the stage re-deploys on
live feeds. The table's "Lands with" column names the live-feed
landing; the mock-backed stage deploys first.

| Stage | Content | Lands with |
|---|---|---|
| D0 | Shell + launcher (stage 1) | already live |
| D1 | Shell re-tokened on the extracted Workhorse Kit v1 | S2 |
| D2 | Scheduler app surfaces over pipeline `/api/v1` | S8 (scheduler) |
| D3 | Workbench app surfaces over work-record feeds | S8 (workbench) |
| D4 | Runner app: venue-keyed leases, budget, events | S5 + S8 (runner) |
| D5 | Attention app: glance, Today, unified triage rows | §9 + S8 (attention) |
| D6 | Unified Settings complete; launcher badge + Today widget live | S11 |

## 9. Attention amendment (S10 — landed)

Executed. Pin: owner-attention
`24ae5bc245b1eeeef32284603bfe3d14931a9fa8` (tree clean at the
pin; `var/` is gitignored wholesale, so the live state is
overlay by construction). Review:
`docs/review/2026-11-12/review-attention.md`, run under the
same read-only protocol as the other three. No delta here
reopens a pipeline contract; the one open question the review
carried (the `/vocab` write surface, its §9.4c) is resolved
from §4.6 in item 5, not a §10 decision.

**Structure — the split is cut, not found.** Attention is one
stdlib process over a single JSON state dict: the evaluator,
the digest builder, the dispatch consumer, and the Today
builder read and write the same dict under one lock, and the
pipeline/app split exists today only at the `api/1` HTTP
boundary (review Finding 1, §7). The integration method is to
cut the seams along the call sites the review names —
evaluator, dispatch, work record, and fact measurement become
pipeline services; glance, Today, Digest, and the handlers
surface become the attention app over their served shapes.
Two derivations sitting surface-side today are engine in
nature and move behind pipeline feeds: push-fact measurement
and Digest's workbench pull (item 4).

1. **Registry (§4.1): confirmed, with a form delta and a
   second registry.** The handler registry is what §4.1
   expects — the shell's programme/lane directory and the
   dispatch target source. But it has **no file form**:
   handlers, programmes, rules, templates, and vocab are
   API-written rows inside the one untracked store
   `var/data/state.json`, unseeded in tracked code (live at
   review: 10 handlers, 3 programmes, 39 sends, 52 items;
   review Finding 2, §6). The merged contract therefore gains
   an explicit **store-migration + seed/export step**: the
   store migrates verbatim at capture — §3's attention capture
   is existential, since losing the file loses every registry
   it owns — and the pipeline registry gives these registries
   the seed/export form they have never had. The step lands
   with S7's registry implementation, re-seeded from the S1
   capture. The **programme registry** (the supervision
   directory proper: cadence, staffing band, escalation,
   venue, worktree roots, contract sourcing) joins §4.1
   alongside the handlers. Its contract-sourced fields
   reconcile against §4.11: `contracts.sync` already refreshes
   `rule_text` and `cadence_minutes` from the goal contract at
   `contract_path`, so **the goal record owns the contract
   fields (§4.11) and the programme registry is its directory
   projection** — declaration fields (handles, band,
   escalation, venue, roots) live in the registry; contract
   fields are sourced from the record, never duplicated
   (review §6).
2. **Dispatch (§4.5): confirmed over the substrate, three
   contract additions.** (a) **Settle-first ordering** — the
   consumer settles outstanding bridge records before claiming
   or enqueueing new sends — and the **suppressed-but-
   fulfilled edge** — a suppressed send's late fulfillment is
   stamped as fact, never resurrected — are contract, not
   implementation detail; a merged consumer that enqueues
   first, or resurrects suppressed sends, reintroduces the
   twin-send class the 2026-11-12 cures removed. (b) The
   **deduped failure record rides with the substrate** (one
   per hour per send + reason; an undelivered failure surfaces
   as a `steer_undeliverable` staffing row). (c) The pipeline
   contract names the **ledger + `record_send` minting surface
   with its four producer classes** — wait-rule engine, owner
   verbs, handler actions, continuation pass — not only the
   consumer: owner verbs and continuation mint above the
   substrate, not beside it (review §5, §9.2).
3. **Evaluator as pipeline: confirmed, five inputs, three
   clocks.** The evaluator reads **five** inputs — armed rows,
   status posts, programme declarations, runner run records +
   panel capacity, and lane record/worktree snapshots — not
   only the armed rows §4.3 writes (review §4). The snapshot
   contracts (capacity, worktree, record, armed) are named
   **pipeline feeds**; the evaluator's one piece of state —
   first-seen/escalation memory (`staffing_rows`) — is
   **pipeline-owned state**. Its three clocks stay distinct
   and are preserved: measure at Digest assembly, act on the
   60-second tick (continuation), collect on the slow loop.
4. **Today/Digest as surfaces: confirmed, asymmetry
   contractual, one relocation.** The **presence asymmetry is
   contractual**: the glance is presence-filtered; the decision
   queue never is — §8's D5 stage (glance + Today widget)
   preserves the asymmetry rather than unifying it away
   (review §3). Digest is not a pure surface today: it pulls
   workbench parked plans live at assembly and feeds staffing
   evidence from the same pull. In the target structure that
   pull is a **work-record pipeline feed**; the attention app
   keeps no private workbench client, and the §8-of-the-review
   overlap does not survive consolidation (review §7, §8).
5. **Status vocabulary (§4.6): the `/vocab` write surface
   homes in the pipeline.** The vocab registry is
   owner-extensible at runtime through the `/vocab` write
   surface (review §6). Under §4.6's ruling — one pipeline
   contract, served ready, apps render and never re-derive —
   vocabulary edits are pipeline registry writes and the write
   surface lands in the pipeline; apps stay render-only.
   Resolved from §4.6, not a new §10 decision. (Hard-stop wait
   classes stay named in code and uneditable through the
   surface, as today.)
6. **Decision machinery and presence/glance: confirmed as
   designed.** Verdict recorded at the tap; the "Decided —
   awaiting fulfillment" band; fulfillment derived from the
   send ledger or the scripted push measurement; failed and
   stalled items returned to the queue with decision history
   on the item's face; replies direct to the owning thread,
   main copied (Decision 1); one presence model, two consumers
   (launcher widget + app), expiry resolved at read time
   (review §3). These join the §2 preserve list with this
   amendment.

Slots: the attention app build takes its slot in S8 alongside
the other three apps, and its stage deploy is §8's D5 row.
S10's remaining work is the S7 seed/export step (item 1) and
the S6 consumer-surface freeze this amendment unblocks.

## 10. Decisions owed by the owner

Short by design — only what the reviews could not settle from
the rulings. Everything else in this plan is decided.

1. **`/ops` authentication posture.** Today `POST /ops` trusts
   a self-asserted `caller` string — attribution is audited,
   not authenticated; safety rests on the loopback bind and
   workspace scope (scheduler review, Finding 6). Keep as-is:
   zero build cost, audit-only attribution forever. Harden to
   the `/tools` token model: one pipeline change plus every
   ops client re-issued a token — small, and it closes the
   one unauthenticated write/exec surface before the mega
   repo widens its use. **RULED 2026-11-13: harden to the
   `/tools` token model.**
2. **Retired-sweeper connector compatibility.** The connector
   still serves the retired approval sweeper's state file and
   nudge ledger at fixed workspace paths, with the retired
   schema inlined in scheduler code (scheduler review §2, §7).
   Keep as a pipeline contract: carries dead weight
   deliberately, preserves the records' readability. Retire:
   the tools and the inlined schema leave at S3; the records
   stay on disk, unread by the pipeline. **RULED 2026-11-13:
   retire at S3.**
3. **Legacy lease/run records' venue.** Every existing record
   lacks a venue key (runner review §8). Rule them Colab by
   default at read time: one stated rule, no record rewrites,
   correct for today's all-Colab fleet. Or stamp them in a
   one-time migration at S5: records rewritten once, no
   read-time default to outlive its truth. **RULED
   2026-11-13: stamp them in the one-time migration at S5.**
4. **Kit distribution to non-bun stacks.** Token consumption
   today is the bun generator only; the scheduler and
   attention stacks have no bun (workbench review §8). Ship
   generated CSS from the kit's home as the distribution:
   consumers take checked-in CSS, one generator exists.
   Or a generator per consumer stack: more machinery, each
   stack regenerates — the drift class the checked-in-CSS
   rule exists to prevent. **RULED 2026-11-13: one generator
   in the kit's home; the generated CSS ships as the
   distribution and consumers take it checked-in. The owner's
   correction to the framing stands in the record: the
   consolidated repo is one repo with one `package.json` and
   one frontend build — generation is a single build step the
   backends never perform, so no per-stack fork exists inside
   the superapp.**

All four decisions ruled 2026-11-13 (owner walkthrough).
Nothing in this section remains open.

## 11. Risks

- **Pinned tree ≠ live system** (all three reviews): any step
  that starts from a tracked tree alone silently loses the
  scheduler's fleet, the runner's registries, or the
  workbench's runtime state. S1 + G1 exist to make that
  impossible; a step that skips either has failed by
  definition.
- **Overlay drift during execution:** the scheduler engine
  rescans `jobs/` every tick, so overlay edits change the
  running system outside git history while capture is in
  flight. Capture is a census with a timestamp, and S11
  re-censuses immediately before cutover; a mismatch pauses
  the cutover, it does not get absorbed.
- **Split-brain at cutover:** consume-before-run protects one
  engine, not two. S11's single-writer discipline is the
  mitigation; the failure mode is double-fired jobs.
- **Consolidating the wrong pair of stores:** the workbench
  has two todo stores and a third projection (scheduler
  entries). §2 keeps them distinct; a merge of the wrong pair
  corrupts the work record.
- **External registrations are not in any repo:** the runner's
  reaper and notify hooks, the keeper, and the liveness
  entries live outside the trees being consolidated. S1
  records them; S11 re-homes them; a missed registration is a
  silent loss of a duty, discovered late.
- **Sibling-layout seams:** the arming writers and several
  consumers locate each other by workspace-relative paths and
  must keep working for external adopting projects with the
  harness absent. Internalizing the seams must not break
  external adopters (workbench review §8).
- **Catalog fragility carries over:** the Colab shape catalog
  is parsed from CLI help text and the shape vocabulary is
  Colab-denominated (CU rates, `gpu`/`tpu`/`high_mem`). V2
  contains this inside the adapter; budget semantics across a
  future mixed fleet remain venue-denominated until a second
  venue forces the question (D1: proven when a second venue
  exists).
- **The connector contract annex is not in the pin** — it is
  referenced as living in the scheduler's ignored `.plans/`.
  S0 treats the pinned code plus the `bin/harness` header as
  the enforceable contract; if the annex surfaces and
  disagrees, the annex is evidence for a §10-class decision,
  not a silent override.
- **Three-tree UI drift:** repo source, runtime mirror, and
  hosted artifact can diverge independently in all four apps
  today. §4.9's shell contract plus P2's release record are
  the cure; until P2 lands, stage deploys are recorded by
  hand in `docs/` and a stage is "live" only on a served
  check, not on a deploy script's say-so.

## 12. Supersession ledger (counted 2026-11-12)

The counts below were taken from the four reviews and
verified against the live stores on 2026-11-12 (scheduler
jobs/ on disk, runner config/, attention's state census, the
Muse cron list). Machine-entry families fluctuate; their
family counts are the constant, instance counts are
tonight's.

Registries — 14 stores fold away:

- **Into the one pipeline registry (§4.1), 6 stores → 1:**
  the scheduler connector caller registry (inside live
  config.json), the runner caller registry
  (config/callers.json), the scheduler routing table
  (bodies/bridge-wake-owners.yaml), the runner routing table
  (config/notify-routes.json), attention's handler registry
  and programme registry (rows in var/data/state.json).
- **Into pipeline contracts and stores, 7:** attention's
  rules registry (→ the evaluator's rule set), attention's
  templates (→ migrate as data), attention's vocabulary
  registry (→ the §4.6 vocabulary contract), the armed-row
  file registry (owner-attention/var/armed/ — abolished as a
  file drop; arming becomes pipeline-internal state), the
  workbench per-project registry DBs (the cross-repo pattern
  — one DB inside every adopting project — → partitions of
  the one work-record store), the workbench server-local
  repos-registry.json cache (abolished; no cross-process
  cache registry in one app), the runner's repos.json (→ the
  venue layer's repo set).
- **Closed at S0, 1:** the scheduler file registry
  (registry/file-registry.yaml) — homed under the pipeline
  platform config pattern by §4.4's S0 amendment: the
  manifest rides the seed/example pattern and its check
  becomes a platform survival loop, not a registry entry.
- **Survivors, transformed not superseded:** the scheduler
  job registry becomes the pipeline scheduling registry; the
  workbench record stores merge into the one work-record
  store; lease/run records become the venue-keyed store;
  attention's send ledger becomes the dispatch ledger.
  Target registry surface: the directory registry, the
  scheduling registry, the work-record store, and the venue
  store.

Write paths — 5 mechanisms fold into the one writer
(§4.15, amendment 4):

- The scheduler `/ops` service as a standalone per-repo
  service (its implementation survives as the writer's
  base, moved at S3 — the mechanism that retires is the
  per-repo delegation form, not the code).
- The workbench's cross-repo file drops: scheduler-entry
  YAML written into the scheduler repo (the armed-row
  JSON half is already counted above, abolished as a
  file drop; the arming act itself survives under §4.3).
- The attention state store's in-process writer.
- The runner lease core's record-writer helpers
  (contract 12's shapes survive; the writer code folds).
- Every per-app atomic-write helper — the scheduler's
  state I/O discipline, the workbench editor's private
  guarded save, the stores' `.tmp`-sibling writers —
  replaced by wrapper calls under contract 15.

Crons and jobs — of the 26 entries on disk in the scheduler
registry tonight:

- **Superseded as entries, 15:** the two machine-entry
  families (wb-progress-* ×2 live, colab-liveness-* ×3 live
  — arming and venue health become internal pipeline acts,
  not registry entries); 8 cross-app watch/maintenance jobs
  that exist only because the apps are separate processes
  (owner-attention-healthcheck, workbench-viewer-healthcheck,
  workbench-viewer-doctor, file-registry-check,
  stale-mockup-cleanup, colab-runner-transient-restore,
  colab-extend-guard, colab-store-prune → internal
  health/maintenance loops of the pipeline services); the
  dispatch pair (bridge-wake minter, bridge-drain → pipeline
  dispatch internals).
- **Folded into the platform services, 4:** flap-watch,
  vm-restart-detector, restart-reconcile, local-test-watch
  (deployment self-watch → the gate runner / backup /
  supervision services of §6).
- **Migrating as ordinary jobs, 7:** storage-watch,
  memory-index-watchdog, weekly-gmail-otp-cleanup,
  weekly-gmail-stale-jobs-cleanup,
  pinehollow-daily-scheduler,
  pinehollow-deferral-retries, pinehollow-lane-watchdog —
  client work, unchanged in substance.
- **The Muse cron layer, as a class:** every harness watch
  living as a Muse cron (programme-a-parallel-staffing-reminder,
  greenfield-progress-watch, gap-closure-sweep,
  programme-a-dup-audit-progress, attention-settle-watch,
  programme-b-checklist-reconcile, the manual interval job)
  is superseded by a pipeline scheduling entry armed by a
  record (§4.11 decoupling) — no harness motion lives in
  Muse crons in the target structure. Runtime system jobs
  (feed pulses, the deterministic doctor) are not harness
  machinery and are out of scope.

The ledger is a checklist for the S-steps — an entry or
store not accounted for here at cutover is a defect against
the plan.
