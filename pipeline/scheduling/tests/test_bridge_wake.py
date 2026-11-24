import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops.bridge import bridge_wake  # noqa: E402
from dispatch.ledger import Ledger  # noqa: E402
from dispatch.outbox import Outbox  # noqa: E402

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
CHAT = "chat-target-1"
OWNER_CHAT = "chat-owner-1"


def record(rid, tool, caller, args=None, status="queued"):
    return {"id": rid, "tool": tool, "caller": caller,
            "args": args or {}, "status": status,
            "ts": "2026-11-10T11:59:00+00:00"}


class BridgeWakeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bridge = os.path.join(self.tmp, "bridge")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.bridge)
        os.makedirs(self.state)
        self.owners_path = os.path.join(self.tmp, "owners.yaml")
        with open(self.owners_path, "w", encoding="utf-8") as fh:
            fh.write("version: 1\nowners:\n  sweeper-venue:\n"
                     f"    chat: \"{OWNER_CHAT}\"\n")
        self.outbox = Outbox(self.state, Ledger(self.state))

    def plant(self, rec):
        path = os.path.join(self.bridge, rec["id"] + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)

    def ping_for(self, job_id):
        return next(p for p in self.pending()
                    if p["job_id"] == job_id)

    def run_minter(self):
        return bridge_wake.run(bridge_dir=self.bridge,
                               state_dir=self.state,
                               owners_path=self.owners_path,
                               now=NOW, outbox=self.outbox)

    def pending(self):
        return self.outbox.pending()


class MintTests(BridgeWakeCase):
    def test_chat_send_mints_to_its_own_chat_without_a_drain_home(self):
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        lines = self.run_minter()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("WAKE r1 "))
        self.assertIn(f"target={CHAT}", lines[0])
        self.assertEqual(lines[1], "DRAIN items=1")
        ping = self.ping_for("bridge-wake-r1")
        self.assertEqual(ping["job_id"], "bridge-wake-r1")
        self.assertEqual(ping["kind"], "agent-due")
        self.assertEqual(ping["body_ref"], "bodies/bridge-wake-item.md")
        # The wake carries identity and destination, never text.
        self.assertEqual(ping["detail"], {
            "request_id": "r1", "tool": "chat_send",
            "caller": "sweeper-venue", "target_chat": CHAT})
        self.assertNotIn("hello", json.dumps(ping))

    def test_read_tool_mints_to_the_callers_owner_thread(self):
        self.plant(record("r2", "permissions_list", "sweeper-venue"))
        lines = self.run_minter()
        self.assertEqual(len(lines), 2)
        self.assertIn(f"target={OWNER_CHAT}", lines[0])
        self.assertEqual(
            self.ping_for("bridge-wake-r2")["detail"]["target_chat"],
            OWNER_CHAT)

    def test_unmapped_caller_is_unresolved_and_left_queued(self):
        self.plant(record("r3", "chat_list", "local-test-watch"))
        lines = self.run_minter()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("UNRESOLVED r3 "))
        self.assertEqual(self.pending(), [])

    def test_chat_send_without_chat_id_is_unresolved(self):
        self.plant(record("r4", "chat_send", "sweeper-venue", {}))
        lines = self.run_minter()
        self.assertTrue(lines[0].startswith("UNRESOLVED r4 "))
        self.assertEqual(self.pending(), [])

    def test_second_pass_does_not_remint_a_pending_item(self):
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        self.assertEqual(len(self.run_minter()), 2)
        self.assertEqual(self.run_minter(), [])
        self.assertEqual(len(self.pending()), 2)
        self.assertEqual(
            self.ping_for("bridge-wake-r1")["coalesced_count"], 1)

    def test_acked_unfulfilled_item_is_reminted(self):
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        self.run_minter()
        ping = self.ping_for("bridge-wake-r1")
        self.outbox.ack(ping["id"])
        lines = self.run_minter()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("WAKE r1 "))
        self.assertNotEqual(
            self.ping_for("bridge-wake-r1")["id"], ping["id"])

    def test_terminal_records_are_never_minted(self):
        self.plant(record("r5", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "x"}, status="done"))
        self.plant(record("r6", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "x"}, status="failed"))
        self.assertEqual(self.run_minter(), [])
        self.assertEqual(self.pending(), [])

    def test_empty_queue_is_quiet(self):
        self.assertEqual(self.run_minter(), [])

    def test_missing_owners_config_resolves_nobody(self):
        os.unlink(self.owners_path)
        self.plant(record("r2", "permissions_list", "sweeper-venue"))
        lines = self.run_minter()
        self.assertTrue(lines[0].startswith("UNRESOLVED r2 "))
        # A chat_send still carries its own target without the file.
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        lines = self.run_minter()
        self.assertTrue(any(line.startswith("WAKE r1 ") for line in lines))


class EscalationTests(BridgeWakeCase):
    """The F5 episode escalation: one
    bridge-drain ping per non-empty queue episode."""

    def test_chat_send_wake_addresses_the_drain_home(self):
        # With a drain home configured, a chat_send's
        # per-item wake goes to the drain, not to the
        # destination chat: delivery is the drain's work,
        # and the destination lane never has to read an
        # instruction-shaped payload to relay it (the
        # screen-stall defect). The record's
        # own destination is untouched.
        with open(self.owners_path, "w", encoding="utf-8") as fh:
            fh.write("version: 1\ndrain:\n"
                     f"  chat: \"{OWNER_CHAT}\"\nowners:\n"
                     "  sweeper-venue:\n"
                     f"    chat: \"{OWNER_CHAT}\"\n")
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        self.run_minter()
        self.assertEqual(
            self.ping_for("bridge-wake-r1")["detail"]["target_chat"],
            OWNER_CHAT)

    def test_drain_ping_shape(self):
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        self.run_minter()
        ping = self.ping_for("bridge-drain")
        self.assertEqual(ping["kind"], "agent-due")
        self.assertEqual(ping["body_ref"], "bodies/bridge-drain.md")
        self.assertEqual(ping["detail"], {"items": 1})

    def test_unresolved_only_queue_never_escalates(self):
        self.plant(record("r3", "chat_list", "local-test-watch"))
        lines = self.run_minter()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("UNRESOLVED r3 "))
        self.assertEqual(self.pending(), [])

    def test_escalation_counts_resolvable_only(self):
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        self.plant(record("r3", "chat_list", "local-test-watch"))
        lines = self.run_minter()
        self.assertIn("DRAIN items=1", lines)
        self.assertEqual(
            self.ping_for("bridge-drain")["detail"], {"items": 1})

    def test_drain_ping_carries_the_configured_home_chat(self):
        with open(self.owners_path, "w", encoding="utf-8") as fh:
            fh.write("version: 1\ndrain:\n"
                     f"  chat: \"{CHAT}\"\nowners:\n"
                     "  sweeper-venue:\n"
                     f"    chat: \"{OWNER_CHAT}\"\n")
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        self.run_minter()
        self.assertEqual(self.ping_for("bridge-drain")["detail"],
                         {"items": 1, "target_chat": CHAT})

    def test_episode_rearms_after_drain_ack_and_empty_queue(self):
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"}))
        self.run_minter()
        # The executor drains the item and acks both pings
        # with the queue empty: the episode closes.
        self.outbox.ack(self.ping_for("bridge-wake-r1")["id"])
        self.outbox.ack(self.ping_for("bridge-drain")["id"])
        self.plant(record("r1", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "hello"},
                          status="done"))
        self.assertEqual(self.run_minter(), [])
        # A fresh item opens a fresh episode.
        self.plant(record("r2", "chat_send", "sweeper-venue",
                          {"chat_id": CHAT, "text": "again"}))
        lines = self.run_minter()
        self.assertIn("DRAIN items=1", lines)


if __name__ == "__main__":
    unittest.main()
