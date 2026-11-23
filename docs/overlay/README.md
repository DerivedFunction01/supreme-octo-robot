# S1 overlay capture — manifest

Capture window: 01:46–01:55 EST (America/New_York).
Sources read-only throughout; nothing in a source repo was
edited. Execution pins: scheduler `cf910ce`, workbench-viewer
`b0b9cc5`, colab-runner `636033b`, owner-attention `7f13ae7`.

Held material lives under `holding/<repo>/` — held for the G1
gate, per plan §3; it is not promoted into the mega repo's
tracked structure by this step. Inventories:
[scheduler](scheduler.md) · [workbench](workbench.md) ·
[runner](runner.md) · [attention](attention.md). The full
workbench manifest census (every manifest root + SHA-256) is
in [workbench-manifest-census.json](workbench-manifest-census.json).

## Reconciliation against the reviews

| Census | Review | Capture | Delta |
|---|---|---|---|
| Scheduler live job entries beyond the 2 tracked | ~40 | 24 (19 operator + 5 machine-derived) | Explained: the review's ~40 was the fleet at its inspection peak. Per-lease `colab-liveness-*` entries (3 at capture) and `wb-progress-*` entries (2 at capture) are born and self-delete with leases/todos, so the count moves with live fleet size; the day's landings also retired entries. The operator set is stable and fully named in the scheduler inventory. |
| Scheduler bodies | 12 files in `bodies/` | 14 files: 12 Markdown bodies + 2 routing-config YAML | Explained: +2 are the restart-reconcile pair (`restart-reconcile.md`, `restart-reconcile-owners.yaml`) landed with that job after the review. The 12-body core matches. |
| Runner live configs | 5 (+ transient registry) | 5 + `transient.json` held; auth mirror by reference only | Match, except the caller registry grew 14 → 15 thread callers (active still 3): one caller registered by live operator traffic since the review. |
| Workbench manifest census | (no fixed count in review; sweep is the view) | 11 canonical projects, 241 manifest roots, 0 sweep errors | Live: the programme-b slug alone folds 231 roots (worktrees/exports) and grew during the capture hour as new worktrees were created. |
| Attention handlers / programmes | 10 / 3 | 10 / 3 | Match. |
| Attention sends / items | 39 / 52 | 47 / 53 | Explained: live dispatch traffic — 9 sends carry timestamps at/after 2026-11-12T20:00Z and the newest item's `waiting_since` is 2026-11-12T20:55Z, bracketing the review's count point. |

## Validation results (S1 done-evidence)

- **Scheduler fresh tree:** a bare checkout of the pin
  (`git archive cf910ce`, scratch since removed) →
  `bin/sched validate` = **1 valid, 1 invalid**
  (`bridge-drain.yaml: body file does not exist:
  bodies/bridge-drain.md`), exit 1. With the held overlay
  applied → **26 valid entries, 0 invalid**, catalog v1
  (20 rows, 13 adoptable), exit 0; `bin/sched census` lists
  all 26. One correction to the review/plan wording: the
  bare pin quarantines only `bridge-drain` at load —
  `bridge-wake` *validates* (its missing wake body and
  owners config are runtime dependencies the loader does not
  check), so it is operationally incomplete on the bare pin
  rather than load-quarantined. The overlay completes both.
- **Attention store load:** the captured `state.json` loaded
  through the pinned code's own `JsonFileStore.load_state()`
  from a scratch copy (since removed): no exception; every
  registry count identical raw vs loaded (handlers 10,
  programmes 3, rules 8, templates 18, sends 47, items 53,
  waits 0, action_rules 7, status_codes 8, fields 12,
  wait_classes 16, item_kinds 11, owner_actions 26,
  dispatch_failures 442, armed_rows 2); presence mode `away`
  preserved; no top-level key lost.

## Classification totals (held + inventoried)

| Class | Count | Where |
|---|---|---|
| Promote to tracked | 37 files held | scheduler: 19 job entries, 12 bodies, 5 member scripts, `jobs/RETIRED.md` |
| Live config (seed/example pattern) | 4 scheduler files + 6 runner files held; attention store + armed rows held as data (below) | scheduler config/owners/file-registry; runner `config/*` |
| Data, held verbatim | attention `var/data/state.json` (393,986 B) + 2 armed rows | the existential capture; migrates as data at S10 |
| Runtime state, not carried | scheduler `state/` (2,860 files, ~44.8 MB) + ledger; runner 5 lease records / 1,825 run records / 4,644 detached outputs (counts only); workbench `state/` (22 files, ~74.3 MB) | inventoried, re-seeded or left in place at cutover |
| Credential, reference only — never copied | scheduler `scheduler.env` (raw connector token); runner auth mirror `state/transient/colab-cli/token.json` (938 B, mode 600); attention `var/connector/bridge-token` (43 B, mode 600); workbench `state/` edit-backups containing secret-bearing `.bak` files | named by path/nature/owning contract only; no values, no hashes of credential files |
| Debris, not captured | attention `var/xfer` (639 files, ~49.1 MB), `var/storyboard-build` (12), `var/venv` (1,332, ~192.7 MB); scheduler `__pycache__` sets incl. stale sweeper bytecode; workbench probe temp files | named as excluded in the per-repo inventories |

## Findings

1. **Scheduler bare-pin quarantine is one entry, not two**
   (above) — plan §3's wording ("quarantines the two bridge
   entries") overstates the loader's check; the second entry
   fails at runtime, not at load. Recorded here; the plan
   text is the parent's to amend.
2. **`scheduler.env` held a raw connector token**
   (`SWEEPER_CONNECTOR_TOKEN`) — a live credential sitting in
   the scheduler working tree outside `config.json`'s
   hash-only registry. Not in §3's list; inventoried by
   reference only. **Dispositioned by the
   scheduler thread: verified a redundant copy of the live
   sweeper-venue token (never committed, read by nothing)
   and removed; deletion verified. Detail in the scheduler
   inventory.**
3. **Runner runtime hook definitions are not readable from
   this lane's tools** — the reaper and notify hooks are
   recorded from the runner repo's own material (names,
   duties, poll) in the runner inventory; the runtime-side
   registration definitions remain for the parent to close.
4. **Three run records in the runner's `results/runs/` do
   not parse** and the state census shows 3 `polling` + 1
   `completed` alongside the three ruled terminal states —
   inventoried as found (counts only); record hygiene is
   the venue layer's, not S1's.
