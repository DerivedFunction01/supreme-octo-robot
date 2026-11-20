"""Formation-clone sweeper tests.

Fixture roots, a fixed injected now, fake proc roots and
fake results dirs — no live-root reads, no sleeps, no
timing dependence. NOW is 2026-11-17T12:00:00Z; the window
is the production 3600s.
"""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from ops.watches import clone_sweep as sweep

NOW = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)

OLD = "gate-job-20261117T090000Z"          # 3.0h old — reaped
JUST_PAST = "gate-job-20261117T105959Z"    # 3601s old — reaped
BOUNDARY = "gate-job-20261117T110000Z"     # exactly 3600s — kept
YOUNG = "gate-job-20261117T113000Z"        # 1800s old — kept

NEAR_MISSES = [
    "gate-job-20261301T000000Z",      # month 13
    "gate-job-20260230T000000Z",      # Feb 30
    "gate-job-20261117T250000Z",      # hour 25
    "gate-job-20261117T006000Z",      # minute 60
    "gate-job-20261117T150319",       # missing Z
    "gate-job-20261117T150319Z-x",    # timestamp mid-name
    "gate-job-20261117",              # date only
    "gate-job-20261117t150319z",      # lowercase t/z
    "gate-job-2026117T150319Z",       # 7-digit date
    "gate-job-20261117T15031Z",       # 5-digit time
    "sched-tmp-hold-20261117",        # the section-1 hold dir
    "bare-tree-proof",                # loose formation-era names
    "batch-gate-scratch",
    "UPPER-20261117T090000Z",         # uppercase prefix
    "-20261117T090000Z",              # empty prefix
]


def make_dir(root, name, marker=True):
    path = os.path.join(root, name)
    os.makedirs(path)
    if marker:
        with open(os.path.join(path, "clone-marker.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("clone\n")
    return path


def make_file(root, name):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("data\n")
    return path


class StampCase(unittest.TestCase):
    def test_good_stamp_parses(self):
        stamp = sweep.formation_stamp(OLD)
        self.assertEqual(
            stamp, datetime(2026, 11, 17, 9, 0, 0,
                            tzinfo=timezone.utc))

    def test_run_id_shaped_name_parses(self):
        # Run ids share the <job>-<stamp> shape; the pattern
        # admitting them is correct — run records themselves
        # live outside the scratch roots and are protected by
        # the non-terminal-record guard, not by the pattern.
        self.assertIsNotNone(sweep.formation_stamp(
            "workhorse-scratch-hygiene-proof-20261117T153827Z"))

    def test_near_misses_refuse(self):
        for name in NEAR_MISSES:
            self.assertIsNone(sweep.formation_stamp(name), name)

    def test_bundles_and_records_never_match(self):
        # Guard (3): bundles and run records are never
        # selected — their names carry no formation stamp.
        for name in ("tree.bundle", "gate.log", "checkpoint.json",
                     "heartbeat.log", "results", "xfers"):
            self.assertIsNone(sweep.formation_stamp(name), name)


class SweepCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="clone-sweep-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "tmp-gate")
        os.makedirs(self.root)

    def sweep(self, **kw):
        kw.setdefault("held_paths", set())
        kw.setdefault("record_texts", [])
        return sweep.run([self.root], NOW, **kw)

    def test_old_reaped_young_and_boundary_kept(self):
        old = make_dir(self.root, OLD)
        just = make_dir(self.root, JUST_PAST)
        boundary = make_dir(self.root, BOUNDARY)
        young = make_dir(self.root, YOUNG)
        code, lines = self.sweep()
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(old))
        self.assertFalse(os.path.exists(just))
        self.assertTrue(os.path.isdir(boundary))
        self.assertTrue(os.path.isdir(young))
        self.assertEqual(len(lines), 2)
        self.assertTrue(any("reaped" in ln and OLD in ln
                            for ln in lines))

    def test_nonmatching_untouched(self):
        kept = [make_dir(self.root, name) for name in NEAR_MISSES]
        code, lines = self.sweep()
        self.assertEqual((code, lines), (0, []))
        for path in kept:
            self.assertTrue(os.path.isdir(path), path)

    def test_matching_named_file_and_symlink_untouched(self):
        file_path = make_file(self.root, OLD)
        target = make_dir(self.root, "real-target")
        link = os.path.join(self.root, JUST_PAST)
        os.symlink(target, link)
        code, lines = self.sweep()
        self.assertEqual((code, lines), (0, []))
        self.assertTrue(os.path.isfile(file_path))
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.isdir(target))

    def test_fd_held_kept_then_reaped_when_released(self):
        held_dir = make_dir(self.root, OLD)
        inside = os.path.join(held_dir, "clone-marker.txt")
        code, lines = self.sweep(held_paths={inside})
        self.assertEqual((code, lines), (0, []))
        self.assertTrue(os.path.isdir(held_dir))
        code, lines = self.sweep(held_paths=set())
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(held_dir))
        self.assertEqual(len(lines), 1)

    def test_record_named_kept_terminal_record_no_protection(self):
        named = make_dir(self.root, OLD)
        other = make_dir(self.root, JUST_PAST)
        texts = ["cloned into '%s' ..." % named,
                 "cloned into '%s' ..." % other]
        code, lines = self.sweep(record_texts=texts[:1])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isdir(named))
        self.assertFalse(os.path.exists(other))

    def test_dry_run_lists_and_removes_nothing(self):
        old = make_dir(self.root, OLD)
        code, lines = self.sweep(dry_run=True,
                                 held_paths=set(),
                                 record_texts=[])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isdir(old))
        self.assertEqual(len(lines), 1)
        self.assertIn("would reap", lines[0])
        self.assertIn(OLD, lines[0])

    def test_dry_run_names_guard_keeps_apply_mode_silent(self):
        held_dir = make_dir(self.root, OLD)
        inside = os.path.join(held_dir, "clone-marker.txt")
        code, lines = self.sweep(dry_run=True, held_paths={inside})
        self.assertTrue(any("kept (live fd)" in ln for ln in lines))
        code, lines = self.sweep(held_paths={inside})
        self.assertEqual((code, lines), (0, []))
        self.assertTrue(os.path.isdir(held_dir))

    def test_unreadable_root_is_loud(self):
        missing = os.path.join(self.tmp, "no-such-root")
        code, lines = sweep.run([missing], NOW, held_paths=set(),
                                record_texts=[])
        self.assertEqual(code, 3)
        self.assertEqual(len(lines), 1)
        self.assertIn("root unreadable", lines[0])


class ProbeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="clone-sweep-probe-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "tmp-gate")
        os.makedirs(self.root)

    def test_fd_probe_reads_fake_proc(self):
        held_dir = make_dir(self.root, OLD)
        inside = os.path.join(held_dir, "clone-marker.txt")
        proc = os.path.join(self.tmp, "proc")
        fd_dir = os.path.join(proc, "4242", "fd")
        os.makedirs(fd_dir)
        os.symlink(inside, os.path.join(fd_dir, "3"))
        os.symlink("/nonexistent/elsewhere",
                   os.path.join(fd_dir, "4"))
        os.makedirs(os.path.join(proc, "self", "fd"))
        held = sweep.fd_held_paths(proc)
        self.assertIn(inside, held)
        code, lines = sweep.run([self.root], NOW, proc_root=proc,
                                record_texts=[])
        self.assertEqual((code, lines), (0, []))
        self.assertTrue(os.path.isdir(held_dir))

    def test_record_probe_reads_fake_results(self):
        named = make_dir(self.root, OLD)
        stale = make_dir(self.root, JUST_PAST)
        results = os.path.join(self.tmp, "results")
        live = os.path.join(results, "run-live")
        os.makedirs(live)
        with open(os.path.join(live, "checkpoint.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"completed_units": 0}, fh)
        with open(os.path.join(live, "gate.log"), "w",
                  encoding="utf-8") as fh:
            fh.write("cloned HEAD into %s\n" % named)
        done = os.path.join(results, "run-done")
        os.makedirs(done)
        with open(os.path.join(done, "checkpoint.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"completed_units": 1, "exit_code": 0}, fh)
        with open(os.path.join(done, "gate.log"), "w",
                  encoding="utf-8") as fh:
            fh.write("cloned HEAD into %s\n" % stale)
        texts = sweep.nonterminal_record_texts(results)
        self.assertTrue(any(named in t for t in texts))
        self.assertFalse(any(stale in t for t in texts))
        code, lines = sweep.run([self.root], NOW, held_paths=set(),
                                results_dir=results)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isdir(named))
        self.assertFalse(os.path.exists(stale))


if __name__ == "__main__":
    unittest.main()
