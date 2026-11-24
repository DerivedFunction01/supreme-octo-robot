"""The attention service, landed in the mega tree at S11
from the pinned owner-attention backend (pin 7f13ae7) in
the target's shape: a real package under the pipeline
root (the pinned tree's `backend` package, flattened —
foundation/settings and foundation/errors sit at the
package root as settings.py and errors.py).

- domain: the pure rules (registries, defaults, views'
  vocabulary).
- services: the builders, writers, ingest, engine,
  staffing measure, dispatch, and the tick passes.
- infra: the store seam (this package's migrated
  AttentionStateStore behind it), the sample-state
  fixture builder, and the loopback clients for the
  sibling surfaces (workbench, scheduler bridge, lease
  panel) — HTTP, exactly as the pinned service consumed
  them.
- settings: the one environment seam. The serving shell
  (server.py, on the platform serving core) binds the
  state store EXPLICITLY through it: ATTENTION_DATA names
  the migrated store file, and its absence is a startup
  refusal — there is no seeded-sample default anywhere in
  the serving path (the sample builder survives only as a
  fixture source for tests).
- capacity: the slow capacity collector's pass and
  loop, extracted from the serving shell along its
  seam; the shell wires the loop as a supervised
  worker, and the pass merges its snapshots into the
  same store under the shared lock.
- cli/client: the connector CLI (the `attn` verbs),
  riding ATTN_URL like the pinned connector did.
"""
