# 14 — Registry entry format

**Canonical owner:** the pipeline scheduling engine — it
owns the registry the entries land in and the validator
that enforces the format; every writer, reader, and the
engine itself conforms to it. (Plan §4.14, added by
amendment 2, owner's ruling. At S0 this
format rode as contract 02's shared substrate; the
substrate note there recorded that §4 assigned it no
entry of its own, and this contract is the closure.)

**The contract in one line:** a scheduler job is one
file in one strict form — `jobs/<id>.yaml`, id equal to
the filename stem, fields exactly as tabled here — and
anything outside the form is invalid at load, not
interpreted leniently.

**Parties:** the writers are §4.2's two registered
machine writers (the workbench harness, the runner lease
core), hand authors, and the adoption service; the
readers are the engine (contract 13, which fires from
entries in this form), the classified catalog (contract
07, which classifies entries and whose block is one of
the format's fields), the arming projection (contract
03, whose scheduler entries are rendered in this form),
and the scheduler app viewer, which renders entries and
never re-derives their semantics (contract 06). The
store the format lives in is the job registry §12 names
a survivor — the pipeline scheduling registry in the
target structure.

## The frozen shape

One file per job: `jobs/<id>.yaml`; the filename stem is
the job id and an internal `id` field must match it
(**SCH1**). Entries use the registry's strict YAML
subset (nested maps by two-space indentation, scalar
lists only, no anchors, flow maps, multiline strings,
or lists of maps). Unknown fields are invalid and
quarantined; secret-shaped values anywhere fail
validation.

The pinned scheduler carries the schema of record as
tracked prose + validator code (`jobs/README.md`,
`server/registry.py` at the pin) — no machine-readable
schema file exists in tracked form, so this field table
is the frozen statement of the format, field-for-field
from that schema:

| Field | Form |
|---|---|
| `id` | = filename stem |
| `title` | string |
| `kind` | `scripted` \| `agent` |
| `status` | `active` (default) \| `suspended` (+ `suspend_reason`, `suspended_on`) |
| `cadence` | exactly one of `{type: interval, every: <Ns\|Nm\|Nh>}`, `{type: daily, at: "HH:MM"}`, `{type: weekly, dow: [...], at: "HH:MM"}` |
| `timezone` | IANA name (adoption renders it; machine renders may omit) |
| `owner` | `goal:<slug>`, or `none` with `owner_reason` |
| `run` | scripted: `argv` (list of strings), optional `cwd`, `env_names` (names only), `shell: true` only with `shell_reason` |
| `body` | agent: `bodies/<id>.md`, repo-relative, must exist at validation |
| `escalate_body` | optional on scripted entries |
| `timeout_secs` | integer |
| `report` | `when` (`never\|on_failure\|always\|on_output`), `ok_exit_codes`, `fail_patterns`, `report_patterns`, `quiet_patterns` |
| `state_paths` | where the member job's state lives; the server does not move it |
| `classification` | required evidence text (contract 07's boundary test) |
| `lifetime` | `permanent` \| `until_complete` (+ `self_removal`) |
| `source` | one of the two stamp forms below — the forms never mix |
| `catalog` | the classified-catalog block (contract 07) |

The pinned schema of record also carries a migration
field family — `migrated`, `migrated_at`,
`migration_note`, `proof_pending`. By amendment 3
(owner's ruling) those fields do NOT exist
in this format: an entry stands in the registry store
only by being written through contract 02's writer
path, so presence in the store is admission and no
field records it (contract 13 states the firing half).
Their absence from the table above is ruled, not an
omission.

Portability: entry paths may be bare command names or
start with `${REPO}/`, `${WS}/`, `${HOME}/`; any other
slash-bearing path fails validation (contract 10).
Schema-change ordering is part of the format: code
lands and is committed → server restarts onto the new
schema → only then may entries use new fields (the
engine-side half of this ordering is contract 13's).

## The two `source` stamp forms (SCH1)

- *Adoption form:* `catalog`, `catalog_version`, flat
  `parameters` (contract 07).
- *Machine form* (lawful only when `catalog.origin` is
  `machine`): `writer`, `project`, `todo`, `source_class`
  (`project|fixture`).

The forms are shapes of this format; the writer-class
consequences of the machine form (lifecycle owned by
the writer, drift counted per writer) are contract
02's.

## Fixtures

The scheduler entries S0 gathered, one per source form —
this contract's evidence:

| Fixture | Provenance |
|---|---|
| `fixtures/scheduler-entry-wb-progress.yaml` | produced by the pinned workbench `render_entry` from the pinned tests' fixture todo (machine form, workbench family) |
| `fixtures/scheduler-entry-colab-liveness.yaml` | the tracked catalog specimen of the runner lease core's render (machine form, runner family) |
| `fixtures/scheduler-entry-bridge-wake.yaml` | tracked live hand entry (hand form) |
| `fixtures/scheduler-entry-bridge-drain.yaml` | tracked live agent entry (hand form) |
| `fixtures/scheduler-entry-catalog-example.yaml` | tracked catalog example carrying the `catalog` block (adoption form) |

Contracts 03 and 07 cite the wb-progress and
catalog-example fixtures as specimens of their own
clauses (the arming render; an entry carrying its
catalog block); the fixtures' home as format evidence
is here. The fixtures are verbatim specimens of the
source (pinned) format and are not edited: the machine
renders among them carry the migration field family
(`migrated`, `migrated_at`, `migration_note`) as
history — amendment 3 drops those fields from the
target format above, and the specimens keep them as
the record of what the pinned writers wrote.

## Migration notes

S3 moves the registry behind this contract into
`pipeline/scheduling/`: the files move whole, in this
form, and the moved validator must accept exactly the
pinned validator's language — no field is added,
renamed, or relaxed in transit, save the migration
field family amendment 3 rules out of the target
format. Admission (validate → server-context proof →
admitted by the writer-path write itself) is contract
02's half of the lifecycle and leaves no field on the
entry; this contract freezes only the form an admitted
entry takes. A change to the format is a ruling, not
a migration detail.

## Preserve clauses carried

SCH1 — whole (job ids, the strict YAML subset and field
semantics, owner values, both source stamp forms).
ARM1's entry-form half (the arming act itself is
contract 03's).
