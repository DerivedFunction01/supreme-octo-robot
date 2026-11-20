"""Services layer: orchestration and the read side.

Grouped by behavior:

- `waits` — the wait lifecycle: the engine decides waits,
  the standing rules act beside it, owner actions record
  verdicts, facts re-verify the load-bearing claims, and
  fulfillment verifies a decision took effect.
- `dispatch` — the send ledger and its own consumer.
- `measure` — the capacity loop's evidence collectors
  (records, stamps, worktrees), the staffing measure, and
  continuation, the stall actuator the measure drives.
- `reads` — the read side: the section builders, read-time
  derivation from the workbench, and the digest assembly.
- `writes` — the two write entrances: agent posting
  (ingest) and owner writes.

The programme declaration machinery stays at the root —
`programmes` (the declarations every family evaluates
against) and `contracts` (their wb-carried contract
sourcing): the base the groups read, not a family.
"""
