"""Owner-action pins for the waits/actions service: a
rule_it tap is two acts in one (§1.13, D-A8's sibling) —
the pick lands as the item's verdict (send written,
decision recorded) AND the standing rule is created in
shadow on the item's handle + kind with the picked
option. A plain pick is the control: the same verdict
lands and no rule is created. Fixture state only: the
store seam's empty state plus one handler and one
decision item, built in memory — never a live store.
"""

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import store as store_mod  # noqa: E402
from attention.services.waits import actions  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def _fixture_state():
    state = store_mod.empty_state()
    state["handlers"].append(
        {"handle": "@lane", "label": "Lane", "thread_id": "thread-lane"}
    )
    state["items"].append(
        {
            "id": "@lane:decision-1",
            "handle": "@lane",
            "kind": "decision",
            "title": "Pick a route",
            "status_code": None,
            "source_ref": "decision-1",
            "source_url": "",
            "clears_at_source": False,
            "due_at": None,
            "waiting_since": NOW,
            "need": "owner_actionable",
            "tier": "digest",
            "triage": "open",
            "snooze_return_at": None,
            "snooze_on_activity": False,
            "resume_note": None,
            "provenance": "offer",
            "options": [
                {"id": "opt-a", "label": "Route A"},
                {"id": "opt-b", "label": "Route B"},
            ],
            "wait_id": None,
        }
    )
    return state


def _act(state, verb, option_id="opt-b"):
    return actions.apply_item_action(
        state,
        Settings(data_path=None),
        "@lane:decision-1",
        {"verb": verb, "option_id": option_id},
        NOW,
    )


class RuleItTests(unittest.TestCase):
    def test_rule_it_lands_the_verdict_and_creates_the_shadow_rule(self):
        state = _fixture_state()
        standing = len(state["action_rules"])
        item = _act(state, "rule_it")
        # The verdict half: triage done, decision recorded
        # against the send that carries the picked label.
        self.assertEqual(item["triage"], "done")
        decision = item["decision"]
        self.assertEqual(decision["verb"], "rule_it")
        self.assertEqual(decision["option_id"], "opt-b")
        self.assertIsNotNone(decision["send_id"])
        self.assertEqual(len(state["sends"]), 1)
        send = state["sends"][0]
        self.assertEqual(send["id"], decision["send_id"])
        self.assertEqual(send["rule_id"], "owner:rule_it")
        self.assertIn("Route B", send["text"])
        # The rule half: one new shadow rule on handle +
        # kind, standing for the pick of the chosen option.
        self.assertEqual(len(state["action_rules"]), standing + 1)
        rule = state["action_rules"][-1]
        self.assertEqual(rule["verb"], "pick")
        self.assertEqual(rule["mode"], "shadow")
        self.assertEqual(rule["created_from"], "rule_it")
        self.assertEqual(rule["match"], {"handle": "@lane", "kind": "decision"})
        self.assertEqual(rule["option_id"], "opt-b")
        # The tap itself is on the owner-action record.
        self.assertEqual(len(state["owner_actions"]), 1)
        self.assertEqual(state["owner_actions"][0]["verb"], "rule_it")

    def test_pick_lands_the_verdict_and_creates_no_rule(self):
        state = _fixture_state()
        standing = list(state["action_rules"])
        item = _act(state, "pick")
        self.assertEqual(item["triage"], "done")
        self.assertEqual(item["decision"]["verb"], "pick")
        self.assertIsNotNone(item["decision"]["send_id"])
        self.assertEqual(len(state["sends"]), 1)
        self.assertEqual(state["sends"][0]["rule_id"], "owner:pick")
        self.assertIn("Route B", state["sends"][0]["text"])
        self.assertEqual(state["action_rules"], standing)


if __name__ == "__main__":
    unittest.main()
