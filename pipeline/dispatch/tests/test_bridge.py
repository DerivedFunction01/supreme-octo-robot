"""The bridge queue (dispatch.bridge, contract 05
SCH8): a chat_send round-trips through enqueue → poll →
fulfill → read; a duplicate enqueue with the same
(caller, envelope_id) returns the existing record and
queues nothing; a terminal record refuses a second
fulfill.
"""

import tempfile
import unittest
from pathlib import Path

from dispatch import bridge


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dispatch-bridge-"))
        self.dir = str(self.tmp / "connector-bridge")


class RoundTripTests(BridgeCase):
    def test_chat_send_round_trip(self):
        record = bridge.enqueue(
            self.dir, "attention-dispatch", "chat_send",
            {"chat_id": "chat-target-1", "text": "hello"},
            envelope_id="attn-s0001-a1")
        self.assertEqual(record["status"], "queued")
        queued = bridge.poll_queued(self.dir)
        self.assertEqual([r["id"] for r in queued], [record["id"]])
        done = bridge.fulfill(
            self.dir, record["id"], "bridge-home", ok=True,
            result={"submission_message_id": "sub-1"})
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["fulfilled_by"], "bridge-home")
        reread = bridge.read_request(self.dir, record["id"])
        self.assertEqual(reread["result"],
                         {"submission_message_id": "sub-1"})
        self.assertEqual(bridge.poll_queued(self.dir), [])

    def test_duplicate_envelope_returns_existing_record(self):
        first, deduped = bridge.enqueue_idempotent(
            self.dir, "attention-dispatch", "chat_send",
            {"chat_id": "chat-target-1", "text": "hello"},
            "attn-s0001-a1")
        self.assertFalse(deduped)
        second, deduped = bridge.enqueue_idempotent(
            self.dir, "attention-dispatch", "chat_send",
            {"chat_id": "chat-target-1", "text": "hello"},
            "attn-s0001-a1")
        self.assertTrue(deduped)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(len(bridge.poll_queued(self.dir)), 1)
        # A different caller with the same envelope id is a
        # different record — idempotency is per (caller, id).
        third, deduped = bridge.enqueue_idempotent(
            self.dir, "other-caller", "chat_send",
            {"chat_id": "chat-target-1", "text": "hello"},
            "attn-s0001-a1")
        self.assertFalse(deduped)
        self.assertNotEqual(third["id"], first["id"])

    def test_terminal_record_refuses_second_fulfill(self):
        record = bridge.enqueue(
            self.dir, "caller-a", "chat_list", {})
        bridge.fulfill(self.dir, record["id"], "bridge-home",
                       ok=False, error="tool unavailable")
        with self.assertRaises(ValueError):
            bridge.fulfill(self.dir, record["id"], "bridge-home",
                           ok=True, result={})
        reread = bridge.read_request(self.dir, record["id"])
        self.assertEqual(reread["status"], "failed")
        self.assertEqual(reread["error"], "tool unavailable")

    def test_missing_request_reads_and_fulfills_as_none(self):
        self.assertIsNone(bridge.read_request(self.dir, "nope"))
        self.assertIsNone(bridge.fulfill(
            self.dir, "nope", "bridge-home", ok=True, result={}))

    def test_envelope_id_validation(self):
        self.assertTrue(bridge.valid_envelope_id("attn-s0001-a1"))
        self.assertFalse(bridge.valid_envelope_id(""))
        self.assertFalse(bridge.valid_envelope_id("has space"))
        self.assertFalse(bridge.valid_envelope_id("x" * 129))
        self.assertFalse(bridge.valid_envelope_id(None))


if __name__ == "__main__":
    unittest.main()
