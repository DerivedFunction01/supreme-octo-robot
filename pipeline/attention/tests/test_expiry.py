"""Expiry evaluation pins (the decision-staleness plan,
Step 3): the tick's evaluate_expiry pass prices every
pending/surfaced wait and every waiting item — basis
detectors first, the registry age cap as backstop —
and a stale record expires to record (expiry record
written, item off the waiting surface, wait decision
moved), with zero sends and no decision record.
Hard-stop records expire only on basis evidence, to
the blocked-unruled form; decided items are exempt
while their ruling stands. The digest assembly gains
the expired section; the served item view carries
stale_basis / expires_at / expired. Fixture stores,
injected now, fakes at the ports (a temp .plans root,
a stubbed push measurement) — no live store, no live
workspace, no wall clock beyond the one tick test,
whose fixture ages by days against a 72 h cap.
"""

import sys
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention import server as server_mod  # noqa: E402
from attention.domain import attention as dom  # noqa: E402
from attention.infra import store as store_mod  # noqa: E402
from attention.services.reads import digest as digest_mod  # noqa: E402
from attention.services.reads import model  # noqa: E402
from attention.services.waits import engine  # noqa: E402
from attention.services.writes import ingest  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
OPTIONS = [
    {"id": "opt-a", "label": "Route A"},
    {"id": "opt-b", "label": "Route B"},
]
RULED = (
    "settled_continue",
    "program_step",
    "defect_fix",
    "result_preserving",
    "followup_worktree",
    "stall_hold",
    "redrive",
    "ruling_propagation",
)


def _state():
    state = store_mod.empty_state()
    state["handlers"].append(
        {"handle": "@lane", "label": "Lane", "thread_id": "thread-lane"}
    )
    return state


def _settings(tmp, **overrides):
    values = {"data_path": None, "run_records_dir": Path(tmp) / "records"}
    values.update(overrides)
    return Settings(**values)


def _wait(state, wait_class, age, **payload):
    base = {"handle": "@lane", "wait_class": wait_class, "summary": "An ask"}
    base.update(payload)
    return ingest.post_wait(state, base, NOW - age)


def _item(state, kind, age, **payload):
    base = {
        "handle": "@lane",
        "source_ref": payload.pop("source_ref", f"ref-{kind}"),
        "kind": kind,
        "title": f"A {kind} ask",
    }
    if kind == "decision":
        base["options"] = OPTIONS
    base.update(payload)
    return ingest.upsert_item(state, base, NOW - age)


def _handler_done(state, at=NOW):
    """Seed the waits remainder's input directly: no new
    status posts arrive, so the historical record is
    written as a record."""
    state["handler_status"]["@lane"] = {
        "status_code": "DONE",
        "summary": "Done",
        "at": at,
        "provenance": "commission",
    }


def _handler_status(state, code, at=NOW):
    state["handler_status"]["@lane"] = {
        "status_code": code,
        "summary": "On it",
        "at": at,
        "provenance": "commission",
    }


class WaitAgeTests(unittest.TestCase):
    def test_each_ruled_class_expires_at_its_cap(self):
        for wait_class in RULED:
            with self.subTest(wait_class=wait_class):
                state = _state()
                wait = _wait(state, wait_class, timedelta(hours=49))
                events = engine.evaluate_expiry(state, NOW)
                self.assertEqual(wait["decision"], "expired")
                self.assertEqual(wait["expired"]["basis"], "age")
                self.assertFalse(wait["expired"]["blocked"])
                self.assertEqual(wait["expired"]["at"], NOW)
                self.assertEqual([e["id"] for e in events], [wait["id"]])

    def test_each_ruled_class_is_live_under_its_cap(self):
        for wait_class in RULED:
            with self.subTest(wait_class=wait_class):
                state = _state()
                wait = _wait(state, wait_class, timedelta(hours=47))
                self.assertEqual(engine.evaluate_expiry(state, NOW), [])
                self.assertEqual(wait["decision"], "pending")
                self.assertNotIn("expired", wait)


class WaitHardStopTests(unittest.TestCase):
    def test_hard_stop_never_age_expires(self):
        for wait_class in dom.HARD_STOP_CLASSES:
            with self.subTest(wait_class=wait_class):
                state = _state()
                wait = _wait(state, wait_class, timedelta(days=3650))
                self.assertEqual(engine.evaluate_expiry(state, NOW), [])
                self.assertEqual(wait["decision"], "pending")
                self.assertNotIn("expired", wait)

    def test_hard_stop_basis_expires_to_blocked_unruled(self):
        for wait_class in dom.HARD_STOP_CLASSES:
            with self.subTest(wait_class=wait_class):
                state = _state()
                _handler_done(state, at=NOW - timedelta(minutes=1))
                wait = _wait(state, wait_class, timedelta(minutes=30))
                events = engine.evaluate_expiry(state, NOW)
                self.assertEqual(wait["decision"], "expired_blocked")
                self.assertNotEqual(wait["decision"], "owner_approved")
                self.assertEqual(wait["expired"]["basis"], "basis")
                self.assertTrue(wait["expired"]["blocked"])
                self.assertEqual(len(events), 1)


class WaitBasisTests(unittest.TestCase):
    def test_young_wait_expires_on_handler_terminal(self):
        state = _state()
        _handler_done(state, at=NOW - timedelta(minutes=1))
        wait = _wait(state, "program_step", timedelta(minutes=10))
        engine.evaluate_expiry(state, NOW)
        self.assertEqual(wait["decision"], "expired")
        self.assertEqual(wait["expired"]["basis"], "basis")
        self.assertIn("terminal", wait["expired"]["evidence"])

    def test_handler_still_working_is_live(self):
        state = _state()
        _handler_status(state, "WORKING", NOW - timedelta(minutes=1))
        wait = _wait(
            state, "program_step", timedelta(minutes=10), status_code="WORKING"
        )
        self.assertEqual(engine.evaluate_expiry(state, NOW), [])
        self.assertEqual(wait["decision"], "pending")

    def test_handler_moved_past_the_ask_is_stale(self):
        state = _state()
        _handler_status(state, "REVIEW", NOW - timedelta(minutes=1))
        wait = _wait(
            state, "program_step", timedelta(minutes=10), status_code="WORKING"
        )
        engine.evaluate_expiry(state, NOW)
        self.assertEqual(wait["expired"]["basis"], "basis")
        self.assertIn("moved WORKING → REVIEW", wait["expired"]["evidence"])


class SurfacedPairTests(unittest.TestCase):
    def test_hard_stop_pair_expires_together_blocked(self):
        state = _state()
        wait = _wait(state, "login", timedelta(minutes=20))
        with tempfile.TemporaryDirectory() as tmp:
            engine.evaluate_waits(state, _settings(tmp), NOW)
        self.assertEqual(wait["decision"], "surfaced")
        item = next(i for i in state["items"] if i.get("wait_id") == wait["id"])
        _handler_done(state)
        engine.evaluate_expiry(state, NOW + timedelta(minutes=1))
        self.assertEqual(wait["decision"], "expired_blocked")
        self.assertEqual(item["triage"], "done")
        self.assertTrue(item["expired"]["blocked"])
        self.assertEqual(item["expired"]["basis"], "basis")
        self.assertNotIn("decision", item)

    def test_ruled_pair_age_expires_together(self):
        state = _state()
        wait = _wait(state, "program_step", timedelta(hours=49))
        # The engine's own surfacing act, driven directly:
        # the pair under test is the surfaced form.
        engine._surface_item(state, wait, NOW)
        wait["decision"] = "surfaced"
        item = next(i for i in state["items"] if i.get("wait_id") == wait["id"])
        events = engine.evaluate_expiry(state, NOW)
        self.assertEqual(wait["decision"], "expired")
        self.assertEqual(item["triage"], "done")
        self.assertEqual(item["expired"], wait["expired"])
        self.assertEqual(len(events), 1)  # one expiry, one event


class ItemAgeTests(unittest.TestCase):
    def test_capped_kinds_expire_over_and_live_under(self):
        caps = {
            "decision": 72,
            "approval": 48,
            "push_needed": 24,
            "rule_proposal": 168,
            "followup": 168,
            "improvement": 168,
            "consolidation": 168,
            "performance": 168,
        }
        for kind, cap in caps.items():
            with self.subTest(kind=kind, side="over"):
                state = _state()
                item = _item(state, kind, timedelta(hours=cap + 1))
                engine.evaluate_expiry(state, NOW)
                self.assertEqual(item["triage"], "done")
                self.assertEqual(item["expired"]["basis"], "age")
                self.assertFalse(item["expired"]["blocked"])
            with self.subTest(kind=kind, side="under"):
                state = _state()
                item = _item(state, kind, timedelta(hours=cap - 1))
                self.assertEqual(engine.evaluate_expiry(state, NOW), [])
                self.assertEqual(item["triage"], "open")
                self.assertNotIn("expired", item)

    def test_uncapped_kinds_never_age_expire(self):
        for kind in ("action", "defect", "fyi"):
            with self.subTest(kind=kind):
                state = _state()
                item = _item(state, kind, timedelta(days=3650))
                self.assertEqual(engine.evaluate_expiry(state, NOW), [])
                self.assertEqual(item["triage"], "open")


class ItemBasisTests(unittest.TestCase):
    def test_answered_plan_sentinel_expires_young(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plan-x.md").write_text(
                "# Plan\n\n<!-- wb-question\nid=q1\nanswer=adopt the table\n-->\n",
                encoding="utf-8",
            )
            state = _state()
            item = _item(
                state, "decision", timedelta(hours=1), source_ref="plan-x.md#q1"
            )
            engine.evaluate_expiry(state, NOW, plans_root=root)
            self.assertEqual(item["triage"], "done")
            self.assertEqual(item["expired"]["basis"], "basis")
            self.assertIn("q1", item["expired"]["evidence"])

    def test_unanswered_plan_sentinel_is_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plan-x.md").write_text(
                "# Plan\n\n<!-- wb-question\nid=q1\n-->\n", encoding="utf-8"
            )
            state = _state()
            item = _item(
                state, "decision", timedelta(hours=1), source_ref="plan-x.md#q1"
            )
            self.assertEqual(engine.evaluate_expiry(state, NOW, plans_root=root), [])
            self.assertEqual(item["triage"], "open")

    def test_push_head_moved_expires_young(self):
        state = _state()
        item = _item(state, "push_needed", timedelta(hours=1))
        measured = {item["id"]: {"state": "superseded", "head": "abcdef123456"}}
        with mock.patch.object(
            engine.facts_mod, "derive_push_facts", return_value=measured
        ):
            engine.evaluate_expiry(state, NOW)
        self.assertEqual(item["expired"]["basis"], "basis")
        self.assertIn("head moved", item["expired"]["evidence"])

    def test_push_head_current_is_live_until_the_backstop(self):
        state = _state()
        item = _item(state, "push_needed", timedelta(hours=1))
        measured = {item["id"]: {"state": "current", "head": "abcdef123456"}}
        with mock.patch.object(
            engine.facts_mod, "derive_push_facts", return_value=measured
        ):
            self.assertEqual(engine.evaluate_expiry(state, NOW), [])
        self.assertEqual(item["triage"], "open")

    def test_handler_terminal_expires_a_young_item(self):
        state = _state()
        _handler_done(state, at=NOW - timedelta(minutes=1))
        item = _item(state, "decision", timedelta(minutes=30))
        engine.evaluate_expiry(state, NOW)
        self.assertEqual(item["expired"]["basis"], "basis")

    def test_poster_ref_source_is_not_a_fiction_expiry(self):
        # clears_at_source defaults on at post, but the
        # item's source lives outside this store: with no
        # source provider the detector cannot decide, so
        # a young item stands until its age cap.
        state = _state()
        item = _item(state, "decision", timedelta(hours=1))
        self.assertTrue(item["clears_at_source"])
        self.assertEqual(engine.evaluate_expiry(state, NOW), [])
        self.assertEqual(item["triage"], "open")


class HardStopItemTests(unittest.TestCase):
    def _hard_stop_item(self, state, age):
        item = _item(state, "approval", age)
        item["hard_stop"] = True
        return item

    def test_hard_stop_item_never_age_expires(self):
        state = _state()
        item = self._hard_stop_item(state, timedelta(days=3650))
        self.assertEqual(engine.evaluate_expiry(state, NOW), [])
        self.assertEqual(item["triage"], "open")

    def test_hard_stop_item_basis_expires_blocked(self):
        state = _state()
        _handler_done(state, at=NOW - timedelta(minutes=1))
        item = self._hard_stop_item(state, timedelta(minutes=30))
        engine.evaluate_expiry(state, NOW)
        self.assertEqual(item["triage"], "done")
        self.assertTrue(item["expired"]["blocked"])
        self.assertEqual(item["expired"]["basis"], "basis")


class ExemptionTests(unittest.TestCase):
    def _returned_item(self, state):
        """The worked example's shape: ruled 2026-11-13,
        fulfillment stalled — the ruling stands."""
        item = _item(state, "decision", timedelta(days=10))
        item["triage"] = "done"
        item["decision"] = {
            "verb": "pick",
            "at": NOW - timedelta(days=4),
            "option_id": "opt-a",
            "option_ids": ["opt-a"],
            "note": None,
            "send_id": "s0001",
        }
        state["sends"].append(
            {
                "id": "s0001",
                "at": NOW - timedelta(days=4),
                "rule_id": "owner:pick",
                "wait_id": None,
                "handle": "@lane",
                "target": "thread-lane",
                "template": "verdict",
                "version": 1,
                "attempt": 1,
                "presence": "active",
                "text": "verdict",
                "fact_hash": None,
                "mode": "active",
                "outcome": "recorded",
                "dispatch": {
                    "consumer": None,
                    "claimed_at": None,
                    "claim_expires_at": None,
                    "delivered_at": None,
                    "delivery_ref": None,
                    "attempts": 0,
                },
            }
        )
        state.setdefault("dispatch_failures", []).append(
            {"send_id": "s0001", "at": NOW - timedelta(days=4), "reason": "boom"}
        )
        return item

    def test_returned_decision_is_exempt(self):
        state = _state()
        item = self._returned_item(state)
        self.assertEqual(engine.evaluate_expiry(state, NOW), [])
        self.assertNotIn("expired", item)
        self.assertEqual(item["triage"], "done")
        self.assertEqual(item["decision"]["verb"], "pick")

    def test_reopened_decided_item_is_still_exempt(self):
        state = _state()
        item = self._returned_item(state)
        item["triage"] = "open"  # a fresh post re-raised it
        self.assertEqual(engine.evaluate_expiry(state, NOW), [])
        self.assertNotIn("expired", item)

    def test_decided_wait_is_untouched(self):
        state = _state()
        wait = _wait(state, "program_step", timedelta(days=10))
        wait["decision"] = "owner_approved"
        self.assertEqual(engine.evaluate_expiry(state, NOW), [])
        self.assertNotIn("expired", wait)


class NoDispatchTests(unittest.TestCase):
    def test_expiry_writes_no_send_and_no_decision_record(self):
        state = _state()
        _item(state, "decision", timedelta(days=5))
        _item(state, "approval", timedelta(days=5), source_ref="ref-appr-2")
        _wait(state, "program_step", timedelta(hours=49))
        _wait(state, "login", timedelta(days=3650))
        sends_before = len(state["sends"])
        log_before = len(state["action_log"])
        events = engine.evaluate_expiry(state, NOW)
        self.assertEqual(len(events), 3)
        self.assertEqual(len(state["sends"]), sends_before)
        self.assertEqual(len(state["action_log"]), log_before)
        for item in state["items"]:
            self.assertNotIn("decision", item)


class IdempotenceTests(unittest.TestCase):
    def test_second_tick_changes_nothing(self):
        state = _state()
        item = _item(state, "decision", timedelta(days=5))
        wait = _wait(state, "program_step", timedelta(hours=49))
        first = engine.evaluate_expiry(state, NOW)
        self.assertEqual(len(first), 2)
        stamp = item["expired"]["at"]
        second = engine.evaluate_expiry(state, NOW + timedelta(hours=6))
        self.assertEqual(second, [])
        self.assertEqual(item["expired"]["at"], stamp)
        self.assertEqual(wait["decided_at"], NOW)


class BasisFactsTests(unittest.TestCase):
    def test_unpopulated_ports_are_absent_not_invented(self):
        facts = engine.basis_facts(_state())
        self.assertNotIn("wait_facts", facts)
        self.assertNotIn("source_records", facts)
        self.assertIn("handler_status", facts)
        self.assertIn("terminal_codes", facts)
        self.assertIn("DONE", facts["terminal_codes"])
        self.assertIn("CLOSED", facts["terminal_codes"])


class DigestTests(unittest.TestCase):
    def test_expired_section_carries_one_note_per_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _state()
            _item(state, "decision", timedelta(days=5))
            live = _item(state, "decision", timedelta(hours=1), source_ref="ref-live")
            engine.evaluate_expiry(state, NOW)
            payload = digest_mod.build_digest(state, _settings(tmp), NOW)
            self.assertEqual(len(payload["expired"]), 1)
            note = payload["expired"][0]
            self.assertEqual(tuple(note), dom.EXPIRED_NOTE_FIELDS)
            self.assertEqual(note["stale_basis"], "age")
            self.assertFalse(note["blocked"])
            self.assertEqual(note["expired_at"], NOW.isoformat())
            self.assertNotIn(live["id"], [n["title"] for n in payload["expired"]])

    def test_blocked_note_for_the_hard_stop_form(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _state()
            _wait(state, "login", timedelta(minutes=20))
            engine.evaluate_waits(state, _settings(tmp), NOW)
            _handler_done(state)
            engine.evaluate_expiry(state, NOW + timedelta(minutes=1))
            payload = digest_mod.build_digest(
                state, _settings(tmp), NOW + timedelta(minutes=1)
            )
            self.assertEqual(len(payload["expired"]), 1)
            self.assertTrue(payload["expired"][0]["blocked"])
            self.assertEqual(payload["expired"][0]["stale_basis"], "basis")

    def test_no_expiries_empty_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = digest_mod.build_digest(_state(), _settings(tmp), NOW)
            self.assertEqual(payload["expired"], [])


class ModelTests(unittest.TestCase):
    def test_live_item_serves_cap_moment_and_no_basis(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _state()
            item = _item(state, "decision", timedelta(hours=70))
            view = model.item_view(item, state, NOW, _settings(tmp))
            self.assertEqual(
                view["expires_at"],
                (item["waiting_since"] + timedelta(hours=72)).isoformat(),
            )
            self.assertIsNone(view["stale_basis"])
            self.assertIsNone(view["expired"])

    def test_basis_stale_item_serves_its_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _state()
            _handler_done(state, at=NOW - timedelta(minutes=1))
            item = _item(state, "decision", timedelta(minutes=30))
            view = model.item_view(item, state, NOW, _settings(tmp))
            self.assertIn("terminal", view["stale_basis"])

    def test_expired_item_serves_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _state()
            item = _item(state, "decision", timedelta(days=5))
            engine.evaluate_expiry(state, NOW)
            view = model.item_view(item, state, NOW, _settings(tmp))
            self.assertEqual(view["expired"]["basis"], "age")
            self.assertEqual(view["expired"]["at"], NOW.isoformat())
            self.assertFalse(view["expired"]["blocked"])

    def test_hard_stop_item_serves_no_cap_moment(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _state()
            item = _item(state, "approval", timedelta(hours=1))
            item["hard_stop"] = True
            view = model.item_view(item, state, NOW, _settings(tmp))
            self.assertIsNone(view["expires_at"])


class TickTests(unittest.TestCase):
    def test_tick_pass_expires_and_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _state()
            real_now = datetime.now(UTC)
            item = ingest.upsert_item(
                state,
                {
                    "handle": "@lane",
                    "source_ref": "tick-decision",
                    "kind": "decision",
                    "title": "A tick ask",
                    "options": OPTIONS,
                },
                real_now - timedelta(days=5),
            )
            store = store_mod.MemoryStore(state)
            settings = _settings(
                tmp,
                bridge_url="http://127.0.0.1:1",
                bridge_timeout_s=0.2,
                armed_dir=Path(tmp) / "armed",
            )
            server_mod._tick_pass(store, settings, threading.Lock())
            saved = store.load_state()
            saved_item = next(i for i in saved["items"] if i["id"] == item["id"])
            self.assertEqual(saved_item["triage"], "done")
            self.assertEqual(saved_item["expired"]["basis"], "age")


if __name__ == "__main__":
    unittest.main()
