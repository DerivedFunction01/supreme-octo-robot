"""Ingest pins for the tail stack (S-5 and the
routing-422 cure), which landed proven only live
(re-gate finding 2, 2026-11-16): report pings upsert
agent-clearable items on @workhorse keyed ping:<id>,
clear when the ping leaves the pending set, and never
resurrect a closed item; the scheduler client raises
SchedulerUnavailable on failure; a malformed routing
is refused with the failing half named. Fixture state
only — the store seam's empty state, built in memory;
the scheduler read is a stubbed urlopen.
"""

import sys
import unittest
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.errors import Validation  # noqa: E402
from attention.infra import scheduler_client  # noqa: E402
from attention.infra import store as store_mod  # noqa: E402
from attention.services.writes import ingest  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)


def _ping(ping_id="p1", tail="all quiet\nFINDING: reports pooled unrouted"):
    return {
        "id": ping_id,
        "kind": "report",
        "job_id": "nightly-watch",
        "created": "2026-11-16T00:12:39+00:00",
        "detail": {"stdout_tail": tail, "stderr_tail": ""},
    }


class ReportPingIngestTests(unittest.TestCase):
    def setUp(self):
        self.state = store_mod.empty_state()

    def _items(self):
        return [
            i for i in self.state["items"] if i["handle"] == ingest.REPORT_PING_HANDLE
        ]

    def test_pending_report_ping_upserts_agent_clearable_item(self):
        changed = ingest.ingest_report_pings(self.state, [_ping()], NOW)
        self.assertTrue(changed)
        (item,) = self._items()
        self.assertEqual(item["id"], "@workhorse:ping:p1")
        self.assertEqual(item["kind"], "followup")
        self.assertEqual(item["need"], "agent_clearable")
        self.assertEqual(item["source_ref"], "ping:p1")
        self.assertEqual(item["triage"], "open")
        self.assertTrue(item["clears_at_source"])
        self.assertEqual(
            item["title"], "nightly-watch: FINDING: reports pooled unrouted"
        )

    def test_non_report_kinds_and_idless_pings_are_ignored(self):
        pings = [
            {**_ping("p2"), "kind": "warning"},
            {"kind": "report", "job_id": "nightly-watch", "detail": {}},
        ]
        changed = ingest.ingest_report_pings(self.state, pings, NOW)
        self.assertFalse(changed)
        self.assertEqual(self._items(), [])

    def test_reingest_is_idempotent_and_refreshes_the_title(self):
        ingest.ingest_report_pings(self.state, [_ping()], NOW)
        self.assertFalse(ingest.ingest_report_pings(self.state, [_ping()], NOW))
        changed = ingest.ingest_report_pings(
            self.state, [_ping(tail="FINDING: a second finding")], NOW
        )
        self.assertTrue(changed)
        (item,) = self._items()
        self.assertEqual(item["title"], "nightly-watch: FINDING: a second finding")

    def test_departed_ping_clears_its_item(self):
        ingest.ingest_report_pings(self.state, [_ping()], NOW)
        changed = ingest.ingest_report_pings(self.state, [], NOW)
        self.assertTrue(changed)
        (item,) = self._items()
        self.assertEqual(item["triage"], "done")

    def test_closed_item_never_resurrects(self):
        ingest.ingest_report_pings(self.state, [_ping()], NOW)
        ingest.ingest_report_pings(self.state, [], NOW)
        changed = ingest.ingest_report_pings(self.state, [_ping()], NOW)
        self.assertFalse(changed)
        (item,) = self._items()
        self.assertEqual(item["triage"], "done")


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class SchedulerClientTests(unittest.TestCase):
    def test_unreachable_scheduler_raises_unavailable(self):
        with mock.patch.object(
            urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with self.assertRaises(scheduler_client.SchedulerUnavailable):
                scheduler_client.fetch_pending_pings(Settings())

    def test_malformed_payload_raises_unavailable(self):
        with mock.patch.object(
            urllib.request,
            "urlopen",
            return_value=_FakeResponse(b'{"pings": {"not": "a list"}}'),
        ):
            with self.assertRaises(scheduler_client.SchedulerUnavailable):
                scheduler_client.fetch_pending_pings(Settings())

    def test_pending_pings_returned(self):
        body = b'{"pings": [{"id": "p1", "kind": "report"}]}'
        with mock.patch.object(
            urllib.request, "urlopen", return_value=_FakeResponse(body)
        ):
            pings = scheduler_client.fetch_pending_pings(Settings())
        self.assertEqual(pings, [{"id": "p1", "kind": "report"}])


class RoutingProblemTests(unittest.TestCase):
    def test_non_object_names_the_pair(self):
        self.assertEqual(
            ingest._routing_problem("workbench"),
            "must be an object naming workhorse and thread",
        )

    def test_bad_workhorse_names_the_set(self):
        problem = ingest._routing_problem({"workhorse": "nope", "thread": "t"})
        self.assertTrue(problem.startswith("workhorse must be one of: "))

    def test_missing_thread_names_the_missing_half(self):
        for routing in (
            {"workhorse": "workbench"},
            {"workhorse": "workbench", "thread": "  "},
        ):
            self.assertEqual(
                ingest._routing_problem(routing),
                "thread is required — the owning thread the routing notifies",
            )
            self.assertIsNone(ingest._routing(routing, NOW))

    def test_valid_pair_cleans(self):
        cleaned = ingest._routing({"workhorse": "workbench", "thread": "chat-1"}, NOW)
        self.assertEqual(cleaned["workhorse"], "workbench")
        self.assertEqual(cleaned["thread"], "chat-1")

    def test_upsert_refusal_carries_the_named_half(self):
        state = store_mod.empty_state()
        state["handlers"].append(
            {"handle": "@lane", "label": "Lane", "thread_id": "thread-lane"}
        )
        payload = {
            "handle": "@lane",
            "kind": "followup",
            "source_ref": "defect-1",
            "title": "A routed defect",
            "routing": {"workhorse": "workbench"},
        }
        with self.assertRaises(Validation) as ctx:
            ingest.upsert_item(state, payload, NOW)
        routing_errors = [
            e for e in ctx.exception.field_errors if e["field"] == "routing"
        ]
        self.assertEqual(
            [e["message"] for e in routing_errors],
            ["thread is required — the owning thread the routing notifies"],
        )


if __name__ == "__main__":
    unittest.main()
