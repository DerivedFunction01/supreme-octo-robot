# pipeline/venue

The venue layer: the generic lease core, run records,
transport, and gate policy, extracted alongside the
untouched colab-runner repo — venue-keyed from the first
extracted write.

- **Lands in:** step S5 (runner pin `636033b`), executing
  plan §7 (V1–V5): venue keys on records and portions, the
  funnel dispatch change, the legacy-record stamp migration
  (§10.3 — legacy records are stamped `venue: colab` once;
  no read-time default exists), the panel's venue-keyed
  portions, and the registries' re-homing.
- **Landed (S5, 2026-11-13):** executed against the advanced
  baseline `8e9cb9b` (the standing collector ports with the
  tree). The tree here is the venue root in the runner's
  self-rooting shape: `sync/` (lease core + runner),
  `bin/`, `tests/`, `ui/` (the panel server), `config/`
  (tracked examples + the live registries re-homed from the
  S1 capture, untracked by the carried `.gitignore`),
  `docs/`, `ops/`. The Colab adapter's material lives under
  `adapters/colab/` (snippets, probes, job manifests). The
  pinned README of the source repo rides as
  `docs/README-runner.md`; the source repo itself is
  untouched (D4). Lane record:
  `hidden_files/s5-venue-report.md` in the build goal's
  workspace.
- **Governed by:** contract 01 (the caller registry leads
  the re-homing, §7 V5), contract 02 (the liveness-entry
  generator becomes a pipeline writer), contract 04 (lease
  config + repos registry under the config pattern).
- **Traceability note:** the lease/run record shapes,
  placement, and bundle lineage are preserve items
  RUN1/RUN2/RUN4/RUN5 — carried by plan §7 + S5 with no §4
  contract clause (finding F1 in
  `contracts/traceability.md`); their schemas live in
  `contracts/schemas/` as pinned-code evidence.
- Adapters live one level down (`adapters/`); anything in
  this layer that cannot name its venue is a defect (the
  D2 binding rule).
