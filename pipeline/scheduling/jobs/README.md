# Registry entry schema — `jobs/<id>.yaml`

The schema of record for registry entries. One file per
repeating job. The filename is the id; an `id` field inside
must match it or the entry is invalid.

**Paths are portable.** Tracked files in this repo never
carry absolute, home-anchored, or otherwise outside-repo
paths (the portability rule, enforced by the root gate
(`check.py`, §4.16) and at registry load). In `run.argv` and `state_paths` a path is
either a bare command name (resolved via PATH, no slash) or
begins with an anchor the server expands at load:

- `${REPO}/...` — inside this repo.
- `${WS}/...` — inside the workspace root (the repo's parent
  directory by default; config key `workspace_root`, env
  `SCHEDULER_WORKSPACE_ROOT`).
- `${HOME}/...` — inside the directory above the workspace
  root.

Any other path containing a slash fails validation.

Entries are YAML in the strict subset the registry module
parses: nested maps by two-space indentation, lists of
scalars (`- item` lines or a flow `[a, b]`), and scalar
values (bare, single- or double-quoted, integers, booleans,
`null`). No anchors, no flow maps, no multi-line strings, no
lists of maps.

## Fields

- `id` (required) — must equal the filename stem.
- `title` (required) — one line.
- `kind` (required) — `scripted` | `agent`, decided by the
  classification test in `../AGENTS.md`.
- `status` — `active` (default) | `suspended`. A suspension
  carries `suspend_reason` and `suspended_on`, and suspended
  entries print in every census so they cannot rot silently.
  A suspension is a deliberate pause of a live job — not a
  disabled-zombie state, which never enters the registry at
  all (see "Retiring a job" below).
- `cadence` (required) — exactly one of:
  - `{type: interval, every: <Nm|Nh>}` (Ns also accepted)
  - `{type: daily, at: "HH:MM"}`
  - `{type: weekly, dow: [Mon..Sun], at: "HH:MM"}`
- `timezone` — optional IANA override; default is the server
  config's `default_timezone`.
- `owner` (required) — `goal:<slug>`, or `none` with
  `owner_reason`. The shipped examples use `goal:example`;
  replace it with your own tracking slug.
- `run` (scripted, required) — a map:
  - `argv` — the command as a list of strings, never a shell
    string, unless `shell: true` with `shell_reason`, in
  which case `argv` may be one string run under `bash -c`.
    Path elements follow the portability rule above.
  - `cwd` — optional working directory.
  - `env_names` — optional list of environment variable
    NAMES whose values are taken from the server's own
    environment. Names only — no literal values, and never
    secrets.
- `body` (agent, required) — path under `bodies/`. Body
  existence is checked in two contexts: in the live registry
  a missing body is invalid, and the server's load requires
  bodies unconditionally. A clean checkout carries no
  `bodies/` at all (the live overlay is gitignored working
  state), so there a reference into the absent overlay is
  not an error — `validate`/`census` report it as a named
  overlay-absent state, counted in their output.
- `executor` (agent, required) — the registered name of
  the surface that claims and works the job's pings: a
  cron id, a named worker, a seat, a thread's registered
  name. The server mints an agent job's pings and never
  works them, so the field is the admission contract for
  the kind: an agent entry without one fails validation
  and does not arm, and a lone generic word or
  to-be-decided marker (`TBD`, `none`, `agent`, …) is a
  placeholder, not a designation, and fails the same way.
  Scripted entries do not carry it — the server runs
  those itself. A named executor whose pings stand
  unclaimed past two cadences is named by `bin/sched
  census` as an unworked defect.
- `escalate_body` — optional, for a scripted job whose
  failure hands an agent a remediation body.
- `timeout_secs` (required, no default) — an entry without
  a budget does not validate.
- `report` — a map:
  - `when` — `never` | `on_failure` | `always` | `on_output`
    (default `on_failure`). `on_output` fires a `report`
    ping when a successful run's output carries a line that
    is neither blank nor matched by `quiet_patterns` — for
    jobs that are silent when there is nothing to say.
  - `ok_exit_codes` — list of integers, default `[0]`. A run
    ending outside this list is a failure. A check whose
    findings are a normal outcome declares them here (e.g.
    `[0, 1]`: clean and findings-exist are both normal).
  - `fail_patterns` — optional list of output substrings
    that make an otherwise-ok exit a failure, with the
    matched pattern named in the run record.
  - `report_patterns` — optional list of output substrings
    that make a successful run produce a `report` ping
    without being a failure (the mirror of `fail_patterns`).
  - `quiet_patterns` — optional list of substrings; with
    `when: on_output`, output lines matching one are the
    nothing-to-report case.
- `state_paths` — where the job's own state lives. Recorded,
  never moved; the server touches those paths only by
  running the job's recorded command.
- `classification` (required) — one line of evidence for the
  kind, under the three-part test in `../AGENTS.md`.
- `lifetime` — `permanent` (default) | `until_complete`.
  `self_removal` records how an `until_complete` job removes
  itself and its entry when its condition is met.
- Admission — there is no admission field. The migration
  field family (`migrated`, `migrated_at`, `migration_note`,
  `proof_pending`) does not exist in this format (contract
  14, amendment 3): an entry stands in the registry only by
  being written through the one writer path — validate,
  then the server-context proof run, then the write — so
  presence is admission and the engine fires every `active`
  entry it finds here. Admission evidence (validation
  counts, proof outcome) is recorded as events in the
  ledger, not as fields on the entry. Machine-rendered
  entries (`wb-progress-*`, `venue-liveness-*`) are admitted
  the same way: by their writer's write, with no
  born-admitted class.
- `catalog` — the classified-catalog block (examples layer):
  `origin` (hand | machine | per-session), `generality`
  (generalized | parameterized | deployment-specific),
  `use_case` (a discoverability label), and `parameters`
  (a map keyed by name; each declares a dotted `field` path
  and exactly one of `default` or `required: true`, plus an
  optional `description`). Classification is descriptive,
  not activating. The catalog index is
  `examples/registry/catalog.yaml`; `bin/sched validate`
  checks the layer.
- `catalog.setup` — what an adoption must establish beyond
  the entry itself: `state_dirs` (created by the adopt
  verb), `files` (a map keyed by name: a `target`, copied
  from a catalog specimen when `from_catalog` names one,
  otherwise verified present), `stores` (a map keyed by
  name: a `path`, verified present or initialized by the
  declared `init` argv), `companions` (catalog entries that
  must already be adopted), `registrations` (declared
  manual steps the verb surfaces in its report), and `docs`
  (Markdown files in the layer describing documentation
  amendments — AGENTS.md edits — the adoption requires; the
  verb records them under `state/adoptions/<live-id>/` and
  names them, and never performs an amendment itself).
  Every `state_paths` entry must be covered by the setup
  declaration — the validator enforces it.
- `source` — the provenance stamp on a live entry, in one
  of two forms that never mix. The adoption form, stamped by
  `bin/sched adopt`: `catalog` (the example's id),
  `catalog_version`, and `parameters` (the flat map of
  effective parameters the adoption used, standard set
  included); `bin/sched catalog-drift` re-renders the
  expected live form from the stamp and diffs. The machine
  form, stamped by a rendering writer (the wb-progress
  family — retired, Step 6; the harness renders no new
  ones and its entries are deleted): `writer`,
  (`project` | `fixture`) — lawful only on an entry whose
  `catalog` block declares `origin: machine`, and counted
  as machine-written by the drift census, never as adopted.
  A machine entry declaring `source_class: fixture` is held
  out of the live registry at load (quarantined and named,
  like an invalid file): fixture work must never fire.
- `config` — the entry's tunable-knob block (contract 09):
  the entry record is the source the engine reads at fire
  time; edits write back through the one writer path (the
  guarded save in `server/entries/configblocks.py`). Map-shaped,
  because the YAML subset has no lists of maps: `version`
  (the store's version stamp — a positive integer; a save
  presents the version it loaded and is refused when the
  stamp has moved), `knobs` (a map keyed by knob name; each
  knob declares `label`, `type` (`integer` | `number`),
  `unit`, `value`, `min`, `max`, with the value inside its
  range, and may declare `env`), and optional
  `constraints` (a map keyed by name;
  each declares `kind: lt`, `left` and `right` knob names,
  and a `message`; the block's own values must satisfy
  every constraint). The API serves the block projected to
  the contract's array form, version stamp included. An
  entry with no knobs carries no block — honest absence,
  not an empty block.
- `config` knobs' `env` — the fire-time seam (contract 09):
  a knob declaring `env: <NAME>` names the environment
  variable the engine sets to the knob's value, in the
  knob's own unit, when the entry fires — the variable the
  fired script actually reads (`storage-watch`'s tiers →
  `STORAGE_WATCH_HOME_LOW_GB` / `STORAGE_WATCH_HOME_CRIT_GB`;
  `memory-index-watchdog`'s thresholds →
  `SCHEDULER_TOPIC_FILE_MAX_BYTES` /
  `SCHEDULER_TOPIC_PER_FILE_BYTES`, which its check script
  already takes as parameters). The mapping is declared on
  the knob, beside the block schema — the engine carries no
  per-job table. A knob with no `env`, and an entry with no
  block, fire with exactly the environment they fire with
  without the seam.

Not an entry field: next-due bookkeeping. It is runtime
state under `state/` (gitignored), so a restart neither
refires nor skips a job and the tracked registry stays a
pure description.

Secret-shaped values anywhere in an entry fail validation:
no credential values, tokens, or key material, ever.

## Retiring a job

A retired job's entry is deleted, never disabled — the
registry admits active jobs only. Record the retirement in
`jobs/RETIRED.md` (id, what it was, and why it is retired)
so the census stays complete even
though the entry is gone.

## Worked example — scripted

One of the shipped examples, `jobs/example-pulse.yaml`:

```yaml
id: example-pulse
title: Example pulse (scripted interval job)
kind: scripted
status: active
cadence:
  type: interval
  every: 5m
owner: goal:example
run:
  argv:
    - bash
    - ${REPO}/examples/example_pulse.sh
timeout_secs: 60
report:
  when: on_failure
  ok_exit_codes:
    - 0
state_paths: []
classification: fixed command; prints one line and exits 0; every outcome branches on the exit code alone
lifetime: permanent
```

## Worked example — agent

One of the shipped examples, `jobs/example-agent-review.yaml`:

```yaml
id: example-agent-review
title: Example agent review (agent job)
kind: agent
status: active
cadence:
  type: daily
  at: "09:00"
owner: goal:example
body: bodies/example-agent-review.md
executor: operator agent surface
timeout_secs: 1800
state_paths: []
classification: the work is reading the day's run record and judging what deserves the operator's attention - judgment over content, so agent
lifetime: permanent
```
