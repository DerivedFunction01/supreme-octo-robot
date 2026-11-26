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
        bare.update({
            "GIT_CONFIG_NOSYSTEM": "1",
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


if __name__ == "__main__":
    unittest.main()
