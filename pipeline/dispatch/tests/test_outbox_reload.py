"""Outbox reload keying and terminal retention (the
health-wedge cure): an operation re-reads the
file only when its stamp moved — another process's write
is still seen on the next operation — and a save prunes
terminal pings past the retention horizon while pending
and recent terminal pings stay.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import dispatch.outbox as outbox_mod
from dispatch.outbox import Outbox
from dispatch.stateio import write_json

UTC = timezone.utc


def _ping(pid, state, created, acked_at=None):
    ping = {
        "id": pid,
        "job_id": f"job-{pid}",
        "due": created,
        "kind": "agent-due",
        "body_ref": None,
        "detail": {},
        "created": created,
        "state": state,
        "coalesced_count": 1,
        "last_woken_at": None,
    }
    if acked_at is not None:
        ping["acked_at"] = acked_at
    return ping


class ReloadKeyingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dispatch-outbox-reload-")
        self.outbox = Outbox(self.tmp)

    def test_unchanged_file_is_not_reread(self):
        self.outbox.add_or_coalesce("job-a", datetime.now(UTC), "agent-due")
        reads = []
        original = outbox_mod.read_json

        def counting(path, default):
            reads.append(path)
            return original(path, default)

        outbox_mod.read_json = counting
        try:
            self.outbox.pending()
            self.outbox.depth()
            self.outbox.get("whatever")
        finally:
            outbox_mod.read_json = original
        self.assertEqual(reads, [])

    def test_external_write_is_seen_on_next_operation(self):
        other = Outbox(self.tmp)
        other.add_or_coalesce("job-b", datetime.now(UTC), "escalation")
        seen = {p["job_id"] for p in self.outbox.pending()}
        self.assertIn("job-b", seen)


class TerminalRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dispatch-outbox-retention-")
        self.outbox = Outbox(self.tmp)

    def test_save_prunes_expired_terminal_pings_only(self):
        now = datetime.now(UTC)
        old = (now - timedelta(days=30)).isoformat()
        recent = (now - timedelta(days=1)).isoformat()
        write_json(
            self.outbox.path,
            {
                "pings": [
                    _ping("pend-old", "pending", old),
                    _ping("ack-old", "acked", old, acked_at=old),
                    _ping("ack-recent", "acked", recent, acked_at=recent),
                    _ping("void-old", "void", old),
                    _ping("ack-undated", "acked", "not-a-stamp",
                          acked_at="not-a-stamp"),
                ]
            },
        )
        # A save (any mutation) applies the prune.
        new_ping, _created = self.outbox.add_or_coalesce(
            "job-new", now, "report")
        kept = {p["id"] for p in self.outbox.pending()}
        self.assertEqual(kept, {"pend-old", new_ping["id"]})
        remaining = {p["id"] for p in self.outbox._pings}
        self.assertEqual(
            remaining,
            {"pend-old", "ack-recent", "ack-undated", new_ping["id"]},
        )


if __name__ == "__main__":
    unittest.main()
