# 04 — Platform config (seed/example pattern)

**Canonical owner:** the pipeline platform — the config
pattern (each app keeps its own live config file; the
pattern, precedence, and source-reporting are
pipeline-owned), and the platform's
ops-service and watchdog/keeper clauses below.

**The contract in one line:** every live config is an
untracked file seeded from a tracked fictional example,
resolved env > live > defaults, with per-key source
reporting — and no live value ever enters a tracked file.

## The pattern

- **Tracked fictional example** ↔ **untracked live file**:
  the example carries invented values only; gitignore
  entries document why each live file is local.
- **Precedence:** environment > live file > built-in
  defaults, with **per-key source reporting** — the
  scheduler's `/health` serves resolved config with sources
  (connector config redacted to caller names and scopes;
  hashes never ride it), and the workbench config states
  the same precedence in its example's comment.
- **Timezone default:** the scheduler's
  `config.example.json` and the code default agree:
  `default_timezone: "America/New_York"`
  (`pipeline/scheduling/config.example.json`;
  `pipeline/scheduling/server/config.py`).

## Instances

| Live file (untracked) | Tracked example | Fixture |
|---|---|---|
| runner `config/callers.json` | `config/callers.example.json` | `fixtures/callers.example.json` (contract 01) |
| runner `config/lease.json` | `config/lease.example.json` | `fixtures/lease-config.example.json` |
| runner `config/repos.json` | `config/repos.example.json` | `fixtures/repos.example.json` |
| runner `config/notify-routes.json` | `config/notify-routes.example.json` | `fixtures/notify-routes.example.json` (contract 01) |
| runner `config/denylist.txt` | — (no example; literals are never tracked) | — (contract 10) |
| runner `config/transient.json` + auth-transient mirror | — (runtime state, mirrored never blind-copied back) | — |
| scheduler `config.json` | `config.example.json` | `fixtures/scheduler-config.example.json` |
| workbench `config.json` | `config.example.json` | `fixtures/workbench-config.example.json` |
| workbench `viewer.env` | `viewer.env.example` | `fixtures/viewer.env.example` |
| attention — none | — | the weak sibling (below) |

The runner's lease config keys (caps and policy:
`daily_cu_budget` / `monthly_cu_budget`, `default_shape`,
`session_gate`, `standing`, `keepalive`, `extend_guard`,
`sync_claim`, `auto_acquire`) and repos registry
(pointer-only entries: `clone_url`, `local_path`, `dest`,
`venv`, `init`, `version_checks`, `scan_roots` — a package
spec in an entry is rejected by validation) keep their
field sets as written in the fixtures.

**Attention is the pattern's weak sibling**
(docs/review/review-attention.md §6): settings are env-only, no config file is read,
and there is no tracked example for its store, handlers, or
programmes. It gains the pattern through contract 01's
seed/export step — attention has nothing to contribute
here and everything to gain.

**Negative instance:** the runner's `config/profiles.json`
is retired by ruling and must not exist; records are read
only in the shape/caller vocabulary they are written in
today.

## The file registry

The scheduler file registry — live manifest
`registry/file-registry.yaml` (untracked), tracked specimen
`examples/file-registry/example-file-registry.yaml`,
checker `ops/watches/file_registry.py` (file-registry contract v1;
canonical text in the starter SPEC) — homes under this
pattern:

- the manifest is a live config under the seed/example
  pattern: tracked fictional specimen, untracked live
  manifest, restored-from-declared-sources semantics as the
  checker defines them;
- the `file-registry-check` job is a registry entry
  (`jobs/file-registry-check.yaml`) whose body runs the
  checker.

Fixture: `fixtures/file-registry.example.yaml`.

## The ops service (SCH6 — the `/ops` half)

`POST /ops` is the platform's delegated write/exec service:
the server process
performs `write`,
`patch`, and `exec` on behalf of a caller whose own
process class cannot be trusted to land a write. The HTTP
layer only routes; `bin/sched` carries the client verbs
(`pipeline/scheduling/server/serving/ops.py`). Request forms:
`{caller, op: "write", path, content}`,
`{caller, op: "patch", path, old, new}`,
`{caller, op: "exec", argv, cwd?, timeout?}` — the body is
capped at 4 MiB.

- **Staged-write discipline:** every write lands via a
  sibling temp file (`.<name>.sched-tmp-<pid>-<tid>`):
  write, flush, fsync, **read back and compare** (a
  mismatch is `verify_failed`), rename over the target,
  then a directory fsync for the rename's durability. A
  failed or denied write leaves the target untouched and
  the temp unlinked; a crash mid-write cannot tear the
  target. `patch` is a single-match replace through the
  same staged path.
- **Scope enforced server-side:** paths are absolute or
  workspace-relative; the resolved real path must stay
  inside the workspace root.
- **Error names and status mapping (closed set):**

  | Error | Status | Meaning |
  |---|---|---|
  | `bad_request` | 400 | malformed request shape |
  | `unauthenticated` | 401 | no valid bearer token presented |
  | `scope_refused` | 403 | authenticated caller lacks the op's scope |
  | `caller_mismatch` | 403 | `caller` label ≠ the authenticated caller |
  | `outside_scope` | 403 | resolved path escapes the workspace |
  | `not_found` | 404 | patch target does not exist |
  | `no_match` | 409 | patch `old` text absent |
  | `multi_match` | 409 | patch `old` text not unique |
  | `verify_failed` | 500 | staged read-back mismatch |
  | `io_error` | 500 | the operation itself failed |

  Responses are `{ok: true, ...result}` or
  `{ok: false, error: <name>, detail: <text>}`.
- **Audit:** every attempt — success, refusal, or error —
  is ledgered as an `op` event with caller, target,
  status, error, and exit code (the ledger is contract
  05's). Exit 4 on the client means the server was
  unreachable and **nothing was performed** — the client
  never writes directly.
- **Authentication:** `/ops` uses the
  `/tools` token model; callers resolve through contract
  01's registry. Exec timeouts default to 120 s, capped at
  600 s.
- **Scope mapping:** **`write` and `patch` require the
  `write-state` scope; `exec` requires the `exec` scope.**
  Contract 01 carries the
  exec-denoting scope `exec` (home-side only, never issued
  to a venue caller — mapping `exec` onto `write-state`
  would hand arbitrary command execution to every
  state-writing token, a widening, not a hardening).
  **The client token home:** `bin/sched`'s ops
  client resolves the acting caller's raw token from an
  untracked per-caller token file — `<caller>.token` in
  the scheduling package's `ops-tokens/` directory (the
  `SCHED_OPS_TOKEN_DIR` env var re-points the home),
  on the bridge-token precedent; contract 01 still stores
  hashes only, server-side. The hardening is in force:
  `ops.perform` authenticates the presented token through
  the connector's registry (read fresh per call, as
  `/tools` does), refuses unauthenticated, mismatched, or
  under-scoped calls as a ledgered refusal before anything
  is performed, and the self-asserted `caller` string is
  an audit label only, never an authentication input.
  Caller provisioning rides `bin/sched connector-token`
  (mint, re-issue, and `--save-client` delivery into the
  token home; the first mint bootstraps by direct
  staged write because no token yet exists to authenticate
  it), and the live config is provisioned from the shipped
  example by `bin/sched config-init`; the server refuses
  to start without a live config rather than running on
  silent defaults.
- **The `GIT_SSH_COMMAND` pair rule (SCH6's tail):** the
  exec environment's SSH pair comes from the untracked
  live config, never tracked code — **both keys set, or
  nothing is pinned**. The keys home in this contract's
  scheduler config instance (above).

## The watchdog/keeper (SCH9 — the survival half)

The keeper is the external driver of the platform's
survival services; it survives server crashes and host
restarts by design, so no part of it lives in the server
it watches (`pipeline/scheduling/ops/server-care/watchdog.sh`
and the platform unit templates in
`pipeline/platform/ops/`; the ladder conforms to the VM-restart survival
pattern, contract v1, canonical text in the starter SPEC).

- **Two halves:** the wake half — poll wakeable pings,
  wake the agent surface, ack only after the work is done
  — is contract 05's. This clause carries the health half:
- **Presence before health:** the ladder reads the unit's
  presence and load state before any health probe.
- **Render-when-invalid:** a present unit whose bytes are
  not the current template render is re-rendered. The
  expected render is hashed **in memory, never landed to a
  file**; installs stage to a fresh sibling, hash-verify,
  rename over. A failed or denied render classifies the
  unit `unknown`, never `stale`. A healthy server whose
  unit file is missing gets it reinstalled quietly.
- **One ladder attempt per episode:** attempts are capped
  by an episode marker under `state/`; health probes are
  detached and bounded under a hard budget; the repair
  verb is the load-state verb (`start` when not loaded,
  `restart` when loaded); a fresh restore is confirmed
  inside a 180 s window.
- **Health is the verdict:** supervision answering after
  the repair verb acts on the supervised unit proves
  restoration. Exit 0 = healthy, or restored-and-verified;
  exit 1 = down, and the ladder failed or was already
  spent for the episode. The in-process sibling is the
  stackdump watchdog (`stackdump-contract: v1`), which
  rides the same platform home.
- **Build home:** the platform services
  (`pipeline/platform/`, `pipeline/scheduling/ops/server-care/`);
  the survival services' external registrations are the
  unit templates in `pipeline/platform/ops/`.

## Preserve clauses carried

RUN6 (the seed/example pattern itself, whole), SCH6's
`/health` config half (`/health`'s per-key source reporting
is this contract's reporting rule) and its `/ops` half
(payload semantics, above; authentication is the token-model
ruling), and SCH9's watchdog/keeper half (above). The
remaining SCH6 halves are traced in `traceability.md`.
