"""Staleness contract pins (the decision-staleness plan,
Step 1): the registry seeds carry the adopted
stale_after_hours / on_stale pair, the pure stale_state
evaluation honours basis-over-age, the exact cap
boundary, the null cap, and the hard-stop floor; the
attstore backfill appends the pair without overwriting;
the wait-class registration validates it. Fixture state
only — in-memory stores, an injected now, no live store
or workspace reads.
"""

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.domain import attention as dom  # noqa: E402
from attention.errors import Validation  # noqa: E402
from attention.infra import attstore  # noqa: E402
from attention.services.writes import writes  # noqa: E402

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)

EXPECTED_WAIT_CLASSES = {
    "settled_continue": (48, "expire"),
    "program_step": (48, "expire"),
    "defect_fix": (48, "expire"),
    "result_preserving": (48, "expire"),
    "followup_worktree": (48, "expire"),
    "stall_hold": (48, "expire"),
    "redrive": (48, "expire"),
    "ruling_propagation": (48, "expire"),
    "execution_risk_flag": (48, "expire"),
    "unreported_stall": (48, "expire"),
    "permission_card": (None, "expire_blocked"),
    "scope_expansion": (None, "expire_blocked"),
    "login": (None, "expire_blocked"),
    "external_send": (None, "expire_blocked"),
    "purchase": (None, "expire_blocked"),
    "form_submit": (None, "expire_blocked"),
    "calendar_write": (None, "expire_blocked"),
    "schedule_change": (None, "expire_blocked"),
}

EXPECTED_ITEM_KINDS = {
    "decision": (72, "expire"),
    "action": (None, "expire"),
    "defect": (None, "expire"),
    "approval": (48, "expire"),
    "fyi": (None, "expire"),
    "rule_proposal": (168, "expire"),
    "followup": (168, "expire"),
    "improvement": (168, "expire"),
    "consolidation": (168, "expire"),
    "performance": (168, "expire"),
    "push_needed": (24, "expire"),
}


def record(age: timedelta, cap=72, hard_stop=False):
    return {
        "waiting_since": NOW - age,
        "stale_after_hours": cap,
        "hard_stop": hard_stop,
    }


class SeedShapeTests(unittest.TestCase):
    def test_wait_class_seeds_carry_the_adopted_pair(self):
        entries = {c["name"]: c for c in dom.default_wait_classes()}
        self.assertEqual(set(entries), set(EXPECTED_WAIT_CLASSES))
        for name, (cap, on_stale) in EXPECTED_WAIT_CLASSES.items():
            self.assertEqual(entries[name]["stale_after_hours"], cap, name)
            self.assertEqual(entries[name]["on_stale"], on_stale, name)
            self.assertIn(entries[name]["on_stale"], dom.ON_STALE_DISPOSITIONS)

    def test_item_kind_seeds_carry_the_adopted_pair(self):
        entries = {e["kind"]: e for e in dom.default_item_kinds()}
        self.assertEqual(set(entries), set(EXPECTED_ITEM_KINDS))
        for kind, (cap, on_stale) in EXPECTED_ITEM_KINDS.items():
            self.assertEqual(entries[kind]["stale_after_hours"], cap, kind)
            self.assertEqual(entries[kind]["on_stale"], on_stale, kind)

    def test_fixture_store_registries_carry_the_pair(self):
        state = attstore.empty_state()
        for entry in state["wait_classes"]:
            self.assertIn("stale_after_hours", entry)
            self.assertIn("on_stale", entry)
        for entry in state["item_kinds"]:
            self.assertIn("stale_after_hours", entry)
            self.assertIn("on_stale", entry)


class StaleStateTests(unittest.TestCase):
    def test_at_cap_is_stale_one_minute_under_is_live(self):
        at_cap = dom.stale_state(record(timedelta(hours=72)), NOW, None)
        self.assertEqual(at_cap["state"], dom.STALE_AGE)
        under = dom.stale_state(
            record(timedelta(hours=72) - timedelta(minutes=1)), NOW, None
        )
        self.assertEqual(under["state"], dom.STALE_LIVE)
        self.assertIsNone(under["evidence"])

    def test_basis_beats_age(self):
        basis = {"stale": True, "evidence": "handler posted DONE"}
        young = dom.stale_state(record(timedelta(minutes=5)), NOW, basis)
        self.assertEqual(young["state"], dom.STALE_BASIS)
        self.assertEqual(young["evidence"], "handler posted DONE")
        old = dom.stale_state(record(timedelta(days=30)), NOW, basis)
        self.assertEqual(old["state"], dom.STALE_BASIS)
        self.assertEqual(old["evidence"], "handler posted DONE")

    def test_basis_not_stale_falls_through_to_age(self):
        basis = {"stale": False, "evidence": None}
        old = dom.stale_state(record(timedelta(hours=73)), NOW, basis)
        self.assertEqual(old["state"], dom.STALE_AGE)
        young = dom.stale_state(record(timedelta(hours=1)), NOW, basis)
        self.assertEqual(young["state"], dom.STALE_LIVE)

    def test_null_cap_never_age_stale(self):
        ancient = dom.stale_state(record(timedelta(days=3650), cap=None), NOW, None)
        self.assertEqual(ancient["state"], dom.STALE_LIVE)

    def test_hard_stop_is_basis_only(self):
        ancient = dom.stale_state(
            record(timedelta(days=3650), cap=None, hard_stop=True), NOW, None
        )
        self.assertEqual(ancient["state"], dom.STALE_LIVE)
        # Even a (mis-seeded) cap on a hard-stop record cannot age-stale it.
        capped = dom.stale_state(
            record(timedelta(days=3650), cap=1, hard_stop=True), NOW, None
        )
        self.assertEqual(capped["state"], dom.STALE_LIVE)
        basis = {"stale": True, "evidence": "session state moved"}
        moved = dom.stale_state(
            record(timedelta(minutes=1), cap=None, hard_stop=True), NOW, basis
        )
        self.assertEqual(moved["state"], dom.STALE_BASIS)


class ExpiredNoteTests(unittest.TestCase):
    def test_note_shape_is_row_plus_expiry_fields(self):
        row = {
            "kind": "decision",
            "title": "Pick one",
            "handle": "main",
            "handler_label": "Main",
            "provenance": "offer",
            "provenance_label": "Offer",
            "at": "2026-11-12T15:21:00+00:00",
            "age_label": "5 days",
            "unrelated": "dropped",
        }
        expired = {
            "at": "2026-11-17T12:00:00+00:00",
            "basis": "age",
            "evidence": "age 120.0h at or over the 72h cap",
            "blocked": False,
        }
        note = dom.expired_note(row, expired)
        self.assertEqual(tuple(note), dom.EXPIRED_NOTE_FIELDS)
        self.assertEqual(note["expired_at"], expired["at"])
        self.assertEqual(note["stale_basis"], "age")
        self.assertEqual(note["evidence"], expired["evidence"])
        self.assertFalse(note["blocked"])


class BackfillTests(unittest.TestCase):
    def test_bare_entries_gain_seed_values(self):
        state = {
            "wait_classes": [{"name": "program_step", "hard_stop": False}],
            "item_kinds": [
                {
                    "kind": "decision",
                    "label": "Decision",
                    "status_kind": False,
                    "digest_owner": None,
                }
            ],
        }
        attstore.backfill(state)
        entry = state["wait_classes"][0]
        self.assertEqual(entry["stale_after_hours"], 48)
        self.assertEqual(entry["on_stale"], "expire")
        kind = state["item_kinds"][0]
        self.assertEqual(kind["stale_after_hours"], 72)
        self.assertEqual(kind["on_stale"], "expire")

    def test_owner_edited_values_survive(self):
        state = {
            "wait_classes": [
                {
                    "name": "program_step",
                    "hard_stop": False,
                    "stale_after_hours": 999,
                    "on_stale": "expire_blocked",
                }
            ],
            "item_kinds": [
                {
                    "kind": "decision",
                    "label": "Decision",
                    "status_kind": False,
                    "digest_owner": None,
                    "stale_after_hours": None,
                    "on_stale": "expire_blocked",
                }
            ],
        }
        attstore.backfill(state)
        entry = state["wait_classes"][0]
        self.assertEqual(entry["stale_after_hours"], 999)
        self.assertEqual(entry["on_stale"], "expire_blocked")
        kind = state["item_kinds"][0]
        self.assertIsNone(kind["stale_after_hours"])
        self.assertEqual(kind["on_stale"], "expire_blocked")

    def test_unseeded_entries_gain_floor_defaults(self):
        state = {
            "wait_classes": [
                {"name": "custom_class", "hard_stop": False},
                {"name": "custom_stop", "hard_stop": True},
            ],
            "item_kinds": [{"kind": "custom_kind", "label": "Custom"}],
        }
        attstore.backfill(state)
        plain, stop = state["wait_classes"]
        self.assertIsNone(plain["stale_after_hours"])
        self.assertEqual(plain["on_stale"], "expire")
        self.assertIsNone(stop["stale_after_hours"])
        self.assertEqual(stop["on_stale"], "expire_blocked")
        kind = state["item_kinds"][0]
        self.assertIsNone(kind["stale_after_hours"])
        self.assertEqual(kind["on_stale"], "expire")


class AddWaitClassTests(unittest.TestCase):
    def state(self):
        return {"wait_classes": dom.default_wait_classes()}

    def test_valid_pair_is_stored(self):
        state = self.state()
        entry = writes.add_wait_class(
            state,
            {"name": "novel_class", "stale_after_hours": 12.5, "on_stale": "expire"},
        )
        self.assertEqual(entry["stale_after_hours"], 12.5)
        self.assertEqual(entry["on_stale"], "expire")
        stored = next(c for c in state["wait_classes"] if c["name"] == "novel_class")
        self.assertEqual(stored["stale_after_hours"], 12.5)

    def test_absent_pair_defaults_to_no_cap_expire(self):
        entry = writes.add_wait_class(self.state(), {"name": "plain_class"})
        self.assertIsNone(entry["stale_after_hours"])
        self.assertEqual(entry["on_stale"], "expire")

    def test_null_cap_is_accepted(self):
        entry = writes.add_wait_class(
            self.state(),
            {"name": "uncapped", "stale_after_hours": None, "on_stale": "expire"},
        )
        self.assertIsNone(entry["stale_after_hours"])

    def test_unknown_on_stale_is_refused(self):
        with self.assertRaises(Validation) as caught:
            writes.add_wait_class(
                self.state(), {"name": "bad", "on_stale": "resurface"}
            )
        fields = {e["field"] for e in caught.exception.field_errors}
        self.assertIn("on_stale", fields)

    def test_non_positive_or_non_numeric_cap_is_refused(self):
        for bad in (0, -5, "72", True):
            with self.assertRaises(Validation, msg=repr(bad)):
                writes.add_wait_class(
                    self.state(), {"name": "bad", "stale_after_hours": bad}
                )


if __name__ == "__main__":
    unittest.main()
