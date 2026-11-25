# Contracts

Fifteen living agreements — documents + schemas +
fixtures — that the pipeline packages and apps implement.
A shape that disagrees with its contract is a defect
against the contract, not a local choice. Contracts are
updated in place as implementations supersede their terms.

- **Owner** — each contract names its canonical owner;
  only the owner changes the contract.
- **Preserve references** — clauses cite the preserve
  items they carry by the ids in `traceability.md` (WR,
  ARM, SCH, RUN, ATT, VOC).
- **Fixtures** — `fixtures/` holds specimens drawn from
  tracked examples, the tests' own fixture inputs, or
  bytes produced by running the writers/serializers
  themselves. No live untracked store data is copied
  anywhere in this directory. Each contract lists its
  fixtures with their provenance.
- **Schemas** — `schemas/` holds JSON Schemas for the
  data-shaped contracts, field-for-field from the code;
  YAML/Markdown shapes carry exact field tables in their
  contract documents instead.
- **Rulings** — four rulings bind where a contract touches
  them: the /ops token model, sweeper retirement, the
  venue stamp, and one kit generator. The annexed clauses
  are part of this contract set and are carried in the
  contracts they amend (01, 03, 05, 06, 09).

| # | Contract | Owner |
|---|---|---|
| 01 | Caller + routing registry | pipeline registry |
| 02 | Machine-entry writer | pipeline scheduling engine |
| 03 | Supervision arming | pipeline (work-record service) |
| 04 | Platform config (seed/example pattern) | pipeline platform config |
| 05 | Dispatch substrate | pipeline dispatch |
| 06 | Status vocabulary | pipeline (semantics) / kit (table) |
| 07 | Classified catalog | pipeline scheduling engine |
| 08 | Spec/supervision kit | spec-driven starter |
| 09 | App shell + bridge adapter | Workhorse Kit (app-shell) |
| 10 | Portability/denylist seam | pipeline gate runner |
| 11 | Goal records + work-record substrate | pipeline work-record service |
| 12 | Venue records and placement | pipeline venue layer |
| 13 | Engine semantics | pipeline scheduling engine |
| 14 | Registry entry format | pipeline scheduling engine |
| 15 | Unified state writer | pipeline platform |
