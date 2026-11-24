"""The reap surfacing vocabulary (sync/reap_vocabulary.py):
the reaper hook's decision section renders the reap pass's
top-level action through this classification, and every
designed action must render as designed — kept-unknown and
kept-absent-unconfirmed are read-health notes, not the
catch-all "unexpected action" alarm they used to wake as.

The mirror discipline: the vocabulary here is pinned to the
reaper's own _REAP_PRIORITY and the lease foundation's home
venue, so a reap action the surfacing layer has not
classified fails this suite until it is.
"""

import importlib
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

from unit_harness import lease  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rv = _load("reap_vocabulary", REPO_ROOT / "sync" / "reap_vocabulary.py")
foundation = importlib.import_module("lease.core.foundation")


def test_vocabulary_mirrors_the_reaper():
    assert set(rv.REAP_RECORD_ACTIONS) == set(lease._REAP_PRIORITY)
    assert set(rv.REAP_PASS_ACTIONS) == set(lease._REAP_PRIORITY) | {"none", "already-running"}
    assert rv.HOME_VENUE == foundation.VENUE


def test_every_designed_action_classifies():
    for action in rv.REAP_PASS_ACTIONS:
        assert rv.classify_reap_action(action, venue=rv.HOME_VENUE, unknown_streak=1) != "unexpected", action


def test_foreign_venue_kept_unknown_is_a_note_at_any_streak():
    for streak in (0, 1, 2, rv.UNKNOWN_ESCALATE_STREAK, 10):
        assert rv.classify_reap_action("kept-unknown", venue="local", unknown_streak=streak) == "note"


def test_home_venue_kept_unknown_is_a_note_before_the_bound():
    assert rv.classify_reap_action("kept-unknown", venue=rv.HOME_VENUE, unknown_streak=1) == "note"
    assert rv.classify_reap_action("kept-unknown", venue=None, unknown_streak=rv.UNKNOWN_ESCALATE_STREAK - 1) == "note"


def test_home_venue_kept_unknown_escalates_at_the_bound():
    assert rv.UNKNOWN_ESCALATE_STREAK == 3
    assert rv.classify_reap_action("kept-unknown", venue=rv.HOME_VENUE, unknown_streak=3) == "escalate"
    assert rv.classify_reap_action("kept-unknown", venue=None, unknown_streak=4) == "escalate"


def test_kept_absent_unconfirmed_is_a_note():
    assert rv.classify_reap_action("kept-absent-unconfirmed", venue=rv.HOME_VENUE, unknown_streak=1) == "note"
    assert rv.classify_reap_action("kept-absent-unconfirmed", venue="local", unknown_streak=9) == "note"


def test_unlisted_action_stays_unexpected():
    assert rv.classify_reap_action("frobnicate") == "unexpected"
    assert rv.classify_reap_action("") == "unexpected"
    assert rv.classify_reap_action(None) == "unexpected"


def test_known_actions_render_as_before():
    for action in ("released-deadline", "released-idle", "cleared-dead", "released-standing-expired"):
        assert rv.classify_reap_action(action) == "release", action
    assert rv.classify_reap_action("kept") == "ok"
    assert rv.classify_reap_action("none") == "ok"
    assert rv.classify_reap_action("already-running") == "ok"
    assert rv.classify_reap_action("renewed") == "note"
    assert rv.classify_reap_action("renewal-failed") == "note"


def test_unknown_streak_counts_consecutive_same_session():
    assert rv.next_unknown_streak(None, None, 0, "kept-unknown", "s1") == 1
    assert rv.next_unknown_streak("kept-unknown", "s1", 1, "kept-unknown", "s1") == 2
    assert rv.next_unknown_streak("kept-unknown", "s1", 2, "kept-unknown", "s1") == 3


def test_unknown_streak_resets_on_change():
    assert rv.next_unknown_streak("kept-unknown", "s1", 5, "kept-unknown", "s2") == 1
    assert rv.next_unknown_streak("kept", "s1", 0, "kept-unknown", "s1") == 1
    assert rv.next_unknown_streak("kept-unknown", "s1", 5, "kept", "s1") == 0
    assert rv.next_unknown_streak("kept-unknown", "s1", 5, "released-deadline", "s1") == 0
