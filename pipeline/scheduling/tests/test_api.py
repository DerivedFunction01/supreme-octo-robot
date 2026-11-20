import os
import tempfile
import unittest
from datetime import timedelta

from server.firing.engine import Engine
from server.serving import api
from tests.helpers import (T0, Clock, agent_yaml, make_home, scripted_yaml,
                           write_body, write_entry)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.values, self.sources = make_home(self.tmp)
        self.clock = Clock(T0)

    def engine_with_job(self):
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", "/bin/true"))
        return Engine(self.values, now_fn=self.clock, inline=True)

    def test_outcome_labels(self):
        self.assertEqual(api.outcome_label({"status": "ok", "exit_code": 0}),
                         "OK")
        # an accepted non-zero exit is normal, never a failure
        self.assertEqual(api.outcome_label({"status": "ok", "exit_code": 1}),
                         "Exit 1 · normal")
        self.assertEqual(api.outcome_label({"status": "failure",
                                            "exit_code": 2}),
                         "Failed · exit 2")
        self.assertEqual(api.outcome_label({"status": "timeout"}),
                         "Timed out")

    def test_job_view_no_runs_is_honest_null(self):
        engine = self.engine_with_job()
        view = api.job_view(engine, engine.entries["job-a"], self.clock())
        self.assertIsNone(view["last_run"])
        self.assertEqual(view["runs_24h"], {"total": 0, "ok": 0, "failed": 0})
        self.assertEqual(view["failure_streak"], 0)
        self.assertIsNotNone(view["next_due"])  # seeded at rescan

    def test_failure_streak_and_24h_counts(self):
        engine = self.engine_with_job()
        for status in ("ok", "failure", "timeout"):
            engine.ledger.record("run", job_id="job-a", status=status,
                                 exit_code=1, due="x")
        view = api.job_view(engine, engine.entries["job-a"], self.clock())
        self.assertEqual(view["failure_streak"], 2)
        self.assertEqual(view["runs_24h"]["failed"], 2)
        self.assertEqual(view["last_run"]["label"], "Timed out")

    def test_overview_storage_and_totals(self):
        engine = self.engine_with_job()
        engine.ledger.record("run", job_id="job-a", status="ok", exit_code=0)
        engine.ledger.record("ping_woken", job_id="job-a", ping_id="p1")
        data = api.overview(engine, self.clock())
        self.assertEqual(data["registry"]["total"], 1)
        # presence is admission: the one entry is a migrated
        # entry, so the restored count is the total
        self.assertEqual(data["registry"]["migrated"], 1)
        self.assertEqual(data["totals_24h"]["runs"], 1)
        self.assertEqual(data["totals_24h"]["wakeups_served"], 1)
        self.assertEqual(data["storage"]["kind"], "sqlite")
        self.assertGreaterEqual(data["storage"]["events"], 2)
        self.assertIn("served_at", data)

    def test_overview_totals_match_direct_counts(self):
        # The overview's 24h totals ride one grouped pass;
        # pin them against the direct per-counter counts on a
        # seeded mix (every failure status, a status-less run,
        # records outside the window, one on the boundary).
        from datetime import datetime, timedelta, timezone
        from dispatch.ledger import iso
        engine = self.engine_with_job()
        now = self.clock()
        epoch_24h = (now - timedelta(hours=24)).timestamp()

        def rec(ts, kind, **fields):
            r = {"ts": iso(ts), "kind": kind}
            r.update(fields)
            engine.ledger._insert(r)

        h = timedelta(hours=1)
        rec(now - h, "run", job_id="job-a", status="ok", exit_code=0)
        rec(now - 2 * h, "run", job_id="job-a", status="failure",
            exit_code=2)
        rec(now - 3 * h, "run", job_id="job-a", status="timeout")
        rec(now - 4 * h, "run", job_id="job-a", status="spawn_error")
        rec(now - 5 * h, "run", job_id="job-a", status=None)
        rec(now - 24 * h, "run", job_id="job-a", status="failure",
            exit_code=1)
        rec(now - 25 * h, "run", job_id="job-a", status="failure",
            exit_code=1)
        rec(now - h, "ping_woken", job_id="job-a", ping_id="p1")
        rec(now - 30 * h, "ping_woken", job_id="job-a", ping_id="p0")
        rec(now - h, "ping_created", job_id="job-a", ping_id="p2")
        ledger = engine.ledger
        expected = {
            "runs": ledger.count_since(epoch_24h, kinds=["run"]),
            "failures": sum(
                ledger.count_since(epoch_24h, kinds=["run"], statuses=[s])
                for s in api.FAILURE_STATUSES),
            "wakeups_served": ledger.count_since(
                epoch_24h, kinds=["ping_woken"]),
            "pings_created": ledger.count_since(
                epoch_24h, kinds=["ping_created"]),
        }
        self.assertEqual(expected, {"runs": 6, "failures": 4,
                                    "wakeups_served": 1,
                                    "pings_created": 1})
        data = api.overview(engine, now)
        self.assertEqual(data["totals_24h"], expected)

    def test_pings_oldest_first_and_overdue(self):
        engine = self.engine_with_job()
        engine.outbox.add_or_coalesce("job-a", self.clock(), "report",
                                      detail={"x": 1}, now=self.clock())
        self.clock.advance(seconds=7200)  # past the 1h ack timeout
        data = api.pings_list(engine, self.clock())
        self.assertEqual(len(data["pings"]), 1)
        self.assertTrue(data["pings"][0]["overdue"])
        self.assertGreater(data["pings"][0]["age_secs"], 3600)

    def test_job_detail_unknown_job(self):
        engine = self.engine_with_job()
        self.assertIsNone(api.job_detail(engine, "nope", self.clock()))

    def test_ledger_feed_detail_lines(self):
        engine = self.engine_with_job()
        engine.ledger.record("run", job_id="job-a", status="ok", exit_code=1,
                             matched_pattern="DRIFT")
        feed = api.ledger_feed(engine, self.clock())
        self.assertEqual(feed["events"][0]["detail"],
                         "Exit 1 · normal · matched DRIFT")


class AgentActivityCase(unittest.TestCase):
    """job_view for agent entries: the activity lifecycle
    (agent_due + ping ack state) served ready, since agent jobs
    never produce `run` records."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.values, self.sources = make_home(self.tmp)
        self.clock = Clock(T0)
        write_body(self.tmp, "job-b")
        write_entry(self.tmp, "job-b", agent_yaml("job-b"))
        self.engine = Engine(self.values, now_fn=self.clock, inline=True)

    def _view(self):
        return api.job_view(self.engine, self.engine.entries["job-b"],
                            self.clock())

    def _due_with_ping(self):
        self.engine.ledger.record("agent_due", job_id="job-b", due="x")
        self.engine.outbox.add_or_coalesce(
            "job-b", self.clock(), "agent-due",
            body_ref="bodies/job-b.md", now=self.clock())

    def test_no_dues_is_honest_null(self):
        view = self._view()
        self.assertIsNone(view["last_activity"])
        self.assertEqual(view["activity_24h"],
                         {"dues": 0, "acked": 0, "overdue": False})
        self.assertIsNone(view["last_run"])

    def test_pending_ping(self):
        self._due_with_ping()
        view = self._view()
        act = view["last_activity"]
        self.assertEqual(act["state"], "pending")
        self.assertEqual(act["label"], "Ping pending")
        self.assertEqual(act["tone"], "warn")
        self.assertEqual(view["activity_24h"]["dues"], 1)

    def test_overdue_ping(self):
        self._due_with_ping()
        self.clock.advance(seconds=7200)  # past the 1h ack timeout
        view = self._view()
        self.assertEqual(view["last_activity"]["state"], "overdue")
        self.assertEqual(view["last_activity"]["label"], "Past ack timeout")
        self.assertEqual(view["last_activity"]["tone"], "fail")
        self.assertTrue(view["activity_24h"]["overdue"])

    def test_acked_cycle(self):
        self._due_with_ping()
        ping = self.engine.outbox.pending()[0]
        self.engine.outbox.ack(ping["id"])
        view = self._view()
        act = view["last_activity"]
        self.assertEqual(act["state"], "acked")
        self.assertEqual(act["label"], "Served · acked")
        self.assertEqual(act["tone"], "ok")
        self.assertIsNotNone(act["acked_at"])
        self.assertEqual(view["activity_24h"]["acked"], 1)

    def test_detail_lists_recent_dues(self):
        self._due_with_ping()
        detail = api.job_detail(self.engine, "job-b", self.clock())
        self.assertEqual(len(detail["recent_dues"]), 1)
        self.assertEqual(detail["recent_runs"], [])

    def test_scripted_view_has_no_activity(self):
        write_entry(self.tmp, "job-a", scripted_yaml("job-a", "/bin/true"))
        engine = Engine(self.values, now_fn=self.clock, inline=True)
        view = api.job_view(engine, engine.entries["job-a"], self.clock())
        self.assertIsNone(view["last_activity"])
        self.assertIsNone(view["activity_24h"])


if __name__ == "__main__":
    unittest.main()
