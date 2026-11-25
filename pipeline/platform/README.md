# pipeline/platform

Platform services: the unified state writer, the ops
service and its client, the platform serving core, the
deployment/release record, state-store backup, and the
survival machinery (unit templates, the watchdog ladder,
the healthcheck) under `ops/`.

- `writer.py` — the unified
  state writer (contract 15): the
  staged-write protocol core (stage → fsync → read-back →
  rename-over → directory fsync) and the writer operation
  set (write, patch, cas-update, delete) over contract 04's
  closed error table plus `version_conflict`. The ops
  service and the harness connector ride the scheduling
  server package that hosts them (`pipeline/scheduling/
  server/serving/ops.py`, `server/serving/connector.py`): the endpoint
  delegates its staged write to `writer.py`, so the protocol
  has exactly one implementation. `exec` stays the ops
  service's contract-04 clause, not a writer operation.
- `ops_client.py` — the client half of the ops route:
  token resolution and the server URL, with its retry
  discipline, for callers that ride `bin/sched exec` /
  write / patch.
- `serving.py` — the platform serving core the repo-root
  `run.py` mounts the surfaces on: `serve` (the coupled
  scheduler + attention process), `serve-workbench`, and
  `serve-venue`, each in its own process and unit (below).
- `releases.py`
  — the deployment/release record: an append-only JSONL
  store tying artifact ↔ repo commit ↔ stage, written
  through the unified writer (first entry `write`, then
  stamp-guarded `cas-update`, acting caller on every
  entry), with `drift_check` as the callable — an artifact
  with no resolving entry reads undeployed, never
  deployed.
- `backup.py` — state-store backup: one shared
  snapshot/restore act (SHA-256 manifest, hash-verified
  restore, counts proven through each store's own loader)
  over adapters for the stores that exist (scheduling
  registry, the Ledger class's two runtime stores, the
  work-record store).
- `ops/` — the survival machinery: the unit templates
  and `units-spec.json` (three serving units —
  `workhorse.service` for the coupled process,
  `workbench.service`, `venue.service` — each with its
  watchdog timer), `watchdog.sh` (the ladder the timers
  drive), `healthcheck.py` (the per-unit healthcheck the
  ladder reads), the install scripts, the publish
  machinery, and `ops/cutover/` — the executed cutover's
  drivers and freeze-record shape, standing as its kit.
- The retired approval sweeper's connector compatibility
  (`sweeper_state_read`, `sweeper_state_write`, and
  `nudge_append` with its inlined schema) is gone from
  the moved connector; the sweeper's records
  stay on disk, unread by the pipeline.
- **Governed by:** contract 04 (platform config + the
  file-registry's home), contract 15 (the writer),
  contract 10 (the portability/denylist seam),
  contract 01 (the connector's token-caller
  registry).
- **Ruling that binds here:** `/ops` rides the
  `/tools` token model (§10.1): per-caller
  token-authenticated calls, hashes only in the live
  config, every call ledgered.
