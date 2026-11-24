import json
import os
import tempfile
import unittest

from ops.watches import load_snapshot
from ops.watches import proc_sample

TICKS = proc_sample.ticks_per_second()
PAGE_KB = proc_sample.page_size() // 1024


def write_proc(root, load=(9.0, 5.0, 2.0), cpus=2):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "loadavg"), "w",
              encoding="utf-8") as fh:
        fh.write("%.2f %.2f %.2f 1/100 999\n" % load)
    with open(os.path.join(root, "cpuinfo"), "w",
              encoding="utf-8") as fh:
        for i in range(cpus):
            fh.write("processor\t: %d\nmodel name\t: fake\n\n" % i)
    with open(os.path.join(root, "meminfo"), "w",
              encoding="utf-8") as fh:
        fh.write("MemTotal:        1000000 kB\n"
                 "MemFree:          100000 kB\n"
                 "MemAvailable:     250000 kB\n")
    with open(os.path.join(root, "uptime"), "w",
              encoding="utf-8") as fh:
        fh.write("1000.00 900.00\n")


def write_process(root, pid, argv, cwd, utime, stime=0,
                  starttime=None, rss_kb=2048):
    if starttime is None:
        starttime = 900 * TICKS
    pdir = os.path.join(root, str(pid))
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, "cmdline"), "wb") as fh:
        fh.write(b"\0".join(a.encode() for a in argv) + b"\0")
    os.symlink(cwd, os.path.join(pdir, "cwd"))
    rest = ["S", "1"] + ["0"] * 28
    rest[11] = str(utime)
    rest[12] = str(stime)
    rest[19] = str(starttime)
    rest[21] = str(rss_kb // PAGE_KB)
    with open(os.path.join(pdir, "stat"), "w",
              encoding="utf-8") as fh:
        fh.write("%d (fake) %s\n" % (pid, " ".join(rest)))


def row(pid, ticks, cwd, argv, starttime=None):
    if starttime is None:
        starttime = 900 * TICKS
    return {"pid": pid, "ppid": 1, "argv": argv, "cwd": cwd,
            "utime": ticks, "stime": 0,
            "starttime": starttime, "rss_kb": 2048}


class ProcSampleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proc = os.path.join(self.tmp, "proc")
        write_proc(self.proc)

    def test_reads_load_cpus_and_meminfo(self):
        self.assertEqual(
            proc_sample.read_loadavg(self.proc), (9.0, 5.0, 2.0))
        self.assertEqual(proc_sample.cpu_count(self.proc), 2)
        self.assertEqual(
            proc_sample.read_meminfo(self.proc),
            {"total_kb": 1000000, "available_kb": 250000,
             "used_kb": 750000})

    def test_process_table_and_cpu_percents(self):
        cwd = os.path.join(self.tmp, "cwd")
        os.makedirs(cwd)
        write_process(self.proc, 111, ["python3", "check.py"],
                      cwd, utime=100)
        table = proc_sample.read_process_table(self.proc)
        self.assertEqual(len(table), 1)
        entry = table[0]
        self.assertEqual(entry["pid"], 111)
        self.assertEqual(entry["ppid"], 1)
        self.assertEqual(entry["argv"], ["python3", "check.py"])
        self.assertEqual(entry["cwd"], cwd)
        self.assertEqual(entry["utime"], 100)
        self.assertEqual(entry["rss_kb"], 2048)
        later = [dict(entry, utime=100 + 3 * TICKS)]
        self.assertEqual(
            proc_sample.cpu_percents(table, later, 3.0, TICKS),
            {111: 100.0})
        # A changed starttime is a reused pid: no delta.
        reused = [dict(entry, starttime=entry["starttime"] + 1,
                       utime=100 + 3 * TICKS)]
        self.assertEqual(
            proc_sample.cpu_percents(table, reused, 3.0, TICKS),
            {})


class LoadSnapshotCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proc = os.path.join(self.tmp, "proc")
        write_proc(self.proc)
        self.workspace = os.path.join(self.tmp, "ws")
        self.repo = os.path.join(self.workspace, "repo-x")
        self.cwd = os.path.join(self.repo, "pkg")
        os.makedirs(self.cwd)
        self.routes = {
            "threads": {self.repo: {"label": "thread-x"}},
            "service_patterns": [], "main": None}
        self.venues = [
            {"kind": "msi", "name": "local", "live": True,
             "in_flight": None},
            {"kind": "colab", "name": "solar-falcon-70",
             "live": True, "in_flight": None}]
        self.episode = {"open": True,
                        "opened_at": "2026-11-24T00:00:00Z",
                        "last_spoke_at": "2026-11-24T00:00:00Z"}

    def build(self):
        busy = ["python3", "check.py", "scheduling"]
        idle = ["python3", "idle.py"]
        table_a = [row(111, 0, self.cwd, busy),
                   row(222, 0, self.cwd, idle)]
        table_b = [row(111, 3 * TICKS, self.cwd, busy),
                   row(222, 0, self.cwd, idle)]
        return load_snapshot.build_snapshot(
            self.proc, table_a, table_b, 3.0, self.venues,
            self.episode, workspace=self.workspace,
            routes=self.routes, at="2026-11-24T00:00:00Z",
            ticks=TICKS)

    def test_busy_process_first_with_repo_thread_load_venues(self):
        snap = self.build()
        self.assertEqual(snap["load"], [9.0, 5.0, 2.0])
        self.assertEqual(snap["cpus"], 2)
        self.assertEqual(snap["mem"]["used_kb"], 750000)
        top = snap["processes"][0]
        self.assertEqual(top["pid"], 111)
        self.assertEqual(top["cpu_pct"], 100.0)
        self.assertEqual(top["repo"], "repo-x")
        self.assertEqual(top["thread"], "thread-x")
        self.assertEqual(top["cwd"], self.cwd)
        self.assertEqual(top["elapsed_s"], 100.0)
        self.assertEqual(snap["processes"][1]["cpu_pct"], 0.0)
        kinds = {(v["kind"], v["name"]) for v in snap["venues"]}
        self.assertEqual(
            kinds, {("msi", "local"), ("colab", "solar-falcon-70")})
        self.assertTrue(snap["episode"]["open"])

    def test_write_store_ring_bounded_to_episodes(self):
        path = os.path.join(self.tmp, "store.json")
        snap = self.build()
        store = None
        for _ in range(15):
            store = load_snapshot.write_store(
                snap, path=path, store=store)
        self.assertEqual(store["current"], snap)
        self.assertEqual(len(store["recent"]), 12)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), store)
        calm = dict(snap, episode={
            "open": False, "opened_at": None,
            "last_spoke_at": None})
        store = load_snapshot.write_store(
            calm, path=path, store=store)
        self.assertEqual(store["current"], calm)
        self.assertEqual(len(store["recent"]), 12)

    def test_load_store_missing_file_is_empty(self):
        self.assertEqual(
            load_snapshot.load_store(
                os.path.join(self.tmp, "nope.json")),
            {"current": None, "recent": []})


if __name__ == "__main__":
    unittest.main()
