# Traceability — plan §2 preserve items → contract clauses

Every plan §2 preserve item traces to a contract clause:
**36 items — 36 traced.** Ids are assigned here for
citation; the item text is plan §2's, grouped as §2
groups it.

## Full mapping

### Work record (4)

| Id | Item (short name) | Clause |
|---|---|---|
| WR1 | File-todo format + id scheme, checkpoint line format, stall verdict | 11 (file todos) + 03 (derivation) |
| WR2 | Registry unified schema, `registry.json` export shape, data-never-migrates | 11 |
| WR3 | Manifest format incl. `catalog_*` fields | 11 + 07 (axes) |
| WR4 | Two stores stay two; DB todo table link-only | 11 |

### Arming contracts (2)

| Id | Item | Clause |
|---|---|---|
| ARM1 | Scheduler-entry YAML per armed todo | 03 (+ 14 entry form) |
| ARM2 | Attention armed-row JSON | 03 |

### Scheduler (9)

| Id | Item | Clause |
|---|---|---|
| SCH1 | Job ids, strict YAML subset + semantics, owner values, both source stamps | 14 — the registry entry format's own contract (§4.14); field table carries no migration field family |
| SCH2 | Catalog v1, adoption, setup coverage, drift, classification boundary, admission | 07 (+ 02 machine-writer half; no born-admitted exception — admission is presence through the writer path) |
| SCH3 | Engine firing semantics | 13 (the firing clause: status `active` + presence in the registry store through the one writer path) |
| SCH4 | Ledger format (canonical JSON, kind vocabulary, SQLite schema, JSONL + SHA-256, empty-store import) | 05 (audit-ledger clause) |
| SCH5 | Outbox ping shape, ids, states, coalescing, wake window, ack, void | 05 |
| SCH6 | HTTP routes/payloads; ops errors + staged writes; `GIT_SSH_COMMAND` pair rule | 05 (`/pings`) + 01 + 05 (`/tools`) + 04 (`/health`, `/ops`) + 09 (`/api/v1`) |
| SCH7 | Connector scopes, hash-only registry, fresh-read, refusal ledgering, envelope idempotency, no-authority boundary | 01 + 05 (envelope) |
| SCH8 | Bridge record shape + target-resolution rule | 05 (+ 01 routing tables) |
| SCH9 | Body refs, ack-after-work, watchdog/keeper, portability anchors | 05 (body refs, ack) + 04 (watchdog/keeper) + 10 (portability) |

The `GIT_SSH_COMMAND` pair rule (SCH6's tail): both
live-config keys set or nothing is pinned — the keys
themselves home in contract 04's scheduler config instance;
the rule rides contract 04's ops-service clause.

### Runner (6)

| Id | Item | Clause |
|---|---|---|
| RUN1 | Lease record shape + naming + atomic write + evidence projection | 12 |
| RUN2 | Run record shape, terminal states, one `run-terminal` event | 12 |
| RUN3 | Caller attribution semantics in full | 01 |
| RUN4 | Placement + spend attribution | 12 |
| RUN5 | Snapshot-bundle lineage | 12 |
| RUN6 | Seed/example config pattern itself | 04 |

### Attention (14)

| Id | Item | Clause |
|---|---|---|
| ATT1 | State-store discipline (atomic write, backfill, datetime heuristic) | 01 (§9.1 annex) |
| ATT2 | Decision machinery (verdict at tap, band, derived fulfillment, 120-min stall, return with history, replay guards) | 05 (§9.6) |
| ATT3 | Reply routing — direct to owner, main copied | 05 |
| ATT4 | Presence semantics + glance/Today asymmetry | 09 (§9.4) |
| ATT5 | Send + dispatch shapes, `mode`/`outcome`, id schemes, envelope + bridge meta | 05 |
| ATT6 | Delivered-only-on-reference (claiming consumer, 15-min lease, submission reference) | 05 |
| ATT7 | Suppress semantics (terminal, reasoned, refused on delivered, late fulfillment stamped) | 05 (§9.2a) |
| ATT8 | Wait record + fact-hash dedupe; one item per wait; terminal post resolves, ack never | 05 (+ 03 status posts) |
| ATT9 | Armed-row consumer half (shape, `(project, todo)` join, fixture exclusion) | 03 |
| ATT10 | Status-post form (grouped, refs-only, sticky `owner_waiting`) | 03 |
| ATT11 | Programme declaration fields incl. contract-sourced `rule_text`/`cadence_minutes` | 01 (+ 11 ownership) |
| ATT12 | Staffing row kinds/labels, escalation-memory semantics | 03 (§9.3) |
| ATT13 | Push-fact measurement (five fact states, measured titles, tick self-clearing) | 03 (§9.3 feed) |
| ATT14 | Vocabulary registry contents migrate as data | 06 |

### Status vocabulary (1)

| Id | Item | Clause |
|---|---|---|
| VOC1 | Ruled entry vocabulary + token status table — one contract in two files, move together | 06 |

## Standing rulings behind the mapping

- **The registry entry format has its own contract.**
  SCH1 traces to contract 14 (§4.14, canonical owner: the
  pipeline scheduling engine); contract 02's substrate
  section is a pointer to 14.
- **The migration field family does not exist in the
  target.** `migrated`, `migrated_at`, `migration_note`,
  and `proof_pending` are not fields of the registry entry
  format (contract 14) or its semantics: an entry stands
  in the registry store only by being written through
  contract 02's writer path (validate under §4.14's
  format, server-context proof for hand-authored entries),
  an entry fires iff its status is `active` and it stands
  in that store (contract 13), and presence through the
  path IS admission; there is no directory-drop path for a
  flag to guard. Admission evidence (validation counts,
  proof outcome) is recorded as events in the
  dispatch/ledger store, not as fields on the entry, and
  the workbench doctor's never-admitted check is
  presence-in-store through the writer path (contract 03).
  The `source` stamp is provenance, not a migration field,
  and stays.
- **Contract 15 carries no §2 preserve item of its own**
  and changes none: SCH6's `/ops` half traces to contract
  04, RUN1's atomic write to contract 12, ATT1's store
  discipline to contract 01. Contract 15 unifies the
  mechanism behind those traced disciplines — the
  per-workhorse write workarounds the write-denial flap
  forced fold into the one pipeline writer, whose
  operation set, atomicity protocol, and failure semantics
  generalize contract 02's one-mutation-path principle
  from the registry store to all state.
- **The scheduler file registry is homed under contract
  04** (plan §4.4; seed/example pattern; its check is a
  platform survival loop). Its specimen is
  `contracts/fixtures/file-registry.example.yaml` and its
  catalog example is
  `pipeline/scheduling/examples/file-registry/example-file-registry.yaml`.

## Review disagreements (plan governs)

- **Venue legacy reading:** the runner review (§7/§8)
  states legacy records "defaulted to Colab"; plan §10.3
  rules the **stamp migration** — no read-time default
  exists. The contracts follow §10.3 (01, 03).
- **Kit generators:** the workbench review (§8) leaves the
  kit needing "a generator story per consumer stack"; plan
  §10.4 rules **one generator**, generated CSS shipped.
  Contract 09 follows §10.4.
- **Runner↔attention contact:** the runner review (§6)
  calls the attention contact "attribution-level only";
  the attention review (Finding 5, §8) shows two read
  seams (run records off the filesystem, panel served
  state). Plan §9.3 sides with the attention review — both
  are named evaluator feeds in contract 03.
- **Settled after review:** the scheduler review (§7)
  carries the /ops posture and the sweeper-compatibility
  question as open; both are ruled in the plan (§10.1
  harden, §10.2 retire) and are recorded as rulings, not
  disagreements.
