# Review — workbench-viewer (superapp big-bang consolidation)

Findings first:

- The workbench is already split engine/surface internally: `lib/` is a
  stdlib-only Python engine with exactly one mutation path (the `wb` CLI and
  the companion server both call it; the server contains no SQL), and
  `viewer/` is a React/TS surface consuming backend-computed feeds. The
  pipeline/apps line in the mega repo mostly ratifies a split this repo
  already enforces (`AGENTS.md`: "One mutation path", "Overlay rule").
- The work-record store is two stores, not one: a per-project SQLite
  registry (entries/history) and `.plans/` bundle files (plans + file
  todos) that are the live-work record of truth. A second, older DB todo
  table also exists inside the registry. Consolidation must not conflate
  them.
- This repo is already a contract *producer* into both neighbours: its
  todo writers synchronously write scheduler-registry YAML entries
  (`lib/progress/schedule.py`) and owner-attention armed-row JSON files
  (`lib/progress/attention.py`) into the sibling repos. Those two write
  contracts are the sharpest cross-cutting seams in the whole programme.
- The token system is a single DTCG file (`tokens/tokens.json`, 1,092
  lines) with a deterministic bun generator producing checked-in CSS; it
  is consumed only inside this repo today. Kit extraction = that file +
  the generator's naming rules + the status table, not a redesign.
- Deploy here is the deployment-record gap in miniature: drift-guarded
  shell sync (`viewer.sh`, `viewer/deploy.sh`) with no release ledger.

## 1. Verification

- `git rev-parse HEAD` = `fd870ae3466f220e795c9ed7e1b57050f3602f95` —
  equals the pin exactly. HEAD commit: "Deploy carries no built-in gate;
  gating is the caller's step".
- `git status --porcelain` is empty — tree clean, read at HEAD; no
  checkout, stash, or write was performed in the repo.
- 565 tracked files (`git ls-files`).

## 2. Anatomy

**The `wb` harness.** `wb` (repo root, ~1,070 lines) is a thin argparse
caller over `lib/`; `run.py` launches the companion server
(`server/server.py`, `main()`), bound per config (default
127.0.0.1:8792). Python `lib/` + `server/` are stdlib-only; the repo venv
(`init_venv.py`, uv/Python 3.11) is the launch path. Tests mirror the
split: `tests/harness/`, `tests/lib/`, `tests/server/`; the one gate is
`tools/check.sh` (unittest + Biome + typecheck + client build).

**Stores.**

- *Registry DB* — one SQLite DB per adopting project, at the path its
  manifest declares (default `workbench/registry.db`, untracked in every
  project). `lib/registry/{store,entries,todos,constants}.py`. SPEC §4:
  tables `entries`, `history` (append-only audit/review log), `todos`,
  `todo_events`; the schema is unified — identical in every adopting repo
  (SPEC §1.11, §14) — with `PRAGMA user_version` migrations, WAL +
  busy_timeout, one short `BEGIN IMMEDIATE` per mutation, per-row
  `version` compare-and-swap. Entry statuses use the ruled vocabulary
  (§5 below). `lib/export.py` folds the DB to a generated `registry.json`
  export, regenerated on every mutation.
- *Bundles and file todos* — the live-work record (`lib/plans/bundles.py`,
  `lib/bundles.py` writers). Layout: `.plans/<date>-<slug>/` holding an
  optional `plan.md` and a `todos/` dir of one Markdown file per todo;
  `finished/` holds archived bundles; legacy flat plans enumerate as
  one-file bundles. Todo front matter (§3.2) is the contract: required
  `id`, `title`, `status`, `created`, `updated`; id regex
  `^t-[0-9A-HJKMNP-TV-Z]+$`; statuses `todo|doing|blocked|done`;
  `progress_check` (cadence `30m`/`2h`, `off` = opt-out, absent = writer
  arms at the 15-minute default on the doing move) and `progress_armed`
  stamp; unknown fields preserved losslessly; invalid files surface
  flagged, never silently skipped. Plan files are parsed by
  `lib/plans/parser/` (grammar/document/questions) with closeout
  enforcement (declared Status vs filing location).
- *Registry-DB todos* — `lib/registry/todos.py`: a separate todo table in
  the same DB that may only *link* to a plan/step/entry ("steps are never
  copied here"). Distinct from file todos.
- *Messages store* — a second SQLite DB (`messages.db` in the server
  state dir): `lib/messages/{store,lifecycle,selection,cleanup}.py` plus
  an outbox table; `lib/notify.py` fires webhook/command wake-ups for new
  outbox rows (at-most-once; the outbox is the durable queue).
- *Server runtime state* — untracked `state/`: `health.json`,
  `server.lock`, `link.json`, `repair.json`, `edit-log.jsonl`,
  `repos-history.jsonl`, `repos-registry.json`, `doctor-findings.json`,
  `messages.db`, `edit-backups/`.
- *Discovery* — `lib/sweep.py` + `lib/manifest.py`: projects adopt by
  placing a `workbench.yaml` manifest (name, slug, registry, plans,
  mockups, archive, plus `catalog_origin/generality/use_case`
  classification) at their root; the sweep finds them (config depth/
  prune/TTL). SPEC §2.1 designates a staging project as the pre-home for
  unhomed work.

**Viewer server.** `server/server.py` (~609 lines) routes everything
under `/api` (legacy unprefixed patterns removed, 404): `GET /api/health`,
`/api/config`, `/api/home`, `/api/repos` (+ `/registry`, per-repo
`status|files|file|history|dataset|rows|stats`),
`/api/projects/<slug>/{entries,plans,plan,todos,classification,board,
worktrees,diff}` + entry detail and entry-file routes, `/api/messages`,
`/api/outbox`, `/api/settings/effective`. POST actions live in
`server/actions.py` (`entry_action`, `todo_action`, `plan_resolve`). One
byte route outside `/api` serves entry files verbatim. All derivations
are computed in `server/feeds.py` / `lib/home.py` / `lib/{repos,datasets,
diffs,worktrees,repo_state,staleness}.py` — the client consumes ready
shapes. The server's write surface is exactly two things (AGENTS.md):
guarded file saves (sha-checked, config-gated, default OFF) and `lib/`
mutations. Health/supervision: `server/healthcheck.py`, `linkprobe.py`,
`autorepair.py` (repair ladder, cap 3) driven by `ops/watchdog.sh`;
`ops/` also carries the systemd unit template + generic installer.
`lib/doctor.py` is a read-only consistency engine over every swept
project (runs on a 15-minute cron via `ops/doctor.sh`; `--post` posts
one digest through the message store when findings change).

**Deploy plumbing.** `viewer/` is canonical in-repo. `viewer.sh
status|pull|deploy` does sha256 drift reporting and guarded copy to the
runtime space in the sibling ts-spaces tree (seam: `VIEWER_RUNTIME_DIR`);
`viewer/deploy.sh` is the checkpoint path — sync, then a builder publish
pass via the `hatchlet` CLI (exit 4 with an exact builder request when
absent). No gate is built into deploy (the HEAD commit states this).
`viewer/SYNC.md` documents the two-step semantics and the sync set.

**SPEC.** `SPEC.md`, 1,470 lines, §0–§18: 0 purpose/scope · 1 invariants
· 2 adoption contract (manifest) · 3 discovery (sweep) · 4 registry data
model · 5 status model (ruled vs derived) · 6 the `wb` CLI · 7 companion
server (incl. §7.1 guarded saves) · 8 the artifact (Entries/Plans/Todos/
Board + §8.5 unified collection) · 9 mockup authoring/promotion · 10
validators · 11 fundamentals (theme system, tokens, typography, views,
dependencies) · 12 conformance · 13 resolved questions · 14 unified
schema + uniform interactivity · 15 choice kit · 16 entry attribution ·
17 classified catalog · 18 classification read for venue consumers.

## 3. Pipeline vs apps

**Engines (pipeline candidates).**

- The work-record store itself: `lib/registry/` + `lib/plans/` +
  `lib/bundles.py` writers — one mutation path, two physical stores.
- Progress derivation: `lib/progress/report.py` — pure, computed at read
  time, never stored. Checkpoints are todo-body lines
  `progress-checkpoint: <ISO-8601> — <text>`; stall verdict at 2 missed
  cadence intervals (`STALL_MISSED_CHECKS = 2`).
- The two arming writers (contract producers — see contracts below):
  `lib/progress/schedule.py`, `lib/progress/attention.py`. Both are
  invoked from both todo writers in `lib/bundles.py` (calls at lines
  ~425/430 and ~594/599), so CLI and server writes arm identically; a
  sync failure never fails the todo write — the outcome rides the
  writer's result dict (`progress_entry` / `attention_row`).
- Sweep + manifest (`lib/sweep.py`, `lib/manifest.py`), doctor
  (`lib/doctor.py`), messages/outbox + notify
  (`lib/messages/`, `lib/notify.py`), and the read derivations
  (`lib/repos.py`, `lib/datasets/`, `lib/diffs/`, `lib/worktrees.py`,
  `lib/staleness.py`, `lib/repo_state.py`).

**Surfaces (app side).** The viewer client
(`viewer/client/src/`): sections home, entries, plans, todos, board,
repos (file tree, peek pane, repo editor), inbox, overview, settings,
plus shell chrome (`sections/shell/`); 24 shared components
(`viewer/client/src/components/`). The artifact-side TS bridge
(`viewer/server/src/{bridge,actions,privileged,page,config}.ts` with a
generated contract, `viewer/server/.generated/privileged.contract.ts`)
is a second, thinner server shell between the artifact and the Python
server. `templates/choice-kit/kit.html` is a fourth mini-shell (study
artifacts stamped out by `lib/kit.py`).

**Served-shape contracts.**

- *Feeds*: every `/api` GET returns backend-computed ready state; the
  client's mirrors are `viewer/client/src/lib/api-types.ts` and
  `api-types-repos.ts`. No derivation lives client-side beyond
  presentation (SPEC §14 uniformity catalogue).
- *Classification endpoint* (SPEC §18, `server/feeds.py:
  classification_feed`): `GET /api/projects/<slug>/classification`
  serves, per project, every todo across the active bundles with its
  status, raw `progress_check`, the opt-out derived explicitly, arming
  stamp and last update, plus the progress derivation (cadence, last
  activity, missed checks, stall verdict) for the armed set — so a
  venue-side consumer (the harness connector's workbench tool) judges
  escalations without parsing a todo file. A project with no plans dir
  serves `available: false`. Deliberately *not* served: whether a
  scheduler entry exists on disk — that is the scheduler registry's own
  state, joined consumer-side.
- *Scheduler arming writer* (`lib/progress/schedule.py`): on a todo's
  doing transition, writes one YAML entry per armed todo into the
  sibling scheduler repo's `jobs/` dir (seam `WB_SCHEDULER_JOBS_DIR`;
  silent no-op when absent), named `wb-progress-<project>-<todo-id>.yaml`,
  whose argv runs `wb progress-check <id>` at the todo's cadence (exit 0
  = on track/disarmed/gone, exit 3 = stalled, the stall line rides the
  scheduler's failure ping). Entries are born admitted (`migrated: true`,
  owner ruling 2026-11-08) and carry a classified-catalog block (origin:
  machine; generality: deployment-specific; use_case: work-tracking) and
  a source stamp (writer, project, todo, source_class
  project|fixture). Terminal/disarmed/archived deletes the file. Entry
  paths use the scheduler's `${WS}` anchor, never absolute paths.
- *Attention arming writer* (`lib/progress/attention.py`): on the same
  transitions, writes one JSON file per armed todo into the sibling
  owner-attention repo's `var/armed/` (seam `WB_ATTENTION_ARMED_DIR`;
  silent no-op when no owner-attention repo exists on the machine).
  Filename `wb-armed-<project-slug>-<todo-id-lowercase>.json`. Row shape
  (sorted keys, indent 2, atomic `.tmp` + `os.replace`):
  `{handle, programme, project, todo, title, bundle, cadence,
  cadence_minutes, armed_at, status, source: {writer:
  "workbench-harness", project, todo, source_class}}` — where `handle`
  is the todo id itself (harness todos record no posting lane, and the
  module refuses to guess one), `programme`/`project` are both the
  project slug, and `armed_at` is the todo's `progress_armed` stamp.
  Terminal/disarmed/archived deletes the row; `sync_all` reconciles the
  whole directory against the swept armed set (rides `wb progress
  --sync-entries`). A temp-root leak guard mirrors the scheduler seam:
  scratch (fixture) projects never write into the live armed dir.

## 4. The token system

`tokens/tokens.json` (1,092 lines) is DTCG format (`$value`/`$type`
leaves, `{path.to.token}` aliases). Five top-level groups:

- **primitive** — color: `olive` and `teal` 50–900 ramps, `okabe` (7
  Okabe-Ito hues), `gray-olive`; space {4,8,12,16,24,32}; radius
  {sm 6px, md 10px, lg 12px, pill}; font (Inter UI, IBM Plex Mono);
  font-size xs–2xl; line-height; motion durations.
- **semantic** — per palette (olive, teal) × per mode (light, dark):
  surface/content/border subtrees plus accent (alias to a primitive
  step), accent-hover, on-accent, focus-ring, danger, unknown,
  highlight, shadow-overlay. One-way references only (semantic →
  primitive).
- **status** — 14 named statuses (canonical, implemented, deferred,
  unexplored, hard-gate, abandoned, stale, needs-changes, not-covered,
  approved, in-triage, sent, acknowledged, done), each
  `{hue, text{light,dark}, glyph, $description}`, plus a `chart` 1–7
  series scale. This encodes SPEC §5.1's ruled vocabulary (canonical /
  implemented / deferred / unexplored / hard-gate / abandoned — status
  changes only via a mutation carrying a ruling note) plus derived,
  review, and message-lifecycle states, all on Okabe-Ito hues with a
  glyph per status.
- **component** — chip, lane, card, button, frame, panel, layout, row:
  aliases for radius/padding/height only.
- **density** — comfortable/compact sets that re-point the *same*
  variable names (card-padding, row-height 40px vs 32px, …); density
  never renames (generator comment, `viewer/tools/gen-tokens.mjs`).

Modes × palettes (SPEC §11.1–11.2): dark is design-led, light a full
peer; default follows the OS with a persisted Auto/Dark/Light
preference; palettes are token-set variants over identical semantic
roles; the status system never varies by palette, and every palette
must pass the same contrast verification in both modes
(`viewer/tools/verify-contrast.mjs` reads tokens.json directly).

**Consumption.** Only this repo consumes it today: `viewer/tools/
gen-tokens.mjs` (bun, build-time) generates checked-in CSS into
`viewer/client/src/themes/` (`index.css`, `fonts.css`, `olive.css`,
`teal.css`) as `--wb-*` variables — primitive color → `--wb-<palette>-
<step>`, semantic → `--wb-<role>`, status → `--wb-status-<name>` /
`--wb-status-<name>-text`, density re-points component names.
Regeneration is deterministic (byte-identical, no timestamps);
generated files are checked in and marked do-not-edit. Fonts are
bundled woff2 (Inter var, Plex Mono, KaTeX set) via local `@font-face`.

**Kit extraction must carry:** tokens.json itself as the single source;
the tier discipline (primitive → semantic → component, one-way;
density re-points, never renames); the `--wb-*` naming map in
gen-tokens.mjs `varName()`; the full status table including glyphs and
descriptions; the palettes × modes matrix and its contrast gate; the
deterministic-regen + checked-in-CSS rule; the bundled fonts; and, if
the kit includes components and not just tokens, the 24 primitives in
`viewer/client/src/components/` (Badge, Button, Card, Chip, DataTable,
Lane, Sheet, TriageRow, SegmentedControl, …).

## 5. Cross-cutting contracts designed locally

- **Registries, tracked vs untracked.** The per-project registry DB and
  its `registry.json` export are untracked in *every* adopting repo by
  design (this repo's `.gitignore`: `workbench/registry.db*`,
  `workbench/registry.json`, `workbench/entries/`, `workbench/archive/`);
  only the manifest is tracked (template:
  `templates/manifest/workbench.yaml`). Two registries this repo *writes
  into other repos*: the scheduler's job registry (YAML files, §3) and
  attention's armed registry (JSON files, §3) — both located by
  workspace-relative sibling seams, both no-op when the sibling is
  absent. Runtime `state/repos-registry.json` is a third, server-local
  registry cache.
- **Config seams.** `server/config.py` defaults ← untracked
  `config.json` (tracked specimen: `config.example.json`) ← `WB_VIEWER_*`
  env (untracked `viewer.env`, tracked `viewer.env.example`). Env seam
  family across the harness: `WB_WORKSPACE_ROOT`, `WB_VIEWER_ROOT`,
  `WB_TMP_ROOT`, `WB_VIEWER_SWEEP_ROOTS`, `WB_SCHEDULER_JOBS_DIR`,
  `WB_ATTENTION_ARMED_DIR`, `WB_VIEWER_CONFIG`, `WB_KIT_BACK_HREF`, plus
  deploy's `VIEWER_RUNTIME_DIR` / `HATCHLET`.
- **Spec/supervision-kit copies.** `AGENTS.md` carries a managed
  spec-sync block (`<!-- spec-sync:supervision-rules -->`) synced from
  the starter's `docs/supervision-rules.md` — hard-stop floor, defect
  routing, verified-instructions, only-a-measure-clears,
  registry-driven supervision. It is the only spec-sync marker in the
  tracked tree (also referenced in `context/progress-tracker.md`). The
  six-file `context/` set (project-overview, architecture, ui-context,
  code-standards, ai-workflow-rules, progress-tracker) restates SPEC
  material — ui-context.md restates §11's fundamentals; architecture.md
  restates §§2–4 — a second home for the same rules.
- **Duplicated rule text.** The checkpoint line format and 2-missed-
  checks stall rule are stated in `lib/progress/report.py`, SPEC §6,
  the AGENTS.md supervision block, and rendered into every scheduler
  entry (`schedule.py`'s `_CLASSIFICATION` / `_OWNER_REASON` /
  `_SELF_REMOVAL` strings). The classified-catalog axes
  (origin/generality/use_case) are defined once per surface: manifest
  template + `lib/manifest.py` validation, scheduler-entry renders
  (`lib/progress/schedule.py`), SPEC §17.
- **Templates carrying copies.** `templates/choice-kit/` (kit.html
  runtime + spec.demo.json — a stamped copy of the choice-kit runtime
  per study), `templates/manifest/`, `templates/staging/` (a full
  staging-project manifest + GRADUATIONS.md).

## 6. Overlaps with the other three workhorses

- **Scheduler catalog vs workbench todos.** The harness already writes
  part of the scheduler's catalog: one machine-classified YAML job
  entry per armed todo, lifecycle-owned by the todo writers
  (`lib/progress/schedule.py`; tests `tests/harness/
  test_progress_schedule.py`). The entries are derived state — the
  doctor flags any that outlive their todo. The manifest's `catalog_*`
  fields reuse the scheduler registry's classification vocabulary
  verbatim (`lib/manifest.py`; template comment: "the shared catalog
  axes (the scheduler registry's vocabulary)"). So the overlap is
  contractual, not accidental: workbench todos are the record, scheduler
  entries are their projection.
- **Attention Today/Digest vs workbench surfaces.** Three contact
  points: (1) the armed-row write contract (§3) — workbench is the
  producer, attention's evaluator the consumer; (2) the classification
  endpoint (§3) serves the same progress derivation an evaluator needs,
  to a venue-side consumer; (3) surface-level duplication — the
  viewer's Home/Board/Todos present per-project review queues and
  approval coverage (`lib/home.py`, `lib/staleness.py`) in the same
  territory as attention's Today/Digest, and the harness runs its own
  message store + outbox + Inbox section (`lib/messages/`,
  `/api/messages`, `/api/outbox`) with the doctor posting a findings
  *digest* through it — a dispatch/digest mechanism parallel to
  attention's ledger/digest, built earlier and independently.
- **Runner.** No direct code contact (no colab references in `lib/` or
  `server/`). Indirect: the classification endpoint's named consumer is
  the harness connector's venue-side workbench tool, and the
  worktrees/diff feeds (`lib/worktrees.py`,
  `/api/projects/<slug>/worktrees|diff`) serve venue-lane working state.
- **Viewer shells.** This repo alone has three shells: the Python
  companion server, the artifact TS bridge (`viewer/server/src/`, with
  its generated `privileged.contract.ts`), and the client shell —
  plus the choice-kit's `kit.html`. The seed plan's "viewer shells"
  consolidation candidate starts here, before counting the scheduler's
  and attention's separate viewers.

## 7. Consolidation notes

**Preserve exactly.**

- File-todo format and id scheme: bundle layout
  (`.plans/<date>-<slug>/todos/*.md`, `finished/`), front-matter fields
  including `progress_check` / `progress_armed`, and the
  `progress-checkpoint:` body-line format — scheduler entries,
  attention rows, lane drivers, and the doctor all key off these.
- The armed-row JSON shape and the scheduler-entry YAML shape (§3):
  two other live systems consume them as written.
- Registry unified schema + `registry.json` export shape, and the
  "data never migrates" rule (AGENTS.md): each project's registry DB
  stays in its owning repo; the mega repo inherits tooling, not data.
- The ruled status vocabulary (SPEC §5.1) and its token status table —
  they are one contract expressed in two files (SPEC.md,
  tokens/tokens.json).
- The manifest (`workbench.yaml`) format, including its `catalog_*`
  classification fields.

**Merge into the pipeline layer.** The registry store + plans parser +
bundle writers (the work-record engine); progress derivation + both
arming writers (supervision contract producers); sweep/manifest
discovery; doctor; messages/outbox + notify (a dispatch engine that
predates attention's); the repos/datasets/diffs derivation set.

**Stay app-side.** Viewer client sections and components, generated
themes, the choice-kit runtime, guarded-save editing UX, and the
board/todos/entries presentations (fed by pipeline derivations).

**Platform gaps this repo exposes.** Deploy is drift-guarded sync with
no release record (`viewer/deploy.sh` can report "deployed but NOT
published" — there is no ledger either way); the gate is external by
design (HEAD commit). Both are exactly the pipeline's missing
deployment/release-record and gate-runner services. State-store backup:
registry DBs, `messages.db`, and `state/` have no backup story in-repo.

## 8. Risks and unknowns

- Two todo stores with near-identical vocabularies (registry-DB todos
  vs file todos, §2) plus a third projection (scheduler entries):
  consolidation that merges the wrong pair corrupts the work record.
- The cross-repo write contracts assume sibling layout (workspace root
  = this repo's parent) and the overlay rule — adopting projects must
  keep building with the harness absent. Internalizing the seams in a
  mega repo must not break external adopters (e.g. another-project,
  registered per AGENTS.md with an untracked-only footprint).
- Token consumption is bun-generator-only; how the scheduler and
  attention viewers would consume tokens.json (no bun in their stacks,
  presumably) was not inspected — the kit needs a generator story per
  consumer stack.
- Counterpart sides not inspected here: attention's evaluator (armed-row
  consumer), the scheduler's entry loader, and the harness connector
  (classification consumer). Shapes above are as *written/served* by
  this repo at the pin.
- `state/repos-registry.json` contents and the full messages-DB schema
  were read at file/function level only, not row level.
- Runtime state on this machine (live `state/`, `workbench/` data,
  sibling repos) postdates the pin in places; this review read the
  tracked tree at `fd870ae` only.
