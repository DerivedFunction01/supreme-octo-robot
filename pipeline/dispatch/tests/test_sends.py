"""The send ledger (dispatch.sends, contract 05's
attention clauses): minting only through record_send,
the claim lease with read-time expiry, delivery only by
the claiming consumer's ack carrying a reference,
reasoned terminal suppress, the suppressed-but-
fulfilled edge, deduped failure records, and parking at
attempts exhaustion.

The seed is the contract fixture's send (s0001, the
pinned dispatch tests' constructor specimen), with its
timestamps parsed to datetimes — the surface's type.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dispatch import sends

UTC = timezone.utc
T0 = datetime(2026, 11, 12, 14, 50, tzinfo=UTC)

FIXTURE = (Path(__file__).resolve().parents[3]
           / "contracts" / "fixtures" / "attention-send.json")


def _parse(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, dict):
        return {k: _parse(v) for k, v in value.items()}
    return value


def seed_sends():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [_parse(raw)]


def mint(sends_list, **kw):
    kw.setdefault("producer", "owner-verb")
    kw.setdefault("template", "decision-reply")
    kw.setdefault("version", 1)
    kw.setdefault("text", "Approve — the thing.")
    kw.setdefault("handle", "@aldergrove-xbrl")
    kw.setdefault("target", "thread-1")
    kw.setdefault("now", T0)
    return sends.record_send(sends_list, **kw)


class RecordSendTests(unittest.TestCase):
    def test_mint_continues_the_id_scheme(self):
        ledger = seed_sends()
        send = mint(ledger)
        self.assertEqual(send["id"], "s0002")
        self.assertEqual(send["outcome"], "recorded")
        self.assertEqual(send["dispatch"]["attempts"], 0)
        self.assertEqual(sends.state_of(send, T0), "undispatched")

    def test_shadow_records_and_never_dispatches(self):
        ledger = seed_sends()
        send = mint(ledger, mode="shadow")
        self.assertEqual(send["outcome"], "shadow")
        self.assertEqual(sends.state_of(send, T0), "not_dispatchable")
        with self.assertRaises(sends.SendError):
            sends.claim(ledger, send["id"], "consumer-a", T0)
        self.assertEqual(sends.undispatched(ledger, T0), [ledger[0]])


class ClaimAckTests(unittest.TestCase):
    def setUp(self):
        self.ledger = seed_sends()
        self.send = mint(self.ledger)

    def test_claim_lease_and_ack_with_reference(self):
        sends.claim(self.ledger, self.send["id"], "consumer-a", T0)
        view = sends.view(self.send, T0)
        self.assertEqual(view["state"], "claimed")
        self.assertEqual(view["attempts"], 1)
        self.assertEqual(view["claim_expires_at"],
                         T0 + timedelta(minutes=15))
        sends.ack(self.ledger, self.send["id"], "consumer-a",
                  "sub-s0002-1", T0 + timedelta(minutes=2))
        view = sends.view(self.send, T0 + timedelta(minutes=2))
        self.assertEqual(view["state"], "delivered")
        self.assertEqual(view["delivery_ref"], "sub-s0002-1")

    def test_ack_requires_the_claiming_consumer_and_a_reference(self):
        sends.claim(self.ledger, self.send["id"], "consumer-a", T0)
        with self.assertRaises(sends.SendError):
            sends.ack(self.ledger, self.send["id"], "consumer-b",
                      "sub-x", T0)
        with self.assertRaises(sends.SendError):
            sends.ack(self.ledger, self.send["id"], "consumer-a",
                      "", T0)
        self.assertEqual(sends.state_of(self.send, T0), "claimed")

    def test_expiry_is_read_time_and_reclaimable(self):
        sends.claim(self.ledger, self.send["id"], "consumer-a", T0)
        later = T0 + timedelta(minutes=16)
        self.assertEqual(sends.state_of(self.send, later),
                         "undispatched")
        sends.claim(self.ledger, self.send["id"], "consumer-b", later)
        self.assertEqual(
            sends.view(self.send, later)["consumer"], "consumer-b")

    def test_live_claim_refuses_another_consumer(self):
        sends.claim(self.ledger, self.send["id"], "consumer-a", T0)
        with self.assertRaises(sends.SendError):
            sends.claim(self.ledger, self.send["id"], "consumer-b",
                        T0 + timedelta(minutes=1))


class SuppressTests(unittest.TestCase):
    def setUp(self):
        self.ledger = seed_sends()
        self.send = mint(self.ledger)

    def test_suppress_is_reasoned_and_terminal(self):
        with self.assertRaises(sends.SendError):
            sends.suppress(self.ledger, self.send["id"], "", T0)
        sends.suppress(self.ledger, self.send["id"], "moot", T0)
        self.assertEqual(sends.state_of(self.send, T0),
                         "not_dispatchable")
        with self.assertRaises(sends.SendError):
            sends.claim(self.ledger, self.send["id"], "consumer-a", T0)

    def test_delivered_send_refuses_suppress(self):
        sends.claim(self.ledger, self.send["id"], "consumer-a", T0)
        sends.ack(self.ledger, self.send["id"], "consumer-a",
                  "sub-s0002-1", T0)
        with self.assertRaises(sends.SendError):
            sends.suppress(self.ledger, self.send["id"], "moot", T0)

    def test_late_fulfillment_is_stamped_never_resurrected(self):
        sends.suppress(self.ledger, self.send["id"], "moot", T0)
        sends.stamp_late_fulfillment(
            self.ledger, self.send["id"], "sub-late-1",
            T0 + timedelta(minutes=5))
        view = sends.view(self.send, T0 + timedelta(minutes=5))
        self.assertEqual(view["delivery_ref"], "sub-late-1")
        self.assertEqual(view["suppressed_reason"], "moot")
        self.assertEqual(sends.undispatched(
            self.ledger, T0 + timedelta(minutes=5)), [self.ledger[0]])


class FailureAndParkingTests(unittest.TestCase):
    def test_failure_records_dedupe_inside_the_hour(self):
        failures = []
        first = sends.record_failure(
            failures, "s0002", "consumer-a", "bridge down", T0)
        dupe = sends.record_failure(
            failures, "s0002", "consumer-a", "bridge down",
            T0 + timedelta(minutes=30))
        other = sends.record_failure(
            failures, "s0002", "consumer-a", "timeout",
            T0 + timedelta(minutes=30))
        later = sends.record_failure(
            failures, "s0002", "consumer-a", "bridge down",
            T0 + timedelta(hours=2))
        self.assertIsNotNone(first)
        self.assertIsNone(dupe)
        self.assertIsNotNone(other)
        self.assertIsNotNone(later)
        self.assertEqual(len(failures), 3)

    def test_attempts_exhaustion_parks_and_suppresses(self):
        ledger = seed_sends()
        send = mint(ledger)
        now = T0
        for _ in range(sends.MAX_ATTEMPTS_DEFAULT):
            sends.claim(ledger, send["id"], "consumer-a", now)
            sends.release_claim(ledger, send["id"])
            now += timedelta(minutes=16)
        self.assertTrue(sends.park_exhausted(ledger, send["id"], now))
        view = sends.view(send, now)
        self.assertEqual(view["state"], "not_dispatchable")
        self.assertIn("exhausted", view["suppressed_reason"])

    def test_bridge_envelope_form(self):
        ledger = seed_sends()
        send = mint(ledger)
        sends.claim(ledger, send["id"], "consumer-a", T0)
        self.assertEqual(sends.bridge_envelope(send), "attn-s0002-a1")


if __name__ == "__main__":
    unittest.main()
