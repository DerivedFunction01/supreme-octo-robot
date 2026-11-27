import json
import os
import tempfile
import unittest

from ops.watches import load_venue_watch as watch

LIVENESS = """id: venue-liveness-{full}
title: 'Liveness check - Colab session {full}'
kind: scripted
status: active
run:
  argv:
    - python3
    - ${{REPO}}/../venue/bin/venue-liveness
    - {full}
"""

T0 = "2026-11-24T00:00:00Z"
T1 = "2026-11-24T00:05:00Z"
T2 = "2026-11-24T00:16:00Z"
T3 = "2026-11-24T00:20:00Z"
T4 = "2026-11-24T00:21:00Z"


def write_jobs(root, full_ids):
    os.makedirs(root, exist_ok=True)
    for name in os.listdir(root):
        if name.startswith("venue-liveness-") \
                and name.endswith(".yaml"):
            os.unlink(os.path.join(root, name))
    for full in full_ids:
        with open(os.path.join(
                root, "venue-liveness-%s.yaml" % full), "w",
                encoding="utf-8") as fh:
            fh.write(LIVENESS.format(full=full))
    with open(os.path.join(root, "some-other-job.yaml"), "w",
              encoding="utf-8") as fh:
        fh.write("id: some-other-job\n")


def row(pid, ticks, cwd, argv):
    return {"pid": pid, "ppid": 1, "argv": argv, "cwd": cwd,
            "utime": ticks, "stime": 0, "starttime": 100,
            "rss_kb": 1024}


class LoadVenueWatchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.jobs = os.path.join(self.tmp, "jobs")
        self.workspace = os.path.join(self.tmp, "ws")
        self.repo = os.path.join(self.workspace, "repo-a")
        os.makedirs(os.path.join(self.repo, "sub"))
        self.old_snapshot = watch.SNAPSHOT
        watch.SNAPSHOT = os.path.join(self.tmp, "snapshot.json")
        self.routes = {
            "threads": {self.repo: {"label": "thread-a"}},
            "service_patterns": [], "main": None}
        busy_a = row(4242, 0, os.path.join(self.repo, "sub"),
                     ["python3", "check.py", "scheduling"])
        busy_b = row(4242, 300, os.path.join(self.repo, "sub"),
                     ["python3", "check.py", "scheduling"])
        self.tables = ([busy_a], [busy_b])

    def tearDown(self):
        watch.SNAPSHOT = self.old_snapshot

    def cycle(self, load1, cpus=2, at=T0,
              fleet=("solar-falcon-70-r111",), msi_live=True):
        write_jobs(self.jobs, fleet)
        sessions = watch.live_sessions(self.jobs)
        return watch.run(
            "/nonexistent", load1=load1, cpus=cpus,
            sessions=sessions, tables=self.tables, elapsed_s=3.0,
            msi_live=msi_live, routes=self.routes,
            workspace=self.workspace, at=at)

    def store(self):
        with open(watch.SNAPSHOT, encoding="utf-8") as fh:
            return json.load(fh)

    def test_over_threshold_speaks_naming_process_and_venues(self):
        code, lines = self.cycle(8.5)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(
            "LOAD-MONITOR load1=8.5 cpus=2 threshold=4"))
        self.assertIn("pid=4242", lines[0])
        self.assertIn("check.py", lines[0])
        self.assertIn("repo=repo-a", lines[0])
        self.assertIn("thread=thread-a", lines[0])
        self.assertIn("msi:local", lines[0])
        self.assertIn("colab:solar-falcon-70", lines[0])
        self.assertNotIn("r111", lines[0])

    def test_snapshot_written_every_cycle(self):
        self.cycle(8.5)
        store = self.store()
        snap = store["current"]
        self.assertEqual(snap["load"][0], 8.5)
        self.assertEqual(snap["cpus"], 2)
        self.assertEqual(snap["processes"][0]["pid"], 4242)
        self.assertEqual(snap["processes"][0]["repo"], "repo-a")
        self.assertEqual(
            snap["processes"][0]["thread"], "thread-a")
        kinds = [(v["kind"], v["name"], v["live"])
                 for v in snap["venues"]]
        self.assertIn(("msi", "local", True), kinds)
        self.assertIn(("colab", "solar-falcon-70", True), kinds)
        self.assertTrue(snap["episode"]["open"])
        self.assertEqual(snap["episode"]["opened_at"], T0)
        self.assertEqual(len(store["recent"]), 1)
        # A calm cycle still writes the store and closes.
        self.cycle(1.0, at=T1)
        snap = self.store()["current"]
        self.assertFalse(snap["episode"]["open"])
        self.assertEqual(len(self.store()["recent"]), 1)

    def test_continuing_episode_silent_until_respeak(self):
        self.cycle(8.5, at=T0)
        code, lines = self.cycle(9.25, at=T1)
        self.assertEqual((code, lines), (0, []))
        code, lines = self.cycle(9.25, at=T2)
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            self.store()["current"]["episode"]["last_spoke_at"], T2)

    def test_close_then_rise_speaks_again(self):
        self.cycle(8.5, at=T0)
        code, lines = self.cycle(1.0, at=T1)
        self.assertEqual((code, lines), (0, []))
        code, lines = self.cycle(7.0, at=T3)
        self.assertEqual(len(lines), 1)

    def test_stale_stuck_open_state_does_not_suppress(self):
        stale = {"stamp": "2026-11-16T00:00:00Z",
                 "episode": {"open": True,
                             "opened_at": "2026-11-16T00:00:00Z",
                             "last_spoke_at":
                                 "2026-11-16T00:00:00Z"}}
        os.makedirs(self.tmp, exist_ok=True)
        with open(watch.SNAPSHOT, "w", encoding="utf-8") as fh:
            json.dump({"current": stale, "recent": []}, fh)
        code, lines = self.cycle(8.5, at=T0)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)

    def test_no_live_venue_still_opens_and_speaks(self):
        code, lines = self.cycle(40.0, fleet=(), msi_live=False)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("live venues: none", lines[0])
        venues = self.store()["current"]["venues"]
        self.assertEqual(venues, [{"kind": "msi", "name": "local",
                                   "live": False,
                                   "in_flight": None}])

    def test_at_threshold_is_silent(self):
        # Threshold is LOAD_FACTOR (2.0) x cpus = 4: at or
        # below stays silent.
        code, lines = self.cycle(4.0)
        self.assertEqual((code, lines), (0, []))
        code, lines = self.cycle(2.0, at=T1)
        self.assertEqual((code, lines), (0, []))

    def test_proc_unreadable_exits_3(self):
        code, lines = watch.run(
            os.path.join(self.tmp, "no-proc"),
            jobs_dir=self.jobs, at=T0, interval_s=0,
            sleep=lambda s: None)
        self.assertEqual(code, 3)
        self.assertEqual(len(lines), 1)

    def test_injected_values_are_deterministic(self):
        code, lines = watch.run(
            "/nonexistent", load1=8.5, cpus=2,
            sessions=["solar-falcon-70"], tables=([], []),
            elapsed_s=3.0, msi_live=False, routes=self.routes,
            workspace=self.workspace, at=T0)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("load1=8.5 cpus=2", lines[0])
        self.assertIn("solar-falcon-70", lines[0])

    def test_session_name_falls_back_to_filename(self):
        path = os.path.join(self.jobs, "gone.yaml")
        name = watch.session_name(
            path, "venue-liveness-ember-petal-28-r999.yaml")
        self.assertEqual(name, "ember-petal-28")


if __name__ == "__main__":
    unittest.main()
