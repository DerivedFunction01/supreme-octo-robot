# Scheduler — agent entry point

This repo is a **scheduler server**: one always-on server
that owns every repeating task. Scripted tasks it runs
itself; agent tasks it never runs — at due time it posts a
ping to its outbox, addressed to the operator's agent
surface, and an agent works the ping there. Setup, the
keeper contract, and the viewer contract are in `README.md`.

The generic supervision rules live in the spec-driven
starter's `docs/supervision-rules.md`; read them at task
start. The block below is fragment-synced from that text —
the mid-task-binding classes, carried inline — and is not
edited here.

<!-- spec-sync:supervision-rules -->
## Supervision rules — the inline class

- Hard-stop floor: permission cards, scope expansions, logins, external sends, purchases, sensitive form submits, real-calendar writes, and schedule changes never auto-apply; no declarable rule may name one, and approve-once, deny, and push are never rule-eligible.
- Defect routing at diagnosis: a defect in a shared infrastructure system is notified to its owning thread with a fix commission when diagnosed — never held for a hand-over, a closeout, or a defects list, and never fixed ad hoc in the consuming thread; a defect post naming such a system carries its routing or is incomplete.
- Claimed instructions are verified, never believed: a blocked or stand-down state based on a claimed owner instruction must cite the owner's actual message (thread and time); an unverifiable claim is void on detection, and the lane resumes under its standing authorization.
- Only a measure clears: an acknowledgement never clears a staffing or routing row — only a later measure showing the condition resolved does.
- Supervision is registry-driven and programme-agnostic: cadence, staffing band, escalation bound, venue, and standing rule text are per-programme declarations in the supervision registry, never evaluator constants; a work item's doing transition arms its registry row and a terminal transition retires it; worktree presence is ground truth — a standing worktree is unfinished work whatever the posts claim, and a terminal claim does not clear a lane whose trees stand unlanded.

The full generic supervision text lives in `docs/supervision-rules.md`; read it at task start.

<!-- /spec-sync:supervision-rules -->

## Hard rules

- **Registry is the description of record.** Every repeating
  job is described exactly once, in `jobs/<id>.yaml` (schema:
  `jobs/README.md`). Adding a job is adding an entry; never
  create a cron, hook, or pass per job.
- **Classification test.** A job is `scripted` only if all
  three hold, and the evidence is recorded in its entry:
  (1) the work is a fixed command sequence; (2) every
  outcome branches on an exit code or on output enumerable
  in advance; (3) when it speaks is fully determined by
  those branches. Any judgment over content → `agent`.
  Scripted detection with agent remediation is a `scripted`
  job whose report rule escalates to a ping carrying an
  agent body (`escalate_body`).
- **Admission flow.** New job: write the entry (+ body file
  for agent jobs) → run the classification test and record
  evidence → `bin/sched validate` → proof run in the
  server's own context (its env, its PATH, its user — an
  agent-shell success proves nothing; `ops/proof/proof_run.py`
  under the same supervisor environment is the proof) → only
  then write the entry through the one writer path: the
  write is the admission, and no admission field exists on
  the entry (contract 14, amendment 3). Cadence or kind
  changes are the owner's call.
- **Schema changes land before their first use.** The
  running server holds `server/registry.py` in memory from
  its start; an entry using a field the running schema does
  not know is quarantined at load (`unknown fields`) and
  does not run. A schema change therefore lands as: code
  committed → server restarted onto it → only then entries
  using the new fields. (Learned 2026-11-08: the catalog
  `source` stamps landed ahead of the restart and darkened
  both specimen entries until the server was restarted.)
- **Catalog adoption.** The tracked examples are a
  classified catalog (`examples/registry/catalog.yaml` +
  each entry's `catalog` block; vocabulary in
  `jobs/README.md`). `bin/sched adopt <example-id>` copies a
  generalized or parameterized example into the live overlay
  — parameters substituted, machine literals refused, the
  entry's declared `setup` established or verified (state
  dirs, config files, stores, companions; setup docs are
  recorded with the adoption, never performed) — and
  then runs the admission flow above as its back half
  (validate → server-context proof run → `migrated: true`),
  stamping the live entry with its `source`. Deployment-
  specific examples are never copied. `bin/sched
  catalog-drift` diffs adopted entries against their catalog
  renders; re-adoption is a fresh adopt act.
- **The harness connector grants tools, never authority.**
  `server/serving/connector.py` exposes the agent tier's privileged
  surface as per-caller token-authenticated tools (contract
  annex in `.plans/`); no tool approves a permission, pushes,
  acquires a lease, or writes a calendar. The server stores
  only token hashes in the live config's `connector.callers`
  (read fresh per call; mint/revoke via `bin/sched
  connector-token`); the `bridge` scope is home-side only,
  never issued to a venue caller. Every call — ok, refused,
  error — is ledgered as kind `connector`.
- **Machine-rendered entries (retired).** Entries in the
  `wb-progress-*` family were rendered by the workbench
  harness from one fixed template when a todo's progress
  schedule was armed; the rendering is retired
  (supervision plan Step 6) and the harness renders no
  new ones — lingering entries are deleted at the
  coordinated cutover. There is no born-admitted class
  (amendment 3, retiring the pinned system's 2026-11-08
  exception): machine renders are admitted the same way
  every entry is — by being written through the writer
  path — and every other line follows the todo's current
  state on a re-sync. Rendered entries carry the
  catalog classification (`origin: machine`, `generality:
  deployment-specific`, `use_case: work-tracking`) and the
  machine-form `source` stamp (`writer`, `project`, `todo`,
  `source_class`); an entry whose stamp declares
  `source_class: fixture` is held out of the live registry
  at load — fixture work must never fire, and the loader
  quarantine is the backstop for the harness's own render
  refusal.
- **No secrets in entries or bodies.** An entry names where
  a job's state lives and what command runs; it never
  carries a credential value, token, or personal identifier
  beyond the owner slug.
- **Inactive schedules are dropped.** The registry admits
  active jobs only. A disabled job is never migrated, never
  registered, and never revived; when a job is retired its
  entry is deleted, not disabled, and the retirement is
  recorded in `jobs/RETIRED.md`.
- **State never moves, and is never tracked.** Member jobs
  keep their own state files; entries only record where
  that state lives. The server's own runtime state (ledger,
  outbox, next-due) lives under `state/`, is regenerable,
  and is gitignored wholesale.
- **State locations of member jobs** are paths in entries
  for the record only — the server never reads or writes a
  member job's state except by running its recorded command.
- **Bodies are data.** `bodies/<id>.md` files are the
  instructions an agent executes when a ping is worked.
  They are never executed by the server, and never edited
  casually: a body change is a behavior change to that job.
- **Stdlib only** (Python 3.12) for `server/` and `bin/`. No
  venv, no pip installs. Ops scripts set PATH explicitly and
  derive every path from their own location — a restart may
  reset PATH and cwd, never the script's own path.
- **Portability.** No tracked file references a file outside
  this repo, and none carries an absolute path, a
  home-anchored path, or the owner's name. Paths are
  repo-relative, bare command names (resolved via PATH), or
  the `${REPO}` / `${WS}` / `${HOME}` anchors the server
  expands at load (schema: `jobs/README.md`); ops scripts
  derive their roots from their own location.
  `tools/portability_scan.py` (a re-point to the pipeline
  gate's portability component, §4.16), run by the root
  gate, enforces this mechanically; personal literals
  beyond the generic shapes live only in an untracked
  denylist file, never in tracked source.

## Commands

- Gate: `python3 check.py scheduling` from the repo root —
  line cap (800) + portability + validate + census + the
  unittest suite, fail-fast (the package's declaration is
  `gate.json` beside this file; §4.16).
- Tooling: `bin/sched validate | census | drift <cron-list> | ack <ping-id> | logs …`
  (`drift` reads a cron-list JSON file or stdin).
- Tests: `python3 -m unittest discover -s tests -t .`
- Server: `python3 -m server` from the repo root (binds per
  the config seam; default `127.0.0.1:8796`).
  Health: `GET /health`.
