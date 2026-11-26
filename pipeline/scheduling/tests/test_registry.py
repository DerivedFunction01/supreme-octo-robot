import os
import tempfile
import unittest

from server import registry
from tests.helpers import agent_yaml, scripted_yaml, write_body


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jobs = os.path.join(self.tmp, "jobs")
        self.bodies = os.path.join(self.tmp, "bodies")
        os.makedirs(self.jobs)
        os.makedirs(self.bodies)

    def _load(self, job_id, text):
        with open(os.path.join(self.jobs, f"{job_id}.yaml"), "w", encoding="utf-8") as fh:
            fh.write(text)
        return registry.load_dir(self.jobs, self.tmp)

    def test_valid_scripted_and_agent(self):
        script = os.path.join(self.tmp, "job.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("pass\n")
        entries, errors = self._load("job-a", scripted_yaml("job-a", script))
        self.assertEqual(errors, [])
        self.assertEqual(entries["job-a"].kind, "scripted")
        write_body(self.tmp, "job-b")
        entries, errors = self._load("job-b", agent_yaml("job-b"))
        self.assertEqual(errors, [])
        self.assertEqual(entries["job-b"].kind, "agent")

    def test_rejects_id_mismatch(self):
        script = os.path.join(self.tmp, "job.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("pass\n")
        entries, errors = self._load("job-a", scripted_yaml("job-other", script))
        self.assertEqual(entries, {})
        self.assertTrue(any("does not match" in e for e in errors))

    def test_rejects_missing_timeout(self):
        text = scripted_yaml("job-a", "/bin/true").replace("timeout_secs: 10\n", "")
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("timeout_secs" in e for e in errors))

    def test_rejects_secret_shaped_value(self):
        text = scripted_yaml("job-a", "/bin/true").replace(
            "classification: test fixture", "classification: uses api_key: hunter2hunter2")
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("secret-shaped" in e for e in errors))

    def test_rejects_shell_without_reason(self):
        text = (
            "id: job-a\ntitle: T\nkind: scripted\ncadence:\n  type: interval\n  every: 5m\n"
            "owner: goal:test-goal\nrun:\n  shell: true\n  argv: echo hi\n"
            "timeout_secs: 10\nstate_paths: []\nclassification: fixture\n"
        )
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("shell_reason" in e for e in errors))

    def test_rejects_unknown_field(self):
        text = scripted_yaml("job-a", "/bin/true") + "bogus_field: 1\n"
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("unknown fields" in e for e in errors))

    def test_rejects_migration_field_family(self):
        # Contract 14 (amendment 3): the family does not exist
        # in this format — an entry carrying one is
        # unknown-field invalid, like any unlisted field.
        for field in ("migrated: true", "migrated_at: 2026-11-08",
                      "migration_note: x", "proof_pending: true"):
            text = scripted_yaml("job-a", "/bin/true") + field + "\n"
            entries, errors = self._load("job-a", text)
            self.assertEqual(entries, {}, field)
            self.assertTrue(any("unknown fields" in e for e in errors), field)

    def test_rejects_bad_cadence_shape(self):
        text = scripted_yaml("job-a", "/bin/true").replace(
            "  every: 5m\n", "  every: 5m\n  at: '06:00'\n")
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("interval cadence" in e for e in errors))

    def test_rejects_agent_body_missing(self):
        entries, errors = self._load("job-b", agent_yaml("job-b"))
        self.assertEqual(entries, {})
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_anchors_expand_in_argv_and_state_paths(self):
        text = scripted_yaml("job-a", "/bin/true").replace(
            "state_paths: []", "state_paths:\n  - ${WS}/elsewhere/state.json\n")
        entries, errors = self._load("job-a", text)
        self.assertEqual(errors, [])
        entry = entries["job-a"]
        self.assertEqual(entry.data["run"]["argv"][0], "python3")
        self.assertEqual(entry.data["run"]["argv"][1], os.path.join(self.tmp, "true"))
        ws = os.path.dirname(self.tmp)
        self.assertEqual(entry.data["state_paths"], [os.path.join(ws, "elsewhere", "state.json")])

    def test_anchors_expand_in_run_cwd(self):
        text = scripted_yaml("job-a", "/bin/true").replace(
            "  argv:\n", "  cwd: ${WS}/elsewhere\n  argv:\n")
        entries, errors = self._load("job-a", text)
        self.assertEqual(errors, [])
        ws = os.path.dirname(self.tmp)
        self.assertEqual(entries["job-a"].data["run"]["cwd"],
                         os.path.join(ws, "elsewhere"))

    def test_rejects_absolute_path_in_run_cwd(self):
        text = scripted_yaml("job-a", "/bin/true").replace(
            "  argv:\n", "  cwd: /elsewhere\n  argv:\n")
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("not portable" in e for e in errors))

    def test_rejects_absolute_path_in_argv(self):
        text = scripted_yaml("job-a", "/bin/true").replace(
            "    - ${REPO}/true", "    - /bin/true")
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("not portable" in e for e in errors))

    def test_rejects_unanchored_relative_state_path(self):
        text = scripted_yaml("job-a", "/bin/true").replace(
            "state_paths: []", "state_paths:\n  - somewhere/state.json\n")
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("not portable" in e for e in errors))

    def test_rejects_suspension_without_reason(self):
        text = scripted_yaml("job-a", "/bin/true").replace(
            "kind: scripted\n", "kind: scripted\nstatus: suspended\n")
        entries, errors = self._load("job-a", text)
        self.assertEqual(entries, {})
        self.assertTrue(any("suspend_reason" in e for e in errors))


class MachineSourceCase(unittest.TestCase):
    """The machine-form source stamp (wb-progress family):
    provenance for writer-rendered entries, distinct from the
    adoption form, with the fixture hold-out at load."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jobs = os.path.join(self.tmp, "jobs")
        os.makedirs(self.jobs)
        self.script = os.path.join(self.tmp, "job.py")
        with open(self.script, "w", encoding="utf-8") as fh:
            fh.write("pass\n")

    def _load(self, text, job_id="wb-progress-demo-t-1"):
        with open(os.path.join(self.jobs, f"{job_id}.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(text)
        return registry.load_dir(self.jobs, self.tmp)

    def _stamped(self, source_class="project", origin="machine", extra_source=""):
        base = scripted_yaml("wb-progress-demo-t-1", self.script)
        return base + (
            "catalog:\n"
            f"  origin: {origin}\n"
            "  generality: deployment-specific\n"
            "  use_case: work-tracking\n"
            "source:\n"
            "  writer: workbench-harness\n"
            "  project: demo\n"
            "  todo: t-1\n"
            f"  source_class: {source_class}\n"
            f"{extra_source}"
        )

    def test_machine_stamp_loads(self):
        entries, errors = self._load(self._stamped())
        self.assertEqual(errors, [])
        self.assertIn("wb-progress-demo-t-1", entries)

    def test_fixture_class_is_held_out(self):
        entries, errors = self._load(self._stamped(source_class="fixture"))
        self.assertEqual(entries, {})
        self.assertTrue(any("held out" in e for e in errors), errors)

    def test_machine_stamp_requires_machine_origin(self):
        entries, errors = self._load(self._stamped(origin="hand"))
        self.assertEqual(entries, {})
        self.assertTrue(any("origin: machine" in e for e in errors), errors)

    def test_mixed_forms_rejected(self):
        entries, errors = self._load(
            self._stamped(extra_source="  catalog: example-x\n"))
        self.assertEqual(entries, {})
        self.assertTrue(any("unknown fields" in e or "neither" in e
                            for e in errors), errors)

    def test_adoption_form_still_loads(self):
        base = scripted_yaml("job-a", self.script)
        text = base + ("source:\n  catalog: example-storage-watch\n"
                       "  catalog_version: 1\n  parameters:\n"
                       "    owner: none\n")
        entries, errors = self._load(text, job_id="job-a")
        self.assertEqual(errors, [])
        self.assertIn("job-a", entries)


if __name__ == "__main__":
    unittest.main()
