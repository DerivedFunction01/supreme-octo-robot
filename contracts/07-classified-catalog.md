# 07 — Classified catalog

**Canonical owner:** the pipeline scheduling engine — the
catalog owner; the workbench manifest consumes its axes.

**The contract in one line:** the classification axes are
defined once, every example is indexed exactly once, and
adoption renders from the catalog — never the reverse.

## The axes and the catalog (SCH2)

Catalog **version 1** indexes every file in the examples
layer exactly once. Each catalogued file carries a
`catalog` block; row and block must agree on the three
axes:

| Axis | Values |
|---|---|
| `origin` | `hand` \| `machine` \| `per-session` |
| `generality` | `generalized` \| `parameterized` \| `deployment-specific` |
| `use_case` | per-surface vocabulary (e.g. `demo`, `fleet-health`, `work-tracking`) |

Row classes: `entry`, and `config-example` — data specimens
that ride with one named entry's adoption and are **never
adopted standalone**. Classification is descriptive, not
activating: being catalogued admits nothing.

Fixture: `fixtures/catalog.yaml` (the catalog,
verbatim) and `fixtures/scheduler-entry-catalog-example.yaml`
(an entry carrying its block).

## Classification evidence

`classification` on an entry is required **evidence**, not
prose. The boundary test: an entry is scripted only if
(1) it is a fixed command sequence, (2) every outcome
branches on exit code or output enumerable in advance, and
(3) when it speaks is fully determined by those branches.
Any judgment over content makes it `agent`; scripted
detection with agent remediation is a scripted job whose
failure escalates with an agent body.

## Adoption rendering

`adopt` copies a generalized/parameterized example into the
live overlay and:

- substitutes the declared parameters plus the standard set
  (`id`, `title`, `owner`, `owner_reason`, `timezone`);
- **refuses machine literals in structural fields**;
- renames body paths to the live id (escalation bodies to
  `bodies/<live-id>-escalation.md`);
- **setup-coverage rule:** every `state_paths` entry must
  be covered by the setup declaration — state dirs created;
  files copied from a specimen or verified; stores verified
  or initialized by declared argv; companions verified
  adopted; **registrations are surfaced as manual steps,
  never machine-acted**; setup docs are copied into
  `state/adoptions/<live-id>/` and named, never performed;
- runs the admission back half (validate → server-context
  proof → admitted by the writer-path write itself,
  contract 02) and stamps the
  adoption-form `source` (`{catalog, catalog_version,
  parameters}`).

## Drift

Drift re-renders adopted entries from their stamps and
diffs them against the live files. **Volatile fields** —
named, and excluded from the diff's verdict: `source`.
(No `migrated` or `migrated_at` fields exist
in the format.) Hand-written, machine-written
(per writer family), and per-session entries are counted
separately; their writers own their lifecycle (contract
02).

## Consumption by the work record

The workbench manifest's `catalog_origin` /
`catalog_generality` / `catalog_use_case` fields carry
these same axes verbatim — the manifest consumes the
definition, it does not restate it (contract 11, WR3).

## Preserve clauses carried

SCH2 (catalog version 1, adoption rendering, setup-coverage
rule, drift semantics with its named volatile fields,
classification evidence and the scripted/agent boundary,
admission semantics — the machine-writer half rides
contract 02, and no born-admitted exception exists).
