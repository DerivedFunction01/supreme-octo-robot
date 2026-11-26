"""The attention fold: dispatch
retired, supervision folded to wb + gap-closure.

Pins:
- a new send is born settled retired — never claimable,
  never enqueueable;
- the backfill migration settles the standing ledger
  the same way, removes frozen legacy handler_status
  entries, retires handlers bound to dead chats, settles
  wb-shadow items, and applies the edgar-greenfield
  venue declaration — idempotently;
- the Meta Power Plan zombie shape: picked + done, still
  BLOCKED-OWNER with a past due_at — after the action
  (and after the migration) glance's decision_count
  excludes it, because the action clears the item's
  presentation in the same write;
- repeat taps dedupe: identical owner actions (same
  item, verb, note) inside 60 s record one owner_action;
- a verdict for a retired handler is recorded on the
  `main` handler (the fallback), never on the dead chat.

Fixture state only: the store seam's empty state plus
synthetic records — never a live store.
"""

import copy
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import attstore, store as store_mod  # noqa: E402
from attention.services.dispatch import dispatch  # noqa: E402
from attention.services.reads import model  # noqa: E402
from attention.services.waits import actions, engine  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
SETTINGS = Settings(data_path=None)


def _meta_power_item(**overrides):
    item = {
        "id": "main:meta-power-plan",
        "handle": "main",
        "kind": "decision",
        "title": "Meta Power Plan — keep or cancel",
        "status_code": "BLOCKED-OWNER",
        "source_ref": "meta-power-plan",
        "source_url": "",
        "clears_at_source": True,
        "due_at": NOW - timedelta(days=1),
        "waiting_since": NOW - timedelta(days=14),
        "need": "owner_actionable",
        "tier": "digest",
        "triage": "open",
        "snooze_return_at": None,
        "snooze_on_activity": False,
        "resume_note": None,
        "provenance": "commission",
        "options": [
            {"id": "keep", "label": "Keep the plan"},
            {"id": "cancel", "label": "Cancel the plan"},
        ],
        "wait_id": None,
    }
    item.update(overrides)
    return item


def _state(*items):
    state = store_mod.empty_state()
    state["handlers"].append(
        {"handle": "main", "label": "main", "thread_id": "thread-main"}
    )
    state["items"].extend(items)
    return state


def _decision_count(state, now=NOW):
    return model.build_glance(state, SETTINGS, now, {})["decision_count"]


class BornRetiredTests(unittest.TestCase):
    def test_record_send_is_born_settled_retired(self):
        state = _state()
        send = engine.record_send(
            state, "verdict", "main", {"summary": "x", "verb": "Done", "note": ""},
            NOW, rule_id="owner:done",
        )
        self.assertIsNotNone(send)
        self.assertEqual(send["outcome"], "retired")
        record = send["dispatch"]
        self.assertEqual(record["suppressed_reason"], engine.DISPATCH_RETIRED_REASON)
        self.assertIsNotNone(record["suppressed_at"])
        self.assertEqual(dispatch.state_of(send, NOW), "not_dispatchable")
        self.assertEqual(dispatch.undispatched(state, NOW), [])


class ZombieActionTests(unittest.TestCase):
    def test_pick_clears_the_presentation(self):
        state = _state(_meta_power_item())
        self.assertEqual(_decision_count(state), 1)
        item = actions.apply_item_action(
            state, SETTINGS, "main:meta-power-plan",
            {"verb": "pick", "option_id": "keep"}, NOW,
        )
        self.assertEqual(item["triage"], "done")
        self.assertIsNone(item["status_code"])
        self.assertIsNone(item["due_at"])
        self.assertEqual(_decision_count(state), 0)

    def test_repeat_done_taps_record_one_action(self):
        state = _state(_meta_power_item())
        actions.apply_item_action(
            state, SETTINGS, "main:meta-power-plan",
            {"verb": "pick", "option_id": "keep"}, NOW,
        )
        before = len(state["owner_actions"])
        sends_before = len(state["sends"])
        for seconds in (5, 10, 20):
            actions.apply_item_action(
                state, SETTINGS, "main:meta-power-plan",
                {"verb": "done"}, NOW + timedelta(seconds=seconds),
            )
        self.assertEqual(len(state["owner_actions"]), before + 1)
        self.assertEqual(len(state["sends"]), sends_before)
        # A genuinely later tap is a new act again.
        actions.apply_item_action(
            state, SETTINGS, "main:meta-power-plan",
            {"verb": "done"}, NOW + timedelta(seconds=300),
        )
        self.assertEqual(len(state["owner_actions"]), before + 2)


class MigrationTests(unittest.TestCase):
    def _zombie_state(self):
        item = _meta_power_item(
            triage="done",
            decision={
                "verb": "pick",
                "at": NOW - timedelta(days=13),
                "option_id": "keep",
                "option_ids": ["keep"],
                "note": "",
                "send_id": "s0001",
            },
        )
        state = _state(item)
        state["sends"].append(
            {
                "id": "s0001",
                "at": NOW - timedelta(days=13),
                "rule_id": "owner:pick",
                "wait_id": None,
                "handle": "main",
                "target": "thread-main",
                "template": "verdict",
                "version": 1,
                "attempt": 1,
                "presence": "active",
                "text": "verdict",
                "fact_hash": None,
                "mode": "active",
                "outcome": "recorded",
                "dispatch": {
                    "consumer": "attention-service",
                    "claimed_at": NOW - timedelta(days=13),
                    "claim_expires_at": NOW - timedelta(days=13),
                    "delivered_at": None,
                    "delivery_ref": None,
                    "attempts": 6,
                    "bridge_request_id": "req-1",
                    "envelope_id": "attn-s0001-a6",
                    "suppressed_at": None,
                    "suppressed_reason": None,
                },
            }
        )
        state["dispatch_failures"].append(
            {"send_id": "s0001", "consumer": "attention-service",
             "reason": "Delivery attempts exhausted", "at": NOW - timedelta(days=2)}
        )
        return state

    def test_migration_settles_the_zombie(self):
        state = self._zombie_state()
        # The zombie as it stood: decided, failed
        # fulfillment, back in the owner's count.
        self.assertEqual(_decision_count(state), 1)
        attstore.backfill(state)
        item = state["items"][0]
        self.assertIsNone(item["status_code"])
        self.assertIsNone(item["due_at"])
        send = state["sends"][0]
        self.assertEqual(send["outcome"], "retired")
        self.assertIsNone(send["dispatch"]["claimed_at"])
        self.assertIsNone(send["dispatch"]["bridge_request_id"])
        self.assertEqual(
            send["dispatch"]["suppressed_reason"], engine.DISPATCH_RETIRED_REASON
        )
        self.assertEqual(dispatch.undispatched(state, NOW), [])
        self.assertEqual(_decision_count(state), 0)

    def test_migration_is_idempotent(self):
        state = self._zombie_state()
        attstore.backfill(state)
        once = copy.deepcopy(state)
        attstore.backfill(state)
        self.assertEqual(state, once)

    def test_delivered_history_untouched(self):
        state = self._zombie_state()
        delivered = copy.deepcopy(state["sends"][0])
        delivered["id"] = "s0002"
        delivered["dispatch"]["delivered_at"] = NOW - timedelta(days=3)
        delivered["dispatch"]["suppressed_at"] = None
        state["sends"].append(delivered)
        attstore.backfill(state)
        kept = next(s for s in state["sends"] if s["id"] == "s0002")
        self.assertEqual(kept["outcome"], "recorded")
        self.assertIsNotNone(kept["dispatch"]["delivered_at"])
        self.assertIsNone(kept["dispatch"]["suppressed_at"])

    def test_registry_and_shadow_legs(self):
        state = _state()
        state["handlers"].append(
            {"handle": "venue-lane", "label": "venue lane",
             "thread_id": "specimen-thread"}
        )
        state["handler_freshness"] = {
            "venue-lane": {"handle": "venue-lane",
                           "verdict": "retired-with-cause",
                           "binding_state": "deleted",
                           "cause": "lane-dissolved"},
        }
        state["handler_status"] = {
            "@checker": {"status_code": "REVIEW", "summary": "frozen", "at": NOW},
            "main": {"status_code": "WORKING", "summary": "live", "at": NOW},
        }
        shadow = _meta_power_item(
            id="@workhorse:ping:p1", handle="@workhorse",
            source_ref="ping:p1", provenance="offer",
        )
        genuine = _meta_power_item()
        state["items"].extend([shadow, genuine])
        state["programmes"] = [
            {"slug": "edgar-greenfield", "venue": "colab", "handles": ["@xbrl"]}
        ]
        attstore.backfill(state)
        lane = next(h for h in state["handlers"] if h["handle"] == "venue-lane")
        self.assertTrue(lane["retired"])
        self.assertNotIn("@checker", state["handler_status"])
        self.assertIn("main", state["handler_status"])
        settled = next(i for i in state["items"] if i["id"] == "@workhorse:ping:p1")
        self.assertEqual(settled["triage"], "done")
        self.assertIn("record of truth", settled["settled_reason"])
        self.assertEqual(genuine["triage"], "open")
        self.assertEqual(genuine["status_code"], "BLOCKED-OWNER")
        self.assertEqual(state["programmes"][0]["venue"], "local")


class TerminalSendFulfillmentTests(unittest.TestCase):
    def test_pre_retirement_suppressed_send_never_stalls(self):
        # The live Meta Power Plan shape: decided 13 days
        # ago; its send was suppressed before the fold
        # (outcome recorded, dispatch failures on file).
        # The decision stands as recorded — it must not
        # re-enter the queue as stalled, however old it is.
        decided_at = NOW - timedelta(days=13)
        item = _meta_power_item(
            triage="done",
            status_code=None,
            due_at=None,
            decision={
                "verb": "pick",
                "at": decided_at,
                "option_id": "keep",
                "note": "",
                "send_id": "s0001",
            },
        )
        state = _state(item)
        state["sends"].append(
            {
                "id": "s0001",
                "handle": "main",
                "mode": "live",
                "outcome": "recorded",
                "dispatch": {
                    "consumer": None,
                    "claimed_at": None,
                    "claim_expires_at": None,
                    "delivered_at": None,
                    "delivery_ref": None,
                    "attempts": 164,
                    "suppressed_at": NOW - timedelta(hours=12),
                    "suppressed_reason": "attempts exhausted",
                },
            }
        )
        state["dispatch_failures"].append(
            {"send_id": "s0001", "at": NOW - timedelta(hours=12), "error": "x"}
        )
        from attention.services.waits import fulfillment

        view = fulfillment.derive(item, state, NOW, SETTINGS)
        self.assertEqual(view["state"], "recorded")
        self.assertEqual(fulfillment.returned_items(state, NOW, SETTINGS), [])
        self.assertEqual(_decision_count(state), 0)


class MainFallbackTests(unittest.TestCase):
    def test_verdict_for_retired_handler_lands_on_main(self):
        state = _state()
        state["handlers"].append(
            {"handle": "@dead", "label": "Dead lane", "thread_id": "thread-dead",
             "retired": True}
        )
        item = _meta_power_item(id="@dead:d1", handle="@dead", source_ref="d1")
        state["items"].append(item)
        actions.apply_item_action(
            state, SETTINGS, "@dead:d1", {"verb": "pick", "option_id": "keep"}, NOW
        )
        send = state["sends"][-1]
        self.assertEqual(send["handle"], "main")
        self.assertEqual(send["target"], "thread-main")


if __name__ == "__main__":
    unittest.main()
