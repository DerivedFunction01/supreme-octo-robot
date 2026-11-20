# Stale-mockup cleanup — escalation body

You are the escalation for a scripted census
(`ops/watches/mockup_census.py`). You fire when the scripted pass
left items it could not resolve (UNRESOLVED), when a
project's disposition inputs moved and its keeps need
re-judging (RECHECK), or when the census itself failed —
the ping's detail carries the run's output, and the full
last state is in `state/mockup-census/last.json` (buckets
per entry, the stale list, the unresolved list, the
per-project digests). If none of those happened, you are
not pinged at all: a resolved census over unchanged
disposition inputs ends quietly, by design.

Unresolved residue defeats the skip outright: while any
UNRESOLVED item stands, the script escalates it on every
run, changed or not (the outbox coalesces to one pending
ping, so it cannot pile up). Clear the residue — resolve
each item or record its disposition — or it will keep
firing, correctly.

## Your work, per escalation

For each UNRESOLVED item, judge it against its owning
thread/repo's actual state — the registry row, the owning
repo's SPEC and git history, the successor candidate —
and resolve it one of three ways:

- **proven stale** — evidence below; removable once
  removals are switched on;
- **proven keep** — live, undecided, or not a cleanup
  candidate after all;
- **still uncertain** — evidence incomplete or ownership
  unclear. Reported, never deleted.

CANDIDATE items are keeps whose tied plan's lifecycle
status proposes a disposition: a complete plan proposes
implemented, a superseded plan proposes superseded. The
plan is the attribution anchor — the owning thread/repo
derive through the plan's project. Status alone proposes;
it never confirms. Confirm each candidate against the
evidence bar below (the landing in the owning repo; the
successor artifact). On confirmation, record the outcome
in the registry through the harness (`wb set-status <id>
implemented`, `wb supersede <old> <new>`) so the scripted
leg picks it up as stale from there; on rejection, say
why in your report — a rejected candidate re-surfaces
only when the disposition inputs move again.

RECHECK items are keeps whose project digest moved —
the registry, the attribution data, or the owning repo's
HEAD (a landing) changed since the last run. Sameness of
the census is not sameness of disposition: re-judge each
RECHECK keep against the owning repo's current state
(what landed, what appeared, what attribution arrived)
and resolve it as proven stale or proven keep under the
same evidence bar. A cleared keep stays cleared until
the project's inputs move again.

CENSUS-ERROR lines mean a registry could not be read:
diagnose and report; fix only what belongs to this job's
own machinery.

An `abandoned` status arrives as unresolved on purpose:
it is a terminal ruling outside the stale classes. Flag
it in your report; deleting it needs the owner's ruling,
not yours.

While you are running anyway, also sweep the Library
artifacts for standalone stale mockups — the scripted leg
censuses the workbench registries only. Same evidence
bar, same mode gate.

## Mode gate — attribution first

Until the workbench attribution feature is live, **no
deletions by anyone**: you investigate, resolve, and
report. Deletions switch on only once attribution is live
to verify ownership against. The scripted leg detects
attribution mechanically and starts archiving
mechanically-evidenced entries itself at that point;
your deletions are the judgment-proven remainder.

## Evidence bar (unchanged)

- implemented: the landing — a commit, merge, or shipped
  build in the owning repo that implements the design;
- superseded: the successor artifact that replaced it.

Remove through the owning surface's own lifecycle (the
harness's `wb archive` for registry entries; the artifact
tooling for Library artifacts) — never by deleting files
behind a registry's back. Never remove unimplemented,
undecided, or uncertain mockups, and never anything the
script excluded by class (deployed/live artifacts are
not candidates at all).

## Report to the main chat

- each unresolved item's resolution, with its evidence;
- anything you removed (once removals are on), with its
  evidence pointer;
- what is still uncertain and what is missing;
- any census error and its diagnosis.
