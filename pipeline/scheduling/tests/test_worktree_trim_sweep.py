"""Branch-sweep specimens for the worktree trim,
sharing the fixture harness in test_worktree_trim.py.

The pre-cure trim charged a branch trim only at the purge
of an archive the trim itself had made, plus a crash queue
seeded from archive manifests. Branches pushed to origin
by lanes whose worktrees never stood in the local census
(venue/session clones) were never trimmed: a tenant repo
accumulated 144 origin branches, 111 fully contained in
main. The owner's ruling: the hourly pass takes no
exemptions when it comes to trimming. The sweep censuses
ALL branches every pass; containment in the default branch
is the only criterion — no provenance, no held set, no
name carve-outs. Within the containment half alone, the
default branch itself and, locally, a branch checked out
in a worktree stand mechanically (git refuses those);
the cap phase in TestBranchCap ranks the whole
population by tip activity, but its candidates are the
selectable rows alone: principal branches (the base;
the remote's default) and worktree-checked-out branches
are structurally excluded from candidacy — derived from
the repo at census, never a name list
(test_worktree_trim_principal).
"""

import subprocess
import unittest
from pathlib import Path

from tests.test_worktree_trim import HOUR, NOW, Fixture, _git

BRANCHCAP = (Path(__file__).resolve().parents[1]
             / "ops" / "trim" / "trim_branchcap.sh")


def _advance_main(fx, epoch=NOW - 3000):
    """One more commit on main after a landing, so a
    landed branch stands STRICTLY contained — main has
    moved past its tip, the production shape a day after
    a landing. (A branch left exactly at main's tip is
    the tip-equal case, pinned in TestTipEqual.)"""
    (fx.main / "post-landing.txt").write_text("post\n")
    _git(fx.main, "add", ".", env=fx.env)
    _git(fx.main, "commit", "-m", "post-landing",
         epoch=epoch, env=fx.env)


class TestBranchSweep(Fixture):
    def add_orphan_branch(self, branch, fname):
        """A landed branch with no worktree and no archive
        manifest: grown in a tree, fast-forwarded into main,
        then the tree is removed — the branch stands alone,
        exactly the shape the pre-cure trim never charged.
        Main then advances one commit, so the branch stands
        strictly contained (a branch left at main's exact
        tip is the tip-equal case, pinned in TestTipEqual)."""
        path = self.add_landed_tree(
            f"repo-a-{branch.replace('/', '-')}-wt", branch,
            [(fname, "x\n")], NOW - 4000)
        _advance_main(self)
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
        _advance_main(self)
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
    no exemptions by name). Excess branches are archive-
    before-delete: their tips land in one verified bundle
    with a manifest before any ref moves. The structural
    exclusions (principal branches, checked-out branches)
    bind candidacy, not by name — see
    TestPrincipalBranches."""

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
        # Orphan tips are dated older than main's tip, as in
        # production, where the default branch's tip is the
        # freshest (the landing target) and stands by the
        # same activity ranking as every other branch.
        self.add_origin()
        names = [f"feat/b{i:02d}" for i in range(13)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 120000 + i * 1000)
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
            self.add_orphan(name, NOW - 120000 + i * 1000)
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

    def test_cap_failure_line_carries_the_command_error(self):
        # The diagnosability cure: a covered step's
        # failure records the failing command's own error
        # text on the BRANCH-CAP-FAIL line (err=), not the
        # bare reason alone — a contention-class failure
        # must arrive with its error attached.
        # Manufacture: a standing bundle that is not a
        # bundle at all, so the merge step's fetch of it
        # fails (prior-bundle-unreadable) with git's error
        # in hand.
        self.add_origin()
        names = [f"feat/e{i:02d}" for i in range(12)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 120000 + i * 1000)
        _git(self.main, "push", "origin", "main", *names,
             env=self.env)
        today = subprocess.run(
            ["date", "-d", f"@{NOW}", "+%F"],
            capture_output=True, text=True).stdout.strip()
        cap_dir = (self.ws / "worktree-archive" / today
                   / f"{self.slug}-branch-cap")
        cap_dir.mkdir(parents=True)
        (cap_dir / "branches.bundle").write_text(
            "not a bundle\n")
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 3,
                         out.stdout + out.stderr)
        fail = [ln for ln in out.stdout.splitlines()
                if "BRANCH-CAP-FAIL" in ln]
        self.assertEqual(len(fail), 1, out.stdout)
        self.assertIn("reason=prior-bundle-unreadable",
                      fail[0])
        self.assertIn(" err=", fail[0])
        self.assertIn("Could not read from remote "
                      "repository", fail[0])
        # archive-before-delete still binds: no ref moved
        self.assertEqual(self.local_branches(),
                         {"main"} | set(names))
        self.assertEqual(self.queue(), [])

    def test_recreated_branch_rearchives_at_a_divergent_tip(self):
        # A branch archived by one pass, deleted, then
        # recreated by a lane with fresh history stands at
        # a tip that does not descend from its archived
        # tip. The next pass's merge fetch must still take
        # it — the archive ref is a record and the newest
        # staging wins — where an unforced fetch rejects
        # the update as non-fast-forward and fails the
        # whole cap phase (the production failure: the
        # term-index branches, recreated after archiving).
        self.add_origin()
        names = [f"feat/r{i:02d}" for i in range(13)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 120000 + i * 1000)
        _git(self.main, "push", "origin", "main", *names,
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        heads = _git(self.main, "bundle", "list-heads",
                     str(self.cap_dir() / "branches.bundle"),
                     env=self.env).stdout
        archived = [ln.split()[0] for ln in heads.splitlines()
                    if ln.endswith("refs/archive-cap/feat/r00")]
        self.assertEqual(len(archived), 1)
        archived = archived[0]
        # Recreate the four archived names on fresh
        # history (main has not moved; a new side commit
        # off it is still no descendant of the archived
        # side tip), tips dated oldest so the cap selects
        # them again — and dated off the originals' epochs,
        # since the fixture's commits are deterministic in
        # content, parent and date.
        for i, name in enumerate(names[:4]):
            self.add_orphan(name, NOW - 120500 + i * 1000)
        _git(self.main, "push", "origin", *names[:4],
             env=self.env)
        new_tip = _git(self.main, "rev-parse", "feat/r00",
                       env=self.env).stdout.strip()
        self.assertNotEqual(new_tip, archived)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("BRANCH-CAP-FAIL", out.stdout)
        heads = _git(self.main, "bundle", "list-heads",
                     str(self.cap_dir() / "branches.bundle"),
                     env=self.env).stdout
        now_archived = [ln.split()[0] for ln in heads.splitlines()
                        if ln.endswith("refs/archive-cap/feat/r00")]
        self.assertEqual(now_archived, [new_tip])

    def test_merge_fetch_bound_is_priced_and_timeout_named(self):
        # The merge fetch's bound is priced by the bundle
        # it carries (cap_fetch_timeout at both fetch
        # sites), never a fixed 60s: the largest repo's
        # fetch crossed the fixed bound under the pass's
        # own parallel convoy and died silently, reported
        # as an unreadable bundle the same pass had just
        # verified. A death by the bound (status 124)
        # names itself -bundle-timeout via cap_fetch_fail.
        src = BRANCHCAP.read_text()
        self.assertNotIn("timeout 60", src)
        self.assertEqual(src.count("$(cap_fetch_timeout"), 2)
        self.assertIn("cap_fetch_fail()", src)
        self.assertIn('"$1-bundle-timeout"', src)
        self.assertIn('"$1-bundle-unreadable"', src)

    def test_attached_excess_branch_stands_cap_takes_selectable(self):
        # (h'') A checked-out branch is not cap-selectable
        # on either side and is not archived by the cap
        # phase; the excess is taken from the selectable
        # population instead. Detaching a worktree's HEAD to
        # free its branch can fail against a tree held as
        # unlanded — the tenant-repo form
        # specimen (BRANCH-LOCAL-FAIL
        # reason=detach-failed) — and leave the pass over
        # cap on both sides. Same fixture as (h'): per-slug
        # cap 3; the
        # population per side is main plus the attached
        # branch (the oldest tip of all) plus four orphans.
        self.add_origin()
        tree = self.add_tree("repo-a-held-wt", "feat/held",
                             [("held.txt", "h\n")], NOW - 130000)
        held_tip = _git(self.main, "rev-parse", "feat/held",
                        env=self.env).stdout.strip()
        orphans = [f"feat/o{i}" for i in range(4)]
        for i, name in enumerate(orphans):
            self.add_orphan(name, NOW - 120000 + i * 1000)
        _git(self.main, "push", "origin", "main", "feat/held",
             *orphans, env=self.env)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP_REPO_A": "3"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # ranked by tip activity: held (NOW-130000), o0..o3
        # (NOW-120000..NOW-117000), main (NOW-100000).
        # Blocked: main (principal), feat/held (checked
        # out). The excess of 3 comes from the selectable
        # orphans alone: o0, o1, o2; keep = o3, held, main.
        self.assertEqual(self.local_branches(),
                         {"main", "feat/held", orphans[3]})
        self.assertEqual(len(self.local_branches()), 3)
        self.assertTrue(self.branch_exists("feat/held"))
        remote = self.remote_branches()
        self.assertIn("feat/held", remote)
        self.assertNotIn(orphans[0], remote)
        self.assertNotIn(orphans[1], remote)
        self.assertNotIn(orphans[2], remote)
        self.assertIn(orphans[3], remote)
        self.assertIn("main", remote)
        self.assertIn("BRANCH-CAP repo=repo-a side=local live=6 "
                      "cap=3 archived=3", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin live=6 "
                      "cap=3 archived=3", out.stdout)
        self.assertNotIn("BRANCH-CAP-OVER", out.stdout)
        # the bundle holds the selectable excess only —
        # the attached branch is NOT archived by the cap
        # phase, on either side
        self.assertNotIn("BRANCH-ARCHIVED repo=repo-a "
                         "branch=feat/held", out.stdout)
        rows = self.manifest_rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual([r[0] for r in rows], orphans[:3])
        self.assertTrue(all(r[3] == "local,origin" for r in rows))
        bundle = self.cap_dir() / "branches.bundle"
        verify = _git(self.main, "bundle", "verify", str(bundle),
                      env=self.env, check=False)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        # the worktree still stands, still ON its branch
        # at the same tip, its files untouched — the cap
        # never detaches a tree to take its branch
        self.assertTrue(tree.is_dir())
        head = _git(tree, "rev-parse", "HEAD",
                    env=self.env).stdout.strip()
        self.assertEqual(head, held_tip)
        sym = _git(tree, "symbolic-ref", "-q", "HEAD",
                   env=self.env)
        self.assertEqual(sym.stdout.strip(),
                         "refs/heads/feat/held")
        self.assertEqual((tree / "held.txt").read_text(), "h\n")
        self.assertEqual(self.queue(), [])

    def test_restore_from_bundle_lands_on_recorded_tip(self):
        # (i) the manifest header's restore commands, run
        # verbatim in form, recreate the branch at exactly
        # the tip sha the manifest recorded.
        names = [f"feat/r{i}" for i in range(3)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 120000 + i * 1000)
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


class TestTipEqual(Fixture):
    """The tip-equal exclusion: a branch
    whose tip EQUALS the default branch's tip at census
    is not swept, on either side — the exclusion keys on
    the ref's position, not its name (a tip-equal ref is
    where the default branch itself stands; in a dev-flow
    repo, the standing integration point). The branch
    stays in the cap census, cap-eligible as any other."""

    def add_tip_equal(self, branch, fname):
        """A branch landed by fast-forward and never
        advanced past: its tip is main's tip exactly."""
        path = self.add_landed_tree(
            f"repo-a-{branch.replace('/', '-')}-wt", branch,
            [(fname, "x\n")], NOW - 4000)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        return _git(self.main, "rev-parse", branch,
                    env=self.env).stdout.strip()

    def test_tip_equal_survives_sweep_both_sides(self):
        self.add_origin()
        tip = self.add_tip_equal("feat/eq", "eq.txt")
        _git(self.main, "push", "origin", "main", "feat/eq",
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        line = ("BRANCH-CONTAINED-SKIP-EQUAL repo=repo-a "
                f"branch=feat/eq sha={tip}")
        # one disposition line per side: local and origin
        self.assertEqual(out.stdout.count(line), 2)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a "
                         "branch=feat/eq", out.stdout)
        self.assertTrue(self.branch_exists("feat/eq"))
        self.assertIn("feat/eq", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_branch_leaving_tip_equal_trims_next_pass(self):
        # composition at the boundary: the exclusion is a
        # census-time disposition. Once main advances, the
        # same branch is strictly contained and the sweep
        # takes it by plain containment, in both scopes.
        self.add_origin()
        tip = self.add_tip_equal("feat/eq2", "eq2.txt")
        _git(self.main, "push", "origin", "main", "feat/eq2",
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-CONTAINED-SKIP-EQUAL", out.stdout)
        self.assertTrue(self.branch_exists("feat/eq2"))
        _advance_main(self)
        _git(self.main, "push", "origin", "main", env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/eq2 "
                      f"scope=local sha={tip}", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/eq2 "
                      f"scope=origin sha={tip}", out.stdout)
        self.assertFalse(self.branch_exists("feat/eq2"))
        self.assertNotIn("feat/eq2", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_tip_equal_branch_is_cap_excess_when_oldest(self):
        # the exclusion is from the sweep only: the
        # tip-equal branch stands in the cap census, and
        # ranked oldest — its tip ties the base's epoch
        # and the name tiebreak puts 'dev' ahead of
        # 'main' — it is the excess: archived into the
        # verified bundle and deleted on both sides, like
        # any excess (cap behaviour unchanged).
        self.add_origin()
        dev_tip = self.add_tip_equal("dev", "dev.txt")
        orphans = ["feat/o1", "feat/o2"]
        for i, name in enumerate(orphans):
            p = self.add_tree(
                f"repo-a-{name.replace('/', '-')}-wt", name,
                [(f"{name.split('/')[1]}.txt", "x\n")],
                NOW - 3000 + i * 1000)
            _git(self.main, "worktree", "remove", str(p),
                 env=self.env)
        _git(self.main, "push", "origin", "main", "dev",
             *orphans, env=self.env)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP_REPO_A": "3"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-CONTAINED-SKIP-EQUAL repo=repo-a "
                      f"branch=dev sha={dev_tip}", out.stdout)
        self.assertIn("BRANCH-ARCHIVED repo=repo-a branch=dev "
                      "sides=local,origin", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=local live=4 "
                      "cap=3 archived=1", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin live=4 "
                      "cap=3 archived=1", out.stdout)
        self.assertFalse(self.branch_exists("dev"))
        self.assertNotIn("dev", self.remote_branches())
        self.assertTrue(self.branch_exists("feat/o1"))
        self.assertIn("feat/o2", self.remote_branches())
        cap_dirs = sorted((self.ws / "worktree-archive").glob(
            "*/repo-a-branch-cap"))
        self.assertEqual(len(cap_dirs), 1)
        rows = [ln.split("\t") for ln in
                (cap_dirs[0] / "manifest.tsv")
                .read_text().splitlines()
                if ln and not ln.startswith("#")
                and not ln.startswith("branch\t")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "dev")
        self.assertEqual(rows[0][1], dev_tip)
        self.assertEqual(self.queue(), [])


class TestDrainReverify(Fixture):
    """Drain re-verification: a guarded queue
    charge carries the tip its containment verdict was
    computed against; at discharge the LIVE tip governs.
    A branch that advanced to unlanded work after its
    verdict survives with a BRANCH-DRAIN-SKIP naming both
    tips; one that advanced within main is deleted, and
    the record carries the tip actually deleted."""

    def seed_queue(self, *lines):
        state = self.ws / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / f"remote-pending-{self.slug}.txt").write_text(
            "\n".join(lines) + "\n")

    def add_contained(self, branch, fname):
        """A landed branch main has since advanced past:
        strictly contained in both scopes, no worktree."""
        path = self.add_landed_tree(
            f"repo-a-{branch.replace('/', '-')}-wt", branch,
            [(fname, "x\n")], NOW - 4000)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        _advance_main(self)
        _git(self.main, "push", "origin", "main", branch,
             env=self.env)
        return _git(self.main, "rev-parse", branch,
                    env=self.env).stdout.strip()

    def grow_tip(self, branch, fname, push):
        """Advance a branch by one unlanded commit grown
        in a scratch tree (removed after); returns the
        new tip."""
        tree = self.ws / f"repo-a-{branch.replace('/', '-')}-move"
        _git(self.main, "worktree", "add", str(tree), branch,
             env=self.env)
        (tree / fname).write_text("more\n")
        _git(tree, "add", ".", env=self.env)
        _git(tree, "commit", "-m", "more work",
             epoch=NOW - 2000, env=self.env)
        tip = _git(tree, "rev-parse", "HEAD",
                   env=self.env).stdout.strip()
        if push:
            _git(self.main, "push", "origin", branch,
                 env=self.env)
        _git(self.main, "worktree", "remove", str(tree),
             env=self.env)
        return tip

    def write_sibling_manifest(self, branch, path, head):
        """A dead archive's sibling manifest: the crash
        window the seed phase charges, carrying the
        head the branch trim is evaluated against."""
        cap = self.ws / "worktree-archive" / "2026-01-01"
        cap.mkdir(parents=True, exist_ok=True)
        (cap / f"{self.slug}__gone.manifest.txt").write_text(
            f"repo={self.slug}\ntree=gone\nbranch={branch}\n"
            f"path={path}\nhead={head}\n"
            f"expiry_epoch={NOW + HOUR}\n")

    def test_origin_tip_moved_uncontained_survives(self):
        # (a) the charge was enqueued against the old,
        # contained tip; the branch then advanced to
        # unlanded work. The drain re-evaluates the live
        # tip, keeps the branch, and drops the charge.
        self.add_origin()
        evaluated = self.add_contained("feat/mv", "mv.txt")
        self.seed_queue(f"feat/mv\t{evaluated}\tsweep")
        live = self.grow_tip("feat/mv", "more.txt", push=True)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(
            "BRANCH-DRAIN-SKIP repo=repo-a branch=feat/mv "
            "scope=origin reason=tip-moved-not-contained "
            f"evaluated={evaluated} live={live}", out.stdout)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a "
                         "branch=feat/mv", out.stdout)
        self.assertIn("feat/mv", self.remote_branches())
        self.assertTrue(self.branch_exists("feat/mv"))
        self.assertEqual(self.queue(), [])

    def test_origin_tip_moved_contained_trims_at_live_sha(self):
        # (b) the branch advanced — to the base's own tip,
        # still contained. (At census the sweep spares it
        # as tip-equal; the standing queue charge still
        # governs the drain.) The drain re-verifies the
        # live tip, deletes, and records the LIVE sha.
        self.add_origin()
        evaluated = self.add_contained("feat/mv2", "mv2.txt")
        self.seed_queue(f"feat/mv2\t{evaluated}\tsweep")
        live = _git(self.main, "rev-parse", "main",
                    env=self.env).stdout.strip()
        _git(self.main, "push", "origin",
             "main:refs/heads/feat/mv2", env=self.env)
        _git(self.main, "branch", "-D", "feat/mv2",
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-CONTAINED-SKIP-EQUAL repo=repo-a "
                      "branch=feat/mv2", out.stdout)
        self.assertIn(
            "BRANCH-TRIMMED repo=repo-a branch=feat/mv2 "
            f"scope=origin sha={live}", out.stdout)
        self.assertNotIn("feat/mv2", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_origin_tip_unchanged_trims_at_evaluated_sha(self):
        # (c) no movement: the drain deletes as before,
        # and both the result line and the ledger carry
        # the evaluated tip — the pass record now states
        # what it evaluated.
        self.add_origin()
        evaluated = self.add_contained("feat/still", "still.txt")
        self.seed_queue(f"feat/still\t{evaluated}\tsweep")
        _git(self.main, "branch", "-D", "feat/still",
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(
            "BRANCH-TRIMMED repo=repo-a branch=feat/still "
            f"scope=origin sha={evaluated}", out.stdout)
        self.assertNotIn("feat/still", self.remote_branches())
        self.assertEqual(self.queue(), [])
        ledger = (self.ws / "state" / "ledger.jsonl").read_text()
        self.assertIn(
            "act=branch-trim repo=repo-a branch=feat/still "
            f"scope=origin sha={evaluated}", ledger)

    def test_local_seed_tip_moved_uncontained_survives(self):
        # (d) the local path, reached through the seed: a
        # dead archive's manifest charges the branch trim
        # against its recorded head; the branch has since
        # moved to unlanded work, so the local delete
        # re-evaluates and keeps it.
        path = self.add_landed_tree(
            "repo-a-sd-wt", "feat/sd", [("sd.txt", "x\n")],
            NOW - 4000)
        evaluated = _git(self.main, "rev-parse", "feat/sd",
                         env=self.env).stdout.strip()
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        live = self.grow_tip("feat/sd", "more.txt", push=False)
        self.write_sibling_manifest("feat/sd", str(path),
                                    evaluated)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(
            "BRANCH-DRAIN-SKIP repo=repo-a branch=feat/sd "
            "scope=local reason=tip-moved-not-contained "
            f"evaluated={evaluated} live={live}", out.stdout)
        self.assertTrue(self.branch_exists("feat/sd"))

    def test_local_seed_tip_moved_contained_trims_at_live_sha(self):
        # (d2) the seed charge, the branch moved within
        # main (re-pointed at the base's advanced tip):
        # re-evaluation finds the live tip contained, the
        # delete proceeds, and the record carries the
        # live sha — not the manifest's stale head.
        path = self.add_landed_tree(
            "repo-a-sc-wt", "feat/sc", [("sc.txt", "x\n")],
            NOW - 4000)
        evaluated = _git(self.main, "rev-parse", "feat/sc",
                         env=self.env).stdout.strip()
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        _advance_main(self)
        live = _git(self.main, "rev-parse", "main",
                    env=self.env).stdout.strip()
        _git(self.main, "branch", "-f", "feat/sc", "main",
             env=self.env)
        self.write_sibling_manifest("feat/sc", str(path),
                                    evaluated)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(
            "BRANCH-TRIMMED repo=repo-a branch=feat/sc "
            f"scope=local sha={live}", out.stdout)
        self.assertFalse(self.branch_exists("feat/sc"))
