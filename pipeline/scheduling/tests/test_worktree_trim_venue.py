"""Venue-form trim specimens (owner ruling:
the same trim system maintains the local venues' disk
under the identical rules). The fixture builds a fake
venue home — run trees, clones, bundles — and runs
ops/worktree_trim_venue.sh against it: caps bind every
surface, dirty clones auto-commit in place before
ranking, a failed auto-commit is reported by name and
its clone is never cut unpreserved, and a population
left over cap is reported as a defect (exit 3).
"""

import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "ops"
SCRIPT = OPS / "worktree_trim_venue.sh"
NOW = int(time.time())

IDENT = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


def _git(cwd, *args, env):
    out = subprocess.run(
        ["git", "-c", "core.fsync=none", "-C", str(cwd), *args],
        env=env, capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)}: {out.stdout}{out.stderr}")
    return out


class VenueFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "venue-home"
        self.home.mkdir()
        self.env = {**os.environ, **IDENT}

    def tearDown(self):
        self.tmp.cleanup()

    def make_run_tree(self, name, epoch):
        d = self.home / "runs" / name
        d.mkdir(parents=True)
        (d / "log.txt").write_text("run\n")
        os.utime(d, (epoch, epoch))
        return d

    def make_sized_run_tree(self, name, epoch, size):
        d = self.home / "runs" / name
        d.mkdir(parents=True)
        # Sparse: du -sb reports apparent size, so the
        # fixture's byte total is exact without writing
        # real payload.
        with open(d / "payload.bin", "wb") as fh:
            fh.truncate(size)
        os.utime(d, (epoch, epoch))
        return d

    def make_cache_store(self, name, epoch, size, parent=None):
        d = (parent or (self.home / ".cache")) / name
        d.mkdir(parents=True)
        with open(d / "payload.bin", "wb") as fh:
            fh.truncate(size)
        os.utime(d / "payload.bin", (epoch, epoch))
        os.utime(d, (epoch, epoch))
        return d

    def make_clone(self, name, epoch, branch="main"):
        d = self.home / name
        d.mkdir(parents=True)
        _git(d, "init", "-b", branch, env=self.env)
        (d / "f.txt").write_text("base\n")
        _git(d, "add", "-A", env=self.env)
        _git(d, "commit", "-m", "base", env=self.env)
        self._age_clone(d, epoch)
        return d

    def _age_clone(self, d, epoch):
        os.utime(d / ".git" / "index", (epoch, epoch))
        os.utime(d, (epoch, epoch))

    def run_venue(self, extra_env=None, env=None):
        full = dict(env or self.env)
        full.update({
            "WORKTREE_TRIM_VENUE_HOME": str(self.home),
            "WORKTREE_TRIM_NOW": str(NOW),
        })
        if extra_env:
            full.update(extra_env)
        return subprocess.run(
            ["bash", str(SCRIPT)], env=full,
            capture_output=True, text=True)


class TestVenueTrim(VenueFixture):

    def test_run_trees_capped_oldest_first(self):
        names = [f"run-{i}" for i in range(5)]
        for i, name in enumerate(names):
            self.make_run_tree(name, NOW - 50000 + i * 10000)
        out = self.run_venue({"WT_TRIM_VENUE_RUN_CAP": "2"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("RUN-TREES before=5 after=2 cap=2", out.stdout)
        for name in names[:3]:
            self.assertIn(f"RUN-TREE-CUT path={self.home}/runs/{name}",
                          out.stdout)
            self.assertFalse((self.home / "runs" / name).exists())
        for name in names[3:]:
            self.assertTrue((self.home / "runs" / name).exists())

    def test_dirty_clone_autocommits_and_ranks(self):
        a = self.make_clone("clone-a", NOW - 50000)
        b = self.make_clone("clone-b", NOW - 40000)
        c = self.make_clone("clone-c", NOW - 30000)
        (b / "f.txt").write_text("work in progress\n")
        out = self.run_venue({"WT_TRIM_VENUE_CLONE_CAP": "2"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f"AUTOCOMMIT clone={b} branch=main", out.stdout)
        self.assertIn("CLONES before=3 after=2 cap=2", out.stdout)
        self.assertIn(f"CLONE-CUT path={a}", out.stdout)
        self.assertFalse(a.exists())
        self.assertTrue(b.exists())
        self.assertTrue(c.exists())
        self.assertEqual(
            _git(b, "show", "main:f.txt", env=self.env).stdout,
            "work in progress\n")
        self.assertEqual(
            _git(b, "status", "--porcelain", env=self.env).stdout, "")

    def test_detached_dirty_clone_gets_the_trim_branch(self):
        d = self.make_clone("clone-d", NOW - 40000)
        _git(d, "checkout", "--detach", "HEAD", env=self.env)
        (d / "f.txt").write_text("detached work\n")
        out = self.run_venue({"WT_TRIM_VENUE_CLONE_CAP": "5"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(
            f"AUTOCOMMIT clone={d} branch=trim/autocommit-clone-d",
            out.stdout)
        self.assertEqual(
            _git(d, "show", "trim/autocommit-clone-d:f.txt",
                 env=self.env).stdout, "detached work\n")

    def test_autocommit_failure_keeps_clone_and_reports_over(self):
        a = self.make_clone("clone-a", NOW - 50000)
        b = self.make_clone("clone-b", NOW - 40000)
        (b / "f.txt").write_text("unpreservable\n")
        bare = {k: v for k, v in os.environ.items()
                if not k.startswith("GIT_")}
        # The global scope is pinned to an empty file:
        # a host can resolve a global config outside
        # $HOME (the passwd-home / XDG route) carrying an
        # identity, which would defeat the no-identity
        # condition no matter where HOME points.
        empty_global = self.home / "empty-gitconfig"
        empty_global.write_text("")
        bare.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(empty_global),
            "HOME": str(self.home),
        })
        out = self.run_venue({"WT_TRIM_VENUE_CLONE_CAP": "1"},
                             env=bare)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn(
            f"AUTOCOMMIT-FAILED clone={b} step=commit "
            "reason=no-identity", out.stdout)
        self.assertIn("CLONE-CAP-OVER live=2 cap=1", out.stdout)
        self.assertTrue(b.exists())
        self.assertEqual((b / "f.txt").read_text(), "unpreservable\n")

    def test_worktree_clone_cut_prunes_its_registration(self):
        main = self.make_clone("clone-main", NOW - 30000)
        wt = self.home / "clone-wt"
        _git(main, "worktree", "add", str(wt), "-b", "feat/w",
             env=self.env)
        self._age_clone(main, NOW - 30000)
        os.utime(wt, (NOW - 60000, NOW - 60000))
        self.make_clone("clone-c", NOW - 20000)
        out = self.run_venue({"WT_TRIM_VENUE_CLONE_CAP": "2"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f"CLONE-CUT path={wt}", out.stdout)
        self.assertFalse(wt.exists())
        listing = _git(main, "worktree", "list", "--porcelain",
                       env=self.env).stdout
        self.assertNotIn(str(wt), listing)
        self.assertTrue(main.exists())

    def test_stale_bundle_cut_young_stands(self):
        old = self.home / "transport-old.bundle"
        old.write_bytes(b"bundle\n")
        os.utime(old, (NOW - 90000, NOW - 90000))
        young = self.home / "transport-young.bundle"
        young.write_bytes(b"bundle\n")
        os.utime(young, (NOW - 60, NOW - 60))
        out = self.run_venue()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f"BUNDLE-CUT path={old}", out.stdout)
        self.assertFalse(old.exists())
        self.assertTrue(young.exists())


class TestVenueTrimBytesAndCaches(VenueFixture):

    def _line(self, out, prefix):
        m = re.search(rf"^{prefix} .*$", out.stdout, re.M)
        self.assertIsNotNone(m, out.stdout + out.stderr)
        return m.group(0)

    def test_run_bytes_cut_to_budget_oldest_first(self):
        names = [f"run-{i}" for i in range(4)]
        for i, name in enumerate(names):
            self.make_sized_run_tree(name, NOW - 50000 + i * 10000,
                                     200_000)
        out = self.run_venue({"WT_TRIM_VENUE_RUN_BYTES": "450000"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        line = self._line(out, "RUN-BYTES")
        fields = dict(kv.split("=") for kv in line.split()[1:])
        self.assertEqual(fields["budget"], "450000")
        self.assertGreater(int(fields["before"]), 450000)
        self.assertLessEqual(int(fields["after"]), 450000)
        for name in names[:2]:
            self.assertIn(f"RUN-TREE-CUT path={self.home}/runs/{name}",
                          out.stdout)
            self.assertFalse((self.home / "runs" / name).exists())
        for name in names[2:]:
            self.assertTrue((self.home / "runs" / name).exists())

    def test_run_bytes_still_over_reports_partial(self):
        # An rm stub that refuses run-1: its bytes survive
        # the leg, so the re-measured total stays over
        # budget and the pass reports partial.
        stub = self.home / ".local" / "bin"
        stub.mkdir(parents=True)
        rm = stub / "rm"
        rm.write_text(
            "#!/bin/bash\n"
            "for a in \"$@\"; do case \"$a\" in *run-1) exit 1;;"
            " esac; done\n"
            "exec /bin/rm \"$@\"\n")
        rm.chmod(0o755)
        for i in range(2):
            self.make_sized_run_tree(f"run-{i}", NOW - 50000 + i * 10000,
                                     200_000)
        out = self.run_venue({"WT_TRIM_VENUE_RUN_BYTES": "1000"})
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self._line(out, "RUN-BYTES-OVER")
        self.assertFalse((self.home / "runs" / "run-0").exists())
        self.assertTrue((self.home / "runs" / "run-1").exists())

    def test_run_bytes_measure_failure_skips_the_leg(self):
        stub = self.home / ".local" / "bin"
        stub.mkdir(parents=True)
        du = stub / "du"
        du.write_text("#!/bin/bash\nexit 1\n")
        du.chmod(0o755)
        self.make_sized_run_tree("run-0", NOW - 50000, 200_000)
        out = self.run_venue({"WT_TRIM_VENUE_RUN_BYTES": "1"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("RUN-BYTES skipped=measure-timeout", out.stdout)
        self.assertTrue((self.home / "runs" / "run-0").exists())

    def test_cache_cuts_oldest_first_to_budget(self):
        a = self.make_cache_store("cache-a", NOW - 50000, 300_000)
        b = self.make_cache_store("cache-b", NOW - 40000, 300_000)
        c = self.make_cache_store("cache-c", NOW - 30000, 300_000)
        out = self.run_venue({"WT_TRIM_VENUE_CACHE_BYTES": "650000"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f"CACHE-CUT path={a} bytes=", out.stdout)
        self.assertFalse(a.exists())
        self.assertTrue(b.exists())
        self.assertTrue(c.exists())
        line = self._line(out, "CACHE")
        fields = dict(kv.split("=") for kv in line.split()[1:])
        self.assertEqual(fields["budget"], "650000")
        self.assertLessEqual(int(fields["after"]), 650000)

    def test_cache_playwright_cuts_builds_keeps_newest(self):
        pw = self.home / ".cache" / "ms-playwright"
        old = self.make_cache_store("chromium-1000", NOW - 50000,
                                    300_000, parent=pw)
        new = self.make_cache_store("chromium-2000", NOW - 40000,
                                    300_000, parent=pw)
        # The store dir's own mtime is content too: age it
        # to the newest build, as a settled store stands.
        os.utime(pw, (NOW - 40000, NOW - 40000))
        out = self.run_venue({"WT_TRIM_VENUE_CACHE_BYTES": "350000"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f"CACHE-CUT path={old} bytes=", out.stdout)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertTrue(pw.exists())

    def test_cache_active_store_skipped_and_cap_over(self):
        active = self.make_cache_store("cache-active", NOW - 10, 500_000)
        out = self.run_venue({"WT_TRIM_VENUE_CACHE_BYTES": "100000"})
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn(f"CACHE-ACTIVE-SKIP path={active}", out.stdout)
        self._line(out, "CACHE-CAP-OVER")
        self.assertTrue(active.exists())

    def test_cache_old_cut_active_kept_still_over(self):
        old = self.make_cache_store("cache-old", NOW - 50000, 300_000)
        active = self.make_cache_store("cache-active", NOW - 10, 500_000)
        out = self.run_venue({"WT_TRIM_VENUE_CACHE_BYTES": "100000"})
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn(f"CACHE-CUT path={old} bytes=", out.stdout)
        self.assertFalse(old.exists())
        self.assertIn(f"CACHE-ACTIVE-SKIP path={active}", out.stdout)
        self._line(out, "CACHE-CAP-OVER")
        self.assertTrue(active.exists())


if __name__ == "__main__":
    unittest.main()
