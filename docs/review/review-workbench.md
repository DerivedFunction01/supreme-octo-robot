# Review — workbench-viewer (superapp consolidation)

Findings first:

- The workbench is already split engine/surface
  internally: `lib/` is a stdlib-only Python engine with
  exactly one mutation path (the `wb` CLI and the
  companion server both call it; the server contains no
  SQL), and the viewer is a React/TS surface consuming
  backend-computed feeds. The pipeline/apps line in the
  mega repo mostly ratifies a split this repo already
  enforces.
- The work-record store is two stores, not one: a
  per-project SQLite registry (entries/history) and
  `.plans/` bundle files (plans + file todos) that are
  the live-work record of truth. A second, older DB todo
  table also exists inside the registry. Consolidation
  must not conflate them.
- This repo is already a contract *producer* into both
  neighbours: its todo writers synchronously write
  scheduler-registry YAML entries and owner-attention
  armed-row JSON files into the sibling repos. Those two
  write contracts are the sharpest cross-cutting seams in
  the whole programme.
- The token system is a single DTCG file with a
  deterministic generator producing checked-in CSS; it
  is consumed only inside this repo at review. Kit
  extraction is that file + the generator's naming rules
  + the status table, not a redesign.
- Deploy here is the deployment-record gap in miniature:
  drift-guarded shell sync with no release ledger.

## Anatomy, as it bears on the consolidation

**The harness.** A thin CLI over `lib/`; a companion
server bound per config. Tests mirror the split
(harness/lib/server). The one gate is the repo's own
check script (unittest + Biome + typecheck + client
build) — per-repo check files are drift; the shared legs
consolidate into the one pipeline gate (plan §4.16).

**Stores.**

- *Registry DB* — one SQLite DB per adopting project, at
  the path its manifest declares. Tables `entries`,
  `history` (append-only audit/review log), `todos`,
  `todo_events`; the schema is unified — identical in
  every adopting repo — with versioned migrations, WAL,
  one short immediate transaction per mutation, and
  per-row version compare-and-swap. Entry statuses use
  the ruled vocabulary (§5 below). An export folds the DB
  to a generated `registry.json`, regenerated on every
  mutation.
- *Bundles and file todos* — the live-work record.
  Layout: `.plans/<date>-<slug>/` holding an optional
  `plan.md` and a `todos/` dir of one Markdown file per
  todo; `finished/` holds archived bundles; legacy flat
  plans enumerate as one-file bundles. Todo front matter
  is the contract: required `id`, `title`, `status`,
  `created`, `updated`; the id scheme
  `^t-[0-9A-HJKMNP-TV-Z]+$`; statuses
  `todo|doing|blocked|done`; `progress_check` (a cadence,
  `off` = opt-out, absent = the writer arms at the
  default on the doing move) and the `progress_armed`
  stamp; unknown fields preserved losslessly; invalid
  files surface flagged, never silently skipped. Plan
  files are parsed by the plans parser with closeout
  enforcement (declared Status vs filing location).
- *Registry-DB todos* — a separate todo table in the
  same DB that may only *link* to a plan/step/entry —
  steps are never copied here. Distinct from file todos.
- *Messages store* — a second SQLite DB: a messages
  store plus an outbox table, with a notify mechanism
  firing wake-ups for new outbox rows (at-most-once; the
  outbox is the durable queue). A dispatch/digest
  mechanism built earlier and independently of
  attention's; it retires into the one dispatch
  substrate (plan §4.5).
- *Discovery* — projects adopt by placing a
  `workbench.yaml` manifest (name, slug, registry,
  plans, mockups, archive, plus the
  `catalog_origin/generality/use_case` classification
  fields) at their root; the sweep finds them. A staging
  project is the designated pre-home for unhomed work.

**Progress derivation** is pure, computed at read time,
never stored. Checkpoints are todo-body lines
(`progress-checkpoint: <ISO-8601> — <text>`); the stall
verdict lands at 2 missed cadence intervals.

**The two arming writers** (contract producers). Both
are invoked from both todo writers, so CLI and server
writes arm identically; a sync failure never fails the
todo write — the outcome rides the writer's result.

- *Scheduler arming writer*: on a todo's doing
  transition, writes one YAML entry per armed todo into
  the scheduler's `jobs/` dir (a sibling seam; silent
  no-op when absent), named
  `wb-progress-<project>-<todo-id>.yaml`, whose argv runs
  the progress check at the todo's cadence. Entries are
  born admitted and carry a classified-catalog block
  (origin: machine; generality: deployment-specific;
  use_case: work-tracking) and a source stamp (writer,
  project, todo, source_class project|fixture).
  Terminal/disarmed/archived deletes the file. Entry
  paths use the scheduler's `${WS}` anchor, never
  absolute paths.
- *Attention arming writer*: on the same transitions,
  writes one JSON file per armed todo into attention's
  armed dir (a sibling seam; silent no-op when no
  owner-attention repo exists on the machine), named
  `wb-armed-<project-slug>-<todo-id-lowercase>.json`.
  The row carries handle (= the todo id itself — harness
  todos record no posting lane, and the writer refuses
  to guess one), programme, project, todo, title, bundle,
  cadence, armed stamp, status, and its source stamp;
  written atomically (`.tmp` + rename, sorted keys).
  Terminal/disarmed/archived deletes the row; a
  whole-directory sync reconciles against the swept
  armed set. A temp-root leak guard mirrors the
  scheduler seam: fixture projects never write into the
  live armed dir.

**Viewer server.** All derivations are computed
server-side; the client consumes ready shapes. The
server's write surface is exactly two things: guarded
file saves (sha-checked, config-gated, default off) and
`lib/` mutations. A read-only doctor runs over every
swept project on a cadence and posts one digest through
the message store when findings change.

**Classification feed.** The server serves, per project,
every todo across the active bundles with its status,
raw progress_check, the opt-out derived explicitly,
arming stamp and last update, plus the progress
derivation for the armed set — so a venue-side consumer
judges escalations without parsing a todo file.
Deliberately not served: whether a scheduler entry
exists on disk — that is the scheduler registry's own
state, joined consumer-side.

## The token system

`tokens/tokens.json` is DTCG format, five top-level
groups: **primitive** (color ramps, space, radius, font,
sizes, motion), **semantic** (per palette × per mode:
surface/content/border plus accent, focus, danger,
shadow roles — one-way references to primitives only),
**status** (14 named statuses, each with hue,
per-mode text, glyph, description, plus a chart series
scale), **component** (aliases for radius/padding/height
only), and **density** (comfortable/compact sets that
re-point the same variable names — density never
renames).

The status group encodes the ruled entry vocabulary —
canonical / implemented / deferred / unexplored /
hard-gate / abandoned (status changes only via a mutation
carrying a ruling note) — plus derived, review, and
message-lifecycle states, all on Okabe-Ito hues with a
glyph per status. The vocabulary and its token status
table are one contract in two files; both halves move
together or not at all.

Modes × palettes: dark is design-led, light a full peer;
default follows the OS with a persisted preference;
palettes are token-set variants over identical semantic
roles; the status system never varies by palette, and
every palette must pass the same contrast verification
in both modes, reading the token file directly.

Generation is deterministic (byte-identical, no
timestamps); generated CSS is checked in and marked
do-not-edit, as `--wb-*` variables per the generator's
naming map. Fonts are bundled. Kit extraction carries:
the token file as the single source, the tier discipline
(primitive → semantic → component, one-way; density
re-points, never renames), the naming map, the full
status table, the palettes × modes matrix and its
contrast gate, the deterministic-regen + checked-in-CSS
rule, the bundled fonts, and the viewer primitives.
(Ruled for distribution: one generator in the kit's
home; the generated CSS ships as the distribution and
consumers take it checked-in — plan §9.)

## Cross-cutting contracts designed locally

- **Registries, tracked vs untracked.** The per-project
  registry DB and its export are untracked in every
  adopting repo by design; only the manifest is tracked.
  The two registries this repo writes into other repos
  (scheduler entries, attention armed rows) are located
  by workspace-relative sibling seams and no-op when the
  sibling is absent. A third, server-local registry
  cache is runtime state; the consolidated app abolishes
  it (plan §11).
- **Duplicated rule text.** The checkpoint line format
  and the stall rule are stated in the progress module,
  the SPEC, the synced supervision block, and rendered
  into every scheduler entry. The classified-catalog
  axes are defined once per surface (manifest template +
  validation, scheduler-entry renders, SPEC). The
  consolidation gives each one home (plan §4.7, §4.8).
- **Spec copies.** The repo carries a fragment-synced
  supervision block from the starter and a six-file
  context set restating SPEC material — a second home
  for the same rules. In the mega repo the restatements
  retire into pointers at the one text.

## Overlaps with the other three workhorses

- **Scheduler.** Todos are the record, scheduler entries
  are their projection: one machine-classified YAML entry
  per armed todo, lifecycle-owned by the todo writers;
  the doctor flags any entry that outlives its todo. The
  manifest's `catalog_*` fields reuse the scheduler
  registry's classification vocabulary verbatim — the
  overlap is contractual, not accidental.
- **Attention.** Three contact points: the armed-row
  write contract (producer here, consumer there); the
  classification feed (the same progress derivation an
  evaluator needs, served to a venue-side consumer); and
  surface territory — the viewer's Home/Board/Todos and
  attention's Today/Digest present overlapping "what
  needs the owner" ground, and the harness's own message
  store + outbox + digest is a dispatch mechanism
  parallel to attention's, built earlier and
  independently.
- **Runner.** No direct code contact. Indirect: the
  classification feed's named consumer is the harness
  connector's venue-side workbench tool, and the
  worktrees/diff feeds serve venue-lane working state.

## Preserve exactly

- File-todo format and id scheme: bundle layout, front
  matter including `progress_check` / `progress_armed`,
  and the `progress-checkpoint:` body-line format —
  scheduler entries, attention rows, lane drivers, and
  the doctor all key off these.
- The armed-row JSON shape and the scheduler-entry YAML
  shape: two other live systems consume them as written.
- Registry unified schema + `registry.json` export
  shape, and the "data never migrates" rule: each
  project's registry DB stays in its owning repo; the
  mega repo inherits tooling, not data.
- The ruled status vocabulary and its token status
  table — one contract in two files.
- The manifest (`workbench.yaml`) format, including its
  `catalog_*` classification fields.
- The two stores stay two stores: registry DB vs
  `.plans/` bundles are not conflated, and the
  registry-DB todo table stays link-only.

## Risks the consolidation carries

- Two todo stores with near-identical vocabularies plus
  a third projection (scheduler entries): merging the
  wrong pair corrupts the work record.
- The cross-repo write contracts assume sibling layout
  and must keep working for external adopting projects
  with the harness absent. Internalizing the seams in a
  mega repo must not break external adopters.
- Deploy is drift-guarded sync with no release record,
  and the gate is external by design — exactly the
  pipeline's missing release-record and gate-runner
  services (plan §5).
- State-store backup: registry DBs, the messages store,
  and server state have no backup story in-repo.
