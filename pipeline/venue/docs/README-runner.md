# colab-runner

Runs compute-bound work from this 2-vCPU machine on a Colab Pro high-RAM CPU runtime (measured 8 vCPU / ~51–55 GB) via Google's official `google-colab-cli`. First consumer: an XBRL workload repo — code and gate jobs, pipeline jobs, and probes.

## How a job runs

1. `bin/colab-run <job>` (or `bin/colab-check <paths>` for a gate job) restores transient state from the repo mirror and acquires-or-adopts the shared lease session for the manifest's shape (`bin/colab-lease`; `sync/lease/`) — a generated session name per lease, treated as a VM, 8 h hard cap, budget-guarded. Code syncs by the manifest's declared transport (next section): branch on origin by default for a committed tree, a git bundle on top of a base HTTPS clone for an uncommitted one.
2. A remote bootstrap snippet prepares the VM (clone, dependencies, resource probe, Python-version assertion).
3. The job executes detached on the VM (never as a kernel cell — the kill matrix measured that cells die with the local CLI); the wrapper polls and pushes checkpoints off the VM at the job's cadence.
4. Results return as artifacts plus a hash manifest. The session stays up for the next job; a script-level reaper hook (2-minute poll) enforces the lease deadline. Colab is compute-only: code is authored on this machine, never on the VM.

## Dispatch routes

Gate dispatches ride pre-authorized routes: the scheduler ops route (`bin/sched exec`) and the venue runner's own entries (`bin/colab-run`, `bin/local-run` — the `--daemonize` form when the firing context is bounded, so the fire survives it). Both routes execute without a per-fire approval, so a dispatch's outcome is the run's own: a record, a verdict, or a named refusal from the pre-dispatch validation.

The anti-form is a bare agent-shell exec of a dispatch. Each such fire mints a runtime approval card, and an unanswered card kills the fire with no run performed — the dispatch dies before launch and leaves nothing to reconcile. Twenty cards timed out unanswered in one day of the wall-clock measurement, ≈7h44m of card-pending time, inside dispatch windows that produced no runs at all. A fire that needs a route it does not have stops and names the route; it never falls back to a bare-shell dispatch.

## Venue selection under load (local fleet)

Dispatch under load follows the fleet's measured contention curve for the gate shape (identical job, identical tree, production worker sizing), not a fixed machine order. Each machine's curve has a knee: the concurrency at which its per-job speed falls to a slower machine's solo speed and its throughput stops growing. The convention: gate-class work routes to the fastest machine up to a cap set one below its knee, so routed jobs keep their headroom; work beyond the cap spills to the next machine under the load-aware routing rule, where a spilled job finishes no later than one queued past the knee and the second machine's throughput adds to the fleet instead of contending. The measured curves and the fleet's current cap values are this deployment's binding, recorded in the Muse AGENTS.md for the deployment, and re-measured when the fleet or the gate shape changes.

## Envelope launches (local venue)

An envelope groups jobs pending on the same local venue into ONE launch with one thread budget for the whole envelope, divided among the grouped jobs — instead of N independent trees each spawning uncapped pools against the venue's pid ceiling (the starvation class: one test worker bursting to ~710 threads and holding the ceiling). The grouped jobs run concurrently inside the envelope, each at its divided share; grouping never serializes. Dispatch: `bin/local-run --envelope <name> [--caller TAG] [--detach]`.

The declaration stands at `adapters/local/jobs/<name>/envelope.json`:

```json
{"shape": "local-hp", "jobs": ["gate-a", {"name": "gate-b", "connections": 5, "threads_per_connection": 39}], "fraction": 0.75, "burst_per_worker": 860, "caller": "workhorse"}
```

`shape` and `jobs` (in order) are required; `fraction`, `burst_per_worker`, `caller`, and `timeout_s` are optional. A job entry is a plain job name, or a mapping declaring the job's connection pool. The envelope takes one run record (constituents recorded in order, with their stamps), one run dir per job under the envelope's run dir, and per-job exit files; the envelope's exit is the first non-zero job exit in order, or 0. `--poll <envelope run id>` attaches through the standing poll form, and the envelope settles when its last job settles. A sealed job never rides an envelope — it dispatches solo from its blob.

The arithmetic (the pure leaf is `sync/runner/envelope.py`; declared capacities: `local` 16 cores / 1024 pids, `local-hp` 8 cores / 1024 pids): the envelope budget is `fraction` (default 0.75) of the shape's pid ceiling, divided as a per-job thread share (the division remainder goes one each to the first jobs in order). Per job, the launch environment carries the stamps:

| Stamp | Value |
| --- | --- |
| `GATE_WORKERS` | the job's worker count (below) |
| `ENVELOPE_THREADS` | the job's thread share |
| `ENVELOPE_JOB_INDEX` / `ENVELOPE_JOB_COUNT` | the job's position in the envelope |
| `OMP_THREAD_LIMIT`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS` | the job's pool cap: `thread_share ÷ workers` |

Two pool classes stand behind the pricing, and they are not priced alike:

- **The connection pool (the DuckDB class)** — a per-connection thread pool (measured +39 threads per connection at 8 cores) that honours NO env cap: the thread delta is identical capped and uncapped. It is priced by workers × connections only. A job that holds connections declares `connections` and `threads_per_connection`; its per-worker worst case is `connections × threads_per_connection + 150`.
- **The import pool (the numeric-stack class)** — the pools the stamped env caps bind. The pool-cap stamps are advisory: they bind the libraries that honour them.

The binding cap is the **worker count**: `workers = max(1, min(cores ÷ jobs, thread_share ÷ per-worker worst case))`, where the worst case is the job's declared connection figure, or `burst_per_worker` (default 860 — the observed ~710 burst plus ~150 of controller/subprocess overhead) for a job that declares none. With the default, a thread share of 384 prices 1 worker — a worker priced so that even a full burst stays inside its share.

A job form needs no change to ride an envelope: it reads `GATE_WORKERS` as it already does (the stamp replaces its `$(nproc)` derivation), and the pool caps ride the environment. A solo job's envelope (one job) divides the full budget to that job.

## Job manifests: transport

The manifest declares the tree's form; the runner holds the preference. Every run record stamps the transport used (`transport` on `results/runs/<run_id>.json`), the bytes the runner moved, and the claim→launch span, so adoption is measured from records — `ops/transport_report.py` reads the records back as per-programme branch / bundle / never-launched counts over a day or a rolling window.

Branches are throwaway working surfaces. Disposable branches, detached-HEAD checkouts, and other ephemeral working states are all acceptable forms; nothing about a branch is precious or preserved for its own sake. The point of the discipline is that the main lineage carries finalized clean work only — work is finished, gated, and clean on the branch or detached surface, and only that finalized state lands on main.

**Branch transport — the default for a committed, pushed tree.** The job names its tree's branch on origin; the runner skips the snapshot build and the code-payload upload, drives the session's base clone (`sync/base_clone.sh`) to fetch the branch, and launches only when the fetched tip equals the announced SHA:

```json
"transport": {"kind": "branch", "repo": "specimen-repo", "branch": "cure/my-change-20261123", "sha": "0123456789abcdef0123456789abcdef01234567"}
```

`repo` is a key in the local repos registry (`config/repos.json`), `sha` the full 40-hex tip the run is judged on. The branch is transport only, never a landing: the run is judged on the tree at that SHA, and the transport branch is deleted from origin when the work lands. A fetched tip that differs from `sha`, or an origin the session cannot reach, refuses the run before launch — the runner never substitutes the bundle mid-launch. Small non-code uploads (job scripts, kits, keys) keep the verified upload path exactly as before, and untracked provisioned material (the denylist, keys, kit files) never rides a branch: it moves on the upload/plant channel as today.

**Bundle transport — the fallback for a genuinely uncommitted tree.** Name no `transport` and the run takes the snapshot-bundle path as before: a bundle built on the origin lineage (never the local lineage), byte size and SHA-256 recorded before transfer and verified after, applied over the base clone (the `--seed` route for registry repos). A malformed branch declaration — a missing `repo`, `branch`, or `sha`, or a short SHA — refuses at manifest load, naming the field, before any session work.

## Key pieces

- `config/transient.json` + `ops/mirror_transient.py` — transient capture/restore; the canonical runbook is `ops/restore-cron.md`.
- `config/lease.json` — the lease machinery's config: budget caps, the session shape-gate policy, the default shape jobs fall back to, and the standing lease's caller/shape. The shape catalog itself is dynamic, parsed from the CLI's own help; measured per-shape rates persist in `var/shape-rates.json` (null = unconfirmed).
- `ui/` — the operator's lease control panel (127.0.0.1:8793): start any spec for a chosen duration, grant a two-tier lease (standing tier + burst shape), terminate early; every action is a `bin/colab-lease` call, and starts/stops/grants are announced to the main chat via the outbox + notify hook. No agent operates the lease.
- `sync/` — snapshot-bundle construction on the origin lineage, bundle apply, the per-class data manifest (transfer vs driver-plus-regenerate vs network regeneration, priced), and result pull-back with hash verification.
- `probes/` — the P0–P4 probe suites: local network, session shape, transfer channels, execution behaviour + kill matrix, restart survival. Results land in `probes/results/`.
- `snippets/` — the versioned snippet library (the CLI has no snippet feature): remote bootstrap, resource probe, smoke tests, heartbeat job, and job zero (`env_build.sh`: Unit 0 `uv` guarantee + the clone's own `init_venv.py`, driven from the local repo registry in `config/repos.json` — untracked, seeded from `config/repos.example.json`).
- `jobs/` — job manifests: pipeline jobs and gate jobs.

## Venue state

A venue's truth is its process table, never a run record's face. The venue-state mechanism classifies every venue into one of four states — **idle** (no live job trees), **advancing** (at least one job tree with CPU progression and headroom), **saturated** (pid occupancy at or above 85% of the declared capacity), **wedged** (a job tree alive with frozen CPU across two consecutive samples past its progression grace, or alive past its manifest timeout) — and publishes the classification as one file per venue: `var/venue-state-<venue>.json`, written atomically, carrying `{venue, state, sampled_at, pids_current, pids_capacity, jobs: [{run_id, caller, root_pid, tree_alive, cpu_s, cpu_delta_s, verdict}]}`. **That file is the measures' read surface**: staffing, liveness, and dispatch decisions read the state file, and no consumer reconstructs venue state from run-record faces.

Writers: for the local targets, `bin/venue-state-sample` samples each venue's pid occupancy and every live run dir's tree CPU in one SSH exec every 120 s (the sampler cron) and classifies the sample against the previous one; a venue that cannot be sampled reads `unreachable`, a transport verdict rather than a classification. The same probe reads the venue's disk — the root store's and the workspace mount's used GB — and the sampler merges a `disk` block into the local targets' state files: `{root_used_gb, workspace_used_gb, warn_gb, stop_gb, state}`, with state `ok`, `warn`, or `stop` evaluated on the root store (the store that fills and kills the venue) against the target's own warn/stop figures. The figures are per-instance operator configuration, seeded untracked at `var/disk-thresholds.json` from each instance's disk-guard environment; a target with no seed entry carries no disk block. An unreachable venue's state file carries the last successful sample's disk block, stamped with that sample's time as `disk_sampled_at`. For Colab, the lease reap pass computes the same classification from its existing session reads — the shared snapshot and each record's live-jobs projection, with the run's evidence clock as the progression signal — into the same shape, one file per session plus the fleet aggregate at `var/venue-state-colab.json`.

Actuators wired to the classification (`bin/venue-state-actuate`, on the sampler's cron family): a wedged tree — and any live tree past its record's timeout — is reaped: the reap sweeps by run-dir match across the whole process table (a tree can outlive its root, reparented to init and invisible to a root-pid read), TERMs the match, KILLs survivors after the grace, and writes the run's exit file (143) only after verifying no process still names the run dir; the record then settles failed through the poll path's finalize, with the two CPU samples stamped on it as `reaped` evidence. A fresh `saturated` verdict refuses new fires in both dispatch entries (`bin/local-run`, `bin/colab-run`), naming the state, until the table drains. A dispatch stamps the job's parallelism share — the shape's declared cores scaled by the venue's free pid fraction — onto the record and, on the local entry, into the run environment as `GATE_WORKERS`. The liveness checker consumes the same files and speaks the standing findings in its escalation form: `wedged-killed` (a reaped run, routed to its caller), `saturated-standing`, and `idle-capacity` (the venue surfaces as available capacity; routing staffable work to it is the staffing measure's act on this surface). The disk block speaks there too: `disk-warn:<target>` and `disk-stop:<target>` when a venue's root store stands at its warn or stop figure, and `disk-last:<target>` when a venue is dark and its last reading stood at warn or stop — the warning the host-side disk guard writes only to its own log, carried on the surface that is read.

## First-time setup

```bash
ops/bootstrap_local.sh          # installs google-colab-cli via uv, restores transients
```

Operator-only step: the one-time OAuth login. Create a session with the CLI (`colab new -s <any-name>`, adding `--high-mem` for the High-RAM shape); the command prints a URL to open anywhere and paste the returned code back.

After that, the token is cached and mirrored, and wrappers handle the rest.

