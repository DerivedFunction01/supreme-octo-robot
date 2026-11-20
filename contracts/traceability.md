# Traceability — plan §2 preserve items → contract clauses

The S0 done-evidence (plan §5, step S0): every §2 preserve
item traces to a contract clause. **Result: 36 items — 36
traced.** At S0 the count was 29 traced, 2 partially
traced, 5 with no clause; the 2026-11-13 amendment
(owner's word) closed the seven: §4.12/§4.13 and contracts
12/13 carry the five unclaused items, and named clauses in
contracts 04 and 09 resolve the two partials. The gaps are
kept below as finding history, with their dispositions;
they were not papered over anywhere in `contracts/`.

## Findings — items that had no clause (all closed by the 2026-11-13 amendment)

**F1 — Five items trace to no §4 contract clause.** §4's
eleven entries have no venue-records entry and no engine
entry. The plan carries these items as component and step
detail (§1 structure, §7, S3/S5) but commissions no contract
for them, so nothing in the frozen set freezes their shapes:

| Item | What it preserves | Where the plan carries it instead |
|---|---|---|
| SCH3 | Engine firing semantics (consume-before-run, missed-point collapse with counts, no self-overlap, last-good registry, fail-safe halt, migrated-only firing, schema → restart → entries ordering) | §1 lists the engine under pipeline/scheduling; S3 moves it "behind the S0 contracts" — but §4 defines none for it |
| RUN1 | Lease record JSON shape, per-session naming, staged-sibling atomic write, `session-evidence-` projection | §7 V1 + S5 (schemas exist here as evidence: `schemas/lease-record.schema.json`, `schemas/session-evidence.schema.json` — drawn from the pinned code, owned by no §4 clause) |
| RUN2 | Run record shape, three terminal states, exactly-one `run-terminal` outbox event | §7 + S5 (`schemas/run-record.schema.json`, same status) |
| RUN4 | Placement (latest-deadline adoption, adoption-only pins, no pin in the run/gate funnel); spend from the repo's own lease segments | §7 + S5 |
| RUN5 | Snapshot-bundle lineage (origin lineage, size + SHA-256 recorded and verified, ff-only apply) | §7 V2/V3 + S5 |

Recommendation: a plan amendment adding the carrying
clauses (a venue-records + placement entry, and an
engine-semantics home) before S3/S5 freeze against them.
S0 flags this; it does not amend beyond its commission
(the §4.4 file-registry amendment is the commissioned one,
closed below).

**Disposition (2026-11-13 amendment, owner's word):**
done as recommended. Plan §4.12 (venue records and
placement) + contract 12 carry RUN1, RUN2, RUN4, RUN5 —
the three evidence schemas are adopted as contract 12's
schemas, joined by a bundle-manifest schema; plan §4.13
(engine semantics) + contract 13 carry SCH3. §1's
canonical owners table gains both rows.

**F2 — SCH6 is partially traced.** `/pings` payloads trace
to contract 05, `/tools` to contracts 01 + 05, and
`/health`'s per-key config sources to contract 04. The
remaining halves have no clause: **`/ops` semantics**
(staged-write discipline, the error-name/status mapping —
only its authentication posture is ruled, §10.1) and the
**`/api/v1` view shapes**. §1 names an ops service as
platform content; no §4 entry freezes either surface.

**Disposition (2026-11-13 amendment):** the `/ops`
payload semantics are frozen in contract 04's ops-service
clause (the platform contract; its authentication is
§10.1's ruling), and the `/api/v1` view shapes in contract
09's `/api/v1` clause. SCH6 traces whole.

**F3 — SCH9 is partially traced.** Body refs and
ack-after-work trace to contract 05, portability anchors
and the no-machine-literals rule to contract 10. The
**watchdog/keeper contract** (external driver, presence
before health, render-when-invalid, one ladder attempt per
episode, health as the verdict) has no §4 clause — §1 names
survival services as pipeline/platform content, but no
contract and no §6 sub-step carries the keeper contract
itself.

**Disposition (2026-11-13 amendment):** the
watchdog/keeper contract is frozen in contract 04's
survival clause (its wake half stays in contract 05), and
its build homes in plan §6's platform services (step S9;
external registrations re-home at S11). SCH9 traces
whole.

## Full mapping

Ids are assigned here for citation; the item text is plan
§2's, grouped as §2 groups it.

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
| SCH1 | Job ids, strict YAML subset + semantics, owner values, both source stamps | 14 — the registry entry format's own contract (§4.14, amendment 2); at S0 carried as 02's shared substrate; field table amended by amendment 3 (the migration field family dropped) |
| SCH2 | Catalog v1, adoption, setup coverage, drift, classification boundary, admission | 07 (+ 02 machine-writer half; its born-admitted exception retired by amendment 3) |
| SCH3 | Engine firing semantics | 13 (F1, closed by the 2026-11-13 amendment; the firing clause amended by amendment 3 — status `active` + presence in the registry store through the one writer path) |
| SCH4 | Ledger format (canonical JSON, kind vocabulary, SQLite schema, JSONL + SHA-256, empty-store import) | 05 (audit-ledger clause; the kind vocabulary spans the F1/F2 producers) |
| SCH5 | Outbox ping shape, ids, states, coalescing, wake window, ack, void | 05 |
| SCH6 | HTTP routes/payloads; ops errors + staged writes; `GIT_SSH_COMMAND` pair rule | 05 (`/pings`) + 01 + 05 (`/tools`) + 04 (`/health`, `/ops`) + 09 (`/api/v1`) (F2, closed by the amendment) |
| SCH7 | Connector scopes, hash-only registry, fresh-read, refusal ledgering, envelope idempotency, no-authority boundary | 01 + 05 (envelope) |
| SCH8 | Bridge record shape + target-resolution rule | 05 (+ 01 routing tables) |
| SCH9 | Body refs, ack-after-work, watchdog/keeper, portability anchors | 05 (body refs, ack) + 04 (watchdog/keeper) + 10 (portability) (F3, closed by the amendment) |

The `GIT_SSH_COMMAND` pair rule (SCH6's tail): both
live-config keys set or nothing is pinned — the keys
themselves home in contract 04's scheduler config instance;
the rule rides contract 04's ops-service clause.

### Runner (6)

| Id | Item | Clause |
|---|---|---|
| RUN1 | Lease record shape + naming + atomic write + evidence projection | 12 (F1, closed by the 2026-11-13 amendment) |
| RUN2 | Run record shape, terminal states, one `run-terminal` event | 12 (F1, closed by the amendment) |
| RUN3 | Caller attribution semantics in full | 01 |
| RUN4 | Placement + spend attribution | 12 (F1, closed by the amendment) |
| RUN5 | Snapshot-bundle lineage | 12 (F1, closed by the amendment) |
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

## Amendment 2 (2026-11-13, owner's ruling)

Contract 02's substrate note recorded a gap of standing,
not of trace: SCH1 traced through 02, but §4 assigned
the registry entry format no entry of its own — §4.2
(the writers) and §4.7 (the catalog) flanked it. The
owner ruled the format gets its own entry: plan §4.14 +
contract 14 (canonical owner: the pipeline scheduling
engine) now carry SCH1 whole, and 02's substrate section
is a pointer to 14. The count stays 36 of 36; no item's
status changed, only SCH1's home.

## §12 gap closure

§12's unhomed store — the scheduler file registry
(`registry/file-registry.yaml`) — is homed by the S0
amendment to plan §4.4 under contract 04 (seed/example
pattern; its check becomes a platform survival loop). The
plan's §12 ledger line is updated to match.

## Amendment 3 (2026-11-13, owner's ruling)

The migration field family — `migrated`, `migrated_at`,
`migration_note`, `proof_pending` — does not exist in
the target registry entry format or its semantics. The
evidence: all 26 live entries carry `migrated: true`
(the flag discriminates nothing); the machine writers
(the workbench progress renders, the runner liveness
renders) are born-admitted and stamp it unconditionally;
the pinned engine's firing condition is `status ==
active` AND migrated (`server/engine.py:199` at the
pin); and the catalog's drift diff already excludes
`migrated` / `migrated_at` / `source` as volatile. The
flag's one real function — admission gating for
hand-authored entries — is carried in the target by the
named replacement: the pipeline registry store has
exactly one mutation path (contract 02's writer path —
validate under §4.14's format, server-context proof for
hand-authored entries), an entry fires iff its status
is `active` and it stands in that store, and presence
through the path IS admission; there is no
directory-drop path for a flag to guard. Admission
evidence (validation counts, proof outcome) is recorded
as events in the dispatch/ledger store, not as fields
on the entry, and the workbench doctor's never-admitted
check (pinned: keyed on `migrated` being false) is
replaced by presence-in-store through the writer path
(contract 03). Amended: plan §2, §4.2, §4.13, §4.14, §5
(S4's byte-identical evidence qualified); contracts 02,
03, 07, 09, 13, 14. The `source` stamp is provenance,
not a migration field, and stays. The live scheduler is
untouched — the ruling binds the target at S3. The
count stays 36 of 36: SCH3 traces to contract 13's
amended firing clause, SCH1 to contract 14's amended
field table.

## Amendment 4 (2026-11-13, owner's ruling)

Contract 15 (unified state writer, plan §4.15) carries
no §2 preserve item of its own and changes none: SCH6's
`/ops` half still traces to contract 04, RUN1's atomic
write to contract 12, ATT1's store discipline to
contract 01. What amendment 4 unifies is the mechanism
behind those traced disciplines — the per-workhorse
write workarounds the write-denial flap forced (the
scheduler's `/ops` delegation, the workbench's
cross-repo file drops, the attention store's in-process
writer, the runner's record writers, per-app
atomic-write helpers) fold into the one pipeline
writer, whose operation set, atomicity protocol, and
failure semantics are contract 15's, generalizing
contract 02's one-mutation-path principle from the
registry store to all state. The re-pointings ride the
plan's steps (S3 base; S4, S5, S7 writers; §6 P4
closes the service over the set). The count stays 36
of 36.

## Review disagreements (plan governs)

- **Venue legacy reading:** the runner review (§7/§8)
  states legacy records "defaulted to Colab"; plan §10.3
  rules the S5 **stamp migration** — no read-time default
  exists. The contracts follow §10.3 (01, 03; S5 evidence).
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
  question as open; both were ruled after the review
  (§10.1 harden, §10.2 retire at S3) and are recorded as
  rulings, not disagreements.
