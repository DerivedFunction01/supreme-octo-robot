"""Held-set, purge-branch, and restore specimens for the
worktree trim (the 2026-11-21 cure), sharing the fixture
harness in test_worktree_trim.py: one specimen per hold
reason, the purge branch dispositions, and the mechanical
restore verb round-trips and refusals.
"""

import subprocess
import unittest

from tests.test_worktree_trim import (
    NOW, OPS, Fixture, _archive_dir, _git)


class TestHeldSet(Fixture):
    """The 2026-11-21 held set, one specimen per reason."""

    def test_unlanded_tree_is_held(self):
        # The DF-NEXT-101 specimen shape: a formation tree
        # ahead of base, unmerged, archived twice in one
        # night by the pre-cure trim while its band gates
        # were in flight. Now: HELD at cap 0, and a landed
        # elder trims in the same pass — a held tree does
        # not consume cap.
        self.add_tree("repo-a-u-wt", "feat/u",
                      [("u.txt", "u\n")], NOW - 2000)
        elder = self.add_landed_tree("repo-a-e-wt", "feat/e",
                                     [("e.txt", "e\n")], NOW - 9000)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        held = [ln for ln in out.stdout.splitlines()
                if ln.startswith("HELD")]
        self.assertEqual(len(held), 1)
        self.assertIn("tree=repo-a-u-wt", held[0])
        self.assertIn("unlanded", held[0])
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-e-wt",
                      out.stdout)
        self.assertTrue((self.ws / "repo-a-u-wt").exists())
        self.assertFalse(elder.exists())

    def test_live_process_holds_the_tree(self):
        tree = self.add_landed_tree("repo-a-l-wt", "feat/l",
                                    [("l.txt", "l\n")], NOW - 4000)
        proc = self.ws / "proc" / "4242"
        proc.mkdir(parents=True)
        (proc / "cwd").symlink_to(tree)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        held = [ln for ln in out.stdout.splitlines()
                if ln.startswith("HELD")][0]
        self.assertIn("live", held)
        self.assertTrue(tree.exists())
        self.assertEqual(self.archives(), [])

    def test_nonterminal_run_record_holds_terminal_does_not(self):
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
        held = [ln for ln in out.stdout.splitlines()
                if ln.startswith("HELD")][0]
        self.assertIn("run", held)
        self.assertTrue(tree.exists())
        # the same record, terminal: the hold lapses and
        # the landed tree trims at the cut
        (runs / "gate-1.json").write_text(
            '{"run_id": "gate-1", "state": "complete",'
            f' "tree": "{tree}"}}')
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-r-wt",
                      out.stdout)
        self.assertFalse(tree.exists())

    def test_explicit_holds(self):
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
        held = [ln for ln in out.stdout.splitlines()
                if ln.startswith("HELD")]
        self.assertEqual(len(held), 2)
        for ln in held:
            self.assertIn("held", ln)
        self.assertTrue(t1.exists())
        self.assertTrue(t2.exists())
        self.assertEqual(self.archives(), [])


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
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("branch_local=kept-moved", out.stdout)
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
