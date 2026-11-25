"""Principal-branch specimens for the worktree trim:
the census's own reference points — the
base branch and the remote's default branch, both derived
from the repo at census time, never a name list — are not
trim material in either scope, the drain refuses charges
naming one, and cap selection excludes checked-out
branches, reporting uncoverable excess honestly. A third
principal source — a branch the deployment config
declares for the repo (repos.conf field 4), for the
standing integration branch neither derivation can see —
stands in the same set, in every phase. Shares the
fixture harness in test_worktree_trim.py.
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


class TestDeclaredPrincipals(Fixture):
    """Declared principals: steampowernj's
    shape — the base and the remote's default both resolve
    to main, while the programme lands through dev, its
    standing integration branch. No derivation sees dev,
    so an hourly pass cap-archived origin dev
    at 00fb3e09 and deleted the ref. The deployment
    declares dev in repos.conf's 4th field; the declared
    branch is then principal in every phase — sweep, cap
    census, seed, drain — while the identical fixture
    WITHOUT the declaration trims it, proving the
    declaration, not the name, is what protects it."""

    def add_steam_shape(self):
        """main base + main remote default; dev one commit
        ahead of main (uncontained, never tip-equal) with
        the OLDEST tip in the population; three orphan
        lane branches, newer. All pushed to origin."""
        origin = self.add_origin()
        _git(origin, "symbolic-ref", "HEAD",
             "refs/heads/main", env=self.env)
        path = self.add_tree("repo-a-dev-wt", "dev",
                             [("dev.txt", "d\n")], NOW - 90000)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        names = [f"feat/p{i}" for i in range(3)]
        for i, name in enumerate(names):
            p = self.add_tree(
                f"repo-a-{name.replace('/', '-')}-wt", name,
                [(f"{name.replace('/', '-')}.txt", "x\n")],
                NOW - 80000 + i * 10000)
            _git(self.main, "worktree", "remove", str(p),
                 env=self.env)
        _git(self.main, "push", "origin", "main", "dev",
             *names, env=self.env)
        return names

    def write_config(self, principals=None):
        state = self.ws / "state"
        state.mkdir(parents=True, exist_ok=True)
        row = "repo-a 10 5"
        if principals:
            row += " " + principals
        (state / "repos.conf").write_text(row + "\n")

    def run_with_config(self):
        # no WORKTREE_TRIM_REPOS env: the target set, the
        # worktree cap, and the declaration all come from
        # the fixture repos.conf, as in deployment
        return self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_TRIM_REPOS": None,
                       "WT_TRIM_BRANCH_CAP_REPO_A": "3"})

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

    def test_declared_integration_branch_survives_cap(self):
        # population 5 per side, branch cap 3: the excess
        # is drawn from the selectable branches alone —
        # dev, though it carries the oldest tip, is never
        # selected, never archived, and stands in both
        # scopes; the two oldest lane branches go instead.
        names = self.add_steam_shape()
        self.write_config("dev")
        out = self.run_with_config()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("branch=dev", out.stdout)
        self.assertTrue(self.branch_exists("dev"))
        self.assertIn("dev", self.remote_branches())
        self.assertIn("BRANCH-CAP repo=repo-a side=local live=5 "
                      "cap=3 archived=2", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin live=5 "
                      "cap=3 archived=2", out.stdout)
        self.assertFalse(self.branch_exists(names[0]))
        self.assertFalse(self.branch_exists(names[1]))
        self.assertTrue(self.branch_exists(names[2]))
        remote = self.remote_branches()
        self.assertNotIn(names[0], remote)
        self.assertNotIn(names[1], remote)
        self.assertIn(names[2], remote)
        self.assertEqual(self.queue(), [])
        rows = self.cap_manifest_rows()
        self.assertEqual([r[0] for r in rows], names[:2])

    def test_undeclared_integration_branch_trims_at_cap(self):
        # the control: the identical fixture with no 4th
        # field — behaviour is exactly the pre-cure pass.
        # dev is the oldest selectable branch, so the cap
        # archives and trims it in both scopes.
        names = self.add_steam_shape()
        self.write_config()
        out = self.run_with_config()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-CAP repo=repo-a side=local live=5 "
                      "cap=3 archived=2", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin live=5 "
                      "cap=3 archived=2", out.stdout)
        self.assertFalse(self.branch_exists("dev"))
        self.assertNotIn("dev", self.remote_branches())
        self.assertFalse(self.branch_exists(names[0]))
        self.assertTrue(self.branch_exists(names[1]))
        self.assertTrue(self.branch_exists(names[2]))
        self.assertEqual(self.queue(), [])
        rows = self.cap_manifest_rows()
        self.assertEqual([r[0] for r in rows],
                         ["dev", names[0]])

    def test_drain_refuses_declared_principal_charge(self):
        # a standing cap charge naming dev — the incident
        # class of residue — is refused and dropped by the
        # drain once dev is declared; no delete is
        # attempted against the fixture remote.
        self.add_steam_shape()
        self.write_config("dev")
        dev_tip = _git(self.main, "rev-parse", "dev",
                       env=self.env).stdout.strip()
        self.seed_queue(f"dev\t{dev_tip}\tcap")
        out = self.run_with_config()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-DRAIN-SKIP repo=repo-a branch=dev "
                      "scope=origin reason=principal", out.stdout)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a "
                         "branch=dev", out.stdout)
        self.assertIn("dev", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_sweep_never_enqueues_declared_principal(self):
        # dev strictly contained in main (main advanced
        # past it after a sync): the containment sweep's
        # exact material pre-cure. Declared, it is never
        # enqueued and stands in both scopes.
        origin = self.add_origin()
        _git(origin, "symbolic-ref", "HEAD",
             "refs/heads/main", env=self.env)
        path = self.add_tree("repo-a-dev-wt", "dev",
                             [("dev.txt", "d\n")], NOW - 90000)
        self.land("dev")
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        self.add_landed_tree("repo-a-x-wt", "feat/x",
                             [("x.txt", "x\n")], NOW - 80000)
        _git(self.main, "push", "origin", "main", "dev",
             env=self.env)
        self.write_config("dev")
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_TRIM_REPOS": None})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("branch=dev", out.stdout)
        self.assertTrue(self.branch_exists("dev"))
        self.assertIn("dev", self.remote_branches())
        self.assertEqual(self.queue(), [])


if __name__ == "__main__":
    unittest.main()
