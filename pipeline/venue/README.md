# pipeline/venue

The venue layer: the generic lease core, run records,
transport, and gate policy — venue-keyed from the first
write. It dispatches compute-bound work to the fleet's
venues as peers: local machines (the local adapter,
SSH into a workspace container) and Colab sessions
(the Colab adapter), through the one lease machinery.

- **The tree** is the venue root in the runner's
  self-rooting shape: `sync/` (lease core + runner),
  `bin/` (`venue-run`, `venue-lease`, `colab-check`,
  and the rest of the wrapper set),
  `tests/`, `ui/` (the lease panel server), `config/`
  (tracked examples + the live registries, untracked
  by the carried `.gitignore`),
  `docs/`, `ops/`. Adapter material lives one level
  down (`adapters/colab/`, `adapters/local/`); anything in
  this layer that cannot name its venue is a defect (the
  D2 binding rule).
- **Records carry their venue.** Lease and run records
  are venue-keyed; legacy records were stamped
  `venue: colab` once at the cutover — no read-time
  default exists.
- **Governed by:** contract 01 (the caller registry),
  contract 02 (the liveness-entry generator is a
  pipeline writer), contract 04 (lease config + repos
  registry under the config pattern).
- **Traceability note:** the lease/run record shapes,
  placement, and bundle lineage are preserve items
  RUN1/RUN2/RUN4/RUN5 — carried by plan §7 with no §4
  contract clause (finding F1 in
  `contracts/traceability.md`); their schemas live in
  `contracts/schemas/` as pinned-code evidence.
- The Colab adapter's operator README rides as
  `docs/README-runner.md`; the local venue's runbook
  is `docs/local-compute.md`, and the lease mechanics
  of record are `docs/lease-workflow.md`.
