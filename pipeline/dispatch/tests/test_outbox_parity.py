"""Outbox parity (plan §5 S6 done-evidence): wake / ack
/ coalesce behaviour over pings matches the pinned
scheduler's ledger event sequence, and the contract's
fixture ping (produced by the pinned Outbox) loads and
wakes through the consolidated substrate unchanged.
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dispatch.ledger import Ledger
from dispatch.outbox import Outbox

UTC = timezone.utc
T0 = datetime(2026, 11, 12, 15, 52, tzinfo=UTC)

FIXTURE = (Path(__file__).resolve().parents[3]
           / "contracts" / "fixtures" / "outbox-ping.json")


class LedgerSequenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dispatch-outbox-")
        self.ledger = Ledger(self.tmp)
        self.outbox = Outbox(self.tmp, self.ledger)

    def kinds(self):
        return [rec["kind"] for rec in self.ledger.read_all()]

    def test_wake_ack_coalesce_event_sequence(self):
        ping, created = self.outbox.add_or_coalesce(
            "job-a", T0, "agent-due", now=T0)
        self.assertTrue(created)
        again, created = self.outbox.add_or_coalesce(
            "job-a", T0 + timedelta(minutes=15), "agent-due",
            now=T0 + timedelta(minutes=15))
        self.assertFalse(created)
        self.assertEqual(again["id"], ping["id"])
        self.assertEqual(again["coalesced_count"], 2)
        self.assertEqual(self.outbox.wake_set(T0, 3600), [again])
        self.outbox.mark_woken([ping["id"]], now=T0)
        # Inside the ack window the ping does not re-wake.
        self.assertEqual(
            self.outbox.wake_set(T0 + timedelta(minutes=30), 3600),
            [])
        self.outbox.ack(ping["id"])
        # Acking an acked ping is a ledgered no-op.
        self.outbox.ack(ping["id"])
        self.assertEqual(
            self.kinds(),
            ["ping_created", "ping_coalesced", "ping_woken",
             "ping_acked", "ack_noop"])

    def test_void_on_entry_removal(self):
        self.outbox.add_or_coalesce("job-a", T0, "agent-due", now=T0)
        self.assertEqual(self.outbox.void_for_job("job-a"), 1)
        self.assertEqual(self.outbox.pending(), [])
        self.assertEqual(self.kinds(),
                         ["ping_created", "ping_voided"])


class FixturePingTests(unittest.TestCase):
    def test_fixture_ping_loads_and_wakes(self):
        tmp = tempfile.mkdtemp(prefix="dispatch-outbox-fx-")
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with open(Path(tmp) / "outbox.json", "w",
                  encoding="utf-8") as fh:
            json.dump({"pings": [fixture]}, fh)
        outbox = Outbox(tmp, Ledger(tmp))
        pending = outbox.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], fixture["id"])
        wake = outbox.wake_set(T0, 3600)
        self.assertEqual([p["id"] for p in wake], [fixture["id"]])
        self.assertEqual(wake[0]["detail"]["target_chat"],
                         "chat-target-1")


if __name__ == "__main__":
    unittest.main()
