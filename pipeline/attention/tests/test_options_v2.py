"""Options shape v2 pins (plan Step 4): the write path.

Ingest accepts {id, label, effect} options — effect
optional, defaulting to the verdict-send statement (the
label) — and an item-level mode (single | multi,
default single). apply_item_action validates picks by
mode: single takes exactly one known id (the pre-v2
behaviour, pinned here against legacy-shaped items),
multi takes a non-empty subset; the decision record
and the owner action carry option_ids beside the
legacy option_id (the pick when exactly one id is
picked, else None); one verdict send names every
picked label; rule_it under multi stores the picked
set on its shadow rule. The CLI round-trips the effect
segment and --mode. Fixture state only — the store
seam's empty state plus one handler, built in memory;
never a live store.
"""

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention import cli  # noqa: E402
from attention.errors import Validation  # noqa: E402
from attention.infra import store as store_mod  # noqa: E402
from attention.services.waits import actions  # noqa: E402
from attention.services.writes import ingest  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)

OPTIONS = [
    {"id": "opt-a", "label": "Route A", "effect": "Dispatch route A"},
    {"id": "opt-b", "label": "Route B", "effect": "Dispatch route B"},
    {"id": "opt-c", "label": "Route C", "effect": "Dispatch route C"},
]


def _state():
    state = store_mod.empty_state()
    state["handlers"].append(
        {"handle": "@lane", "label": "Lane", "thread_id": "thread-lane"}
    )
    return state


def _post(state, payload):
    base = {
        "handle": "@lane",
        "source_ref": "decision-1",
        "kind": "decision",
        "title": "Pick a route",
    }
    base.update(payload)
    return ingest.upsert_item(state, base, NOW)


def _act(state, payload, item_id="@lane:decision-1"):
    return actions.apply_item_action(
        state, Settings(data_path=None), item_id, payload, NOW
    )


class IngestOptionsV2Tests(unittest.TestCase):
    def test_effects_and_multi_mode_are_stored(self):
        item = _post(_state(), {"options": OPTIONS, "mode": "multi"})
        self.assertEqual(item["options"], OPTIONS)
        self.assertEqual(item["mode"], "multi")

    def test_legacy_post_defaults_effect_to_label_and_mode_to_single(self):
        item = _post(
            _state(),
            {
                "options": [
                    {"id": "opt-a", "label": "Route A"},
                    {"id": "opt-b", "label": "Route B"},
                ]
            },
        )
        self.assertEqual(
            item["options"],
            [
                {"id": "opt-a", "label": "Route A", "effect": "Route A"},
                {"id": "opt-b", "label": "Route B", "effect": "Route B"},
            ],
        )
        self.assertEqual(item["mode"], "single")

    def test_bad_mode_is_refused(self):
        with self.assertRaises(Validation) as ctx:
            _post(_state(), {"options": OPTIONS, "mode": "ranked"})
        fields = {e["field"] for e in ctx.exception.field_errors}
        self.assertIn("mode", fields)

    def test_non_string_effect_is_refused(self):
        bad = [{"id": "opt-a", "label": "Route A", "effect": 3}]
        with self.assertRaises(Validation) as ctx:
            _post(_state(), {"options": bad})
        fields = {e["field"] for e in ctx.exception.field_errors}
        self.assertIn("options", fields)

    def test_repost_without_mode_keeps_the_stored_mode(self):
        state = _state()
        _post(state, {"options": OPTIONS, "mode": "multi"})
        item = _post(state, {"options": OPTIONS})
        self.assertEqual(item["mode"], "multi")


class SinglePickTests(unittest.TestCase):
    """The pre-v2 behaviour on a legacy-shaped item:
    options without effect, no mode anywhere."""

    def _legacy_item(self, state):
        item = _post(
            state,
            {
                "options": [
                    {"id": "opt-a", "label": "Route A"},
                    {"id": "opt-b", "label": "Route B"},
                ]
            },
        )
        # The item as a pre-v2 post stored it: no mode key.
        del item["mode"]
        return item

    def test_single_pick_records_and_dispatches_as_before(self):
        state = _state()
        self._legacy_item(state)
        standing_rules = list(state["action_rules"])
        item = _act(state, {"verb": "pick", "option_id": "opt-b"})
        self.assertEqual(item["triage"], "done")
        decision = item["decision"]
        self.assertEqual(decision["verb"], "pick")
        self.assertEqual(decision["option_id"], "opt-b")
        self.assertEqual(decision["option_ids"], ["opt-b"])
        self.assertEqual(len(state["sends"]), 1)
        send = state["sends"][0]
        self.assertEqual(send["id"], decision["send_id"])
        self.assertEqual(send["rule_id"], "owner:pick")
        self.assertIn("Route B", send["text"])
        (entry,) = state["owner_actions"]
        self.assertEqual(entry["option_id"], "opt-b")
        self.assertEqual(entry["option_ids"], ["opt-b"])
        self.assertEqual(state["action_rules"], standing_rules)

    def test_single_pick_unknown_option_refused(self):
        state = _state()
        self._legacy_item(state)
        with self.assertRaises(Validation):
            _act(state, {"verb": "pick", "option_id": "opt-z"})
        self.assertEqual(state["sends"], [])

    def test_single_item_refuses_two_ids(self):
        state = _state()
        self._legacy_item(state)
        with self.assertRaises(Validation):
            _act(state, {"verb": "pick", "option_ids": ["opt-a", "opt-b"]})
        self.assertEqual(state["sends"], [])


class MultiPickTests(unittest.TestCase):
    def setUp(self):
        self.state = _state()
        _post(self.state, {"options": OPTIONS, "mode": "multi"})

    def test_multi_pick_records_the_set_and_sends_one_verdict(self):
        item = _act(
            self.state, {"verb": "pick", "option_ids": ["opt-c", "opt-a"]}
        )
        self.assertEqual(item["triage"], "done")
        decision = item["decision"]
        # The recorded set follows the item's declared
        # option order, not the payload's order.
        self.assertEqual(decision["option_ids"], ["opt-a", "opt-c"])
        self.assertIsNone(decision["option_id"])
        self.assertEqual(len(self.state["sends"]), 1)
        send = self.state["sends"][0]
        self.assertEqual(send["id"], decision["send_id"])
        self.assertIn("Route A", send["text"])
        self.assertIn("Route C", send["text"])
        self.assertNotIn("Route B", send["text"])
        (entry,) = self.state["owner_actions"]
        self.assertEqual(entry["option_ids"], ["opt-a", "opt-c"])
        self.assertIsNone(entry["option_id"])

    def test_multi_pick_of_one_id_via_legacy_field(self):
        item = _act(self.state, {"verb": "pick", "option_id": "opt-b"})
        self.assertEqual(item["decision"]["option_ids"], ["opt-b"])
        self.assertEqual(item["decision"]["option_id"], "opt-b")
        self.assertEqual(len(self.state["sends"]), 1)
        self.assertIn("Route B", self.state["sends"][0]["text"])

    def test_multi_pick_unknown_id_refused(self):
        with self.assertRaises(Validation):
            _act(self.state, {"verb": "pick", "option_ids": ["opt-a", "opt-z"]})
        self.assertEqual(self.state["sends"], [])

    def test_multi_pick_empty_set_refused(self):
        with self.assertRaises(Validation):
            _act(self.state, {"verb": "pick", "option_ids": []})
        with self.assertRaises(Validation):
            _act(self.state, {"verb": "pick"})
        self.assertEqual(self.state["sends"], [])

    def test_multi_pick_replay_records_and_sends_nothing_twice(self):
        _act(self.state, {"verb": "pick", "option_ids": ["opt-a", "opt-c"]})
        _act(self.state, {"verb": "pick", "option_ids": ["opt-c", "opt-a"]})
        self.assertEqual(len(self.state["sends"]), 1)
        self.assertEqual(len(self.state["owner_actions"]), 1)

    def test_changed_multi_pick_replaces_the_standing_decision(self):
        _act(self.state, {"verb": "pick", "option_ids": ["opt-a", "opt-c"]})
        item = _act(self.state, {"verb": "pick", "option_ids": ["opt-b"]})
        self.assertEqual(item["decision"]["option_ids"], ["opt-b"])
        self.assertEqual(item["decision"]["option_id"], "opt-b")
        self.assertEqual(len(self.state["sends"]), 2)
        self.assertEqual(len(item["decision_history"]), 1)
        self.assertEqual(
            item["decision_history"][0]["option_ids"], ["opt-a", "opt-c"]
        )

    def test_rule_it_under_multi_stores_the_set_on_the_shadow_rule(self):
        item = _act(
            self.state, {"verb": "rule_it", "option_ids": ["opt-b", "opt-c"]}
        )
        self.assertEqual(item["decision"]["option_ids"], ["opt-b", "opt-c"])
        self.assertEqual(len(self.state["sends"]), 1)
        send = self.state["sends"][0]
        self.assertIn("Route B", send["text"])
        self.assertIn("Route C", send["text"])
        (rule,) = [
            r for r in self.state["action_rules"] if r["created_from"] == "rule_it"
        ]
        self.assertEqual(rule["verb"], "pick")
        self.assertEqual(rule["mode"], "shadow")
        self.assertEqual(rule["created_from"], "rule_it")
        self.assertEqual(rule["option_ids"], ["opt-b", "opt-c"])
        self.assertNotIn("option_id", rule)


class CliOptionsV2Tests(unittest.TestCase):
    def test_parse_option_segments(self):
        self.assertEqual(
            cli._parse_option("opt-a=Route A"),
            {"id": "opt-a", "label": "Route A"},
        )
        self.assertEqual(
            cli._parse_option("opt-a=Route A=Dispatch route A"),
            {"id": "opt-a", "label": "Route A", "effect": "Dispatch route A"},
        )
        self.assertEqual(
            cli._parse_option("opt-a"), {"id": "opt-a", "label": "opt-a"}
        )

    def test_post_item_round_trips_effect_and_mode(self):
        captured = {}

        def fake_post_item(payload):
            captured.update(payload)
            return {"ok": True}

        args = cli.build_parser().parse_args(
            [
                "post",
                "item",
                "--source-ref",
                "decision-1",
                "--kind",
                "decision",
                "--title",
                "Pick a route",
                "--mode",
                "multi",
                "--option",
                "opt-a=Route A=Dispatch route A",
                "--option",
                "opt-b=Route B",
            ]
        )
        with (
            mock.patch.object(cli.client, "post_item", fake_post_item),
            mock.patch.object(cli, "_posting_handle", lambda: "@lane"),
        ):
            self.assertEqual(cli._post_item(args), 0)
        self.assertEqual(captured["mode"], "multi")
        self.assertEqual(
            captured["options"],
            [
                {"id": "opt-a", "label": "Route A", "effect": "Dispatch route A"},
                {"id": "opt-b", "label": "Route B"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
