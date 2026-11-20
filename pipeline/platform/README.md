# pipeline/platform

Platform services: the ops service, the unified state
writer, the harness connector, and the three services built
new under plan §6 — the automatic gate runner (P1), the
deployment/release record (P2), and state-store backup
(P3) — plus the survival services (watchdog, stackdump,
file-registry check).

- **Landed at S3 (2026-11-13):** `writer.py` — the unified
  state writer's base implementation (contract 15): the
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
- **Retired at S3 (§10.2, ruled):** the retired approval
  sweeper's connector compatibility — `sweeper_state_read`,
  `sweeper_state_write`, and `nudge_append` with its inlined
  schema left the moved connector; the sweeper's records
  stay on disk, unread by the pipeline.
- **Landed at S9 — P2 + P3 (2026-11-13):** `releases.py`
  — the deployment/release record: an append-only JSONL
  store tying artifact ↔ repo commit ↔ stage, written
  through the unified writer (first entry `write`, then
  stamp-guarded `cas-update`, acting caller on every
  entry), with `drift_check` as the callable — an artifact
  with no resolving entry reads undeployed, never
  deployed. `backup.py` — state-store backup: one shared
  snapshot/restore act (SHA-256 manifest, hash-verified
  restore, counts proven through each store's own loader)
  over adapters for the stores that exist now (scheduling
  registry, the Ledger class's two runtime stores, the
  work-record store). Gate + drill evidence:
  `tests/` (13 tests) and the S9 lane report. Still
  riding their own lanes: P1 (the gate-consolidation
  lane) and P4 (the flap drill, over S7's re-point).
- **Lands in S9:** P1–P4 executed over the re-pointed set,
  and the survival services homed here as platform services
  (their code rides the scheduling tree until then, per
  plan §6's build-home ruling; their registry-entry forms
  retire into internal loops, and S11 re-homes their
  external registrations).
- **Governed by:** contract 04 (platform config + the
  file-registry's home), contract 15 (the writer),
  contract 10 (the portability/denylist seam lands in the
  gate runner), contract 01 (the connector's token-caller
  registry).
- **Ruling that binds here:** `/ops` hardens to the
  `/tools` token model (§10.1) — see the S3 lane report for
  its named disposition at this step.
