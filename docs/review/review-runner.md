# Runner review — colab-runner, for the superapp consolidation

Findings first:

- **The adapter seam already exists in fact.** Nearly
  every lease-core function takes the channel as its
  first parameter, and the one callable behind it is the
  CLI funnel in `sync/cli.py`. Extraction is a dispatch
  change at the funnel, not a refactor of the core.
- **The venue-keyed defect is total.** No lease record,
  run record, panel portion, or funnel rule carries a
  venue field; session identity is a bare Colab session
  name that a second venue's names could collide with.
  Anything that cannot name its venue is a defect against
  the coexistence constraint — at review, that is
  everything. The consolidation stamps the venue key from
  the first extracted write (plan §6).
- **The caller registry is the type specimen of the
  local cross-cutting contract**: an untracked live file
  seeded from a tracked example, machinery callers as
  code constants, validated at every wrapper seam. The
  same seed/example pattern repeats for four more configs
  (lease, repos, notify-routes, denylist).
- **The panel is already an app in the pipeline/app
  sense**: it shells out to the lease CLI for every read
  and write and renders only the core's served portions —
  the four workhorses' cleanest existing split.
- **Two missing platform services touch this repo**: the
  gate funnel is a per-invocation gate, not an automatic
  gate runner; and there is no backup of the state stores
  (`var/` lease records, `results/runs/`) beyond the
  auth-transient mirror.

## Anatomy, as it bears on the consolidation

**Lease lifecycle and records.** The core is
`sync/lease/`: acquire (adopt-or-create), extend, adopt,
shorten, release, reap. A lease record is one JSON file
per session, written by staged-sibling + rename, carrying
the session, shape and its spec, rate, acquisition and
deadline stamps, jobs, and budget at acquire; a
deadline-evidence projection is refreshed on every save
so orphan derivation keeps an evidenced deadline if the
record is lost. Lifecycle rules that are contract, not
detail: a record is deleted only on a confirmed-absent
reading or a successful stop, never on an unreadable one;
adoption restores a record from evidence, never invents
one; the reaper duty (a runtime hook outside the repo)
enforces hard deadlines and reconciles orphans; acquire
launches a detached keepalive so a leased session never
sits truly idle.

**Run records.** One JSON per run — the runner's state
of record — carrying run id, job, caller, session, state.
Terminal states are exactly `complete | failed |
orphaned`; a terminal transition appends exactly one
`run-terminal` event to the outbox. Verbs: launch
detached, poll (one bounded reconcile), wait (local
record only, zero channel use), resume, sweep.

**Transport.** Chunked transfer over the channel with
per-part and whole-file SHA-256 verification, resumable.
Code sync is a snapshot bundle built on the origin
lineage, size and SHA-256 recorded before transfer and
verified after, applied by fetch + fast-forward-only
merge.

**Placement.** There is no session pin in the run/gate
funnel. Adoption sorts live records at the requested
shape: caller's own leases first, unattributed next,
non-degraded before degraded, latest deadline last —
latest-deadline adoption. A prefer-session pin names a
lease to adopt only; it cannot combine with create and
refuses on shape mismatch or a dead record. Synchronous
attaches are a separate claim system; callers marked
`active` in the registry are refused sync attaches
outright (detached-only).

**The gate funnel** resolves the caller claim exactly as
the run path does (flag over environment, validated
against the registry before anything starts), takes the
target repo from the repos registry, ships the tree by
snapshot bundle, and runs the repo's check remotely with
the probed worker count. The session shape gate is a
policy engine over the lease config: agent actors may
create High-RAM CPU sessions only; refusals and bypasses
are journaled and served in state.

**The panel** is a pure consumer: reads are the lease
core's served portions, writes are lease verbs, and
served-record shaping happens in the core, not the
panel. Panel starts are creations, never adoptions.

## The adapter seam

The venue-shaped parts are: the shape catalog (parsed
from the Colab CLI's help text — a format change degrades
the fleet to CPU shapes with a catalog error), session
names, CU rates, the stop/exec verb set, endpoint host
grammar (the shape class read out of Colab endpoint
hostnames), and the bridge — a hash-signed command queue
planted in a standing lease, the most Colab-shaped
subsystem in the repo. The venue-neutral core carries
over as-is: the record stores and their write discipline,
caller validation, gate policy, placement sort, budget
accounting structure, spend attribution, the run-record
machinery and its outbox event, transfer chunking and
hash verification, and every served shape. A second
adapter plugs in at the funnel: a per-venue dispatch
behind that callable, plus a per-venue shape catalog and
verb set, is the whole adapter surface; the lease core
does not change shape.

## Cross-cutting contracts designed locally

**The caller registry (type specimen).** Three homes,
three natures: the live registry (untracked, seeded by
hand from the example; thread caller ids plus the
`active` list), the tracked seed (same shape, fictional
callers), and machinery callers as code constants, so a
missing local registry never breaks the panel or the
duties. Semantics: flag over environment; a claim is
validated against machinery ∪ local file (a missing or
malformed file yields the machinery set alone —
fail-closed for thread claims, never a crash); one lane
suffix per claim, validated against its registered base;
a presented-but-unregistered claim is refused at claim
time; an absent claim leaves the call unattributed; the
`active` list is a standing owner marking (detached-only
work); attaches are journaled as the attribution
evidence.

The same seed/example pattern, four more times: lease
config (caps, session-gate policy), repos registry
(pointer-only; a repo's package spec lives in its own
init, never in the registry), notify-routes (caller→chat
routing for the liveness escalation), and the denylist
(personal literals for the portability guard, untracked
permanently). One negative instance: `config/profiles.json`
is retired by ruling and must not exist.

**Overlaps.** The lease core machine-writes scheduler
job entries — one liveness entry per live lease, deleted
in the same call that deletes the lease record; the lease
record, not the entry, is the record of truth. The runner
is also a client of the scheduler's harness connector (it
mints connector tokens through it). The workbench overlap
is registration-level: the harness tracks this repo's
plans and todos from the repo's own files. The attention
overlap is attribution-level from this side: attention's
thread is a registered caller, and attention reads runner
state through its own seams.

## Preserve exactly

Formats and semantics other systems already depend on:

- Lease record JSON shape, per-session file naming, the
  staged-sibling atomic write, and the deadline-evidence
  projection.
- Run record shape, the three terminal states, and the
  exactly-one `run-terminal` outbox event.
- Caller attribution semantics in full: flag over env,
  registry validation with machinery constants, lane
  suffixes, presented-but-unregistered refusal, absent =
  unattributed, `active` = detached-only, the claims
  journal.
- Placement: latest-deadline adoption, adoption-only
  pins, no pin in the run/gate funnel.
- Spend counted from the repo's own lease segments, never
  from account-balance deltas.
- Snapshot-bundle lineage: built on the origin lineage,
  size + SHA-256 recorded and verified, applied
  fast-forward-only.
- The seed/example config pattern itself: tracked
  fictional examples, untracked live files, gitignore
  entries that document why each live file is local.

**Stays in the original repo untouched:** the repo
itself — the generic core is extracted alongside it. The
Colab payload material stays with the Colab adapter by
nature: the snippets (keepalive, bridge agent,
provisioning, job harness kits), probes, and the repo's
own job manifests.

## Risks the consolidation carries

- **Legacy records lack the venue key.** The first
  venue-keyed writer must define how they read; a mixed
  fleet makes a wrong default expensive. (Ruled: stamped
  in a one-time migration — plan §9.)
- **Catalog fragility.** The shape catalog is parsed from
  CLI help text, and the core's shape vocabulary (gpu,
  tpu, high_mem, CU rates) is Colab-denominated — budget
  semantics across a mixed fleet remain venue-denominated
  until a second venue forces the question.
- **Duties outside the repo.** The reaper and notify
  hooks are registered with the runtime's hook system,
  and the liveness entries live in the scheduler's
  registry — external registrations whose re-homing a
  tree copy cannot see.
- **Untracked state is machine-local.** Any consolidation
  step that starts from the tracked tree alone silently
  loses the caller registry, the lease config, and the
  repos registry unless they are re-seeded deliberately
  (the overlay capture, `docs/overlay/`).
