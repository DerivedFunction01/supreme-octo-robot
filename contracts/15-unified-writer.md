# 15 — Unified state writer

**Canonical owner:** the pipeline platform — the writer is a
platform service (plan §6, P4), built on the ops service
that moves into `pipeline/platform/` at S3. (Plan §4.15,
added by amendment 4, owner's ruling.)

**The contract in one line:** every state mutation on this
machine — every pipeline store write, every app state
write, every app-level file edit — is performed by one
wrapper through one atomicity protocol, attributed to a
registry caller and ledgered as an `op` event; no app or
pipeline process writes a state file itself.

**Parties:** every pipeline service and app backend that
mutates state on this machine is a caller; the stores and
files named under Scope are the targets; readers are not
parties (a read never writes, and no read path carries a
write side effect).

## Why one writer — the machine's flaw

This machine denies writes in waves (the write-denial
flap, probed and standing since): Python
`open('w')` / `write_text` is the most reliably denied
mechanism, `fsync` is denied whenever tested from an
agent-class process, and a truncate that succeeds
followed by a denied write destroys the file (proven on
`bin/colab-run`). In the same waves, rename-over and
unlink were never denied, and long-lived server-class
processes (the scheduler server, the hooks, the panel)
were never denied at all. Each workhorse therefore grew
its own workaround: the scheduler's `/ops` delegation to
its never-denied server process (contract 04), the
workbench's file drops into sibling repos, the attention
store's in-process atomic write, the runner's
staged-sibling record writes. In one app the distribution
is the defect: the flaw is this machine's, and it becomes
one component's problem — this one. (Mechanism record:
`TOOLS.md`'s flap entries and `AGENTS.md`'s flap
protocol; this contract freezes the target's answer, not
the probes.)

## The operation set

Four operations, generalizing the `/ops` set of contract
04. Request forms carry `{caller, op, path, …}`:

| Op | Form | Semantics |
|---|---|---|
| `write` | `{path, content}` | full-content replace of the target, via the atomicity protocol |
| `patch` | `{path, old, new}` | single-match replace (`old` absent = `no_match`, not unique = `multi_match`), via the same protocol |
| `cas-update` | `{path, expected_stamp, content}` or `{path, expected_stamp, old, new}` | the write or patch proceeds only if the target's current stamp equals `expected_stamp`; on mismatch nothing is written (`version_conflict`) |
| `delete` | `{path}` | unlink of the target; routed through the wrapper for attribution and ledgering even though unlink itself was never a denied mechanism |

- **The stamp** is the target's identity as served by its
  owning contract: the SHA-256 of the file's bytes for
  file targets (the workbench editor's sha guard), or the
  served version for record targets (contract 11's
  per-row `version` compare-and-swap; contract 09's
  config-view version stamp). A caller obtains the stamp
  from the served read it edited against, never from a
  private re-read.
- **`exec` is not a writer operation.** Delegated
  execution stays contract 04's ops-service clause (its
  timeouts, its environment rules, the `GIT_SSH_COMMAND`
  pair rule); this contract governs mutation only. The
  two halves share the platform service and the ledger,
  not an operation set.

## The atomicity protocol

1. **No process opens a target for truncate-write** —
   not the caller, not the wrapper. The truncate-then-
   denied sequence is the proven destroyer; the protocol
   makes it unrepresentable.
2. Content **stages to a fresh sibling** in the target's
   directory (contract 04's `.<name>.sched-tmp-<pid>-<tid>`
   form, generalized).
3. The stage is flushed and fsync'd **by the wrapper
   process** — the never-denied server class, where the
   fsync posture is the wrapper's own discipline,
   inherited from contract 04's staged write. A caller's
   process class is never in the write path at all.
4. The stage is **read back and compared** byte-for-byte;
   a mismatch is `verify_failed` — temp unlinked, target
   untouched.
5. **Rename over** the target (the mechanism no probe
   wave denied), then a directory fsync for the rename's
   durability.
6. A denial or failure at any stage leaves the **target
   byte-identical to its pre-state** and the temp
   unlinked where the wave permits. That guarantee —
   never a torn or truncated target — is the contract's
   core; everything else is mechanism.

Same-target mutations serialize through the wrapper
service (its single process is the serialization point,
as the pinned server is); the CAS stamp is the
cross-target and cross-caller guard.

## Attribution and ledgering

- **Attribution:** every mutation carries a caller from
  contract 01's registry (thread, machinery, and token
  natures distinct, as there); transport authentication
  is §10.1's token model (contract 04). An unregistered
  presented claim is refused; the writer mints no
  anonymous writes.
- **Ledgering:** every attempt — success, refusal, or
  error — is an `op` event in the pipeline ledger
  (contract 05's store and kind vocabulary, unchanged):
  kind `op`, the op name, caller, path, result or error,
  and for `cas-update` the expected and found stamps.
  The pinned `/ops` audit stream reads identically in
  the unified stream; no consumer re-keys.

## Failure semantics

The error set is contract 04's closed table, **reused,
not redefined** — `bad_request` (400), `outside_scope`
(403), `not_found` (404), `no_match` (409),
`multi_match` (409), `verify_failed` (500), `io_error`
(500) — with one addition this contract's new operation
requires: `version_conflict` (409), a `cas-update` whose
`expected_stamp` no longer matches the target. What a
caller may conclude:

| Error | Conclusion the caller may draw |
|---|---|
| `bad_request`, `outside_scope` | the request was refused before any staging; re-issue only corrected |
| `not_found`, `no_match`, `multi_match` | deterministic against the current target; retrying the identical request cannot succeed |
| `version_conflict` | the target changed under the edit; nothing was written; re-read for the fresh stamp and re-present the edit — never force |
| `verify_failed` | the staged bytes read back wrong; the target is untouched; the wrapper has already retried the stage once internally before surfacing it |
| `io_error` | the wave (or the store) refused the operation; by the atomicity guarantee the target stands at its pre-state, so the caller may conclude the mutation did not happen and may re-issue it whole |
| writer unreachable | **nothing was performed** (the pinned exit-4 rule, generalized); the caller never falls back to writing directly |

**Retry posture:** the wrapper absorbs the wave — a
denied stage is retried a bounded number of times,
spaced in seconds (waves run at minute scale), before
`io_error` surfaces. Retry lives only inside the
wrapper: a caller that retries by another path, or
writes around a refusal, is a defect against this
contract.

## Scope

**In:** every pipeline store write (the scheduling
registry through contract 02's writer path — now riding
this wrapper; the dispatch ledger and outbox; the
work-record store and its `registry.json` export fold;
the venue lease/run records of contract 12; the
attention state store of contract 01's annex); every
app state write; and app-level file editing inside the
mega app, the workbench file editor included (its
guarded sha save is a `cas-update` call). Store shapes
stay their owning contracts' — this contract owns the
act of writing, never the shape written.

**Out:** files on venue sessions (session worktrees
write locally there — the flap is this machine's
disease, not the venue's); other programmes' repos (the
§2b scope fence — clients of the pipeline, never its
write targets); git object/ref writes and human-direct
shell writes during development (the developer's own
hands, under `AGENTS.md`'s flap protocol, are not an
app process).

## What this retires

The per-repo write workarounds fold into the wrapper
(plan §12): the scheduler `/ops` service as a standalone
(its implementation is the wrapper's base — the
surviving-base pattern, as dispatch took the scheduler
outbox in §4.5); the workbench's cross-repo file drops
as a mechanism (§4.3's arming act stays; the drop goes);
the attention store's in-process writer; the runner's
record-writer helpers and every per-app atomic-write
helper (the scheduler's state I/O discipline included).
Each store's re-pointing step is named in plan §4.15's
amendment.

## Fixtures

The `op` event lines in contract 05's fixture set —
produced by the pinned scheduler's Ledger at S0 — are
this contract's audit specimens. A staged-write specimen
set (stage, verify, rename, and a denied-stage case
leaving the target byte-identical) lands with the §6 P4
flap-simulation drill at S9.

**Landed (S9/P4):** the drill ran over one
store of each re-pointed class (scheduling registry
entry, dispatch outbox, work-record armed row and todo
file, venue lease record, pipeline registry store,
attention state store) with a denial injected at each
protocol stage: 32 of 32 cases pass — every denied write
surfaces `io_error` (contract 04's name) where the
surface exposes a name, every target byte-identical,
a stale-stamp cas-update refused whole as
`version_conflict`, a writer killed mid-stage leaving
its target intact, and one ledgered `op` event per
returned attempt (a killed attempt is the one absence:
the audit is written after the act, and its evidence is
the intact target plus the orphaned staged temp).
Drill and results: the goal record's
`s9-p4-drill.py` / `s9-p4-drill-results.json`; the
closure sweep and its dispositions are the S9 P4
report in the same record.

## Preserve clauses carried

None new. This contract generalizes disciplines already
traced: SCH6's `/ops` half stays contract 04's (payload
semantics and authentication), RUN1's staged-sibling
write stays contract 12's shape, ATT1's store discipline
stays contract 01's — their mechanisms become this
wrapper's calls, and traceability records the amendment
(count unchanged, 36 of 36).
