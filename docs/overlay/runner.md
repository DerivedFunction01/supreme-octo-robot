# Overlay inventory — colab-runner

The runner's live registries existed only on the
machine, as untracked live files seeded from tracked
examples — the seed/example pattern in its type-specimen
form. The capture held the six live configs; all six
ride the pattern into `pipeline/venue/config/`:

- `config/callers.json` — the caller registry (contract
  01's type specimen): thread callers with the `active`
  (detached-only) subset.
- `config/lease.json` — caps and session-gate policy.
- `config/repos.json` — the pointer-only target-repo
  registry.
- `config/notify-routes.json` — caller→chat routing for
  the session-liveness escalation.
- `config/denylist.txt` — personal literals for the
  portability guard; held as live config, never a
  tracked candidate.
- `config/transient.json` — the transient registry (file
  mirrors plus recreate entries); the registry of record
  is held, its mirrored contents are governed by the
  reference-only rule.

Negative instance verified: `config/profiles.json` does
not exist — retired by ruling; records are read only in
the shape and caller vocabulary they are written in.

**Credential — reference only, never copied.** The
auth-transient mirror (the OAuth token store, canonical
home in the user's config directory, mirrored under the
repo's state) is inventoried by reference only: no copy
taken, no hash recorded. Its capture and restore ride
the repo's own transient-mirror mechanism, never a blind
copy-back.

**Runtime state — counts only, never copied.**
Machine-local state, re-seeded deliberately at cutover:
the lease records and their deadline-evidence
projections, renewal and liveness transient files, the
run records, and the detached-job outputs (the store
attention's evaluator reads). The run-record census at
capture carried records outside the three ruled terminal
states and a few unparseable records — record hygiene
for the venue layer, recorded without opening the
records. The rest of the runtime state (bridge spools,
transfer parts, claims and gate journals, caches) is the
same class: not itemized, not carried.

**Out-of-repo registrations.** Two duties live in the
runtime's hook system, not in the repo: the reaper hook
(approval-gate evaluation, transient-mirror restore,
liveness reconciliation, then the network duties — reap,
auto-acquire, standing duty — on a fixed poll) and the
notify hook (announces the outbox events the panel
drains; on an approval-needed event it triggers exactly
one immediate reaper run). Both are registered and
enabled, delivering to the main chat. Registrations of
this class are re-homed explicitly at consolidation —
they are invisible to any tree capture.
