# colab-runner

Runs compute-bound work from this 2-vCPU machine on a Colab Pro high-RAM CPU runtime (measured 8 vCPU / ~51–55 GB) via Google's official `google-colab-cli`. First consumer: an XBRL workload repo — code and gate jobs, pipeline jobs, and probes.

## How a job runs

1. `bin/colab-run <job>` (or `bin/colab-check <paths>` for a gate job) restores transient state from the repo mirror and acquires-or-adopts the shared lease session for the manifest's shape (`bin/colab-lease`; `sync/lease/`) — a generated session name per lease, treated as a VM, 8 h hard cap, budget-guarded. Code syncs by the manifest's declared transport (next section): branch on origin by default for a committed tree, a git bundle on top of a base HTTPS clone for an uncommitted one.
2. A remote bootstrap snippet prepares the VM (clone, dependencies, resource probe, Python-version assertion).
3. The job executes detached on the VM (never as a kernel cell — the kill matrix measured that cells die with the local CLI); the wrapper polls and pushes checkpoints off the VM at the job's cadence.
4. Results return as artifacts plus a hash manifest. The session stays up for the next job; a script-level reaper hook (2-minute poll) enforces the lease deadline. Colab is compute-only: code is authored on this machine, never on the VM.

## Job manifests: transport

The manifest declares the tree's form; the runner holds the preference. Every run record stamps the transport used (`transport` on `results/runs/<run_id>.json`), the bytes the runner moved, and the claim→launch span, so adoption is measured from records.

**Branch transport — the default for a committed, pushed tree.** The job names its tree's branch on origin; the runner skips the snapshot build and the code-payload upload, drives the session's base clone (`sync/base_clone.sh`) to fetch the branch, and launches only when the fetched tip equals the announced SHA:

```json
"transport": {"kind": "branch", "repo": "supreme-octo-robot", "branch": "cure/my-change-20261123", "sha": "0123456789abcdef0123456789abcdef01234567"}
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

## First-time setup

```bash
ops/bootstrap_local.sh          # installs google-colab-cli via uv, restores transients
```

Operator-only step: the one-time OAuth login. Create a session with the CLI (`colab new -s <any-name>`, adding `--high-mem` for the High-RAM shape); the command prints a URL to open anywhere and paste the returned code back.

After that, the token is cached and mirrored, and wrappers handle the rest.

