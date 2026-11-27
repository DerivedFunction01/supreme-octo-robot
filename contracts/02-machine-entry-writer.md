# 02 — Machine-entry writer contract

**Canonical owner:** the pipeline scheduling engine — it owns
the registry the entries land in; the workbench harness and
the runner lease core are its two registered writers.

**The contract in one line:** machine-rendered scheduler
entries are one class — stamp form,
lifecycle owned by the writer, drift counted separately per
writer — whichever writer renders them.

## The entry format — contract 14

The format the writers render — one file per job at
`jobs/<id>.yaml`, the strict YAML subset, the field
table, and both `source` stamp forms — is contract 14,
the format's own contract under the same canonical
owner. This section is the pointer, so the format keeps
one home. The writer-class
consequences of the machine stamp form (lifecycle owned by the writer,
drift counted per writer) remain this contract's,
below.

**Admission (hand and adopted entries):**
validate → server-context proof → admitted by the write
itself. The registry store has exactly one mutation
path — this writer path — so an entry's presence in the
store IS its admission; there is no directory-drop path
for a flag to guard, and no admission field exists on
the entry (no `migrated: true` stamp exists in the
format).
Admission evidence — validation counts, proof outcome —
is recorded as events in the dispatch/ledger store
(contract 05), not as fields on the entry. Retired
jobs are deleted, never disabled; the retirement is recorded
in `jobs/RETIRED.md`.

## The machine-writer class

- **No born-admitted class:** machine renders are
  admitted the same way every entry is — by being
  written through the writer path (see Admission above).
  No writer stamps an admission exception at birth, and
  no render carries an admission record in a note field;
  renders write entries through the path, full stop.
- **Lifecycle owned by the writer:** a `wb-progress-*` entry
  is deleted in the same writer call that disarms its todo
  (contract 03); a `venue-liveness-*` entry is deleted in the
  same call that deletes its lease record, and the checker
  self-deletes on the first run that finds no live record.
- **Fixture class never fires:** a fixture-classed machine
  entry is held out of the live registry at load (the
  classification-layer backstop to the writers' own
  temp-root refusals, contract 03).
- **Drift counted separately per writer:** hand-written,
  machine-written (per family), and per-session entries are
  counted separately in drift; their writers own their
  lifecycle (contract 07).

## The two registered writers

| Writer | Family | Trigger | Fixture |
|---|---|---|---|
| workbench harness (`pipeline/workrecord/lib/progress/schedule.py`) | `wb-progress-<project>-<todo-id-lower>.yaml` | todo doing-transition arms; terminal/disarmed/archived retires | `fixtures/scheduler-entry-wb-progress.yaml` |
| runner lease core (`pipeline/venue/sync/liveness_entry.py`) | `venue-liveness-<session>.yaml` | one per live lease; deleted with the lease record | `fixtures/scheduler-entry-venue-liveness.yaml` |

The five scheduler-entry fixtures — the two machine
renders above plus the hand and adoption forms
(`scheduler-entry-bridge-wake.yaml`,
`scheduler-entry-bridge-drain.yaml`,
`scheduler-entry-catalog-example.yaml`) — are contract
14's evidence, with their provenance tabled there.

## Preserve clauses carried

SCH1's writer half (the machine-form stamp as rendered
under this contract; the format itself is contract 14),
SCH2 (machine-writer exception — no born-admitted half
exists; catalog/adoption/drift ride
contract 07), ARM1 (the entry as the arming projection —
its form is contract 14's; the arming act itself is
contract 03).
