# Scheduler review — workhorse superapp consolidation

Findings first:

1. **The pinned commit is not the live system.** The
   tracked tree ships the engine, the registry schema, a
   classified examples catalog, and exactly two live
   entries. The deployed fleet — the remaining job
   entries, all bodies, the bridge caller→chat routing
   config, the file-registry manifest, and several member
   scripts — is an untracked overlay held out of git by
   the tracked `.gitignore` plus local-only exclude
   patterns. A verbatim copy of the pin loses the fleet;
   consolidation inventories the overlay separately and
   promotes its contracts deliberately (`docs/overlay/`).
2. **The two tracked live entries are not
   self-contained.** Both bridge entries name body/config
   files that are absent from the pin; registry
   validation checks body existence on the local
   filesystem, not trackedness — the pin validates on the
   machine and quarantines on a fresh tree.
3. **The scheduler is already a pipeline with apps on
   top.** Engine, schedule math, ledger, outbox, ops
   service, connector/bridge queue, catalog/adoption, and
   the watchdog ladder are separable engines bound by
   explicit record formats; the viewer, job bodies, and
   hand-written entries are consumers and declarations
   over them. The pipeline/apps line formalizes a
   boundary the code already draws: backend does the
   work, the viewer is a consumer.
4. **Three platform services the superapp wants do not
   exist here.** No automatic gate-runner service (gates
   are local check invocations and one-shot proof runs),
   no deployment/release record (nothing ties artifact ↔
   commit), and no automatic state-store backup (ledger
   export is manual; outbox, next-due, config, and bridge
   records have no scheduled backup).
5. **Two dispatch systems already live in this repo.**
   The outbox/keeper wake cycle and the connector bridge
   queue + wake minter + drain job together implement
   wake minting, target resolution, episode coalescing,
   ack semantics, and delivery audit — the same
   functional territory as attention's dispatch. They
   merge into one pipeline dispatch substrate, not a
   re-implementation beside it.
6. **`/ops` attribution was self-asserted.** In the
   reviewed code, `POST /ops` performed no bearer-token
   authentication; it trusted a caller-supplied `caller`
   string for the ledger audit record, its practical
   boundary the loopback bind and workspace scope —
   unlike `/tools`, which is token-authenticated.
   (Ruled: harden to the `/tools` token model — plan
   §9.)

## Anatomy, as it bears on the consolidation

**Shape.** One always-on server owns every repeating
job. Scripted jobs are executed by the server itself;
agent jobs are never executed by the server — at due
time the server appends a durable ping to an outbox and
an external keeper wakes the agent surface. The keeper
is deliberately outside the server so it survives server
crashes and host restarts. The operator CLI carries the
registry verbs (validate, census, drift, adopt,
catalog-drift), the ledger verbs, the ping ack, the
connector-token minter, and the ops clients
(write/patch/exec — exit 4 means the server was
unreachable and nothing was performed; the client never
writes directly).

**Configuration.** Environment over live config over
built-in defaults, with per-key sources reported. Path
anchors `${REPO}` / `${WS}` / `${HOME}` expand at
registry load; tracked files carry no machine literals.
One inconsistency the consolidation fixes: the example
config's timezone default disagrees with the code
default — the platform config contract names one source
(plan §4.4).

**Job registry and catalog.** One file per job; the
filename stem is the job id and an internal `id` field
must match it. Entries use a strict YAML subset (nested
maps by two-space indentation, scalar lists only, no
anchors, flow maps, multiline strings, or lists of
maps); unknown fields are invalid and quarantined;
secret-shaped values anywhere fail validation. Owner is
`goal:<slug>`, or `none` with a reason. Classification
is required evidence: scripted only if a fixed command
sequence whose every outcome branches on exit code or
output enumerable in advance; any judgment over content
makes it agent. Retired jobs are deleted, never
disabled; the retirement is recorded in
`jobs/RETIRED.md`.

The classified catalog (version 1) indexes the examples
layer exactly once; row and entry block must agree on
the axes (origin, generality, use_case). Classification
is descriptive, not activating — being catalogued admits
nothing. Adoption copies a generalized or parameterized
example into the live registry, substitutes declared
parameters, refuses machine literals in structural
fields, establishes or verifies declared setup, and runs
the admission back half. Drift re-renders adopted
entries from their stamps and diffs them against the
live files, with volatile fields named; hand-written,
machine-written, and per-session entries are counted
separately — their writers own their lifecycle.

**Admission and firing.** In the reviewed system an
entry fires only when it carries the migration stamp,
granted after validate → server-context proof; the
consolidation drops the stamp family from the target
format (plan §2, amendment outcome): in the target an
entry fires iff its status is active and it stands in
the pipeline registry store, whose one mutation path is
the writer path — presence through that path is
admission, and admission evidence rides the ledger as
events, not entry fields. Engine semantics are
contract: consume-before-run (a due grid point is
consumed and persisted before the run starts, so a crash
can delay but never duplicate), missed-point collapse
with counts, no self-overlap, same-tick dispatch in
entry-id order, last-good registry on parse failure,
fail-safe halt on corrupt state, and the schema →
restart → entries ordering.

**Ledger.** SQLite, one events table; the full event
record is stored as canonical sorted-key JSON, so the
JSONL export reproduces the historical lines
byte-for-byte — JSONL is the export format, SQLite is
the store. Export carries SHA-256 verification; import
runs only into an empty store. Event kinds span runs,
agent dues, catchups, ping lifecycle, entry removal,
registry and state errors, pruning, ops, and connector
calls.

**Outbox.** The cross-process source of truth for pings
(agent-due, escalation, report kinds). Coalescing is by
pending job id + ping kind. Reading never acknowledges;
ack is explicit and separate; acking an acked or voided
ping is a ledgered no-op; deleting an entry voids its
pending pings. A pending ping is wakeable if never woken
or last woken at least one ack-timeout window ago.

**Ops endpoint.** Delegated write/patch/exec performed
by the server process: writes are staged (sibling temp →
write → read-back verification → rename over target);
patch requires exactly one match; exec runs in its own
process group with tail-capped output and a closed error
table. Every attempt is ledgered as an `op` event. Exec
children receive a pinned `GIT_SSH_COMMAND` only when
both live-config keys of the pair are set — a half-set
pair pins nothing. This service is the unified writer's
base implementation in the consolidation (plan §4.15).

**Harness connector and bridge queue.** The connector
exposes the agent tier's privileged surface as
authenticated tools so agents on other venues can act
while state, ledger, and authority stay home. The caller
registry lives in the live config: token SHA-256 hashes
and scopes only, read fresh on every call; every call —
ok, refused, error — is ledgered. The boundary is
explicit: **no authority crosses the connector** — no
tool approves a permission, pushes, acquires a lease, or
writes a calendar. Bridged tools queue a record in
server state; fulfillment sets it done or failed with
its reference; envelope idempotency (a second enqueue
with the same caller + envelope returns the existing
record) exists specifically so a transport retry cannot
double-send. The wake minter reads queued bridge records
and plants at most one pending wake ping per item, with
the target resolved by rule: the destination chat is
data inside a record; the wake address is a separate
routing decision (a configured drain home wins for
`chat_send`). A pass with resolvable items and no
pending drain ping plants one episode escalation; the
drain job acks it only when its final poll finds the
queue empty — that ack closes the episode and re-arms
the minter.

**Survival services.** The keeper polls health and the
wakeable pings on its cadence: health half runs the
watchdog restore ladder (external driver, presence
before health, render-when-invalid, one ladder attempt
per episode, health as the verdict); wake half wakes the
agent surface per ping and acks only after the work is
done. An in-process stackdump watchdog dumps all thread
stacks on a lag threshold. Both contracts are named
forms whose canonical texts live in the starter
specification; this repo carries conformance and stamps.

**Viewer.** A pure consumer of the served `/api/v1`
shapes: backend computes every derivation, label, count,
and ordering; the client does presentation plus
arithmetic over served values. Bridge-down is kept
distinct from server-down, never conflated; a failed
fetch keeps the last-good snapshot on screen, labeled
with its age. The viewer is read-only — ack, suspend,
and admit stay in the CLI and chat. Its deploy is
drift-guarded sync with a timestamped backup and no
release record (Finding 4).

## Overlaps with the other three workhorses

- **Workbench.** The harness machine-writes one registry
  entry per armed todo (`wb-progress-*`), born admitted,
  with the machine-form source stamp (writer, project,
  todo, source_class) — the cross-repo contract in its
  sharpest form; the chain is workbench todo state →
  scheduler registry entry → scheduler outbox ping. The
  connector also proxies the workbench viewer's API for
  venue-side callers, and a scheduler census job reads
  workbench project registries directly — two coupling
  forms needing explicit ownership.
- **Owner-attention.** The outbox/keeper cycle is a
  wake-and-dispatch substrate in the same territory as
  attention's dispatch (Finding 5). The connector's
  direct tools also still served the retired approval
  sweeper's state file and nudge ledger at fixed
  workspace paths, with the retired schema inlined in
  scheduler code. (Ruled: retire at the scheduling move —
  the tools and the inlined schema leave; the records
  stay on disk, unread by the pipeline — plan §9.)
- **Colab runner.** The runner's lease core renders one
  liveness entry per live lease into this registry and
  deletes it with the lease record; the lease record is
  the record of truth. The harness connector exists so
  venue agents can call home-side tools while scheduler
  state and ledger stay home.

## Preserve exactly

- Job ids (filename stem = entry id), the strict
  registry YAML subset and field semantics (unknown-field
  quarantine, secret-shape refusal), owner values and
  both `source` stamp forms.
- Catalog version 1, adoption rendering, the
  setup-coverage rule, drift semantics with its named
  volatile fields; classification evidence and the
  scripted/agent boundary.
- Engine firing semantics (above); the schema → restart
  → entries ordering (or a deliberate, named
  replacement).
- Ledger format: canonical sorted-key JSON per event,
  the event-kind vocabulary, the SQLite schema and
  indexes, JSONL export byte format with SHA-256
  verification, import only into an empty store.
- Outbox ping shape, ids, states, coalescing by job +
  kind, wake-window discipline, explicit ack,
  void-on-entry-removal.
- HTTP routes and payload shapes for `/health`,
  `/pings`, `/ops`, `/api/v1`, `/tools`; ops error
  names/status mapping and staged-write semantics; the
  pinned `GIT_SSH_COMMAND` pair rule.
- Connector scopes, token-hash-only caller registry,
  fresh-read-per-call, ledgering of refusals, envelope
  idempotency, and the no-authority boundary.
- Bridge record shape and the target-resolution rule.
- Body refs and ack-after-work discipline; the
  watchdog/keeper contract; portability anchors and the
  no-machine-literals rule for tracked files.

## Risks the consolidation carries

- **Pinned tree ≠ live system** (Finding 1): overlay
  edits change the running system outside git history —
  the engine rescans `jobs/` every tick — so capture is
  a census with a timestamp, and the cutover re-censuses
  immediately before it runs.
- **Single-instance, local-state design.** One lock,
  local SQLite, local JSON state. Two engines against
  the same registry/state double-fire; the cutover is
  single-writer by discipline.
- **The bodies directory conflated content and config**
  (the routing table stored among agent bodies); the
  consolidated registry separates the two classes.
- **Three-tree UI deployment.** Repo source, runtime
  mirror, and hosted artifact can drift independently;
  the release record (plan §5) is the cure.
