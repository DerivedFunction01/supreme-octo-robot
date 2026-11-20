# S1 overlay inventory — scheduler

Pin `cf910ce6a2b1c696bb7bcdbc5c9fe49460cea779`. Held copies
under `holding/scheduler/` (46 files). Tracked at the pin for
reference: 107 files, incl. `jobs/bridge-wake.yaml` and
`jobs/bridge-drain.yaml` — the only two live entries in the
tree; both depend on untracked bodies/config below.

## Job entries — 24 overlay beyond the tracked pair

Promote to tracked (19, operator/hand entries; all
`migrated: true`):

| File | Bytes | SHA-256 |
|---|---|---|
| jobs/colab-extend-guard.yaml | 1540 | a2f0033e23ba47ab3ef80e370f82d1b8cd4014f8947f1f7529ba931e3cce2892 |
| jobs/colab-runner-transient-restore.yaml | 2164 | fd0db7e511b001f14c14159b2c5e44506a79457e6ef773ff4fcda93d4225a23d |
| jobs/colab-store-prune.yaml | 1673 | 05e823c7c2f15aaffdc6178a9fe1144cb90ca8b9e81b66e06474d7db6a3abf8a |
| jobs/file-registry-check.yaml | 1836 | be14f5c1a06abff8efd07ac37dac720bdcd5cbe715a770b0d7b0c6e08e188ff1 |
| jobs/flap-watch.yaml | 2283 | e14425bae9e18bd899301504bee6b054b9512a70087bd904276580a50727c7fc |
| jobs/local-test-watch.yaml | 3546 | 6172ba17b135cf9e79a28d88b8f36784304b84360cedfcec3906efab3edaf6d2 |
| jobs/memory-index-watchdog.yaml | 1022 | 312cb9ecaad033686a5c5c2de3764461427c19af3205cedb4405bacd4bc0f931 |
| jobs/owner-attention-healthcheck.yaml | 926 | 67ba170f395468fa5532e2270d224081037eff1e8d5d78dca69b7657ec2bc7ce |
| jobs/restart-reconcile.yaml | 2116 | bfcdd4bb415a2826e9cfc98afeb6b1d25f4d0aa20b4fe6138704859541d389b1 |
| jobs/stale-mockup-cleanup.yaml | 2755 | af8cc072c9a8a14ee20c95258c9cc0fe3cccdf7e659086cd53f861e2141ab2e6 |
| jobs/storage-watch.yaml | 1654 | b228e1a301e67d13a4fa542ad061d529e0a84b3e5ed483295f35406f29e58def |
| jobs/paywatch-lane-watchdog.yaml | 1874 | 0b035db1b92a3608d898b851eba8041eabc0f511ffc5647ea220fc325d1a3b5a |
| jobs/paywatch-daily-scheduler.yaml | 2307 | 5e59c047df7135cf455b95a64bca769099a71260b7f5b1844f34b21cacb863a3 |
| jobs/paywatch-deferral-retries.yaml | 2339 | 0b46e2101716b57252878b0453bedab45248aa396b4456a1d623ab84a36cdafe |
| jobs/vm-restart-detector.yaml | 1392 | be4e251639e73eae6d6e0feab965506e65006179a90d8a4dcc9b65f66ff97e87 |
| jobs/weekly-gmail-otp-cleanup.yaml | 1933 | 5f111c8c55e47eb175de55a6c3f00124728f3c8cea1585c3de2760fe246b7803 |
| jobs/weekly-gmail-stale-jobs-cleanup.yaml | 1987 | ee960ce8c74cfad8036e11b904ec1214e8fc6e8c3ded8eb00fa9ce16d40fe37b |
| jobs/workbench-viewer-doctor.yaml | 781 | 5c18e25cbf7cac9399565c59e30fb47be25cf830c4e5ef0144ba66ca479d3597 |
| jobs/workbench-viewer-healthcheck.yaml | 714 | f873fdb734b751881706714654c0ae9dc4b8762bcb0861cbb2b70bc5a0377d6d |

Machine-derived — captured as snapshot for validation, not
promoted (5; born and retired by their writers):

| File | Bytes | SHA-256 | Writer |
|---|---|---|---|
| jobs/colab-liveness-brisk-rocket-38.yaml | 1549 | a12fdaf6fbde387ae168fd5cef75a1eeabd6a2f4db4056d61b3685a1da8b20e0 | runner lease core (per-lease) |
| jobs/colab-liveness-cozy-pilot-61-r1794547171.yaml | 1589 | aeef909e4368b279c2aa35a2bacebe66020becdfa33746eec4a9674ae34d1682 | runner lease core (per-lease) |
| jobs/colab-liveness-dawn-tower-93.yaml | 1541 | 7acab1c8a477b2501617a481ef7ca3d9a651cde20e82965269cb5df3803e0caf | runner lease core (per-lease) |
| jobs/wb-progress-programme-a-t-01k8r0000000000000000000b1.yaml | 1361 | 694b7d58a570dca1e83208ec89accf6e08129a2933893fd7b8ac8bb6f645adb2 | workbench harness (`origin: machine`) |
| jobs/wb-progress-programme-b-t-01k8r0000000000000000000b2.yaml | 1399 | f14089db798dd1772ee6c80421d883cbdc7f023b837bff5904736d2db48c1df5 | workbench harness (`origin: machine`) |

Also held: `jobs/RETIRED.md` (2,444 B,
`9b5583dd9e0e739be7d9ec54fc921aed7d67748327295985f8dcb3a8b5db3179`)
— promote to tracked; the retirement record the schema
requires, currently hidden by the local exclude.

## Bodies — 14 files in `bodies/`

Promote to tracked (12 Markdown bodies — behavioral
contracts for agent jobs):

| File | Bytes | SHA-256 |
|---|---|---|
| bodies/bridge-drain.md | 5941 | c3a8bd62be26410fa5844cb83e7f700d197b2ac879ed0d1dc0e23391e50f1711 |
| bodies/bridge-wake-item.md | 3640 | d9cc6c083212ea7c6376285d0685c5e56624e93356cb70b97ac26e5a7d214dfd |
| bodies/colab-extend-guard.md | 3252 | 0ded6bcc1cb82ae4bb297ed412788f078828b5d5da9d8911de401a3f73df4a6a |
| bodies/colab-liveness.md | 2884 | 93aac02402348c3e65a16fc67216585b1f62e681b17c89d4eff9bb1754ca40c7 |
| bodies/memory-index-watchdog.md | 5877 | 40c35620e68124b048d6d1d23591a8a47253226b990a50ccb7cab976491f8d8e |
| bodies/owner-attention-healthcheck.md | 2281 | d6132408ff1486a4f4cd3c3c2bfd854fb98253c5d3094915185400f3e3f20c08 |
| bodies/recruiter-reply-drafter.md | 5122 | 08bcfd58a6b50554efcf9d1e4b40093c849dd83f8ca1d92f954fda7154bc16bb |
| bodies/restart-reconcile.md | 1429 | 6dc3a258b889c592036930f54f36f9fa4c4a3ca9abe1fabdc0d4c41e9c746074 |
| bodies/stale-mockup-cleanup.md | 4338 | 29875a1ee1f8cf5de734a447be392d4fbd11caf3d7b56bdf55789c9bf8fd3334 |
| bodies/paywatch-lane-watchdog.md | 3115 | b1f590642a4c492af5c911a2feb140658fb2f5a9144cd600b8c1ef04fbfa703a |
| bodies/workbench-viewer-doctor.md | 2119 | 41323e909717145992838bb1ebd90e21ce711dd96e056924b1abdfcf9b25641c |
| bodies/workbench-viewer-healthcheck.md | 3105 | db9c326e5f88e24d530c034c5ddfaa93b33e71e2fa09a223690b467cdede2edf |

Live config, separated from bodies per §3 (2 routing
tables, held):

| File | Bytes | SHA-256 | Class reason |
|---|---|---|---|
| bodies/bridge-wake-owners.yaml | 644 | 5b2e87b5c6ff45fabc68b9d9b8e9b8578856b36e4ef921643ab0c8cc0246a47f | caller→chat routing config misfiled among bodies |
| bodies/restart-reconcile-owners.yaml | 768 | 7c83762d9d84626f4d1b5f4bb3ba9d7a2cd1c9f182e47ee8e9d11cd634135323 | routing config of the same species, landed with restart-reconcile |

## Other held material

| File | Bytes | SHA-256 | Class |
|---|---|---|---|
| registry/file-registry.yaml | 600 | 7cf07dbc27116d34bcd27625bf17376e0ed4b67f1e94a77055955d3ccfaa04c1 | live config — the file-registry manifest (contract 04's platform pattern; tracked specimen exists under `examples/file-registry/`) |
| config.json | 1166 | 55c8c031c264e61465bf7e577bf451f60abeae71d6a7f2be7698eb43b50c23f3 | live config — connector caller registry (**token hashes + scopes only, 4 callers; no raw tokens**) and the Git SSH path pair; tracked specimen `config.example.json` |
| ops/colab_transient_restore.sh | 955 | 60b6565592aeccdc8d00dfa32655e184580da4d1d34587bfe78e6736e1a8af3e | promote — overlay-only member script |
| ops/memory_watchdog_check.sh | 7708 | ee51ddc4e20fc2bf8f178a72be9a453ea8863d99eff228931138919eec91abb5 | promote — overlay-only member script |
| ops/paywatch_daily_scheduler.sh | 866 | 196b545d58e02d367b05a30ace99627df7d6f09a2d0769a95bca47f460dc822c | promote — overlay-only member script |
| ops/paywatch_deferral_retries.sh | 866 | 61d95b1a5b7fef42b1a4425263a44aa4345f4bd54157b5ba340460241e1b372c | promote — overlay-only member script |
| ops/paywatch_lane_watchdog.sh | 759 | 0451790549ae6bc35985011225042549987ccae9df08fce7e8f2edd929148754 | promote — overlay-only member script |

## Inventoried only — not held

- **`.git/info/exclude`** (1,644 B, SHA-256
  `2d375be6942dd34cc3c024b9ed389bb1198e8acb6589de656f15136d8091d680`)
  — enumerated here, does not travel. 47 patterns: the live
  job entries (`jobs/approval-sweeper.yaml`,
  `jobs/colab-runner-transient-restore.yaml`,
  `jobs/memory-index-watchdog.yaml`,
  `jobs/recruiter-reply-drafter.yaml`,
  `jobs/paywatch-daily-scheduler.yaml`,
  `jobs/paywatch-deferral-retries.yaml`,
  `jobs/weekly-gmail-otp-cleanup.yaml`,
  `jobs/weekly-gmail-stale-jobs-cleanup.yaml`,
  `jobs/workbench-viewer-doctor.yaml`,
  `jobs/workbench-viewer-healthcheck.yaml`,
  `jobs/stale-mockup-cleanup.yaml`,
  `jobs/sweeper-nudge-check.yaml`, `jobs/RETIRED.md`,
  `jobs/storage-watch.yaml`, `jobs/colab-extend-guard.yaml`,
  `jobs/colab-liveness-cozy-pilot-61.yaml`,
  `jobs/colab-liveness-ember-comet-32.yaml`,
  `jobs/colab-liveness-topaz-robin-96.yaml`,
  `jobs/file-registry-check.yaml`, `jobs/flap-watch.yaml`,
  `jobs/local-test-watch.yaml`, `jobs/paywatch-lane-watchdog.yaml`,
  `jobs/vm-restart-detector.yaml`, `jobs/wb-progress-*.yaml`),
  bodies (`bodies/approval-sweeper.md`,
  `bodies/memory-index-watchdog.md`,
  `bodies/recruiter-reply-drafter.md`,
  `bodies/workbench-viewer-doctor.md`,
  `bodies/workbench-viewer-healthcheck.md`,
  `bodies/stale-mockup-cleanup.md`,
  `bodies/approval-sweeper-templates.yaml`,
  `bodies/sweeper-nudge-escalation.md`,
  `bodies/sweeper-git-repos.yaml`,
  `bodies/sweeper-profile-targets.yaml`,
  `bodies/sweeper-idle-plans.yaml`,
  `bodies/sweeper-docs-reconciliation.yaml`,
  `bodies/sweeper-venue-exceptions.yaml`,
  `bodies/sweeper-thread-repos.yaml`,
  `bodies/colab-extend-guard.md`, `bodies/colab-liveness.md`,
  `bodies/paywatch-lane-watchdog.md`), member scripts
  (`ops/colab_transient_restore.sh`,
  `ops/memory_watchdog_check.sh`, `ops/paywatch_daily_scheduler.sh`,
  `ops/paywatch_deferral_retries.sh`, `ops/paywatch_lane_watchdog.sh`),
  and `registry/file-registry.yaml`. Several patterns name
  files that no longer exist (approval-sweeper set,
  sweeper-nudge-check, three former liveness sessions) —
  stale patterns, recorded as found.
- **`scheduler.env`** — credential, reference only: held a
  raw connector token (variable `SWEEPER_CONNECTOR_TOKEN`).
  Never copied, never hashed. Not in §3's list — finding 2
  in the manifest. **Disposition (2026-11-13, scheduler
  thread, owning): verified and removed.** The value
  hash-matched the registry's live sweeper-venue caller;
  the file was a redundant plaintext copy left from the
  Nov 9 venue-setup era — gitignored from the start, never
  committed, mode 600, read by nothing (the venue caller's
  token is delivered session-side by design). Deletion
  verified from this thread as well; recovery, if the
  venue copy is ever lost, is a rotation via
  `bin/sched connector-token`. No copy of the value exists
  in this capture to clean.
- **`state/`** — runtime state, not carried: 2,860 files,
  ~44.8 MB (root stores incl. `scheduler.db` 40,361,984 B —
  the live ledger/outbox store — `outbox.json`, proof files,
  logs; `connector-bridge/` 269 queue records; `flap-*`
  probe series; `adoptions/`; member-job state).
  **Ledger decision (recorded at capture, per §3): no
  manual JSONL export is taken at S1.** The ledger is the
  live server's SQLite store and changes under the running
  server; a file copy would be a torn snapshot. The only
  existing export is `state/exports/logs-all-20261101-225620.jsonl`
  (437,903 B, 2026-11-01) plus the retired
  `state/ledger.jsonl.retired-2026-11-01`. History moves at
  the S3 cutover via `bin/sched logs export` against a
  quiesced store, with its printed SHA-256 as the proof.
- **`.plans/`** (28 ignored files) — the repo's own
  workbench work records; not scheduler overlay, not
  captured (the harness reads them in place).
- **`__pycache__`** sets under `bin/`, `ops/`, `server/`,
  `tests/`, `tools/` — debris, not captured; the `ops/`
  cache still carries bytecode for the retired sweeper
  modules, noted as debris, not scripts.
- The repo's own workbench registration (`workbench.yaml`,
  `workbench/registry.db` + WAL sidecars, `registry.json`)
  is inventoried in the workbench census, not here.

## Validation (done-evidence)

Fresh tree from `git archive cf910ce` in a scratch dir
under this repo (removed after the run, verified gone):

- Bare pin: `python3 bin/sched validate` → `INVALID:
  bridge-drain.yaml: body file does not exist:
  bodies/bridge-drain.md` — **1 valid, 1 invalid**, catalog
  v1 (20 rows, 13 adoptable, 0 invalid), exit 1.
- Held overlay applied (jobs, bodies, registry, config,
  member scripts): **26 valid entries, 0 invalid**, same
  catalog line, exit 0. `bin/sched census` lists all 26.
- Correction to §3's wording: only `bridge-drain` is
  load-quarantined on the bare pin; `bridge-wake` validates
  because the loader never checks its wake body
  (`bodies/bridge-wake-item.md`) or routing config
  (`bodies/bridge-wake-owners.yaml`) — it is operationally
  incomplete on the bare pin, completed by the overlay.
