"""Agent-job admission: the executor rule and the unworked
naming.

An agent job's pings are minted by the server and worked
by somebody else — the server never runs the job. An agent
entry with no designated executing surface is therefore a
job whose pings no one is charged with working (the
retired gap-closure-sweep twin stood exactly so, its
occurrences coalescing unworked). Admission: kind agent
requires `executor`, naming the surface that claims and
works the pings; a placeholder value fails the same way.
Liveness: census names, by job, an agent job whose due
ping stands unclaimed past two of its cadences.
"""
import contextlib
import io
import os
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

from cli import registry_cmds
from dispatch.ledger import iso
from server import registry
from tests.helpers import (T0, agent_yaml, make_home, scripted_yaml,
                           seed_tracked_fleet, write_body, write_entry)

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(tmp):
    return registry.load_dir(os.path.join(tmp, "jobs"), tmp)


class AdmissionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        make_home(self.tmp)
        self.script = os.path.join(self.tmp, "job.py")
        with open(self.script, "w", encoding="utf-8") as fh:
            fh.write("pass\n")

    def _agent(self, job_id, extra=""):
        write_body(self.tmp, job_id)
        write_entry(self.tmp, job_id, agent_yaml(job_id, extra=extra))

    def test_agent_without_executor_does_not_arm(self):
        # The fixture helper writes a designated executor;
        # strip it to stand in the defect's own shape.
        write_body(self.tmp, "job-b")
        text = agent_yaml("job-b").replace(
            "executor: test-agent-surface\n", "")
        write_entry(self.tmp, "job-b", text)
        entries, errors = _load(self.tmp)
        self.assertNotIn("job-b", entries)
        self.assertEqual(len(errors), 1)
        self.assertIn("job-b.yaml", errors[0])
        self.assertIn("executor", errors[0])

    def test_agent_with_executor_validates(self):
        self._agent("job-b")
        entries, errors = _load(self.tmp)
        self.assertEqual(errors, [])
        self.assertEqual(entries["job-b"].executor, "test-agent-surface")

    def test_placeholder_executor_fails_like_an_absent_one(self):
        for value in ("TBD", "none", "agent"):
            with self.subTest(value=value):
                text = agent_yaml("job-b").replace(
                    "executor: test-agent-surface",
                    f"executor: {value}")
                write_body(self.tmp, "job-b")
                write_entry(self.tmp, "job-b", text)
                entries, errors = _load(self.tmp)
                self.assertNotIn("job-b", entries)
                self.assertEqual(len(errors), 1)
                self.assertIn("placeholder", errors[0])

    def test_scripted_without_executor_validates_as_before(self):
        write_entry(self.tmp, "job-a",
                    scripted_yaml("job-a", self.script))
        entries, errors = _load(self.tmp)
        self.assertEqual(errors, [])
        self.assertIn("job-a", entries)

    def test_validate_verb_refuses_the_unarmed_agent_job(self):
        write_body(self.tmp, "job-b")
        text = agent_yaml("job-b").replace(
            "executor: test-agent-surface\n", "")
        write_entry(self.tmp, "job-b", text)
        load_result = _load(self.tmp)
        catalog = ({"version": 1, "rows": {}, "entries": {}}, [])
        with mock.patch.object(registry_cmds, "_load",
                               return_value=load_result), \
                mock.patch.object(registry_cmds.catalog_mod,
                                  "load_catalog", return_value=catalog), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = registry_cmds.cmd_validate()
        self.assertEqual(rc, 1)
        self.assertIn("INVALID: job-b.yaml", buf.getvalue())
        self.assertIn("executor", buf.getvalue())


def _ping(job_id, ping_id, created, kind="agent-due", coalesced=1):
    return {"id": ping_id, "job_id": job_id, "kind": kind,
            "created": iso(created), "coalesced_count": coalesced,
            "state": "pending", "due": iso(created),
            "body_ref": None, "detail": {}, "last_woken_at": None}


class LivenessCase(unittest.TestCase):
    """Seeded ping state against the pure naming core and
    the census verb that surfaces it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        make_home(self.tmp)
        self.script = os.path.join(self.tmp, "job.py")
        with open(self.script, "w", encoding="utf-8") as fh:
            fh.write("pass\n")
        write_body(self.tmp, "job-b")
        write_entry(self.tmp, "job-b", agent_yaml("job-b", every="1h"))
        write_body(self.tmp, "job-c")
        write_entry(self.tmp, "job-c", agent_yaml(
            "job-c", every="1h",
            extra="status: suspended\n"
                  "suspend_reason: test pause\n"
                  "suspended_on: 2026-10-31\n"))
        write_entry(self.tmp, "job-a",
                    scripted_yaml("job-a", self.script))
        self.entries, errors = _load(self.tmp)
        assert errors == [], errors
        self.now = T0 + timedelta(hours=6)

    def test_ping_past_two_cadences_is_named(self):
        stale = _ping("job-b", "ping-stale",
                      T0 + timedelta(hours=2, minutes=30), coalesced=7)
        lines = registry_cmds.unworked_agent_pings(
            self.entries, [stale], self.now)
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertTrue(line.startswith("UNWORKED: job-b:"), line)
        self.assertIn("ping-stale", line)
        self.assertIn("coalesced 7", line)
        self.assertIn("test-agent-surface", line)

    def test_ping_inside_two_cadences_is_silent(self):
        fresh = _ping("job-b", "ping-fresh", T0 + timedelta(hours=4, minutes=30))
        edge = _ping("job-b", "ping-edge", T0 + timedelta(hours=4))
        self.assertEqual(registry_cmds.unworked_agent_pings(
            self.entries, [fresh], self.now), [])
        self.assertEqual(registry_cmds.unworked_agent_pings(
            self.entries, [edge], self.now), [])

    def test_script_jobs_and_other_kinds_are_never_named(self):
        script_ping = _ping("job-a", "ping-script", T0)
        report_ping = _ping("job-b", "ping-report", T0, kind="report")
        suspended_ping = _ping("job-c", "ping-susp", T0)
        self.assertEqual(registry_cmds.unworked_agent_pings(
            self.entries, [script_ping, report_ping, suspended_ping],
            self.now), [])

    def test_census_surfaces_the_defect_and_fails(self):
        stale = _ping("job-b", "ping-stale",
                      T0 + timedelta(hours=2, minutes=30), coalesced=7)
        with mock.patch.object(registry_cmds, "_load",
                               return_value=(self.entries, [])), \
                mock.patch.object(registry_cmds, "_pending_pings",
                                  return_value=[stale]), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = registry_cmds.cmd_census(now=self.now)
        self.assertEqual(rc, 1)
        out = buf.getvalue()
        self.assertIn("UNWORKED: job-b:", out)
        self.assertIn("1 unworked agent ping(s)", out)

    def test_census_is_silent_inside_two_cadences(self):
        fresh = _ping("job-b", "ping-fresh", T0 + timedelta(hours=5))
        with mock.patch.object(registry_cmds, "_load",
                               return_value=(self.entries, [])), \
                mock.patch.object(registry_cmds, "_pending_pings",
                                  return_value=[fresh]), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = registry_cmds.cmd_census(now=self.now)
        self.assertEqual(rc, 0)
        self.assertNotIn("UNWORKED", buf.getvalue())


class LiveCensusCase(unittest.TestCase):
    """The tracked fleet's post-census state, as the census
    of the two live agent jobs resolved it (evidence in the
    commissioning record): bridge-drain's pings are
    addressed by the bridge minter to a designated drain
    home — the main chat, registered as `drain` in the
    bridge-wake owners config — and that surface claimed
    and acked them, so the entry names it and arms;
    declaration-reconcile had no designated executing
    surface anywhere in evidence and was retired to its
    Muse cron twin (the register records it in
    jobs/RETIRED.md), so it stands in neither the fleet
    nor the refusals."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tracked_ids = seed_tracked_fleet(self.tmp, PKG_ROOT)
        self.entries, self.errors = _load(self.tmp)

    def test_tracked_agent_set_is_exactly_bridge_drain(self):
        agents = set()
        for job_id in self.tracked_ids:
            path = os.path.join(self.tmp, "jobs", f"{job_id}.yaml")
            with open(path, encoding="utf-8") as fh:
                if "\nkind: agent\n" in "\n" + fh.read():
                    agents.add(job_id)
        self.assertEqual(agents, {"bridge-drain"})

    def test_bridge_drain_arms_with_its_designated_executor(self):
        entry = self.entries["bridge-drain"]
        self.assertEqual(entry.executor,
                         "main chat (bridge-wake owners drain)")

    def test_no_tracked_entry_stands_refused(self):
        self.assertNotIn("declaration-reconcile", self.entries)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
