# S1 overlay inventory — colab-runner

Pin `636033be98405bab396329728b5d386a3c90a168`. Held copies
under `holding/colab-runner/config/` (6 files). All are the
live-config class (untracked live files seeded from tracked
`*.example.json` specimens — the seed/example pattern,
contract §4.4's family).

## Live configs — held

| File | Bytes | SHA-256 | Notes |
|---|---|---|---|
| config/callers.json | 403 | aaefea86329c7bf201c7595a6a395364f6bfc68c564bb777dc1465edaf98b3df | the caller registry (contract 01's type specimen): **15 thread callers, 3 `active`** at capture — review said 14/3; +1 caller from live operator traffic since 2026-11-12, active set unchanged |
| config/lease.json | 979 | c3579c608eee50caa31e9e3964ef4421433e03c5c91d0037a9b1b572c43bc639 | caps + session-gate policy |
| config/repos.json | 2077 | ec19f20da725c8e51c511718362083e05dd0d375a4f45fb3126a4a9b5bfd7db5 | pointer-only target-repo registry |
| config/notify-routes.json | 324 | e230b4209b5d8e1d9e9cccced4aadd3def0fc729b8b664a3b2f2c7f25c596888 | caller→chat routing for liveness escalation |
| config/denylist.txt | 241 | b58303ae96d085654288e8b98b2e395ec7b0394ec5def56c800eb3542294480a | personal literals for the portability guard — held as live config, never a tracked candidate |
| config/transient.json | 2692 | 98da7f218f2254bf4382b6aa16958f30f5f9f9141a83d8752421d1cf46f2b0e1 | the transient registry: 5 items (4 file mirrors + 1 recreate). Held as the registry of record; its *contents* (the mirrored files) are governed by the reference-only rule below |

Negative instance verified: `config/profiles.json` does
not exist (retired by ruling) — nothing to capture.

## Credential — reference only, never copied

- **Auth-transient mirror**: canonical
  `${HOME}/.config/colab-cli/token.json`, mirror
  `state/transient/colab-cli/token.json` under this repo
  (paths from tracked `docs/auth.md`). Both exist at
  capture, 938 B each, mode 600. The mirror is the OAuth
  token store: per the secrets discipline and this repo's
  own rule (transient contents are never printed, logged,
  or committed), it is **inventoried by reference only —
  no copy was taken into the mega repo, no hash recorded**.
  Its capture/restore at cutover rides the repo's own
  `ops/mirror_transient.py` mechanism, never a blind
  copy-back. This is the one place this capture departs
  from a literal "copy everything held" reading of §3,
  and it departs deliberately.

## Runtime state — inventoried with counts only, never copied

Machine-local state; re-seeded deliberately at cutover
(S5), per §3:

| Store | Count | Bytes | Notes |
|---|---|---|---|
| `var/lease-<session>.json` | 5 | 9,086 | live lease records |
| `var/session-evidence-*.json` | 3 | 672 | deadline-evidence projections of the lease records |
| `var/renewal-config-*.json` | 45 | 12,332 | transient class, rides with `var/` as a whole per `ops/mirror_transient.py` |
| `var/liveness-*.json` | 20 | 2,952 | transient class, same |
| `results/runs/*.json` | 1,825 | 3,200,425 | run records — state census as found: complete 1,050, failed 551, orphaned 217, polling 3, `completed` 1, **unparseable 3** (finding 4 in the manifest: the three ruled terminal states are complete/failed/orphaned; the rest is record hygiene for the venue layer, recorded here without opening the records) |
| `results/detached/*.json` | 4,644 | 1,158,152 | detached-job outputs — the store attention's `run_records_dir` reads (see the attention inventory); not in §3's runner list, inventoried here so the evaluator's ground truth is not lost |

The rest of `var/` (bridge spools, chunk transfer parts,
caller-claims journal, gate journals, caches) is working
runtime state of the same class: not itemized, not carried.

## Out-of-repo registrations — recorded from repo material

- **Reaper hook** (`colab-lease-reaper`, script-level,
  120 s poll; registered with the runtime's hook system,
  outside this repo — `docs/lease-workflow.md`). Each pass,
  in order: approval-gate evaluation → transient mirror
  restore → liveness reconciliation (`bin/colab-liveness
  --sync`, arms/retires the scheduler's per-lease entries)
  → network duties (reap, auto-acquire, standing duty),
  skipped while the approval gate stands. The restore duty
  is the same `ops/mirror_transient.py restore` the
  runbook's cron form names; on this machine the hook, not
  cron, is the registered trigger (marker
  `state/transient/cron-registered.json`).
- **Notify hook** (`colab-lease-notify`): announces each
  event the UI server drains from `var/reaper-events.jsonl`
  into `var/ui-outbox.jsonl` (`lease-extended`,
  `grant-extended`, `lease-renewed`, and the runner core's
  `run-terminal` events) to the main chat. The panel/UI
  server is the outbox's single writer apart from the
  core's `run-terminal` appends.
- **Runtime registrations, recorded by the parent
  (2026-11-13, from the hook system's own records — the
  lane's gap above is closed):** both hooks are registered
  and **enabled**, delivery to the main chat.
  `colab-lease-reaper`: poll 120 s, script
  `${HOME}/hooks/scripts/colab-lease-reaper.sh` (22,380 B,
  SHA-256 `e193e5ada36454a5…`), worker instruction
  report-only (the script has already acted; the woken
  agent announces the action or failure and runs no lease
  commands). `colab-lease-notify`: poll 60 s, script
  `${HOME}/hooks/scripts/colab-lease-notify.sh` (2,699 B,
  SHA-256 `d75c8fc6af6716d2…`), worker instruction
  announcement-only, with one action: on an
  `approval-needed` event it triggers exactly one
  immediate reaper run so the host's approval card mints
  in the same batch. These two registrations are what §5
  re-homes.
