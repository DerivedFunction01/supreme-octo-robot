"""The card-watch source seam pins (card-owner plan,
Step 1 fan-out): normalization whitelist, source-stale
taxonomy, history outcome discipline.

Deterministic throughout: fake transport, fake clock, no
network, no wall clock, no timing assertions. The poison
strings below live only in the specimens' raw payload
fields; the whitelist pins assert they survive nowhere
in a DTO, a snapshot, or a serialized form of either.
"""

import json
import unittest

from registry.cards import cardsource, cardwatch_fakes as fakes

POISON = ("git -C fixture/repo push origin main",
          "send digest to the list",
          "fixture@example.invalid")


def bridge(transport, clock=None):
    return cardsource.BridgeCardSource(transport, clock or fakes.FakeClock())


class NormalizeTest(unittest.TestCase):
    def test_whitelist_fields_exact(self):
        card = cardsource.normalize_card(fakes.RAW_CARD_CHAT)
        self.assertEqual(card.as_dict(), {
            "approval_id": "appr-fixture-001",
            "purpose": "Run a shell command on the home machine",
            "scope": "exec: git push origin main",
            "requested_at": "2026-11-14T14:41:00Z",
            "expires_at": "2026-11-14T16:41:00Z",
            "origin_kind": "chat",
            "origin_id": "chat-fixture-alpha",
        })

    def test_cron_origin(self):
        card = cardsource.normalize_card(fakes.RAW_CARD_CRON)
        self.assertEqual((card.origin_kind, card.origin_id),
                         ("cron", "job-fixture-nightly"))

    def test_raw_payload_dropped(self):
        for raw in fakes.RAW_PENDING:
            card = cardsource.normalize_card(raw)
            blob = json.dumps(card.as_dict()) + repr(card)
            for poison in POISON:
                self.assertNotIn(poison, blob)
            self.assertNotIn("command", card.as_dict())
            self.assertNotIn("tool_params", card.as_dict())

    def test_record_without_approval_id_is_not_a_card(self):
        self.assertIsNone(cardsource.normalize_card({"purpose": "x"}))
        self.assertIsNone(cardsource.normalize_card("not-a-dict"))


class SnapshotTest(unittest.TestCase):
    def test_good_snapshot_dict_form(self):
        transport = fakes.FakeBridgeTransport().script(
            cardsource.LIST_TOOL, {"cards": list(fakes.RAW_PENDING)})
        snap = bridge(transport).pending_snapshot()
        self.assertIsInstance(snap, cardsource.Snapshot)
        self.assertEqual([c.approval_id for c in snap.cards],
                         ["appr-fixture-001", "appr-fixture-002"])
        self.assertEqual(snap.taken_at, fakes.SEED_NOW)
        self.assertEqual(transport.calls, [(cardsource.LIST_TOOL, {})])

    def test_good_snapshot_bare_list_form(self):
        transport = fakes.FakeBridgeTransport().script(
            cardsource.LIST_TOOL, list(fakes.RAW_PENDING))
        snap = bridge(transport).pending_snapshot()
        self.assertIsInstance(snap, cardsource.Snapshot)
        self.assertEqual(len(snap.cards), 2)

    def test_empty_queue_is_a_good_empty_snapshot(self):
        # A drained, fulfilled empty list is a real answer:
        # zero cards observed. Staleness is reserved for
        # reads that did not answer.
        transport = fakes.FakeBridgeTransport().script(
            cardsource.LIST_TOOL, {"cards": []})
        snap = bridge(transport).pending_snapshot()
        self.assertIsInstance(snap, cardsource.Snapshot)
        self.assertEqual(snap.cards, ())

    def test_undrained_is_stale_never_empty(self):
        transport = fakes.FakeBridgeTransport().script(
            cardsource.LIST_TOOL, fakes.FakeBridgeTransport.UNDRAINED)
        result = bridge(transport).pending_snapshot()
        self.assertIsInstance(result, cardsource.SourceStale)
        self.assertEqual(result.reason, cardsource.STALE_UNDRAINED)

    def test_transport_failures_are_stale_with_their_name(self):
        for name in ("scope_refused", "fulfillment_failed", "unreachable"):
            transport = fakes.FakeBridgeTransport().script(
                cardsource.LIST_TOOL, fakes.FakeTransportError(name))
            result = bridge(transport).pending_snapshot()
            self.assertIsInstance(result, cardsource.SourceStale)
            self.assertEqual(result.reason, cardsource.STALE_TRANSPORT)
            self.assertEqual(result.detail, name)

    def test_shadow_read_is_stale(self):
        transport = fakes.FakeBridgeTransport().script(
            cardsource.LIST_TOOL, {"shadow": True, "tool": "permissions_list"})
        result = bridge(transport).pending_snapshot()
        self.assertIsInstance(result, cardsource.SourceStale)
        self.assertEqual(result.reason, cardsource.STALE_TRANSPORT)

    def test_malformed_results_are_stale(self):
        for bad in ({"unexpected": 1}, "a string", 42,
                    {"cards": [{"purpose": "no id here"}]}):
            transport = fakes.FakeBridgeTransport().script(
                cardsource.LIST_TOOL, bad)
            result = bridge(transport).pending_snapshot()
            self.assertIsInstance(result, cardsource.SourceStale, bad)
            self.assertEqual(result.reason, cardsource.STALE_MALFORMED)


class HistoryTest(unittest.TestCase):
    def _history(self, raw, approval_id="appr-fixture-001"):
        transport = fakes.FakeBridgeTransport().script(
            cardsource.HISTORY_TOOL, raw)
        outcome = bridge(transport).history(approval_id)
        self.assertEqual(
            transport.calls,
            [(cardsource.HISTORY_TOOL, {"approval_id": approval_id})])
        return outcome

    def test_outcomes_pass_through_from_the_record(self):
        for raw, want in ((fakes.RAW_HISTORY_APPROVED, "approved"),
                          (fakes.RAW_HISTORY_DENIED, "denied"),
                          (fakes.RAW_HISTORY_EXPIRED, "expired")):
            got = self._history(raw, raw["approval_id"])
            self.assertIsInstance(got, cardsource.Resolved)
            self.assertEqual(got.outcome, want)
            self.assertEqual(got.decided_at, raw["decided_at"])

    def test_explicit_unresolved_is_unresolved(self):
        got = self._history(fakes.RAW_HISTORY_UNRESOLVED)
        self.assertIsInstance(got, cardsource.Unresolved)

    def test_history_undrained_and_failed_are_stale(self):
        for scripted in (fakes.FakeBridgeTransport.UNDRAINED,
                         fakes.FakeTransportError("fulfillment_failed")):
            transport = fakes.FakeBridgeTransport().script(
                cardsource.HISTORY_TOOL, scripted)
            got = bridge(transport).history("appr-fixture-001")
            self.assertIsInstance(got, cardsource.SourceStale)


class FakeSourceParityTest(unittest.TestCase):
    """The shipped fake answers the interface identically,
    so sibling lanes' tests fake the same seam."""

    def test_fake_snapshot_matches_bridge_dtos(self):
        fake = fakes.FakeCardSource(fakes.FakeClock(),
                                    pending=fakes.RAW_PENDING)
        snap = fake.pending_snapshot()
        self.assertEqual([c.as_dict() for c in snap.cards],
                         [cardsource.normalize_card(r).as_dict()
                          for r in fakes.RAW_PENDING])
        self.assertEqual(snap.taken_at, fakes.SEED_NOW)

    def test_fake_history_paths(self):
        fake = fakes.FakeCardSource(
            fakes.FakeClock(),
            history_records={"appr-fixture-002": fakes.RAW_HISTORY_DENIED})
        got = fake.history("appr-fixture-002")
        self.assertIsInstance(got, cardsource.Resolved)
        self.assertEqual(got.outcome, "denied")
        self.assertIsInstance(fake.history("appr-fixture-999"),
                              cardsource.Unresolved)

    def test_fake_stale_switch(self):
        stale = cardsource.SourceStale(cardsource.STALE_UNDRAINED)
        fake = fakes.FakeCardSource(fakes.FakeClock(), stale=stale)
        self.assertIs(fake.pending_snapshot(), stale)
        self.assertIs(fake.history("appr-fixture-001"), stale)


if __name__ == "__main__":
    unittest.main()
