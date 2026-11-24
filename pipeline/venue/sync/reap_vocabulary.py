"""The reap pass's action vocabulary, classified for the
surfacing layer (the reaper hook's decision section).

The reaper (sync/lease/lifecycle/reap.py) returns one top-level
action per pass: the most consequential per-record outcome, or
a pass-level word when no record was reaped. Every one of those
actions is a designed outcome, but the hook's decision section
knew only three of them as routine and three as wake-worthy;
the rest fell into its catch-all and woke as "unexpected
action" — kept-unknown (a sessions listing that exhausted its
read retries, or a foreign venue's record the home pass cannot
classify) alarmed exactly like a genuine anomaly.

This module is the surfacing layer's one home for the
vocabulary and its rendering. It mirrors the reaper's own
_REAP_PRIORITY set rather than importing it (the hook loads
this file by path, without the lease package); a specimen in
tests/test_lease_unit/test_reap_vocabulary.py pins the mirror
to _REAP_PRIORITY and to the lease foundation's home venue, so
a new reap action fails the gate until it is classified here.

Dispositions:
  release    — the reap released or cleared a lease: wake.
  ok         — routine steady state: silent.
  note       — a designed read-health outcome: log, silent.
  escalate   — a home-venue kept-unknown that has persisted
               across UNKNOWN_ESCALATE_STREAK consecutive
               passes for one session: wake.
  unexpected — outside the designed vocabulary: the hook's
               catch-all alarm, unchanged.
"""

from __future__ import annotations

# The home venue: a record whose venue is absent or equal to
# this is classified by the home pass's own session listing.
# Mirrors the lease foundation's VENUE (pinned by specimen).
HOME_VENUE = "colab"

# Per-record outcomes, in the reaper's own priority order
# (sync/lease/lifecycle/reap.py, _REAP_PRIORITY).
REAP_RECORD_ACTIONS = (
    "released-deadline",
    "cleared-dead",
    "released-standing-expired",
    "released-idle",
    "renewed",
    "renewal-failed",
    "kept-absent-unconfirmed",
    "kept-unknown",
    "kept",
)

# Pass-level words the pass returns beside the record outcomes:
# "none" (no lease records) and "already-running" (a concurrent
# pass holds the reap lock).
REAP_PASS_ACTIONS = REAP_RECORD_ACTIONS + ("none", "already-running")

# A legacy surfacing word the hook has always treated as
# routine; the reap never returns it, but the silent rendering
# predates the vocabulary and stands.
LEGACY_OK_ACTIONS = ("no-lease",)

RELEASE_ACTIONS = frozenset(
    ("released-deadline", "released-idle", "cleared-dead", "released-standing-expired")
)
OK_ACTIONS = frozenset(("none", "kept", "already-running") + LEGACY_OK_ACTIONS)
NOTE_ACTIONS = frozenset(("kept-absent-unconfirmed", "renewed", "renewal-failed"))

UNKNOWN_ACTION = "kept-unknown"

# A home-venue session unreadable this many consecutive passes
# stops being weather and becomes a finding: the listing's own
# retry budget already absorbs a single bad read, so a streak
# at the bound means the read path itself is down.
UNKNOWN_ESCALATE_STREAK = 3


def classify_reap_action(action: str | None, *, venue: str | None = None, unknown_streak: int = 0) -> str:
    """Classify one reap pass's top-level action for surfacing.

    venue is the top record's venue as its lease record carries
    it (None when the record names none, i.e. the home venue);
    unknown_streak is the count of consecutive passes, including
    this one, whose top action was kept-unknown for the same
    session (see next_unknown_streak)."""
    if action in RELEASE_ACTIONS:
        return "release"
    if action in OK_ACTIONS:
        return "ok"
    if action in NOTE_ACTIONS:
        return "note"
    if action == UNKNOWN_ACTION:
        # Liveness is per-venue: the home pass reads a foreign
        # venue's record unknown by design — that venue's own
        # liveness source classifies it — so the home pass's
        # kept-unknown for such a record is its standing answer
        # and never escalates from this pass.
        if venue is not None and venue != HOME_VENUE:
            return "note"
        return "escalate" if unknown_streak >= UNKNOWN_ESCALATE_STREAK else "note"
    return "unexpected"


def next_unknown_streak(
    prev_action: str | None,
    prev_session: str | None,
    prev_streak: int,
    action: str | None,
    session: str | None,
) -> int:
    """The consecutive-kept-unknown count after this pass: it
    extends only while the same session's top action stays
    kept-unknown, restarts at one on a new session or a return
    to kept-unknown, and is zero for any other action."""
    if action != UNKNOWN_ACTION:
        return 0
    if prev_action == UNKNOWN_ACTION and prev_session == session:
        return max(prev_streak, 0) + 1
    return 1
