# Scheduler review — workhorse superapp consolidation

Findings first:

1. **The pinned commit is not the live system.** The tracked tree (107 files) ships the engine, the registry schema, a classified examples catalog, and exactly two live entries (`jobs/bridge-wake.yaml`, `jobs/bridge-drain.yaml`). The deployed fleet — roughly forty `jobs/*.yaml`, all twelve `bodies/`, the bridge caller→chat routing config, the file-registry manifest, and several member scripts — is an untracked overlay held out of git by the tracked `.gitignore` plus local-only `.git/info/exclude`. A verbatim copy of the pin loses the fleet; consolidation must inventory the overlay separately and promote its contracts deliberately.
2. **The two tracked live entries are not self-contained.** Both bridge entries name body/config files under `bodies/`, which `.gitignore` ignores wholesale, so `bodies/bridge-drain.md`, `bodies/bridge-wake-item.md`, and `bodies/bridge-wake-owners.yaml` are absent from the pin. Registry validation checks body existence on the local filesystem, not trackedness — the pin validates here and would quarantine on a fresh tree.
3. **The scheduler is already a pipeline with apps on top.** Engine, schedule math, ledger, outbox, ops service, connector/bridge queue, catalog/adoption, and the watchdog ladder are separable engines bound by explicit record formats; the viewer, job bodies, and hand-written entries are consumers/declarations over them. The D6 split mostly formalizes a boundary the code already draws (`server/api.py`: backend does the work, viewer is a consumer).
4. **Three platform services the superapp plan wants do not exist here.** No automatic gate-runner service (gates are local `check.sh` invocations and one-shot proof runs), no deployment/release record (UI deploy keeps timestamped runtime backups; nothing ties artifact ↔ commit), and no automatic state-store backup (ledger export is manual; outbox, next-due, config, and bridge records have no scheduled backup in the inspected code).
5. **Two dispatch systems already live in this repo.** The outbox/keeper wake cycle and the connector bridge queue + `bridge-wake` minter + `bridge-drain` agent job together implement wake minting, target resolution, episode coalescing, ack semantics, and delivery audit — the same functional territory as attention's dispatch. They should merge into one pipeline dispatch substrate, not be re-implemented beside it.
6. **`/ops` attribution is self-asserted.** In the inspected HTTP code, `POST /ops` performs no bearer-token authentication; it trusts a caller-supplied `caller` string for the ledger audit record. Its practical boundary is the loopback bind and workspace scope, unlike `/tools`, which is token-authenticated. This needs an explicit decision in consolidation, not silent inheritance.

## 1. Verification

- `git -C <workspace>/scheduler rev-parse HEAD` → `196a29d013fc44469b9f9b31232ce623ec489d62` — exact match with the pin. Pinned-tree reads below are working-tree reads of tracked files; no `git show` fallback was needed.
- Pin commit: `2026-11-12T15:51:04+00:00`, subject "bridge: chat_send wakes address the drain home; digested queue list".
- `git status --porcelain --untracked-files=all` shows exactly one entry: `?? jobs/owner-attention-healthcheck.yaml` — uncommitted state outside the pin, noted here and not reviewed as committed code.
- The pin is local and unpushed (parent verification, 2026-11-12 11:05 EST: local `196a29d` vs remote `main` `5b98cf0`, ahead 3 / behind 0).
- Tracked tree at the pin: 107 files — `examples/` 32, `tests/` 24, `server/` 17, `ops/` 16, `ui/` 7, `jobs/` 3, `bin/` 2, `tools/` 1, plus `README.md`, `AGENTS.md`, `config.example.json`, `check.sh`, `.gitignore`. Tracked under `jobs/`: only `jobs/README.md`, `jobs/bridge-wake.yaml`, `jobs/bridge-drain.yaml`. Nothing tracked under `bodies/`.
- Read-only throughout: no checkout, stash, commit, test suite, gate, or server run. Behavior claims rest on code and docs.

## 2. Anatomy

### Shape and entry points

One always-on server owns every repeating job (`README.md`). Scripted jobs are executed by the server itself; agent jobs are never executed by the server — at due time the server appends a durable ping to an outbox and an external keeper wakes the agent surface. The keeper is deliberately outside the server so it survives server crashes and host restarts. Python 3.12, standard library only.

- Server: `server/__main__.py` → `server/main.py:main` — resolves config, constructs `Engine`, acquires the single-instance lock, starts the stackdump watchdog, starts `ThreadingHTTPServer.serve_forever` on a daemon thread, then loops `engine.tick()` every `tick_secs` (default 20s). Shutdown waits for running jobs, stops HTTP, releases the lock.
- Operator CLI: `bin/sched` — verbs `validate`, `census`, `drift`, `ack`, `logs` (`stats|prune|export|verify|import-jsonl`), `adopt`, `catalog-drift`, `connector-token`, `flap`, and the ops clients `write|patch|exec`. Caller names come from `--caller` or `$SCHED_CALLER` (default `sched-cli`) and are ledgered with every op; exit 4 means the server was unreachable and nothing was performed — the client never writes directly.
- Venue client: `bin/harness` (see Connector below).
- Supervisor: `ops/scheduler-server.service.tmpl`, `ops/watchdog.sh`, `ops/keeper_poller.sh`.
- Viewer: source in `ui/`, deployed by `ui/ui.sh` (see Deploy plumbing).

### Configuration

`server/config.py`: precedence `SCHEDULER_*` env > live `config.json` > built-in defaults; `resolve()` returns values plus per-key sources, which `/health` reports. Keys: `host` (127.0.0.1), `port` (8796), `home`, `workspace_root`, `tick_secs` (20), `default_timezone` (code default `America/New_York`), `outbox_ack_timeout_secs` (3600), `ledger_retention_days` (90), `capture_cap_bytes` (65536), `git_ssh_identity_file`, `git_ssh_known_hosts_file`, `workbench_base_url` (default `http://127.0.0.1:8792`), and the stackdump cadence/threshold/repeat/max-bytes family. `connector` is read separately and fresh by `server/connector.py`. `home` defaults to the repo root, `workspace_root` to its parent. Path anchors expanded at registry load: `${REPO}` (repo root), `${WS}` (workspace root), `${HOME}` (above workspace root).

Inconsistency: `config.example.json` sets `"default_timezone": "UTC"` while the code default is `America/New_York`.

The live `config.json` is gitignored and may carry port/timezone, the Git SSH path pair, connector caller token hashes and scopes, `workbench_base_url`, and workspace/home settings.

### Job registry and catalog

Authoritative: `jobs/README.md`, `server/registry.py`, `AGENTS.md`.

- One file per job: `jobs/<id>.yaml`; the filename stem is the job id and an internal `id` field must match it. The registry is the description of record — adding a job means adding an entry, never a separate cron/hook per job.
- Entries use a strict YAML subset parsed by `server/registry.py`: nested maps by two-space indentation, scalar lists only (flow scalar lists allowed), no anchors, flow maps, multiline strings, or lists of maps. Unknown fields are invalid and quarantined; secret-shaped values anywhere fail validation.
- Required in practice: `id`, `title`, `kind`, `cadence`, `owner`, `timeout_secs`, `classification`. `kind` is `scripted` or `agent`. `status` is `active` (default) or `suspended` with `suspend_reason` + `suspended_on`. Cadence is exactly one of `{type: interval, every: <Ns|Nm|Nh>}`, `{type: daily, at: "HH:MM"}`, `{type: weekly, dow: [...], at: "HH:MM"}`.
- `owner` must be `goal:<slug>`, or `none` with `owner_reason`.
- Scripted entries require `run`: `argv` (list of strings), optional `cwd`, optional `env_names` (names only, never values), `shell: true` only with `shell_reason`. Agent entries require `body: bodies/<id>.md`; scripted entries may carry `escalate_body`. Body paths must be repo-relative and exist on the filesystem at validation time.
- `report`: `when` (`never|on_failure|always|on_output`), `ok_exit_codes`, `fail_patterns`, `report_patterns`, `quiet_patterns`. `state_paths` records where a member job's state lives; the server does not move it.
- `classification` is required evidence. The test (`AGENTS.md`): scripted only if (1) fixed command sequence, (2) every outcome branches on exit code or output enumerable in advance, (3) when it speaks is fully determined by those branches. Any judgment over content makes it agent; scripted detection with agent remediation is a scripted job whose failure escalates with an agent body.
- `lifetime`: `permanent` or `until_complete` (with `self_removal`). Retired jobs are **deleted**, never disabled; the retirement is recorded in `jobs/RETIRED.md`.
- `migrated` is load-bearing: the engine fires only `migrated: true` entries. Admission flow: write entry + body → record classification → `bin/sched validate` → proof-run in the server's own context (its environment, PATH, user; `ops/proof_run.py` writes `state/proof-<job-id>.txt`) → only then set `migrated: true`. `proof_pending` records an owed proof. Machine-rendered `wb-progress-*` entries are the exception: born `migrated: true` (§5).
- `source` stamps come in two forms that never mix. Adoption form: `catalog`, `catalog_version`, flat `parameters`. Machine form (lawful only when `catalog.origin == machine`): `writer`, `project`, `todo`, `source_class` (`project|fixture`); a fixture-classed machine entry is held out of the live registry at load and must never fire.
- Portability: entry paths may be bare command names or start with `${REPO}/`, `${WS}/`, `${HOME}/`; any other slash-bearing path fails validation. Tracked files must carry no absolute/home-anchored/outside-repo paths; `tools/portability_scan.py` under `check.sh` enforces this.
- Schema-change ordering is explicit: code lands and is committed → server restarts onto the new schema → only then may entries use new fields. The running server holds `server/registry.py` in memory; an entry ahead of it quarantines.

Catalog and adoption (`server/catalog.py`, `examples/registry/catalog.yaml`): the tracked `examples/registry/` layer is a classified catalog in embryo — catalog version 1 indexes every file in the layer exactly once. Each entry carries a `catalog` block; row and block must agree on `origin` (`hand|machine|per-session`), `generality` (`generalized|parameterized|deployment-specific`), and `use_case`. Row classes: `entry`, and `config-example` (data specimens that ride with one named entry's adoption, never adopted standalone). Classification is descriptive, not activating — being catalogued admits nothing. At the pin the catalog holds demo entries, file-registry check, storage watch, VM restart detector, local-test watch, stale-mockup cleanup, a machine-origin Colab liveness example, and several deployment-specific sweeper specimens. `bin/sched adopt` copies a generalized/parameterized example into the live overlay, substitutes declared parameters plus the standard set (`id`, `title`, `owner`, `owner_reason`, `timezone`), refuses machine literals in structural fields, renames body paths to the live id, establishes or verifies declared setup (state dirs created; files copied from a specimen or verified; stores verified or initialized by declared argv; companions verified adopted; registrations surfaced as manual steps, never machine-acted; setup docs copied into `state/adoptions/<live-id>/` and named, never performed), requires every `state_paths` entry to be covered by the setup declaration, then runs the admission back half (validate → server-context proof → `migrated: true`) and stamps the adoption-form `source`. `catalog.drift()` re-renders adopted entries from their stamps and diffs them against live files (`migrated`, `migrated_at`, `source` volatile); hand-written, machine-written, and per-session entries are counted separately — their writers own their lifecycle. The catalog module also carries the YAML serializer that emits exactly the registry's strict subset.

### Engine, schedule, executor

`server/engine.py`, `server/schedule.py`, `server/executor.py`:

- The engine rescans the registry every tick. A registry that fails to parse keeps the last-good registry running and escalates once per distinct error signature. Corrupt durable state is fail-safe: no firing at all.
- A due grid point is consumed and persisted **before** the run starts, so a crash or backward clock jump can delay but never duplicate a run. Missed points collapse to the latest due point; the collapsed count is ledgered. A still-running entry skips its due point (no self-overlap). Same-tick dues dispatch in entry-id order, each scripted execution in its own thread.
- Agent dues create/coalesce an outbox ping plus a ledger `agent_due` record; the server does not run the body.
- Report rules: non-ok runs escalate unless `report.when == never`; successful runs report if `when == always`, a report pattern matches, or `when == on_output` with a non-quiet output line.
- Ledger pruning runs inside the engine once per day per `ledger_retention_days`.
- `health_data()`: `status` (`ok|registry_error|state_error`), state error, registry errors, registry count, last tick, outbox depth, running job ids, last stackdump timestamp.
- Schedule math: durable instants are UTC; timezones only turn wall-clock cadences into grid instants. Interval grids anchor to the persisted first `next_due` and advance by whole intervals. DST: spring-forward gap fires at the first valid instant after the gap; fall-back repeated hour fires once, at its first occurrence.
- Executor: argv in its own subprocess group; stdout/stderr captured in tail buffers up to `capture_cap_bytes` (output alone never kills the process); timeout kills the group (SIGTERM, then SIGKILL after 5s). Run classification: `ok|failure|timeout|spawn_error`; a non-ok exit outside `ok_exit_codes`, or a `fail_patterns` hit on an otherwise-ok exit, is `failure`. Scripted runs ledger a `run` record: job id, due, status, exit code, matched pattern, error, collapsed count, stdout/stderr tails.

### State stores

All runtime state lives under gitignored `state/`; on transfer/reset it is not carried — the README's story is manual ledger export first if history is needed.

- **Ledger** (`server/ledger.py`): SQLite at `state/scheduler.db`, WAL mode, stdlib `sqlite3` only. Table `events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, ts_epoch REAL, kind TEXT, job_id TEXT, status TEXT, record TEXT)`; indexes on `(job_id, ts_epoch DESC)`, `(ts_epoch DESC)`, `(kind, ts_epoch DESC)`. The full event record is stored as canonical JSON (`json.dumps(rec, sort_keys=True)`), so exports reproduce the historical JSONL lines byte-for-byte: JSONL is the export format, SQLite is the store. Operations: record, query by job/kinds/statuses/time, stats, retention prune + VACUUM, export to JSONL with SHA-256, integrity verify, and one-time `import_jsonl` into an **empty** events table only. Event kinds across the code: `run`, `agent_due`, `catchup`, `skipped_overlap`, `ping_created`, `ping_coalesced`, `ping_woken`, `ping_acked`, `ping_voided`, `ack_noop`, `entry_removed`, `registry_error`, `state_error`, `ledger_pruned`, `op`, `connector`.
- **Outbox** (`server/outbox.py`): `state/outbox.json` is the cross-process source of truth — every public operation reloads it first, because the server, `bin/sched`, drills, and `ops/bridge_wake.py` may all write through the `Outbox` class. Writes use the atomic state I/O discipline. Ping kinds: `agent-due`, `escalation`, `report`. Ping record: `id` (12 hex chars from a UUID), `job_id`, `due`, `kind`, `body_ref`, `detail`, `created`, `state` (initially `pending`), `coalesced_count`, `last_woken_at`; ack adds `acked_at`, voiding adds `void_reason`. Coalescing is by pending **job id + ping kind**: a later due updates `due`, increments `coalesced_count`, replaces detail if supplied, ledgers `ping_coalesced`. Reading/listing never acknowledges. A pending ping is wakeable if never woken or last woken at least one ack-timeout window ago. Ack is explicit and separate; acking an already-acked/void ping is a ledgered no-op. Deleting an entry voids its pending pings.
- **Other state** (`server/stateio.py` + ignored `state/`): JSON writes are temp-file-plus-rename with flush and fsync; a missing file returns the caller's default; an existing but unreadable/malformed file raises `StateError`, which the engine treats as fail-safe `state_error` (no firing). Files: `state/next_due.json`, `state/server.lock`, `state/server.log`, `state/stackdumps.log`, `state/connector-bridge/*.json`, `state/adoptions/<live-id>/`, proof files, and member-job state (e.g. `state/flap-state.json`, `state/local-test-watch.json`, `state/mockup-census/`, `state/vm-boot/`, `state/storage-watch/`).

### Served shapes / APIs

`server/http.py` routes; `server/api.py` owns derivations — explicitly "backend does the work; the viewer is a consumer," accepted non-zero exits served as normal outcomes, absent data served as null rather than back-filled. All HTTP JSON is serialized with sorted keys.

- `GET /health` — engine health plus resolved config with per-key sources. Connector config is redacted to caller names and scopes only; hashes never ride `/health`.
- `GET /pings` → `{"pings": [...pending]}`; `GET /pings/wakeable` → `{"pings": [...wakeable]}`; `POST /pings/<id>/ack`; `POST /pings/<id>/woken`.
- `POST /ops` — delegated operations, request body capped at 4 MiB (§2, Ops endpoint).
- `GET /api/v1/overview` — `served_at`, `server_now`, server status/state error/registry errors, pid, uptime, last tick, running jobs, registry totals by kind/status and migrated count, outbox depth by kind and aged count, 24h totals (runs, failures, wakeups served, pings created), total expected wakes/day, storage summary (SQLite kind, event count, DB bytes, oldest/newest, retention days, last prune), selected config values.
- `GET /api/v1/jobs` and `GET /api/v1/jobs/<id>` — job view: id, kind, status, migrated, suspend reason, owner, cadence object + human `cadence_label`, timezone, next due instant + seconds-to-due, last run view or agent activity view, 24h run/activity counts, failure streak, expected wakes/day, report mode. Run view: `ts`, `due`, `status`, `exit_code`, `label`, `matched_pattern`, `collapsed`, `error`, `stdout_tail`, `stderr_tail`; outcome labels are centralized in `outcome_label()` (`OK`, `Exit <n> · normal`, `Failed · exit <n>`, `Timed out`, `Could not start`). Agent activity view distinguishes pending / overdue past ack timeout / served / served · acked. Job detail adds title, timeout, ok exit codes, run/body/escalate_body, state paths, full report block, classification, lifetime, migrated_at, proof_pending, up to 50 recent runs, 50 recent dues, 20 ping-history events.
- `GET /api/v1/pings` — each pending ping plus `age_secs` and `overdue`, oldest first.
- `GET /api/v1/ledger?limit=<1..500, default 50>` — `{served_at, events}`, each event reduced to `ts`, `kind`, `job_id`, and a server-computed human `detail`.
- Connector surface: `GET /tools` (authenticated tool list), `GET /tools/result/<request_id>`, `POST /tools/<name>` (see Connector).

### Ops endpoint

`server/ops.py` implements `POST /ops`; `server/http.py` only routes; `bin/sched` carries the client verbs.

- Requests: write `{"caller", "op": "write", "path", "content"}`; patch `{"caller", "op": "patch", "path", "old", "new"}`; exec `{"caller", "op": "exec", "argv", "cwd"?, "timeout"?}`.
- Paths are absolute or relative to `workspace_root`; the resolved real path must stay inside the workspace root. Writes are staged: sibling temp file → write + fsync → read-back verification → rename over target → best-effort directory fsync. Patch requires exactly one match. Exec: argv a non-empty list of strings; cwd must resolve inside the workspace and exist; timeout an integer 1–600s (default 120); runs in its own process group with tail-capped output; timeout kills the group; response carries `exit_code: null` when timed out, plus `timed_out`, `stdout_tail`, `stderr_tail`. Write/patch success returns workspace-relative `path`, `bytes`, `sha256`.
- Enumerable errors: `bad_request` 400, `outside_scope` 403, `not_found` 404, `no_match` 409, `multi_match` 409, `verify_failed` 500, `io_error` 500. Every attempt is ledgered as kind `op` with caller, op, target, status, error, and exit code where applicable.
- Git SSH seam: exec children receive a pinned `GIT_SSH_COMMAND` (strict host-key checking) only when **both** live-config keys are set (`git_ssh_identity_file` + `git_ssh_known_hosts_file`); a half-set pair pins nothing.
- Authentication: none at this endpoint in the inspected code — see Finding 6. The `bridge` scope discipline on `/tools` does not extend here.

### Harness connector and bridge queue

`server/connector.py`, `bin/harness`, `ops/connector_client.py`. Purpose: expose the agent tier's privileged surface as authenticated tools on the scheduler server so agents on other venues can act while state, ledger, and authority stay home. Explicit boundary: **no authority crosses the connector** — no tool approves a permission, pushes, acquires a lease, or writes a calendar (`server/connector.py`, `AGENTS.md`).

- Caller registry lives in the untracked live config's `connector.callers`: each caller maps to `token_sha256` + `scopes`. Only SHA-256 hashes are stored server-side; the registry is read fresh from `config.json` on every call (mint/revoke needs no restart); a missing/malformed registry means no callers and every call refused. Raw tokens are minted by `bin/sched connector-token`, printed once, never stored in tracked files. Scopes: `read`, `write-state`, `send`, `bridge` — `bridge` is home-side only, never issued to a venue caller. Every call (ok, refused, error) is ledgered as kind `connector` with caller, tool, status, detail; authentication failures are ledgered with caller `unknown`.
- Direct tools: `ping_ack` (write-state; wraps `Outbox.ack`); `sweeper_state_read` (read; `<workspace_root>/approval-sweeper/state.json`, capped 1 MiB); `sweeper_state_write` (write-state; validated JSON, 1 MiB cap, staged write to the same path); `nudge_append` (write-state; appends to `<workspace_root>/approval-sweeper/nudge-ledger.sqlite` — the retired sweeper's SQLite schema is inlined in `server/connector.py` so rows stay indistinguishable from the retired module's, and the server overwrites the record's `source` with the authenticated caller); `workbench_read` (read; only `/api/` paths, base from `workbench_base_url`, 15s timeout with exactly one retry on timeout, returns `{status, body}`).
- Bridged tools: `chat_list`, `chat_tail`, `permissions_list` (read), `chat_send` (send). A bridged call writes a JSON record under `state/connector-bridge/`: `id` (16 hex), `tool`, `args`, `caller`, `ts`, `status: queued`, optional `envelope_id`. Fulfillment (via `bridge_poll`/`bridge_fulfill`, `bridge` scope) sets `done|failed` with `fulfilled_by`, `fulfilled_at`, and `result` or `error`. A caller may fetch only its own result unless it holds `bridge`. Envelope idempotency: `envelope_id` must be 1–128 chars from `[A-Za-z0-9._-]`; a second enqueue with the same `(caller, envelope_id)` returns the existing record with `deduped: true` instead of queueing a twin — specifically so a transport retry cannot double-send a `chat_send`.
- `bin/harness` is the venue client, configured by `HARNESS_URL`, `HARNESS_TOKEN`, `HARNESS_TRANSPORT`, `HARNESS_FERRY_OUT`, `HARNESS_FERRY_IN`, `HARNESS_FERRY_WAIT`; commands cover tool list/call, chat list/tail/send, permissions, ack, sweeper state read/write, nudge append, workbench read, result polling, and bridge poll/list/fulfill/fail. `ops/connector_client.py` is the transport-only client for scripted callers; without a token it runs in shadow mode and records the would-call.
- Legacy coupling: although the approval sweeper is retired, the connector still carries direct tools and fixed workspace paths for its state file and nudge ledger — preserved-record compatibility and a consolidation seam, not a live sweeper engine in the scheduler.

### Bridge-wake minter and in-scheduler agent jobs

Only two live-style entries are tracked at the pin; both are platform machinery with `owner: none` + `owner_reason`, `lifetime: permanent`, `migrated: true`.

`jobs/bridge-wake.yaml` — scripted, every 1m, `America/New_York`, runs `python3 ${REPO}/ops/bridge_wake.py`, timeout 120s, report `on_output` with report pattern `UNRESOLVED` and quiet patterns `WAKE`, `DRAIN`. State paths: `state/connector-bridge`, `state/outbox.json`, `bodies/bridge-wake-owners.yaml`. `ops/bridge_wake.py`:

- Reads queued bridge records directly from `state/connector-bridge/*.json` (no credential needed) and loads caller→chat mappings plus the optional drain-home chat from `bodies/bridge-wake-owners.yaml`.
- Per queued item, plants at most one pending wake ping through the server's own `Outbox` class: job id `bridge-wake-<request_id>`, kind `agent-due`, body ref `bodies/bridge-wake-item.md`, detail exactly `{request_id, tool, caller, target_chat}` — never the item's text.
- Target resolution: for `chat_send`, a configured drain home wins, otherwise the record's own `args.chat_id`; for read tools, the requesting caller's owning thread from the owners config. No honest target → the item stays queued and an `UNRESOLVED` line prints; targets are never guessed.
- Idempotence needs no minter state file: a pending ping for the item suppresses a second mint; a record that leaves `queued` is never re-minted; a ping acked while its record is still queued is re-minted next pass, because fulfillment — not the mint — is the lock.
- Episode escalation: a pass finding ≥1 resolvable queued item and no pending `bridge-drain` ping plants one `bridge-drain` agent-due ping (detail: resolvable count, plus `target_chat` when a drain home is configured). An unresolved-only queue never escalates.
- Output alphabet: silence (nothing to mint), `WAKE…` per mint, `DRAIN items=<n>`, `UNRESOLVED…`.

`jobs/bridge-drain.yaml` — agent, hourly cadence as backstop, body `bodies/bridge-drain.md`, timeout 1800s, state paths `state/connector-bridge` + `state/outbox.json`. Classification: agent by capability, not judgment — only an agent surface holds the runtime tools for the bridged verbs; the body forbids judgment, widening a send, altering queued text, or approving/denying. The primary wake is the minter's once-per-episode escalation ping; the executor acks it only when its final poll finds the queue empty — that ack closes the episode and re-arms the minter.

Tracked-tree gap (Finding 2): `bodies/bridge-drain.md`, `bodies/bridge-wake-item.md`, and `bodies/bridge-wake-owners.yaml` are not in the pin.

### Job bodies

Bodies are data, never code executed by the server; an agent body is the instruction set an agent follows when working a ping, and `AGENTS.md` warns a body change is a behavior change to that job. Tracked catalog body specimens live beside catalog entries in `examples/registry/*.md`, not under `bodies/`; adoption renames them into `bodies/<live-id>.md` (escalation bodies to `bodies/<live-id>-escalation.md`). Specimen shape, e.g. `examples/registry/example-agent-review.md`: read the last day of the ledger and the registry census → note failed runs, escalations, stale jobs → report in at most three lines, repair nothing → ack the ping only after the report is delivered.

### Deploy plumbing

Service (`ops/scheduler-server.service.tmpl`): systemd unit with `@ROOT@`/`@PYTHON@`/`@HOME@` placeholders, `WorkingDirectory=@ROOT@`, optional `EnvironmentFile=-@ROOT@/scheduler.env`, fixed PATH, `ExecStart=@PYTHON@ -m server`, `Restart=on-failure` / `RestartSec=5`, start-limit 300s / burst 5, stdout+stderr appended to `state/server.log`, `WantedBy=default.target`. `HOME` must be the workspace owner's home, not the service user's, because member jobs resolve per-user caches and tool state from HOME.

Keeper (`README.md`, `ops/keeper_poller.sh`): an external poller on a ~120s cadence. Health half: poll `GET /health`; if down, run the watchdog restore ladder; if healthy but the unit file is missing, reinstall it quietly. Wake half: poll `GET /pings/wakeable`, wake the agent surface per ping (agent-due pings worked by body; escalation/report pings relayed), ack only after the work is done. The shipped `ops/keeper_poller.sh` implements the health half via `ops/watchdog.sh` but only **prints** wakeable pings as JSON — actual wake delivery is platform-specific.

Watchdog ladder (`ops/watchdog.sh`): conforms to "VM-restart survival pattern, contract v1" (canonical text in the starter specification, not this repo). Rungs: tracked unit template + installer; external driver (the keeper hook); presence before health; render-when-invalid (a present unit not byte-equal to the current template render is re-rendered); bounded detached health probes under a hard budget; load-state repair verb (`start` when not loaded, `restart` when loaded); 180s fresh-restore confirmation window; poll-verified, episode-capped ladder (one attempt per episode marker under `state/`); supervision as the verdict (health answering after the repair verb acts on the supervised unit proves restoration). Render safety: the expected render is hashed in memory, never landed to a file; installs stage to a fresh sibling, hash-verify, rename over; a failed/denied render classifies the unit `unknown`, never `stale`. Exit 0 = healthy or restored-and-verified; exit 1 = down and the ladder failed or was already spent for the episode.

Stackdump (`server/stackdump.py`): implements `stackdump-contract: v1` (canonical text again in the starter SPEC). An in-process watchdog checks `engine.health_data()` on the configured cadence (defaults: 5s cadence, 15s lag threshold, 60s minimum repeat, 16 MiB cap) and dumps all Python thread stacks to `state/stackdumps.log`; `/health` reports `stackdump_last_dump_at`.

Viewer (`ui/README.md`, `ui/ui.sh`, `ui/client/`, `ui/server/`): the repo `ui/` tree is the source of truth. The client is a consumer only — no derived labels, counts, ordering, or status semantics; presentation plus arithmetic over served values (countdowns, snapshot ages) is allowed. Views: overview, jobs list (filterable all/scripted/agent), job detail, pings (`ui/client/src/app.js`). It polls every 30s; the freshness badge warns after 60s; "down" is declared only after two consecutive failed fetches; a failed fetch keeps the last-good snapshot on screen, dimmed (harder past one hour) and labeled with its age; a bridge transport error is **bridge down**, distinct from any server state, never conflated. The viewer is read-only — ack, suspend, and admit stay in `bin/sched` and chat. Bridge actions (`ui/server/src/actions.ts`): `getOverview`, `getJobs`, `getJob`, `getPings`, `getLedger` → the matching `/api/v1` GETs. Bridge transport (`ui/server/src/privileged.ts`): a raw Node `node:net` socket to the scheduler server, never `fetch` (the reference host's egress proxy breaks loopback fetch); status 0 = transport failure surfaced as a bridge error; HTTP errors return as server errors with the server's JSON body. The host-binding seam imports `definePrivilegedContracts`, `definePrivilegedHandlers`, `z` from `@hatch/space-sdk`; a different host substitutes its own binding at publish time. `ui/server/src/config.ts` is the only target seam: `SCHEDULER_API_HOST` (127.0.0.1), `SCHEDULER_API_PORT` (8796), timeout fixed at 12,000 ms. `ui/ui.sh` (`status`, `deploy [--force]`): runtime tree defaults to a sibling `scheduler-viewer-runtime` (override `SCHEDULER_VIEWER_RUNTIME`); deploy checks drift first and refuses on runtime-side drift unless `--force`, makes a timestamped `cp -a` backup, then rsyncs repo `ui/` → runtime with `--delete` (excluding `node_modules`, `dist`, `.bun-cache`). `ui.sh` never publishes — publishing the hosted viewer from the runtime tree is a separate pass, and `ui/README.md` warns the hosted source is effectively a third tree: shell diffs alone never prove parity, host-side bridge adaptations must be preserved exactly, and the closing state for a UI change is the hosted copy re-synced to the repo tree at a known commit and verified live against real jobs and ledger data.

Gate plumbing (`check.sh`): 800-line cap on tracked source files → portability scan (`tools/portability_scan.py`; the personal-literal leg gates only when a denylist is provisioned via `SCHEDULER_DENYLIST_FILE` or `state/denylist.txt`) → `bin/sched validate` → `bin/sched census` → full `unittest` suite. A local invocation, not a service (Finding 4).

### Ancillary ops engines

Tracked `ops/` also carries platform/member machinery the plan should classify rather than lose: `ops/proof_run.py` (admission proof, above); `ops/file_registry.py` (file-registry checker, contract v1 — live manifest is untracked `registry/file-registry.yaml`, tracked specimen `examples/file-registry/example-file-registry.yaml`, canonical contract in the starter `SPEC.md`; restores missing files from declared sources or flags them to owners after a restart); `ops/storage_watch.py` (free-space tripwire for the home filesystem and `/tmp`, episode state, one report per threshold crossing); `ops/vm_boot_check.sh` (boot-id comparison; reports restarts and lost environment probes); the write-denial flap instruments `ops/flap_probe.py`, `ops/flap_canary.py`, `ops/flap_series.py`, `ops/flap_watch.py` (per-mechanism write matrix, append-only sample series, two-origin watcher comparing server-class vs mimicked agent-class writes); `ops/local_test_watch.py` (deterministic detector of code/tests running on local CPUs, stricter while Colab liveness entries stand — §5); `ops/mockup_census.py` (scripted census leg for stale-mockup cleanup; reads workbench project registries directly — §5). Several live member scripts exist only in the overlay/local exclude, not at the pin (e.g. paywatch and Colab transient-restore wrappers); they are not pinned code.

## 3. Pipeline vs apps

Pipeline-layer candidates (engines and platform services, all under `server/` + named `ops/`):

- Registry parser/validator and entry schema (`server/registry.py`); classified catalog, adoption, drift (`server/catalog.py`); schedule math (`server/schedule.py`); engine firing semantics (`server/engine.py`); scripted executor (`server/executor.py`).
- Stores: ledger (`server/ledger.py`), outbox (`server/outbox.py`), atomic state I/O (`server/stateio.py`).
- Services: delegated ops (`server/ops.py`), harness connector + bridge queue (`server/connector.py`), bridge-wake minter (`ops/bridge_wake.py`), keeper/watchdog restore ladder + systemd template, stackdump watchdog, proof-run mechanism.
- Platform probes/watches: file registry, storage watch, VM boot check, flap machinery, local-test watch. Portability scanner as a gate component.

App-side candidates:

- Scheduler viewer client (`ui/client/`) — a pure consumer of `/api/v1`; its host bridge binding (`ui/server/`) is an app/deploy adapter over the loopback contract.
- Job bodies as programme-owned content: the pipeline stores routes and serves body refs; the instructional content belongs to the owning programme.
- Registry entries as declarations the pipeline consumes: hand-written entries are programme/app configuration; machine-rendered families are contracts from their writers.
- `bridge-drain` as a pipeline-owned agent surface (its body is platform machinery, not programme content).
- `bin/sched` and `bin/harness` as operator/agent client surfaces over pipeline contracts.

Served-shape contracts between the layers:

- Registry YAML entry → engine firing → ledger event records → `/api/v1` ready-made views → viewer.
- Engine → outbox ping record → keeper wake → agent works body → explicit ack → ledger ping lifecycle.
- Venue agent → connector tool call → direct in-process core, or bridge record → home-side fulfillment → result fetch.
- Caller → `POST /ops` → server-process write/patch/exec → ledger `op` audit record.
- Workbench harness → machine-rendered registry entry with source stamp → scheduler firing/wake.
- Catalog example → adoption render + source stamp → live entry → drift diff.

## 4. Cross-cutting contracts designed locally

The tracked-vs-untracked split is the central pattern; each item below is a contract a single repo designed for itself that the mega repo must promote to a pipeline contract or consciously retire.

- **Live config** — untracked `config.json` vs tracked `config.example.json`. The connector caller registry (token hashes + scopes) and machine-local Git SSH paths live only in the live file. (Also the timezone default mismatch in §2.)
- **Live registry overlay** — most deployment `jobs/*.yaml` are untracked, gitignored, or excluded only by local `.git/info/exclude`, which is itself not portable or reviewable. Tracked at the pin: schema + the two bridge entries. Catalog examples are tracked; live adoptions are not.
- **Bodies** — `bodies/` ignored wholesale by tracked `.gitignore`, yet bodies are behavioral contracts for agent jobs. Catalog body specimens are tracked under `examples/registry/` and renamed on adoption — the same content class lives tracked in one place and untracked in another.
- **Caller/owner routing config** — `bodies/bridge-wake-owners.yaml` is live, ignored, and stored inside the bodies directory even though it is configuration, not an agent body: `owners: {<caller>: {chat: <chat-id>}}` plus optional `drain: {chat: <chat-id>}`.
- **Bridge queue records** — untracked runtime JSON under `state/connector-bridge/`; the record shape and envelope-idempotency rule are the contract (§2).
- **File-registry manifest** — live `registry/file-registry.yaml` untracked/locally excluded; tracked example under `examples/file-registry/`.
- **Workbench harness state inside this repo** — `workbench.yaml` and `workbench/` are gitignored as derived runtime state (yaml is the source, the registry DB regenerable), showing the harness already keeps state inside the scheduler repo's tree.
- **Connector contract annex** — `README.md` and `server/connector.py` refer to a contract annex in `.plans/`, but `.plans/` is gitignored and absent from the pin. At the pin, the enforceable contract evidence is the code plus the `bin/harness` header.
- **Spec/supervision-kit copies and references** — `AGENTS.md` carries a fragment-synced block between `<!-- spec-sync:supervision-rules -->` markers: the generic supervision rules live in the spec-driven starter's `docs/supervision-rules.md`; the inline block carries only the mid-task-binding classes (hard-stop floor; defect routing at diagnosis; claimed instructions verified, never believed; only a measure clears; supervision is registry-driven and programme-agnostic, with doing-transition arming, terminal retirement, and worktree presence as ground truth) and is not edited locally. `README.md` likewise references canonical external texts — VM-restart survival contract v1, stackdump-contract v1, file-registry contract v1 — while the scheduler carries conformance and stamps, not the canonical texts. Consolidation inherits these pointers; the mega repo does not own the canonical rule text for them today.
- **Portability/denylist seam** — `tools/portability_scan.py` is tracked and run by `check.sh`; personal literals beyond generic shapes live only in an untracked denylist file, never in tracked source (`AGENTS.md`).

Config seams worth naming: server env > live JSON > defaults with source reporting; registry `${REPO}`/`${WS}`/`${HOME}` anchors expanded at load; UI bridge `SCHEDULER_API_HOST`/`SCHEDULER_API_PORT`; viewer runtime `SCHEDULER_VIEWER_RUNTIME`; watchdog seams `SCHEDULER_ROOT`, `SCHEDULER_UNIT_DIR`, `SCHEDULER_SYSTEMCTL`, `SCHEDULER_CURL`, `SCHEDULER_SED`, `SCHEDULER_HEALTH_URL` plus poll/probe timing envs; harness client `HARNESS_URL`/`HARNESS_TOKEN`/`HARNESS_TRANSPORT`/ferry envs; connector client `CONNECTOR_CLIENT_TOKEN`; member scripts derive roots from their own file location and set PATH explicitly.

## 5. Overlaps with the other three workhorses

Scheduler-side evidence only; the other repos were not inspected in this pass.

### Workbench

- **Job catalog vs todos** — `jobs/README.md` and `AGENTS.md`: `wb-progress-*` entries are machine-rendered by the workbench harness from todos under one fixed template when a todo's progress schedule arms; they are born `migrated: true` (the §2 admission exception), `migrated_at` is the todo's arming date and is preserved across re-syncs, and the machine-form source stamp (`server/registry.py`: `writer`, `project`, `todo`, `source_class`) is the cross-repo contract. `server/catalog.py` counts the `wb-progress-` family separately in drift. The chain is: workbench todo state → scheduler registry entry → scheduler outbox ping. Entry `owner` remains a scheduler-side `goal:<slug>` value.
- **Served API coupling** — connector tool `workbench_read` (`server/connector.py`, `bin/harness`) proxies the workbench viewer's `/api/` surface via `workbench_base_url` (default port 8792, `server/config.py`, `config.example.json`); tests pin `workbench_unavailable` as an enumerable error (`tests/test_connector.py`).
- **Filesystem coupling** — `ops/mockup_census.py` censuses workbench project registries directly (a directory holding both `workbench.yaml` and `workbench/registry.db`, invoking `workbench-viewer/wb`), bypassing the served API. The scheduler repo itself hosts ignored workbench harness runtime (§4).

### Owner-attention

- **Wakes/pings vs dispatch** — the outbox/keeper cycle is a wake-and-dispatch substrate: ping kinds `agent-due`/`escalation`/`report`, an external keeper that wakes an agent surface, ack only after work is done (`README.md`, `server/outbox.py`, `ops/keeper_poller.sh`). The connector bridge adds a second dispatch-like queue on top: bridged records queue in scheduler state, `ops/bridge_wake.py` mints thread-addressed wakes with caller→chat and drain-home routing from `bodies/bridge-wake-owners.yaml`, and the `bridge-drain` agent job works the queue to completion (§2). Wake minting, target resolution, episode coalescing, and delivery audit in the ledger therefore already live scheduler-side; attention's internals were not inspected here and no claim is made about them.
- **Retired-sweeper seam** — the connector's direct tools still read/write the retired approval sweeper's state and nudge ledger under fixed `<workspace_root>/approval-sweeper/` paths (`server/connector.py`), and the catalog carries deployment-specific sweeper specimens including a scripted delivery leg that posts through the bridged `chat_send` and a derivation leg over bridged `permissions_list` (`examples/registry/example-sweeper-deliver.yaml`, `example-sweeper-derive.yaml`). The untracked `jobs/owner-attention-healthcheck.yaml` in the working tree is further live-overlay evidence of the coupling, noted as uncommitted state only.

### Colab runner

- **Machine-rendered per-lease entries** — `.gitignore` ignores `jobs/colab-liveness-*.yaml` because the runner's lease core renders one liveness entry per live lease and deletes it with the lease record; the lease record, not the scheduler entry, is the record of truth. The catalog carries the machine-origin specimen (`examples/registry/example-colab-liveness.yaml`, `use_case: fleet-health`): a scripted check of `${WS}/colab-runner/bin/colab-liveness <session>` with an escalation body (`example-colab-liveness.md`) that reads the runner's `var/liveness-<session>.json` and `var/lease-<session>.json` and routes findings through the runner's `config/notify-routes.json` caller→chat table — a second caller-routing registry, runner-side, parallel to `bridge-wake-owners.yaml`.
- **Venue-agent access** — the harness connector exists so agents on venues can call home-side tools while scheduler state and ledger stay home; `bin/harness` is the venue-side client and the ferry transport covers venues without direct HTTP.
- **Registry-presence coupling** — `ops/local_test_watch.py` switches to strict mode when any `colab-liveness-*` entry stands in the registry: scheduler behavior keys off runner-owned registry presence.

### Viewer shells generally

- The scheduler viewer is a separate Library-style artifact with three trees — repo source, runtime mirror, hosted artifact source — a host-specific privileged bridge binding (`@hatch/space-sdk`), and a loopback-TCP-to-`/api/v1` transport that keeps bridge-down distinct from server-down (`ui/README.md`, `ui/server/src/privileged.ts`, `ui/ui.sh`). Same pattern family as the other workhorse viewers, but this implementation, payload set, and deploy script are its own — consolidation must unify the shell without breaking each app's served-shape contract.

## 6. Consolidation notes

Preserve exactly (contracts, not approximations):

- Job ids: filename stem = entry id; ids are referenced by ledger records, outbox pings, source stamps, and wake job ids (`bridge-wake-<request_id>`).
- The strict registry YAML subset and field semantics, including unknown-field quarantine and the secret-shape refusal.
- Owner values (`goal:<slug>` / `none` + reason) and both `source` stamp forms; catalog version 1, adoption rendering, the setup-coverage rule, and drift semantics (volatile fields named).
- Classification evidence and the scripted/agent boundary; admission semantics (validate → server-context proof → `migrated: true`) and the `wb-progress-*` machine exception.
- Engine firing semantics: consume-before-run, missed-point collapse with counts, no self-overlap, last-good registry on parse failure, fail-safe halt on corrupt state, only `migrated: true` active entries fire, schema → restart → entries ordering (or a deliberate replacement).
- Ledger format: canonical sorted-key JSON per event, the event-kind vocabulary, the SQLite schema/indexes, JSONL export byte format with SHA-256 verification, import only into an empty store.
- Outbox ping shape, ids, states, coalescing by job+kind, wake-window discipline, explicit ack, void-on-entry-removal.
- HTTP routes and payload shapes for `/health`, `/pings`, `/ops`, `/api/v1`, `/tools`; ops error names/status mapping and staged-write semantics; the pinned `GIT_SSH_COMMAND` pair rule.
- Connector scopes, token-hash-only caller registry, fresh-read-per-call, ledgering of refusals, envelope idempotency, and the no-authority boundary.
- Bridge record shape and the target-resolution rule: the destination chat is data inside a record; the executor's wake address is a separate routing decision (drain home for `chat_send`).
- Body refs and the ack-after-work discipline; the watchdog/keeper contract (external driver, presence before health, render-when-invalid, one ladder attempt per episode, health as the verdict); portability anchors and the no-machine-literals rule for tracked files.

Merge into the pipeline layer:

- The scheduler engine and its stores as the scheduling/work-record core.
- Outbox + bridge queue + wake minter as one dispatch substrate; attention's dispatch needs expressed over it rather than re-implemented.
- The connector as the cross-venue tool boundary; the caller registry and the runner's `notify-routes.json` caller→chat table and `bridge-wake-owners.yaml` are three instances of one caller/routing registry class — consolidate them as one pipeline contract (D4's named instance).
- `POST /ops` as the platform's delegated write/exec service — with its authentication posture decided explicitly (Finding 6).
- Catalog/adoption/drift as the platform's job-template service.
- Watchdog, file registry, and stackdump as platform survival services.
- The gate-shaped pieces already present (`check.sh`, portability scanner, registry validate/census) as seed material for the automatic gate runner the harness lacks — no such service exists today.

Stays app-side:

- The scheduler viewer's client and presentation semantics (overview/jobs/detail/pings over `/api/v1`).
- Programme-owned bodies and hand-written entry content.
- Host-specific viewer bridge bindings and deploy adapters.

Gaps the plan already names, confirmed from the scheduler side: no automatic gate-runner service; no deployment/release record tying artifact ↔ repo commit; no automatic backup of the state stores (ledger export is manual; outbox, next-due, config, bridge records unbacked in the inspected code).

## 7. Risks and unknowns

- **Pinned tree ≠ live system.** The live registry, bodies, owners config, file-registry manifest, and many member scripts are untracked, ignored, or excluded only by local `.git/info/exclude` — which is itself not part of the repo. Consolidation must inventory the overlay separately; copying the pin alone loses the fleet, and overlay edits change the running system outside git history (the engine rescans `jobs/` every tick).
- **Tracked bridge entries depend on untracked bodies/config.** `bridge-drain` and `bridge-wake` cannot be reproduced from the pin alone; registry validation is filesystem-dependent, so an entry that validates here quarantines on a tree without the overlay.
- **Single-instance, local-state design.** One lock, local SQLite, local JSON state. A mega-repo migration must never run two engines against the same registry/state — consume-before-run protects one engine, not two; double-firing and split-brain are the failure modes.
- **`/ops` caller is self-asserted** in the inspected code (Finding 6). Attribution is audited, not authenticated; safety rests on bind/process scope. Whether the superapp keeps, hardens, or replaces this posture is an open decision.
- **Legacy sweeper coupling.** Connector direct tools still serve the retired sweeper's state file and nudge ledger at fixed workspace paths, with the retired schema inlined in scheduler code. Consolidation must decide whether that compatibility is a pipeline contract or dead weight.
- **Workbench coupling in two forms.** `workbench_read` depends on a separately running viewer at `workbench_base_url`; `ops/mockup_census.py` reads workbench registry files directly. Both are cross-app contracts needing explicit ownership in the pipeline/apps split.
- **Bodies directory conflates content and config.** `bridge-wake-owners.yaml` is routing configuration stored among agent bodies; a consolidated registry design should separate the two classes.
- **Three-tree UI deployment.** Repo, runtime mirror, and hosted artifact source can drift independently; `ui.sh` proves only the repo↔runtime pair.
- **Connector contract annex is not in the pin.** It is referenced as living in ignored `.plans/`; the enforceable contract at the pin is code plus CLI headers.
- **Config example mismatch.** Example timezone `UTC` vs code default `America/New_York` — small, but exactly the class of drift a consolidated config contract should eliminate.
- **Scope of this review.** The other three repos were not inspected here; §5 overlap statements are scheduler-side evidence only. No tests were run and no server was started, by task instruction.
