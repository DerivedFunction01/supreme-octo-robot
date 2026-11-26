"""No-held-set, auto-commit, purge-branch, and restore
specimens for the worktree trim, sharing the fixture
harness in test_worktree_trim.py: one specimen per former
hold class pinning that it exempts nothing, the
auto-commit path, the purge branch dispositions, and the
mechanical restore verb round-trips and refusals.
"""

import subprocess
import unittest

from tests.test_worktree_trim import (
    NOW, OPS, Fixture, _archive_dir, _git)


class TestNoHeldSet(Fixture):
    """No held set (owner ruling, 2026-11-26): the cap
    binds the whole population — one specimen per former
    hold class, each pinning that the class exempts
    nothing now."""

    def test_unlanded_tree_archives_and_its_branch_stands(self):
        # Unlanded state holds nothing (owner ruling,
        # 2026-11-26): the DF-NEXT-101 specimen shape — a
        # formation tree ahead of base, unmerged — archives
        # at cap 0 in the ordinary pass, exactly like the
        # landed elder. What protects in-flight work now is
        # the activity set (live/run/held), not the landing
        # state. The branch itself stands: branch trims are
        # the purge's act, not the trim's.
        self.add_tree("repo-a-u-wt", "feat/u",
                      [("u.txt", "u\n")], NOW - 2000)
        elder = self.add_landed_tree("repo-a-e-wt", "feat/e",
                                     [("e.txt", "e\n")], NOW - 9000)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-u-wt",
                      out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-e-wt",
                      out.stdout)
        self.assertFalse((self.ws / "repo-a-u-wt").exists())
        self.assertFalse(elder.exists())
        self.assertTrue(self.branch_exists("feat/u"))

    def test_drain_act_pass_matches_the_ordinary_pass(self):
        # The drain act's old exception is subsumed: under
        # WORKTREE_TRIM_DRAIN_ACT an unlanded tree archives
        # and a dirty tree auto-commits and archives,
        # exactly as the ordinary pass treats them — hold
        # evaluation no longer varies by caller.
        self.add_tree("repo-a-u-wt", "feat/u",
                      [("u.txt", "u\n")], NOW - 2000)
        dirty = self.add_tree("repo-a-d-wt", "feat/d",
                              [("d.txt", "d\n")], NOW - 3000)
        (dirty / "scratch.txt").write_text("uncommitted\n")
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_CAP_REPO_A": "0",
                       "WORKTREE_TRIM_DRAIN_ACT": "1"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-u-wt",
                      out.stdout)
        self.assertIn("AUTOCOMMIT repo=repo-a tree=repo-a-d-wt "
                      "branch=feat/d", out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-d-wt",
                      out.stdout)
        self.assertNotIn("HELD", out.stdout)
        self.assertFalse(dirty.exists())

    def test_live_process_exempts_nothing(self):
        # a process holding the tree was the live reason;
        # the trim no longer scans /proc at all. The
        # planted process stands as the specimen's claim,
        # and at cap 0 the tree archives like any other.
        tree = self.add_landed_tree("repo-a-l-wt", "feat/l",
                                    [("l.txt", "l\n")], NOW - 4000)
        proc = self.ws / "proc" / "4242"
        proc.mkdir(parents=True)
        (proc / "cwd").symlink_to(tree)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-l-wt",
                      out.stdout)
        self.assertFalse(tree.exists())

    def test_run_record_exempts_nothing_terminal_or_not(self):
        # a run record naming the tree — non-terminal or
        # terminal — is not read: both passes archive the
        # tree at cap 0.
        tree = self.add_landed_tree("repo-a-r-wt", "feat/rr",
                                    [("r.txt", "r\n")], NOW - 4000)
        runs = self.ws / "runs"
        runs.mkdir(parents=True)
        (runs / "gate-1.json").write_text(
            '{"run_id": "gate-1", "state": "polling",'
            f' "tree": "{tree}"}}')
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-r-wt",
                      out.stdout)
        self.assertFalse(tree.exists())

    def test_explicit_holds_exempt_nothing(self):
        # a .trim-hold file and a holds.txt entry were the
        # explicit hold; both markers stand in place and
        # both trees archive at cap 0 — the files are
        # inert data the trim no longer reads.
        t1 = self.add_landed_tree("repo-a-h1-wt", "feat/h1",
                                  [("h1.txt", "1\n")], NOW - 4000)
        (t1 / ".trim-hold").write_text("gate in flight\n")
        t2 = self.add_landed_tree("repo-a-h2-wt", "feat/h2",
                                  [("h2.txt", "2\n")], NOW - 3000)
        state = self.ws / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "holds.txt").write_text(f"{t2}\n")
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-h1-wt",
                      out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-h2-wt",
                      out.stdout)
        self.assertFalse(t1.exists())
        self.assertFalse(t2.exists())


class TestAutoCommit(Fixture):
    """The auto-commit path (owner ruling, 2026-11-26):
    work state is committed by the trim, never held for."""

    def test_detached_dirty_tree_gets_the_trim_branch(self):
        # A detached tree has no branch to commit onto:
        # the trim names one deterministically —
        # trim/autocommit-<tree> — switches the tree onto
        # it, and commits there. The branch stands after
        # the archive; the work is on it, whole.
        tree = self.add_tree("repo-a-x-wt", "feat/x",
                             [("x.txt", "committed\n")], NOW - 4000)
        _git(tree, "checkout", "--detach", "HEAD", env=self.env)
        (tree / "x.txt").write_text("detached work\n")
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("AUTOCOMMIT repo=repo-a tree=repo-a-x-wt "
                      "branch=trim/autocommit-repo-a-x-wt",
                      out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-x-wt",
                      out.stdout)
        self.assertTrue(
            self.branch_exists("trim/autocommit-repo-a-x-wt"))
        self.assertEqual(
            _git(self.main, "show",
                 "trim/autocommit-repo-a-x-wt:x.txt",
                 env=self.env).stdout, "detached work\n")

    def test_dirty_tree_under_cap_autocommits_and_stands(self):
        # The auto-commit is not a trim act: under the cap
        # the tree stands — with its work committed, its
        # status clean, and its branch advanced.
        tree = self.add_tree("repo-a-c-wt", "feat/c",
                             [("c.txt", "committed\n")], NOW - 4000)
        (tree / "c.txt").write_text("work in progress\n")
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("AUTOCOMMIT repo=repo-a tree=repo-a-c-wt "
                      "branch=feat/c", out.stdout)
        self.assertNotIn("ARCHIVED", out.stdout)
        self.assertTrue(tree.exists())
        self.assertEqual(
            _git(tree, "status", "--porcelain",
                 env=self.env).stdout, "")
        self.assertEqual(
            _git(tree, "show", "HEAD:c.txt",
                 env=self.env).stdout, "work in progress\n")

    def test_dirty_tree_with_a_live_process_autocommits(self):
        # No activity state gates the auto-commit either:
        # a dirty tree a process is planted in is
        # committed in place (the commit reads the
        # working state; it does not move the process's
        # files) and archives at cap 0 in the same pass —
        # preservation is the commit and the archive, not
        # an exemption.
        tree = self.add_landed_tree("repo-a-l-wt", "feat/l",
                                    [("l.txt", "l\n")], NOW - 4000)
        (tree / "l.txt").write_text("live edit\n")
        proc = self.ws / "proc" / "4242"
        proc.mkdir(parents=True)
        (proc / "cwd").symlink_to(tree)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("AUTOCOMMIT repo=repo-a tree=repo-a-l-wt "
                      "branch=feat/l", out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-l-wt",
                      out.stdout)
        self.assertFalse(tree.exists())
        self.assertEqual(
            _git(self.main, "show", "feat/l:l.txt",
                 env=self.env).stdout, "live edit\n")

    def test_autocommit_failure_is_reported_by_name(self):
        # No identity configured anywhere the commit can
        # read: the trim invents none. The failure is
        # reported by name with its step and reason, the
        # pass ends partial (exit 3), and the tree is NOT
        # silently held for it — at cap 0 it archives with
        # its uncommitted state riding the archive whole.
        tree = self.add_tree("repo-a-f-wt", "feat/f",
                             [("f.txt", "committed\n")], NOW - 4000)
        (tree / "f.txt").write_text("dirty change\n")
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_CAP_REPO_A": "0",
                       "GIT_AUTHOR_NAME": None,
                       "GIT_AUTHOR_EMAIL": None,
                       "GIT_COMMITTER_NAME": None,
                       "GIT_COMMITTER_EMAIL": None,
                       "GIT_CONFIG_NOSYSTEM": "1",
                       "HOME": str(self.ws)})
        self.assertEqual(out.returncode, 3,
                         out.stdout + out.stderr)
        self.assertIn("AUTOCOMMIT-FAILED repo=repo-a "
                      "tree=repo-a-f-wt branch=feat/f "
                      "step=commit reason=no-identity",
                      out.stdout)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-f-wt",
                      out.stdout)
        (manifest,) = self.archives()
        adir = _archive_dir(manifest)
        self.assertEqual((adir / "tree" / "f.txt").read_text(),
                         "dirty change\n")


class TestPurgeBranch(Fixture):
    """The purge charges the branch trim only for a branch
    proven to be the archive's own."""

    def _hand_archive(self, branch, head, expiry):
        """An in-dir-format archive written by hand, as the
        trim would leave it, for a branch the trim itself
        would now hold (unlanded) — the pre-cure archives'
        shape."""
        adir = (self.ws / "worktree-archive" / "2026-11-16"
                / f"repo-a__repo-a-z-wt")
        (adir / "tree").mkdir(parents=True)
        (adir / "worktree-admin").mkdir(parents=True)
        (adir / "manifest.txt").write_text(
            f"repo=repo-a\ntree=repo-a-z-wt\n"
            f"path={self.ws}/repo-a-z-wt\nbranch={branch}\n"
            f"head={head}\nbase=main\nahead=1\nmerged=0\n"
            f"expiry_epoch={expiry}\n")
        return adir

    def test_purge_keeps_unlanded_branch(self):
        tree = self.add_tree("repo-a-z-wt", "feat/z",
                             [("z.txt", "z\n")], NOW - 4000)
        head = _git(tree, "rev-parse", "HEAD",
                    env=self.env).stdout.strip()
        # the tree itself is restored by hand (only the
        # archive + branch state is under test here)
        _git(self.main, "worktree", "remove", "--force",
             str(tree), env=self.env)
        self._hand_archive("feat/z", head, NOW - 1)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("PURGED repo=repo-a tree=repo-a-z-wt",
                      out.stdout)
        self.assertIn("branch_local=kept-unlanded", out.stdout)
        self.assertTrue(self.branch_exists("feat/z"))
        self.assertEqual(self.queue(), [])

    def _hand_branch_cap_package(self, expiry):
        """A branch-cap archive package written by hand,
        as the cap phase leaves it: the bundle, its rows,
        and — the 2026-11-26 cure — the purge manifest
        carrying the package's expiry. Before the cure
        the package carried no expiry the clean script
        reads, so branch-cap bundles accumulated past
        their grace forever."""
        adir = (self.ws / "worktree-archive" / "2026-11-18"
                / "repo-a-branch-cap")
        adir.mkdir(parents=True)
        (adir / "branches.bundle").write_bytes(b"bundle\n")
        (adir / "manifest.tsv").write_text(
            "# branch-cap archive repo=repo-a\n"
            "branch\ttip_sha\ttip_date\tsides\n")
        (adir / "manifest.txt").write_text(
            f"repo=repo-a\ntree=repo-a-branch-cap\n"
            f"kind=branch-cap\nexpiry_epoch={expiry}\n")
        return adir

    def test_purge_takes_an_expired_branch_cap_package(self):
        adir = self._hand_branch_cap_package(NOW - 1)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("PURGED repo=repo-a tree=repo-a-branch-cap",
                      out.stdout)
        self.assertIn("branch_local=none", out.stdout)
        self.assertFalse(adir.exists())

    def test_branch_cap_package_within_grace_stands(self):
        adir = self._hand_branch_cap_package(NOW + 1800)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("PURGED", out.stdout)
        self.assertTrue((adir / "branches.bundle").exists())

    def test_purge_keeps_moved_branch(self):
        tree = self.add_landed_tree("repo-a-m-wt", "feat/m",
                                    [("m.txt", "m\n")], NOW - 4000)
        head = _git(tree, "rev-parse", "HEAD",
                    env=self.env).stdout.strip()
        _git(self.main, "worktree", "remove", "--force",
             str(tree), env=self.env)
        # the seat advances the branch after the trim
        _git(self.main, "commit", "--allow-empty", "-m", "later",
             epoch=NOW - 100, env=self.env)
        _git(self.main, "branch", "-f", "feat/m", "main",
             env=self.env)
        self._hand_archive("feat/m", head, NOW - 1)
        live = _git(self.main, "rev-parse", "main",
                    env=self.env).stdout.strip()
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # the purge's own disposition is unchanged: it does
        # not charge a branch that no longer points at the
        # recorded head
        self.assertIn("branch_local=kept-moved", out.stdout)
        # the seat moved the branch onto main itself — its
        # tip now EQUALS main's tip, and under the
        # tip-equal exclusion (test_worktree_
        # trim_sweep.py, TestTipEqual) the branch sweep
        # spares a ref standing at the base's own position:
        # it draws the skip line and the branch stands. (At
        # any strictly-contained position the sweep would
        # trim it in the same pass, as before.)
        self.assertIn("BRANCH-CONTAINED-SKIP-EQUAL repo=repo-a "
                      f"branch=feat/m sha={live}", out.stdout)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a "
                         "branch=feat/m", out.stdout)
        self.assertTrue(self.branch_exists("feat/m"))
        self.assertEqual(self.queue(), [])


class TestRestore(Fixture):
    RESTORE = OPS / "worktree_restore.sh"

    def run_restore(self, adir):
        return subprocess.run(
            ["bash", str(self.RESTORE), str(adir)],
            capture_output=True, text=True, env=self.env)

    def test_restore_round_trip(self):
        tree = self.add_landed_tree("repo-a-v-wt", "feat/v",
                                    [("v.txt", "v\n")], NOW - 4000)
        head = _git(tree, "rev-parse", "HEAD",
                    env=self.env).stdout.strip()
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        (manifest,) = self.archives()
        adir = _archive_dir(manifest)
        out = self.run_restore(adir)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("RESTORED repo=repo-a tree=repo-a-v-wt",
                      out.stdout)
        self.assertTrue(tree.exists())
        self.assertEqual((tree / "v.txt").read_text(), "v\n")
        listed = _git(self.main, "worktree", "list",
                      env=self.env).stdout
        self.assertIn("repo-a-v-wt", listed)
        self.assertEqual(
            _git(tree, "rev-parse", "HEAD", env=self.env
                 ).stdout.strip(), head)
        self.assertEqual(
            _git(tree, "branch", "--show-current", env=self.env
                 ).stdout.strip(), "feat/v")
        self.assertFalse(adir.exists())

    def test_restore_recreates_a_deleted_branch(self):
        # a pre-cure archive: the trim deleted the branch;
        # the restore re-creates it at the recorded head —
        # the Stage-4 drill, mechanized
        tree = self.add_landed_tree("repo-a-w-wt", "feat/w",
                                    [("w.txt", "w\n")], NOW - 4000)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        _git(self.main, "branch", "-D", "feat/w", env=self.env)
        (manifest,) = self.archives()
        out = self.run_restore(_archive_dir(manifest))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("RESTORED", out.stdout)
        self.assertTrue(self.branch_exists("feat/w"))
        self.assertEqual(
            _git(tree, "branch", "--show-current", env=self.env
                 ).stdout.strip(), "feat/w")

    def test_restore_refuses_a_moved_branch(self):
        tree = self.add_landed_tree("repo-a-y-wt", "feat/y",
                                    [("y.txt", "y\n")], NOW - 4000)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        _git(self.main, "commit", "--allow-empty", "-m", "later",
             epoch=NOW - 100, env=self.env)
        _git(self.main, "branch", "-f", "feat/y", "main",
             env=self.env)
        (manifest,) = self.archives()
        adir = _archive_dir(manifest)
        out = self.run_restore(adir)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("RESTORE-FAIL step=branch-moved", out.stdout)
        # the archive stands untouched as the record of truth
        self.assertTrue((adir / "tree").exists())
        self.assertFalse(tree.exists())




if __name__ == "__main__":
    unittest.main()
