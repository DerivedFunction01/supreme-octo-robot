import json
import os
import tempfile
import unittest
from datetime import timedelta

from dispatch.ledger import Ledger
from dispatch.outbox import Outbox
from tests.helpers import T0


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = Ledger(self.tmp)
        self.outbox = Outbox(self.tmp, self.ledger)

    def test_write_before_wake(self):
        ping, created = self.outbox.add_or_coalesce("job-a", T0, "agent-due", now=T0)
        self.assertTrue(created)
        with open(os.path.join(self.tmp, "outbox.json"), encoding="utf-8") as fh:
            on_disk = json.load(fh)
        self.assertEqual(on_disk["pings"][0]["id"], ping["id"])  # durable before any wake
        self.assertEqual(self.outbox.wake_set(T0, 3600), [ping])

    def test_coalescing_one_pending_per_job(self):
        first, _ = self.outbox.add_or_coalesce("job-a", T0, "agent-due", now=T0)
        later = T0 + timedelta(minutes=15)
        second, created = self.outbox.add_or_coalesce("job-a", later, "agent-due", now=later)
        self.assertFalse(created)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.outbox.pending()), 1)
        self.assertEqual(second["coalesced_count"], 2)
        self.assertTrue(second["due"].startswith("2026-10-31T12:15"))

    def test_cross_process_visibility(self):
        # The outbox file is shared across processes (server,
        # bin/sched, a drill): a second instance must see the
        # first instance's writes, and an ack through one must
        # never be resurrected by the other's next save.
        other = Outbox(self.tmp, self.ledger)
        ping, _ = self.outbox.add_or_coalesce("job-a", T0, "agent-due", now=T0)
        self.assertEqual([p["id"] for p in other.pending()], [ping["id"]])
        other.ack(ping["id"])
        self.assertEqual(self.outbox.pending(), [])
        self.outbox.add_or_coalesce("job-b", T0, "escalation", now=T0)
        states = {p["job_id"]: p["state"] for p in other.pending()}
        self.assertEqual(states, {"job-b": "pending"})

    def test_ack_is_explicit_and_separate(self):
        ping, _ = self.outbox.add_or_coalesce("job-a", T0, "agent-due", now=T0)
        self.assertEqual(len(self.outbox.pending()), 1)  # listing does not ack
        self.outbox.ack(ping["id"])
        self.assertEqual(self.outbox.pending(), [])
        again = self.outbox.ack(ping["id"])  # no-op, ledgered
        self.assertEqual(again["state"], "acked")
        kinds = [r["kind"] for r in self.ledger.read_all()]
        self.assertIn("ack_noop", kinds)
        self.assertIsNone(self.outbox.ack("no-such-id"))

    def test_resurface_once_per_ack_timeout_window(self):
        ping, _ = self.outbox.add_or_coalesce("job-a", T0, "report", now=T0)
        self.assertEqual(len(self.outbox.wake_set(T0, 3600)), 1)
        self.outbox.mark_woken([ping["id"]], now=T0)
        self.assertEqual(self.outbox.wake_set(T0 + timedelta(seconds=100), 3600), [])
        self.assertEqual(len(self.outbox.wake_set(T0 + timedelta(seconds=3700), 3600)), 1)

    def test_void_for_job(self):
        ping, _ = self.outbox.add_or_coalesce("job-a", T0, "agent-due", now=T0)
        self.assertEqual(self.outbox.void_for_job("job-a"), 1)
        self.assertEqual(self.outbox.pending(), [])
        self.assertEqual(self.outbox.get(ping["id"])["state"], "void")


if __name__ == "__main__":
    unittest.main()
