# Freeze runbook — the S11 cutover

The cutover is acts, not builds: every step below runs a
driver in this directory (or a named lane's driver),
carries its verification, and carries its rollback. The
freeze record (`freeze_record.example.json` is its
shape) is opened before step 1 and filled as the steps
land; `preflight.py --record <record>` must read green
before step 8 raises anything.

State at kit delivery: all ten drivers dry-run rehearsed
against scratch copies (manifest format:
`{driver: "pass"}`); the freeze inputs still owed are
named at the end, not worked around.

## Topology note (owner rulings, 2026-11-14)

- **One serving process.** The mega app serves through a
  single root entry (`run.py`, repo root): every pipeline
  CLI links in-process as a subcommand, and `serve`
  mounts all four backends on the one platform serving
  core in one process. Ports stay per-surface: 8796
  scheduling, 8792 workbench, 8797 attention, 8793 lease
  panel. The freeze raises **one** mega unit against
  stopping the originals' four services; keeper/watchdog
  re-pointing names the one unit. Unit templates
  collapsed 4 → 1 with the serving build: the one mega
  template stands at
  `pipeline/platform/ops/workhorse.service.tmpl`. The
  rollback's renders are the four installed unit files
  step 8 backs up before it installs anything; the
  originals keep their own templates in their frozen
  repos.
- **The push is a cutover step.** On the generic remake
  gate passing (full-history scan at zero hits + the
  composed gate green on the remade history), the remade
  history pushes to origin as closing act C3 — no
  separate permission. The Library artifact is
  republished from the remade tree first (C2): its
  embedded builds were synced from pre-cure trees at
  various points during the build, so the published
  surface must hash-match the remade tree before the
  push carries it.
- **Two successors.** One frontend handler and one
  backend handler, each succeeding all four originals in
  its layer; the `@workhorse` digest route re-points to
  them at C4. The four original threads retire at C5;
  the build thread archives last (C6).
- **Card-watch owns OI-1.** The mega card-watch owner
  holds permission-card watching from its build
  completion; no interim ownership begins.
- **OI-4.** The scheduler workhorse has no live owning
  thread: its freeze steps execute under main, which also
  verifies the mega scheduler's first full cadence
  window.

## Phase 0 — open the freeze

1. Pin the four originals' tips into the record (local
   == remote verified) and the final resync census: zero
   undispositioned divergence, or the freeze does not
   open.
2. Snapshot the original scheduler's `jobs/` dir aside
   (the assembly's provenance source; nothing the
   assembler strips is lost).
3. Copy `freeze_record.example.json` to the record's
   home, fill `freeze`, and run
   `preflight.py --record <record>`: every red line is a
   named input to clear, in order.

## The steps

### 1. Disarm the keepers
Act: disable the keeper hooks (scheduler keeper, lease
reaper, lease notify, workbench outbox watcher) so
nothing restarts what the freeze stops.
Verify: each hook reports disabled; no keeper fire for
one cadence.
Rollback: re-enable the hooks (they still point at the
originals until step 9).

### 2. Halt the fires
Act: stop the original scheduler server; confirm port
8796 closed. Hold a full 15-minute cadence window with
the ledger still — the quiesce the export reads.
Verify: port closed; ledger event count unchanged
across the window (`sched logs stats` twice).
Rollback: start the original server unit (render from
`render_units.py` if the installed unit was touched).

### 3. Drain
Act: read the connector bridge queue (must be 0) and
the lease state from the original panel; record both in
the record (`steps.3_drain`).
Verify: queue 0 recorded; the lease census is the number
step 6 must match.
Rollback: nothing has moved; resume normal operation.

### 4. Attention store cutover
Act: `migrate_attention.py --source <original state>
--target <mega state>`; the superapp programme
declaration's locations re-base to the mega repo in the
same act (`--refs-edit <programme>=<mega prefix>
--refs-from <each original prefix>`); its `rule_text`
prose is the attention thread's hand edit alongside.
Verify: the driver's census identical before/after on
every carried key (handlers, items, sends, armed rows,
programmes); the migrated store loads through the mega
`AttentionStateStore`.
Rollback: discard the migrated copy — the driver never
mutates the source.

### 5. Workbench store cutover
Act: `migrate_workrecord.py --source-store <original
store> --target-store <mega store>`.
Verify: registry DB SHA-256 equal after copy; export
entry counts equal; the harness `list` probe reads the
migrated DB; the programme's goal record reads back
intact through the mega harness.
Rollback: discard the migrated store (source untouched).

### 5b. Todo slug rename (the naming lane's driver)
Act: for **every project with armed todos** (5 armed
todos at the naming lane's census — 4 edgar-sec, 1
steampowernj; the freeze recounts from the live set),
run the lane's freeze-act form from the mega workrecord
package, dry-run first to capture the manifest, then
applied: `cd pipeline/workrecord && .venv/bin/python
-m lib.writes.todo_rename --root <project-root> [--apply]`
(the same driver as `wb --root <project> todo
migrate-names`). Per project it renames each legacy-id
todo to its title-derived slug, stores `legacy_id:` on
the record (data only, never a lookup path), rewrites
corpus mentions, and re-syncs derived state — the
scheduler entry and the attention armed row are deleted
under the old name and re-created under the slug by the
writers' own sync functions. It runs **after** steps
4–5 (the sync writes into the migrated mega stores) and
**before** step 7 (the assembly reads the re-synced
live entries). History is not rewritten: the attention
store's historical legacy mentions stay as written and
join through `legacy_id` (their disposition rode step
4).
**Named disposition — the invalid armed record.** The
live armed steampowernj todo (bundle
`2026-11-12-steampowernj-programme`; legacy id
`t-01M7860FNPKG0BN2RW0SCB9RWZ`, the armed entry
`wb-progress-steampowernj-t-01m7860fnpkg0bn2rw0scb9rwz`)
is **invalid today: its record is missing `created`** —
pre-existing, untouched by the rename build (the lane's
rehearsal: invalid 1 → 1, renamed cleanly, since the
rename rewrites only the id lines). It is the first
record that project's pass meets, so it is dispositioned
here, in advance, not discovered mid-freeze. The
project's dry-run manifest surfaces it; the freeze act
then takes exactly one of the two recorded paths:
(a) **repair before renaming** — restore `created` from
the record's own evidence (the todo file's timestamps,
its progress-checkpoint stamps), recording the value and
its evidence in the freeze record, then rename with the
project; or (b) **exclude by name** — the record is
named in `steps.5b_todo_rename.dispositions` as
excluded from repair at the freeze, it renames as-is
(proven safe), and the `created` repair becomes a
post-cutover act owned by the successor backend handler
(C4), recorded in the same disposition entry.
Verify: per-project report shows unresolved empty or
dispositioned; the driver's `unresolved_references` are
each dispositioned in the record (cross-project and
historical mentions are left untouched by design; a live
one blocks step 7); the disposition above is recorded
with its path taken; corpus scan finds legacy tokens
only on `legacy_id:` lines plus the named foreign set;
`wb progress-check <name>` succeeds for every previously
armed todo and the armed feed joins with zero skipped
rows; `verify_todo_slugs.py --jobs-dir <live set>
--attention-state <mega state> --workrecord-store
<mega store>` reads zero legacy-only references.
Rollback: snapshot each project's `.plans` tree plus
the scheduler jobs dir and the armed dir (tarball)
immediately before its `--apply`; rollback is
restore-from-snapshot (the sanctioned path — a scripted
reverse rename through `legacy_id` is possible but
secondary). The pass is idempotent: a partial failure
re-runs safely once its cause is fixed.

### 6. Venue state cutover (§10.3 binding stamp)
Act: `migrate_venue.py --source-home <original venue
home> --target-home <mega venue home>`: copies `var/`,
run records, and the live configs (callers, lease,
repos, notify-routes, transient, denylist), then the
binding stamp runs on the target copy.
Verify: the driver's own checks — pre-census projection
== post-stamp census per family, quarantine and
unreadable lists agree, config hashes equal, a second
dry census finds nothing unstamped — and the lease
census matches step 3's read.
Rollback: discard the target home (source untouched;
the stamp is re-runnable by design).

### 7. Scheduler state cutover (under main — OI-4)
Four acts, in order:
1. **Ledger**: `export_ledger.py --source-home
   <original> --target-home <mega> --work-dir <scratch>`
   — export at the step-2 quiesce, SHA-256 + count,
   import into the proven-empty mega store, verify,
   re-export hash-equal; the bridge state and outbox
   carry with per-file hashes.
2. **Registry**: `assemble_registry.py --live-jobs
   <live set> --mega-jobs <mega set> --out-dir
   <assembled> --mega-bodies <mega bodies>
   --strip-provenance --validate-home <mega scheduling
   home>`. The flag drops the past-migration provenance
   keys the mega schema refuses (reported per entry;
   the step-0 snapshot preserves the values). Output
   dispositions: the DECISION entries (the two
   per-service healthchecks) flip as one — the serving
   build's ladder
   (`pipeline/platform/ops/healthcheck.py` +
   `watchdog.sh`, verified against its fixture boot)
   covers the one unit, so both are replaced by the one
   `workhorse-healthcheck` entry at this assembly
   (s11-serve-shells-report.md); REMINT liveness entries re-mint per
   session live at the freeze. Entry-referenced files
   that live only in the original scheduler home —
   driver scripts under its ops/, bodies — are
   provisioned by the assembly itself: copied from the
   live home into the mega scheduling home as untracked
   instance data (never tracked content) and recorded
   per file in the assembly report's `provisioned`
   list. A referenced file missing in both homes is not
   provisioned: a body stays BODY-MISSING, and an argv
   target fails the assembly's verification. The mega-only
   card-watch entry arms here by its own plan.
   Verify: `sched validate` reads the full assembled
   count valid, 0 invalid; zero unre-pointed pointers;
   every anchored argv target in the assembled registry
   exists — the assembler checks it inline and fails on
   any miss, and `verify_argv_targets.py --jobs-dir
   <assembled> --mega-root <mega> --ws <ws>` is the
   standalone form (preflight runs it with
   --assembled-jobs/--assembled-ws).
3. **Live config (OI-2 residue)**: `provision_config.py
   --sched-home <mega scheduling home> --values
   <carried owners/drain values>` — provisions from the
   example where absent, merges the carried values,
   validates through the home's own loader.
4. **Tokens (OI-2 residue)**: `mint_tokens.py` in its
   two phases. Phase 1, server down: the acting caller's
   token mints first (the tokenless-acting-caller
   fallback is a direct staged write of the live config
   — bootstrap only; a refusal *with* a token never
   falls back). Phase 2: start the mega server
   standalone on the assembled registry — this start
   doubles as the state-carry smoke: its health must
   read status ok **and** `registry_count` equal to the
   assembled count (a degraded 200 with an empty
   registry is a failed carry — in rehearsal a
   wrong-shaped carried outbox produced exactly that);
   then mint the remaining callers and run the
   authenticated round-trips (exec probe, write-state
   probe). Stop the standalone server before step 8.
Verify: ledger counts + hash in the record; assembly
report clean; per-caller round-trips recorded; no token
material in any driver output (tokens land in client
homes at 0600).
Rollback: discard the mega store, assembled registry,
live config, and minted tokens; the originals never
moved.

### 8. Raise the one mega unit
Act: back up the four installed original unit files;
render the mega unit from the one template
(`pipeline/platform/ops/workhorse.service.tmpl`, via
`render_units.py`), install it, stop the originals'
four services, start the one unit.
Verify: `verify_endpoints.py --expect-status ok` over
the four surfaces (8796 health, 8792, 8797, 8793) —
status ok, not merely 200 — plus `registry_count` ==
the assembled count on the scheduler health, plus one
fire per registry class (scripted, body, self) observed
in the mega ledger.
Rollback: stop the mega unit, restore the four backed-up
unit files, start the originals' services. The switch
is reversible until step 11 releases it.

### 9. Re-arm the keepers
Act: re-point the keeper hooks at the mega homes and
the one unit; dry-run each; enable one at a time.
Verify: each keeper's first fire lands against the mega
side and is journaled under its caller.
Rollback: re-point back to the originals (step 8's
rollback state).

### 10. Threads switch
Act: each original thread flips to the mega homes and
proves it with its own verification act (its surface
answering from the mega store); the gap-closure sweep's
body is edited to mega discovery. Any thread still
invoking an original path is undispositioned divergence
and is named in the record.
Verify: per-thread evidence lines in the record.
Rollback: a thread flips back to the original paths;
the originals are still frozen and runnable.

### 11. Reversibility hold
Act: the originals stay frozen at their pinned tips,
units re-renderable from the tree's templates, until
post-cutover verification passes (one full cadence
window under main for the scheduler — OI-4 — plus each
thread's verification). Then the record's `rollback`
section is stamped released.
Rollback: any failure before release runs the step
rollbacks in reverse order; the originals never stopped
being runnable.

## Closing acts

- **C1.** The generic remake gate result is recorded
  (`record.remake`: remade head, scan hits 0, composed
  gate green). Basis: the genericity cures (688a553) and
  the gate legs (947ba24) brought the tracked tree to
  zero CURE-class hits, proven three ways
  (genericity-census-report.md). The binding form is the
  every-object scan of the remade history itself,
  recorded here — the tree census is the basis, not the
  proof.
- **C2.** Republish the Library shell artifact from the
  remade tree: re-embed from the cured, remade dist and
  verify the published artifact's dist hashes against
  the remade tree's (`record.published_surface`:
  republished_from == the remade head, hashes match,
  the verification output as proof). An artifact still
  carrying a pre-cure embedded build blocks C3.
- **C3.** Push the remade history to origin (authorized
  as a cutover step by the 2026-11-14 ruling). Record
  sha + time.
- **C4.** The two successors are named in the record —
  frontend handler, backend handler — the `@workhorse`
  digest route re-points to them, and one test item per
  successor proves the route.
- **C5.** The four original threads retire.
- **C6.** The build thread archives last; its purpose is
  complete.

## Freeze inputs still owed (named, not worked around)

1. **The serving build — landed** (committed bdd9969).
   `run.py` + `pipeline/platform/serving.py` are in the
   tree with the one unit template (step 8 renders it),
   the watchdog ladder (step 7's flip basis), and the
   attention store-path binding implemented in the
   serving core (an unbound store path refuses startup
   before any listener binds; the unit template carries
   the binding as `@ATTENTION_DATA@`). Its boot proof —
   one process answering all four surfaces on their
   ports against fixture state, the tick advancing
   through route faults elsewhere — is recorded in
   s11-serve-shells-report.md; the freeze attests it in
   `record.serving`, which the preflight enforces.
2. **The naming lane's report — landed** (committed
   8cfa422). Step 5b is reconciled to its freeze-act
   shape: the `lib.writes.todo_rename` command form, the
   per-project snapshot rollback, and the named
   disposition for the invalid armed record it flagged
   (missing `created`, carried in step 5b itself). At
   the freeze, each project's dry-run manifest is the
   proof the driver and CLI are whole on the day.
3. **Entry-referenced files in the original scheduler
   home — mechanized, no manual port owed.** Files an
   assembled entry references under the scheduler home
   (driver scripts, bodies) that exist only in the
   original's home are provisioned by the assembly
   itself at step 7 (act 2), recorded per file in its
   report; the assembly's argv-target verification
   fails loudly on any reference missing in both homes.
4. **Provenance-strip disposition.** Every live registry
   entry carries past-migration provenance keys the mega
   schema refuses; assembly strips them under
   `--strip-provenance` with the step-0 snapshot as the
   preservation. The freeze record carries the
   disposition.
5. **The degraded-carry check.** Step 7 phase 2's smoke
   (health status ok + assembled registry_count) is a
   hard gate, from the rehearsal observation that a
   wrong-shaped carried state file degrades the raised
   server to a 200 with a non-ok status and an empty
   registry.
