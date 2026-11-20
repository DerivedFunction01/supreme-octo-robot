import os
import tempfile
import unittest

from ops.watches import load_venue_watch as watch

LIVENESS = """id: colab-liveness-{full}
title: 'Liveness check - Colab session {full}'
kind: scripted
status: active
run:
  argv:
    - python3
    - ${{WS}}/supreme-octo-robot/pipeline/venue/bin/colab-liveness
    - {full}
"""


def write_proc(root, load1, cpus):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "loadavg"), "w",
              encoding="utf-8") as fh:
        fh.write("%.2f 1.00 1.00 1/100 999\n" % load1)
    with open(os.path.join(root, "cpuinfo"), "w",
              encoding="utf-8") as fh:
        for i in range(cpus):
            fh.write("processor\t: %d\nmodel name\t: fake\n\n" % i)


def write_jobs(root, full_ids):
    os.makedirs(root, exist_ok=True)
    # Each cycle re-renders the registry as the lease core
    # does: an entry stands only while its session is live
    # and is removed at lease end, so a fleet that leaves
    # takes its entries with it.
    for name in os.listdir(root):
        if name.startswith("colab-liveness-") \
                and name.endswith(".yaml"):
            os.unlink(os.path.join(root, name))
    for full in full_ids:
        with open(os.path.join(
                root, "colab-liveness-%s.yaml" % full), "w",
                encoding="utf-8") as fh:
            fh.write(LIVENESS.format(full=full))
    # A non-liveness entry standing in the same dir is ignored.
    with open(os.path.join(root, "some-other-job.yaml"), "w",
              encoding="utf-8") as fh:
        fh.write("id: some-other-job\n")


class LoadVenueWatchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proc = os.path.join(self.tmp, "proc")
        self.jobs = os.path.join(self.tmp, "jobs")
        self.old = watch.STATE
        watch.STATE = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        watch.STATE = self.old

    def cycle(self, load1, cpus=2,
              fleet=("solar-falcon-70-r111", "flint-shore-39-r222")):
        write_proc(self.proc, load1, cpus)
        write_jobs(self.jobs, fleet)
        return watch.run(self.proc, jobs_dir=self.jobs, at="T")

    def test_over_threshold_with_fleet_speaks_once_naming_both(self):
        code, lines = self.cycle(8.5)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(
            "LOAD-VENUE load1=8.5 cpus=2"))
        self.assertIn("solar-falcon-70", lines[0])
        self.assertIn("flint-shore-39", lines[0])
        # The lease-run suffixes are not part of the names.
        self.assertNotIn("r111", lines[0])
        self.assertNotIn("r222", lines[0])
        self.assertIn("Local checks and code belong on the "
                      "venue while the fleet is live.", lines[0])

    def test_continuing_episode_stays_silent(self):
        self.cycle(8.5)
        code, lines = self.cycle(9.25)
        self.assertEqual((code, lines), (0, []))

    def test_close_then_rise_speaks_again(self):
        self.cycle(8.5)
        code, lines = self.cycle(1.0)
        self.assertEqual((code, lines), (0, []))
        code, lines = self.cycle(7.0)
        self.assertEqual(len(lines), 1)
        self.assertIn("solar-falcon-70", lines[0])

    def test_episode_closes_when_fleet_leaves(self):
        self.cycle(8.5)
        code, lines = self.cycle(8.5, fleet=())
        self.assertEqual((code, lines), (0, []))
        code, lines = self.cycle(8.5)
        self.assertEqual(len(lines), 1)

    def test_no_fleet_always_silent(self):
        code, lines = self.cycle(40.0, fleet=())
        self.assertEqual((code, lines), (0, []))

    def test_under_threshold_silent(self):
        code, lines = self.cycle(2.0)
        self.assertEqual((code, lines), (0, []))
        code, lines = self.cycle(0.5)
        self.assertEqual((code, lines), (0, []))

    def test_proc_unreadable_exits_3(self):
        code, lines = watch.run(os.path.join(self.tmp, "no-proc"),
                                jobs_dir=self.jobs, at="T")
        self.assertEqual(code, 3)
        self.assertEqual(len(lines), 1)

    def test_injected_values_are_deterministic(self):
        code, lines = watch.run(
            "/nonexistent", load1=3.5, cpus=2,
            sessions=["solar-falcon-70"], at="T")
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("load1=3.5 cpus=2", lines[0])
        self.assertIn("solar-falcon-70", lines[0])

    def test_session_name_falls_back_to_filename(self):
        path = os.path.join(self.jobs, "gone.yaml")
        name = watch.session_name(
            path, "colab-liveness-ember-petal-28-r999.yaml")
        self.assertEqual(name, "ember-petal-28")


if __name__ == "__main__":
    unittest.main()
