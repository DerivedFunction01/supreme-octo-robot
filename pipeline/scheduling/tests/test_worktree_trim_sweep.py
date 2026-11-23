"""Branch-sweep specimens for the worktree trim (the
2026-11-22 cure), sharing the fixture harness in
test_worktree_trim.py.

The pre-cure trim charged a branch trim only at the purge
of an archive the trim itself had made, plus a crash queue
seeded from archive manifests. Branches pushed to origin
by lanes whose worktrees never stood in the local census
(venue/session clones) were never trimmed: steampowernj
accumulated 144 origin branches, 111 fully contained in
main. The owner's ruling: the hourly pass takes no
exemptions when it comes to trimming. The sweep censuses
ALL branches every pass; containment in the default branch
is the only criterion — no provenance, no held set, no
name carve-outs. The only mechanical exemptions are the
default branch itself and, locally, a branch checked out
in a worktree (git refuses those).
"""

import unittest

from tests.test_worktree_trim import NOW, Fixture, _git


class TestBranchSweep(Fixture):
    def add_orphan_branch(self, branch, fname):
        """A landed branch with no worktree and no archive
        manifest: grown in a tree, fast-forwarded into main,
        then the tree is removed — the branch stands alone,
        exactly the shape the pre-cure trim never charged."""
        path = self.add_landed_tree(
            f"repo-a-{branch.replace('/', '-')}-wt", branch,
            [(fname, "x\n")], NOW - 4000)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        return path

    def test_orphan_contained_branch_trims_in_both_scopes(self):
        # (a) the regression case: contained on origin, no
        # local worktree, no archive manifest — the sweep
        # enqueues it and the standing drain discharges it
        # in the same pass; the local ref trims too. (d) the
        # default branch is never trimmed in either scope.
        self.add_origin()
        self.add_orphan_branch("feat/done", "done.txt")
        _git(self.main, "push", "origin", "main", "feat/done",
             env=self.env)
        self.assertEqual(self.archives(), [])
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-TRIMMED repo=repo-a branch=feat/done "
                      "scope=local", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a branch=feat/done "
                      "scope=origin", out.stdout)
        self.assertIn("BRANCH-SWEEP repo=repo-a local=1 origin=1 "
                      "kept=0", out.stdout)
        self.assertFalse(self.branch_exists("feat/done"))
        self.assertNotIn("feat/done", self.remote_branches())
        self.assertEqual(self.queue(), [])
        self.assertEqual(self.archives(), [])
        self.assertTrue(self.branch_exists("main"))
        self.assertIn("main", self.remote_branches())
        self.assertNotIn("branch=main", out.stdout)

    def test_uncontained_branch_is_kept_in_both_scopes(self):
        # (b) a branch carrying commits the default branch
        # does not have is not trim material, in either
        # scope, worktree or not
        self.add_origin()
        tree = self.add_tree("repo-a-u-wt", "feat/open",
                             [("o.txt", "o\n")], NOW - 4000)
        _git(self.main, "push", "origin", "main", "feat/open",
             env=self.env)
        _git(self.main, "worktree", "remove", str(tree),
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("BRANCH-TRIMMED", out.stdout)
        self.assertTrue(self.branch_exists("feat/open"))
        self.assertIn("feat/open", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_checked_out_contained_branch_stands_locally(self):
        # (c) containment is proven, but the branch is
        # checked out in a worktree: the local ref stands
        # (git refuses the delete). The origin ref has no
        # such mechanical bar and trims in the same pass.
        self.add_origin()
        self.add_landed_tree("repo-a-k-wt", "feat/kept",
                             [("k.txt", "k\n")], NOW - 4000)
        _git(self.main, "push", "origin", "main", "feat/kept",
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a branch=feat/kept "
                         "scope=local", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a branch=feat/kept "
                      "scope=origin", out.stdout)
        self.assertIn("BRANCH-SWEEP repo=repo-a local=0 origin=1 "
                      "kept=1", out.stdout)
        self.assertTrue(self.branch_exists("feat/kept"))
        self.assertNotIn("feat/kept", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_origin_unreachable_local_sweep_still_runs(self):
        # (e) origin unreachable: the origin half is skipped
        # with a BRANCH-REMOTE-FAIL in the standing style,
        # the local half still trims, and the origin branch
        # stands untouched for a later pass
        origin = self.add_origin()
        self.add_orphan_branch("feat/lone", "lone.txt")
        _git(self.main, "push", "origin", "main", "feat/lone",
             env=self.env)
        _git(self.main, "remote", "set-url", "origin",
             str(self.ws / "missing.git"), env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("BRANCH-REMOTE-FAIL repo=repo-a scope=origin "
                      "reason=origin-unreachable", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a branch=feat/lone "
                      "scope=local", out.stdout)
        self.assertFalse(self.branch_exists("feat/lone"))
        remote = _git(self.main, "ls-remote", "--heads",
                      str(origin), env=self.env).stdout
        self.assertIn("feat/lone", remote)


class TestBranchCap(Fixture):
    """The cap phase (the owner's correction: containment
    is not the end state — the configured max, default 10
    per repo per side, binds the branch population, with
    no exemptions). Excess branches are archive-before-
    delete: their tips land in one verified bundle with a
    manifest before any ref moves."""

    def add_orphan(self, branch, epoch):
        """An unlanded branch with no standing worktree:
        over-cap material the containment sweep must keep
        and the cap phase alone may take."""
        path = self.add_tree(
            f"repo-a-{branch.replace('/', '-')}-wt", branch,
            [(f"{branch.replace('/', '-')}.txt", "x\n")], epoch)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        return path

    def local_branches(self):
        out = _git(self.main, "for-each-ref",
                   "--format=%(refname:short)", "refs/heads",
                   env=self.env).stdout
        return set(out.split())

    def cap_dir(self):
        hits = sorted((self.ws / "worktree-archive").glob(
            f"*/{self.slug}-branch-cap"))
        self.assertEqual(len(hits), 1)
        return hits[0]

    def manifest_rows(self):
        text = (self.cap_dir() / "manifest.tsv").read_text()
        rows = []
        for ln in text.splitlines():
            if not ln or ln.startswith("#") \
                    or ln.startswith("branch\t"):
                continue
            rows.append(ln.split("\t"))
        return rows

    def test_over_cap_archives_oldest_and_trims_both_sides(self):
        # (f) 13 uncontained branches + main = 14 per side,
        # default cap 10: the oldest 4 excess are archived
        # (one bundle, verified, manifest on disk) and their
        # refs deleted on BOTH sides; the newest 10 remain.
        self.add_origin()
        names = [f"feat/b{i:02d}" for i in range(13)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 20000 + i * 1000)
        _git(self.main, "push", "origin", "main", *names,
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        remain = {"main"} | set(names[4:])
        self.assertEqual(self.local_branches(), remain)
        remote = self.remote_branches()
        for name in names[:4]:
            self.assertNotIn(name, remote)
        for name in names[4:]:
            self.assertIn(name, remote)
        self.assertIn("main", remote)
        self.assertIn("BRANCH-CAP repo=repo-a side=local live=14 "
                      "cap=10 archived=4", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin live=14 "
                      "cap=10 archived=4", out.stdout)
        self.assertIn("BRANCH-ARCHIVED repo=repo-a branch=feat/b00 "
                      "sides=local,origin", out.stdout)
        bundle = self.cap_dir() / "branches.bundle"
        self.assertTrue(bundle.exists())
        verify = _git(self.main, "bundle", "verify", str(bundle),
                      env=self.env, check=False)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        heads = _git(self.main, "bundle", "list-heads",
                     str(bundle), env=self.env).stdout.splitlines()
        rows = self.manifest_rows()
        self.assertEqual(len(heads), 4)
        self.assertEqual(len(rows), len(heads))
        self.assertEqual([r[0] for r in rows], names[:4])
        self.assertTrue(all(r[3] == "local,origin" for r in rows))
        self.assertEqual(self.queue(), [])

    def test_bundle_failure_deletes_nothing(self):
        # (g) the archive cannot be written (the archive
        # root is a file): the cap phase records the failure,
        # marks the pass partial, and deletes NO ref on
        # either side — archive-before-delete is the order.
        self.add_origin()
        names = [f"feat/g{i:02d}" for i in range(12)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 20000 + i * 1000)
        _git(self.main, "push", "origin", "main", *names,
             env=self.env)
        blocker = self.ws / "archive-blocker"
        blocker.write_text("not a directory")
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_ARCHIVE_ROOT": str(blocker)})
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("BRANCH-CAP-FAIL repo=repo-a "
                      "reason=archive-unwritable", out.stdout)
        self.assertNotIn("BRANCH-CAP repo=repo-a", out.stdout)
        self.assertEqual(self.local_branches(), {"main"} | set(names))
        remote = self.remote_branches()
        for name in names:
            self.assertIn(name, remote)
        self.assertEqual(self.queue(), [])

    def test_default_and_checked_out_never_archive_deleted(self):
        # (h) per-slug cap 3. Locally the never-delete set is
        # main + the checked-out branch (the oldest tip of
        # all): both stand, and the cap takes the oldest
        # orphan excess instead. On origin the checked-out
        # branch has no such protection — it is a candidate
        # like any other and its origin copy is archived.
        self.add_origin()
        self.add_tree("repo-a-held-wt", "feat/held",
                      [("held.txt", "h\n")], NOW - 30000)
        orphans = [f"feat/o{i}" for i in range(4)]
        for i, name in enumerate(orphans):
            self.add_orphan(name, NOW - 20000 + i * 1000)
        _git(self.main, "push", "origin", "main", "feat/held",
             *orphans, env=self.env)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP_REPO_A": "3"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.local_branches(),
                         {"main", "feat/held", orphans[3]})
        self.assertTrue(self.branch_exists("feat/held"))
        self.assertNotIn("feat/held", self.remote_branches())
        self.assertIn("BRANCH-CAP repo=repo-a side=local live=6 "
                      "cap=3 archived=3", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin live=6 "
                      "cap=3 archived=3", out.stdout)
        # origin keeps main + the newest two candidates;
        # feat/o2 was excess locally only and stands here
        self.assertIn("feat/o2", self.remote_branches())
        self.assertIn("feat/o3", self.remote_branches())
        rows = self.manifest_rows()
        held_rows = [r for r in rows if r[0] == "feat/held"]
        self.assertEqual(len(held_rows), 1)
        self.assertEqual(held_rows[0][3], "origin")

    def test_never_delete_overage_reports_and_stops(self):
        # (h, overage form) the never-delete set alone —
        # main + a checked-out branch — exceeds the cap
        # (global env seam, cap 1): the overage is reported
        # and the local side stops there; nothing is taken.
        self.add_tree("repo-a-held-wt", "feat/held",
                      [("held.txt", "h\n")], NOW - 30000)
        self.add_orphan("feat/orphan", NOW - 20000)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP": "1"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-CAP-OVER repo=repo-a side=local "
                      "live=3 cap=1 never=2", out.stdout)
        self.assertNotIn("BRANCH-ARCHIVED", out.stdout)
        self.assertEqual(self.local_branches(),
                         {"main", "feat/held", "feat/orphan"})

    def test_restore_from_bundle_lands_on_recorded_tip(self):
        # (i) the manifest header's restore commands, run
        # verbatim in form, recreate the branch at exactly
        # the tip sha the manifest recorded.
        names = [f"feat/r{i}" for i in range(3)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 20000 + i * 1000)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP_REPO_A": "3"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertFalse(self.branch_exists("feat/r0"))
        bundle = self.cap_dir() / "branches.bundle"
        manifest = (self.cap_dir() / "manifest.tsv").read_text()
        self.assertIn("# restore_1=git -C ", manifest)
        self.assertIn(f"fetch {bundle} "
                      "refs/archive-cap/<branch>", manifest)
        self.assertIn("# restore_2=git -C ", manifest)
        rows = self.manifest_rows()
        self.assertEqual(len(rows), 1)
        branch, sha = rows[0][0], rows[0][1]
        self.assertEqual(branch, "feat/r0")
        _git(self.main, "fetch", str(bundle),
             f"refs/archive-cap/{branch}", env=self.env)
        _git(self.main, "branch", branch, "FETCH_HEAD",
             env=self.env)
        tip = _git(self.main, "rev-parse", f"refs/heads/{branch}",
                   env=self.env).stdout.strip()
        self.assertEqual(tip, sha)


if __name__ == "__main__":
    unittest.main()
