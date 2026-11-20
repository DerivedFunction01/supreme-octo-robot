"""Delivery-side provenance pins (2026-11-16): a send
delivered into a chat carries only its text — the bridge
record's meta never reaches the message and the channel
stamps the executing chat's identity — so a
machinery-fired send must name its true origin in the
text itself. Fixture state only: the store seam's empty
state plus one handler, built in memory.
"""

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import store as store_mod  # noqa: E402
from attention.services.waits import engine  # noqa: E402

NOW = datetime(2026, 11, 16, 6, 0, tzinfo=UTC)


def _fixture_state():
    state = store_mod.empty_state()
    state["handlers"].append(
        {"handle": "@lane", "label": "Lane", "thread_id": "thread-lane"}
    )
    return state


class MachineryStampTests(unittest.TestCase):
    def test_continuation_send_names_the_machinery(self):
        state = _fixture_state()
        send = engine.record_send(
            state,
            "continuation",
            "@lane",
            {"summary": "Lane — record gap.", "detail": "Next act: post."},
            NOW,
            rule_id="attention:continuation",
        )
        self.assertIsNotNone(send)
        self.assertTrue(send["text"].startswith("Continue — Lane — record gap."))
        self.assertIn(
            "[Provenance: owner-attention machinery — fired under rule "
            "attention:continuation",
            send["text"],
        )
        self.assertIn(f"send {send['id']}", send["text"])
        self.assertIn("not an owner or coordinator act", send["text"])

    def test_action_rule_commission_no_longer_wears_the_owner_voice_alone(self):
        # The defect's in-repo shape: an evaluator-fired
        # rule minting the "commission" template, whose
        # text claims a fresh owner act. The stamp now
        # rides the same text and names the true origin.
        state = _fixture_state()
        send = engine.record_send(
            state,
            "commission",
            "@lane",
            {"summary": "Draw the cohort."},
            NOW,
            rule_id="rule-auto-7",
        )
        self.assertTrue(send["text"].startswith("Commission from the owner:"))
        self.assertIn("owner-attention machinery", send["text"])
        self.assertIn("rule rule-auto-7", send["text"])
        self.assertIn("not an owner or coordinator act", send["text"])

    def test_action_rule_verdict_is_stamped(self):
        state = _fixture_state()
        send = engine.record_send(
            state,
            "verdict",
            "@lane",
            {"summary": "Ship it", "verb": "Approve", "note": ""},
            NOW,
            rule_id="rule-auto-approve",
        )
        self.assertTrue(send["text"].startswith("Owner verdict — Approve:"))
        self.assertIn("owner-attention machinery", send["text"])

    def test_owner_act_is_unstamped(self):
        # An owner's own recorded act: the text's claim is
        # true, the ledger is its proof, no stamp is added.
        state = _fixture_state()
        send = engine.record_send(
            state,
            "commission",
            "@lane",
            {"summary": "Draw the cohort."},
            NOW,
            rule_id="owner:commission",
        )
        self.assertEqual(send["text"], "Commission from the owner: Draw the cohort.")
        self.assertNotIn("Provenance:", send["text"])


class WaitPostStampTests(unittest.TestCase):
    def test_wait_post_names_poster_and_engine(self):
        state = _fixture_state()
        rule = {"id": "wait-rule-1", "action": {"template": "venue-ping"}}
        wait = {"id": "w-1", "handle": "@lane", "posted_at": NOW}
        send = engine._record_post(
            state, rule, wait, {"summary": "Is the venue up?"}, NOW, shadow=False
        )
        self.assertIsInstance(send, dict)
        self.assertTrue(send["text"].startswith("Venue check: Is the venue up?"))
        self.assertIn(
            "[Provenance: owner-attention dispatch — wait w-1 post, "
            "written by its poster, fired by the waits engine under rule "
            "wait-rule-1",
            send["text"],
        )
        self.assertIn(f"send {send['id']}", send["text"])


if __name__ == "__main__":
    unittest.main()
