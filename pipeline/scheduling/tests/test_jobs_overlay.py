"""The jobs overlay: instance jobs live in the untracked
jobs-overlay/ sibling of the tracked jobs/ set and load
through the same validation; the tracked set loads alone
where no overlay stands, and an id in both sets is a named
error, never a shadow."""

import os
import tempfile
import unittest

from server import registry
from tests import helpers


class JobsOverlayCase(unittest.TestCase):
    def _fleet(self, tmp):
        helpers.make_home(tmp)
        jobs = os.path.join(tmp, "jobs")
        helpers.write_entry(tmp, "sys-job", helpers.scripted_yaml(
            "sys-job", helpers.write_script(tmp, "sys.sh", "exit 0\n")))
        return tmp, jobs

    def test_overlay_entry_loads_beside_the_tracked_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, jobs = self._fleet(tmp)
            overlay = os.path.join(tmp, "jobs-overlay")
            os.makedirs(overlay)
            with open(os.path.join(overlay, "instance-job.yaml"), "w",
                      encoding="utf-8") as fh:
                fh.write(helpers.scripted_yaml(
                    "instance-job",
                    helpers.write_script(tmp, "inst.sh", "exit 0\n")))
            entries, errors = registry.load_dir(jobs, home)
            self.assertEqual(errors, [])
            self.assertEqual(sorted(entries), ["instance-job", "sys-job"])

    def test_no_overlay_loads_the_tracked_set_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, jobs = self._fleet(tmp)
            entries, errors = registry.load_dir(jobs, home)
            self.assertEqual(errors, [])
            self.assertEqual(sorted(entries), ["sys-job"])

    def test_an_id_in_both_sets_is_a_named_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, jobs = self._fleet(tmp)
            overlay = os.path.join(tmp, "jobs-overlay")
            os.makedirs(overlay)
            with open(os.path.join(overlay, "sys-job.yaml"), "w",
                      encoding="utf-8") as fh:
                fh.write(helpers.scripted_yaml(
                    "sys-job",
                    helpers.write_script(tmp, "shadow.sh", "exit 0\n")))
            entries, errors = registry.load_dir(jobs, home)
            self.assertEqual(sorted(entries), ["sys-job"])
            self.assertEqual(len(errors), 1)
            self.assertIn("never", errors[0])
            self.assertIn("shadows", errors[0])


if __name__ == "__main__":
    unittest.main()
