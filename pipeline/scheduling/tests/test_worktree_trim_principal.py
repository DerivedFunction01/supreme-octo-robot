"""Principal-branch specimens for the worktree trim:
the census's own reference points — the
base branch and the remote's default branch, both derived
from the repo at census time, never a name list — are not
trim material in either scope, the drain refuses charges
naming one, and cap selection excludes checked-out
branches, reporting uncoverable excess honestly. Shares
the fixture harness in test_worktree_trim.py.
"""

import unittest

from tests.test_worktree_trim import NOW, Fixture, _git


class TestPrincipalBranches(Fixture):
    """Principal-branch and checkout exclusions.
    In the specimen failure, an hourly pass under drain
    re-verification cap-archived steampowernj's main,
    attempted its origin deletion twice, and left a
    standing cap charge for it: in that repo the base
    (containment's reference, the main worktree's
    checkout) is dev and the remote default is main,
    strictly contained in dev, so the sweep and the cap
    both treated main as ordinary landed material; only
    the remote's own default-branch refusal stood in the
    way. The same pass failed to detach the checked-out
    branch of a tree it held as unlanded
    (form/df-next-121, BRANCH-LOCAL-FAIL
    reason=detach-failed). The exclusion is structural,
    derived from the repo at census — the principal set
    (the base branch; the origin/HEAD target) and the
    worktree checkout set — with no name literals and no
    exemption registry."""

    def add_dev_flow(self):
        """steampowernj's shape: the base is dev (the
        main worktree checks it out), the remote default
        is main, and main is strictly contained in dev."""
        origin = self.add_origin()
        _git(origin, "symbolic-ref", "HEAD",
             "refs/heads/main", env=self.env)
        path = self.add_tree("repo-a-dev-wt", "dev",
                             [("dev.txt", "d\n")], NOW - 90000)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        _git(self.main, "checkout", "dev", env=self.env)
        _git(self.main, "push", "origin", "main", "dev",
             env=self.env)
        return origin

    def add_orphan(self, branch, epoch):
        """An unlanded branch with no standing worktree:
        survives the sweep against dev (its commit is in
        neither main nor dev), so the cap phase alone
        decides its fate."""
        path = self.add_tree(
            f"repo-a-{branch.replace('/', '-')}-wt", branch,
            [(f"{branch.replace('/', '-')}.txt", "x\n")], epoch)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        return path

    def seed_queue(self, *lines):
        state = self.ws / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / f"remote-pending-{self.slug}.txt").write_text(
            "\n".join(lines) + "\n")

    def cap_manifest_rows(self):
        cap_dirs = sorted((self.ws / "worktree-archive").glob(
            "*/repo-a-branch-cap"))
        self.assertEqual(len(cap_dirs), 1)
        return [ln.split("\t") for ln in
                (cap_dirs[0] / "manifest.tsv")
                .read_text().splitlines()
                if ln and not ln.startswith("#")
                and not ln.startswith("branch\t")]

    def test_sweep_and_cap_never_take_principal_branches(self):
        # base=dev, default=main, main strictly contained
        # in dev: the sweep enqueues neither principal,
        # and the cap phase — population 5 per side, cap
        # 3 — takes its excess from the selectable
        # branches alone. Both principals stand in both
        # scopes by derivation, not by ranking: their
        # tips are the two OLDEST in the population, so
        # the pre-cure ranking would have taken main
        # first.
        self.add_dev_flow()
        names = [f"feat/p{i}" for i in range(3)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 80000 + i * 10000)
        _git(self.main, "push", "origin", *names,
             env=self.env)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP_REPO_A": "3"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("branch=main", out.stdout)
        self.assertNotIn("branch=dev", out.stdout)
        self.assertTrue(self.branch_exists("main"))
        self.assertTrue(self.branch_exists("dev"))
        remote = self.remote_branches()
        self.assertIn("main", remote)
        self.assertIn("dev", remote)
        self.assertIn("BRANCH-CAP repo=repo-a side=local live=5 "
                      "cap=3 archived=2", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin live=5 "
                      "cap=3 archived=2", out.stdout)
        self.assertFalse(self.branch_exists(names[0]))
        self.assertFalse(self.branch_exists(names[1]))
        self.assertTrue(self.branch_exists(names[2]))
        self.assertNotIn(names[0], remote)
        self.assertNotIn(names[1], remote)
        self.assertIn(names[2], remote)
        self.assertEqual(self.queue(), [])
        rows = self.cap_manifest_rows()
        self.assertEqual([r[0] for r in rows], names[:2])

    def test_drain_refuses_and_drops_principal_charges(self):
        # a standing cap charge naming main (the
        # incident's exact residue) and a legacy bare
        # charge naming dev: the drain refuses both with
        # reason=principal and drops them — no delete is
        # attempted against the fixture remote, whatever
        # code wrote the charges.
        self.add_dev_flow()
        main_tip = _git(self.main, "rev-parse", "main",
                        env=self.env).stdout.strip()
        self.seed_queue(f"main\t{main_tip}\tcap", "dev")
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-DRAIN-SKIP repo=repo-a branch=main "
                      "scope=origin reason=principal", out.stdout)
        self.assertIn("BRANCH-DRAIN-SKIP repo=repo-a branch=dev "
                      "scope=origin reason=principal", out.stdout)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a "
                         "branch=main", out.stdout)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a "
                         "branch=dev", out.stdout)
        remote = self.remote_branches()
        self.assertIn("main", remote)
        self.assertIn("dev", remote)
        self.assertEqual(self.queue(), [])

    def test_cap_over_reports_blocked_survivors(self):
        # the selectable population cannot cover the
        # excess: population 4 (main + two checked-out
        # branches + one orphan), branch cap 2. The one
        # selectable orphan is archived and trimmed; the
        # side ends over the bound, reported as
        # BRANCH-CAP-OVER with the blocked survivors'
        # reasons, and the pass ends partial. The
        # checked-out branches are neither selected nor
        # archived.
        self.add_tree("repo-a-a-wt", "feat/a",
                      [("a.txt", "a\n")], NOW - 5000)
        self.add_tree("repo-a-b-wt", "feat/b",
                      [("b.txt", "b\n")], NOW - 4000)
        self.add_orphan("feat/c", NOW - 6000)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP_REPO_A": "2"})
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("BRANCH-CAP repo=repo-a side=local live=4 "
                      "cap=2 archived=1", out.stdout)
        self.assertIn("BRANCH-CAP-OVER repo=repo-a side=local "
                      "live=4 cap=2 over=1 "
                      "survivors=checked-out,principal", out.stdout)
        self.assertFalse(self.branch_exists("feat/c"))
        self.assertTrue(self.branch_exists("feat/a"))
        self.assertTrue(self.branch_exists("feat/b"))
        self.assertTrue(self.branch_exists("main"))
        rows = self.cap_manifest_rows()
        self.assertEqual([r[0] for r in rows], ["feat/c"])


if __name__ == "__main__":
    unittest.main()
