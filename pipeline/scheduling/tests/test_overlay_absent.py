"""The overlay-absent body state: validate() serves two
contexts. A clean checkout carries no bodies/ directory at
all (the live overlay is gitignored working state), so a
body reference into the absent overlay is a named, countable
state — the entry validates, the reference is recorded on
it, and the validate/census verbs report it. A body missing
from a present overlay is a defect and fails, and the
server's load context (require_bodies=True) fails on a
missing body however the overlay stands."""
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from cli import registry_cmds
from server import registry
from tests.helpers import agent_yaml, scripted_yaml, write_entry


class OverlayAbsentLoadCase(unittest.TestCase):
    """Load-layer contexts: the fixture home is built with a
    jobs/ dir and NO bodies/ dir — the clean-clone shape."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jobs = os.path.join(self.tmp, "jobs")
        os.makedirs(self.jobs)
        self.script = os.path.join(self.tmp, "job.py")
        with open(self.script, "w", encoding="utf-8") as fh:
            fh.write("pass\n")

    def _scripted_with_escalation(self, job_id="job-a"):
        return scripted_yaml(
            job_id, self.script,
            extra="escalate_body: bodies/job-a-escalation.md\n")

    def test_agent_body_overlay_absent_loads_and_is_named(self):
        write_entry(self.tmp, "job-b", agent_yaml("job-b"))
        entries, errors = registry.load_dir(self.jobs, self.tmp)
        self.assertEqual(errors, [])
        entry = entries["job-b"]
        self.assertEqual(entry.overlay_absent_bodies,
                         [("body", "bodies/job-b.md")])

    def test_escalate_body_overlay_absent_loads_and_is_named(self):
        write_entry(self.tmp, "job-a", self._scripted_with_escalation())
        entries, errors = registry.load_dir(self.jobs, self.tmp)
        self.assertEqual(errors, [])
        entry = entries["job-a"]
        self.assertEqual(entry.overlay_absent_bodies,
                         [("escalate_body", "bodies/job-a-escalation.md")])

    def test_present_body_records_no_absent_state(self):
        os.makedirs(os.path.join(self.tmp, "bodies"))
        with open(os.path.join(self.tmp, "bodies", "job-b.md"),
                  "w", encoding="utf-8") as fh:
            fh.write("Body.\n")
        write_entry(self.tmp, "job-b", agent_yaml("job-b"))
        entries, errors = registry.load_dir(self.jobs, self.tmp)
        self.assertEqual(errors, [])
        self.assertEqual(entries["job-b"].overlay_absent_bodies, [])

    def test_require_bodies_fails_in_absent_overlay(self):
        # The server's load context: a missing body is an
        # error even when the whole overlay is absent.
        write_entry(self.tmp, "job-b", agent_yaml("job-b"))
        write_entry(self.tmp, "job-a", self._scripted_with_escalation())
        entries, errors = registry.load_dir(
            self.jobs, self.tmp, require_bodies=True)
        self.assertEqual(entries, {})
        self.assertEqual(len(errors), 2)
        self.assertTrue(all("does not exist" in e for e in errors), errors)

    def test_missing_body_in_present_overlay_still_fails(self):
        # The overlay stands (an empty bodies/ dir) but the
        # referenced files are not in it: the live defect,
        # invalid under the default context too.
        os.makedirs(os.path.join(self.tmp, "bodies"))
        write_entry(self.tmp, "job-b", agent_yaml("job-b"))
        write_entry(self.tmp, "job-a", self._scripted_with_escalation())
        entries, errors = registry.load_dir(self.jobs, self.tmp)
        self.assertEqual(entries, {})
        self.assertEqual(len(errors), 2)
        self.assertTrue(all("does not exist" in e for e in errors), errors)


class OverlayAbsentVerbCase(unittest.TestCase):
    """The report verbs surface the named state and pass on
    the clean-clone shape; real errors still fail them."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jobs = os.path.join(self.tmp, "jobs")
        os.makedirs(self.jobs)
        write_entry(self.tmp, "job-b", agent_yaml("job-b"))
        self.entries, self.errors = registry.load_dir(self.jobs, self.tmp)
        assert self.errors == []

    def _run(self, verb, load_result):
        catalog = ({"version": 1, "rows": {}, "entries": {}}, [])
        with mock.patch.object(registry_cmds, "_load",
                               return_value=load_result), \
                mock.patch.object(registry_cmds.catalog_mod,
                                  "load_catalog", return_value=catalog), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = verb()
        return rc, buf.getvalue()

    def test_validate_passes_and_names_the_state(self):
        rc, out = self._run(registry_cmds.cmd_validate,
                            (self.entries, self.errors))
        self.assertEqual(rc, 0)
        self.assertIn("OVERLAY-ABSENT: job-b: body bodies/job-b.md", out)
        self.assertIn("1 overlay-absent body reference(s)", out)

    def test_census_passes_and_flags_the_row(self):
        rc, out = self._run(registry_cmds.cmd_census,
                            (self.entries, self.errors))
        self.assertEqual(rc, 0)
        self.assertIn("OVERLAY-ABSENT body: bodies/job-b.md", out)
        self.assertIn("1 overlay-absent body reference(s)", out)

    def test_verbs_still_fail_on_real_errors(self):
        bad = ({}, ["job-x.yaml: body file does not exist: bodies/job-x.md"])
        rc, _out = self._run(registry_cmds.cmd_validate, bad)
        self.assertEqual(rc, 1)
        rc, _out = self._run(registry_cmds.cmd_census, bad)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
