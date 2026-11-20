import unittest

from ops.flap import flap_watch


def sample(verdict, placement="placed", denied=None):
    return {"arm": "cgroup", "verdict": verdict,
            "placement": placement, "core_denied": denied or []}


class TransitionsCase(unittest.TestCase):
    def test_baseline_adoption_is_silent(self):
        self.assertEqual(flap_watch.transitions(
            {}, {"cgroup": sample("down")}), [])

    def test_unchanged_is_silent(self):
        prev = {"cgroup": {"verdict": "down", "placement": "placed"}}
        self.assertEqual(flap_watch.transitions(
            prev, {"cgroup": sample("down")}), [])

    def test_verdict_change_reports(self):
        prev = {"cgroup": {"verdict": "down", "placement": "placed"}}
        changed = flap_watch.transitions(
            prev, {"cgroup": sample("mixed", denied=["python_write_new"])})
        self.assertEqual(len(changed), 1)
        report = flap_watch.render_report(
            changed, {"cgroup": changed[0][2]}, "2026-11-09T05:30:00Z")
        self.assertIn("cgroup arm: down -> mixed", report)
        self.assertIn("python_write_new", report)
        self.assertIn("Ground truth needed", report)

    def test_placement_change_reports(self):
        prev = {"cgroup": {"verdict": "down", "placement": "placed"}}
        failed = {"arm": "cgroup", "verdict": None,
                  "placement": "failed", "detail": "procs write: EPERM"}
        changed = flap_watch.transitions(prev, {"cgroup": failed})
        self.assertEqual(len(changed), 1)


class StateCase(unittest.TestCase):
    def test_missing_state_is_empty_baseline(self):
        import os
        import tempfile
        old = flap_watch.STATE
        try:
            flap_watch.STATE = os.path.join(
                tempfile.mkdtemp(), "nope.json")
            self.assertEqual(flap_watch.load_state(), {"arms": {}})
        finally:
            flap_watch.STATE = old


if __name__ == "__main__":
    unittest.main()
