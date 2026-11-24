# Contracts — the S0 freeze

The fourteen entries of plan §4 — the eleven consolidations,
the two carrying entries (§4.12, §4.13) added by
amendment, and the registry entry format
(§4.14) added by amendment 2 — plus the
unified state writer (§4.15, contract 15) added by
amendment 4 — frozen as
documents + schemas + fixtures (plan step S0 and its
amendments). Every lane after
S0 consumes these; a shape that disagrees with its contract
is a defect against the contract, not a local choice.

- **Owner** — each contract names its canonical owner (plan
  §4's owner lines); only the owner changes the contract.
- **Preserve references** — clauses cite the plan §2 preserve
  items they carry by the ids in `traceability.md` (WR, ARM,
  SCH, RUN, ATT, VOC). The traceability index is the S0
  done-evidence.
- **Fixtures** — `fixtures/` holds specimens drawn from the
  pinned trees only: tracked examples, the pinned tests' own
  fixture inputs, or bytes produced by running the pinned
  writers/serializers themselves. No live untracked store data
  is copied anywhere in this directory. Each contract lists
  its fixtures with their provenance.
- **Schemas** — `schemas/` holds JSON Schemas for the
  data-shaped contracts, field-for-field from the pinned code;
  YAML/Markdown shapes carry exact field tables in their
  contract documents instead.
- **Rulings** — the four §10 rulings bind where a contract
  touches them: /ops token model (§10.1), sweeper retirement
  at S3 (§10.2), venue stamp at S5 (§10.3), one kit generator
  (§10.4). §9's clauses are part of this contract set and are
  annexed into the contracts they amend (01, 03, 05, 06, 09).

| # | Contract | Owner | Plan |
|---|---|---|---|
| 01 | Caller + routing registry | pipeline registry | §4.1 + §9.1 |
| 02 | Machine-entry writer | pipeline scheduling engine | §4.2 |
| 03 | Supervision arming | pipeline (work-record service) | §4.3 + §9.3 |
| 04 | Platform config (seed/example pattern) | pipeline platform config | §4.4 |
| 05 | Dispatch substrate | pipeline dispatch | §4.5 + §9.2 + §9.6 |
| 06 | Status vocabulary | pipeline (semantics) / kit (table) | §4.6 + §9.5 |
| 07 | Classified catalog | pipeline scheduling engine | §4.7 |
| 08 | Spec/supervision kit | spec-driven starter | §4.8 |
| 09 | App shell + bridge adapter | Workhorse Kit (app-shell) | §4.9 + §9.4 |
| 10 | Portability/denylist seam | pipeline gate runner | §4.10 |
| 11 | Goal records + work-record substrate | pipeline work-record service | §4.11 |
| 12 | Venue records and placement | pipeline venue layer | §4.12 |
| 13 | Engine semantics | pipeline scheduling engine | §4.13 |
| 14 | Registry entry format | pipeline scheduling engine | §4.14 |
| 15 | Unified state writer | pipeline platform | §4.15 |

Execution pins: scheduler `cf910ce`, workbench-viewer
`b0b9cc5`, colab-runner `636033b`, owner-attention `7f13ae7`
(plan §0).
