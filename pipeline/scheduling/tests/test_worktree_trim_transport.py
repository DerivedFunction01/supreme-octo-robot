"""Venue-transport specimens for the worktree trim, under
the no-held-set ruling (owner, 2026-11-26): a branch a
venue run record names as its transport base gets NO
exemption from the cap in any phase. The 2026-11-23 cure
held such branches (the PPE packet's pperb-base-pin,
deleted twice mid-flight); the ruling retired every hold
that outranks the cap — a claimed in-flight state is
exactly how a surface stays up forever — so the trim no
longer reads run records at all, and a transport-named
branch is swept, capped, and drained on the same
criteria as any other branch. These specimens plant the
records the old cure read and pin that they change
nothing. Shares the fixture harness in
test_worktree_trim.py.
"""

import json
import os
import unittest
from datetime import datetime, timezone

from tests.test_worktree_trim import NOW, Fixture, _git

WINDOW = 6 * 3600


def _iso(epoch):
    return datetime.fromtimestamp(
        epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


class TestVenueTransportNoExemption(Fixture):
    """Run records exempt nothing (owner ruling,
    2026-11-26). The specimens keep the old cure's exact
    shapes — a contained pin, a live family cycling on
    it — and assert the ordinary outcomes."""

    def add_orphan(self, branch, epoch):
        """An unlanded branch with no standing worktree:
        survives the sweep on containment, so the cap
        phase alone decides its fate."""
        path = self.add_tree(
            f"repo-a-{branch.replace('/', '-')}-wt", branch,
            [(f"{branch.replace('/', '-')}.txt", "x\n")], epoch)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        return path

    def add_contained(self, branch, epoch):
        """A branch strictly contained in main, with no
        standing worktree: landed, then main advanced
        past its tip (so it is not tip-equal). The
        sweep's containment verdict is its only judge."""
        path = self.add_tree(
            f"repo-a-{branch.replace('/', '-')}-wt", branch,
            [(f"{branch.replace('/', '-')}.txt", "x\n")], epoch)
        self.land(branch)
        _git(self.main, "worktree", "remove", str(path),
             env=self.env)
        adv = f"feat/advance-{branch.replace('/', '-')}"
        apath = self.add_tree("repo-a-advance-wt", adv,
                              [("advance.txt", "a\n")], epoch + 10)
        self.land(adv)
        _git(self.main, "worktree", "remove", str(apath),
             env=self.env)
        return path

    def add_record(self, name, state, branch, repo="repo-a",
                   stamps=(), mtime=None, raw=None):
        """Plant a venue run record in the fixture runs
        dir, in the runner's pretty-printed form. The
        trim reads no run records under the no-held-set
        ruling; the plant is the specimen's claim, and
        the assertions pin that it changes nothing."""
        runs = self.ws / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        path = runs / f"{name}.json"
        if raw is not None:
            path.write_text(raw)
        else:
            rec = {"run_id": name, "state": state,
                   "transport": {"kind": "branch", "repo": repo,
                                 "branch": branch,
                                 "sha": "0" * 40}}
            rec.update(stamps)
            path.write_text(json.dumps(rec, indent=2))
        if mtime is not None:
            os.utime(path, (mtime, mtime))
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

    def test_running_record_exempts_no_contained_branch(self):
        # the old cure's exact specimen, inverted: the
        # pin is strictly contained in main, and a
        # non-terminal record names it as transport base.
        # Under the ruling the record changes nothing:
        # the sweep trims the pin in both scopes, with no
        # HELD line anywhere.
        self.add_origin()
        self.add_contained("feat/pin", NOW - 80000)
        _git(self.main, "push", "origin", "main", "feat/pin",
             env=self.env)
        self.add_record("run-1", "running", "feat/pin",
                        mtime=NOW - 600)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/pin scope=local", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/pin scope=origin", out.stdout)
        self.assertFalse(self.branch_exists("feat/pin"))
        self.assertNotIn("feat/pin", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_terminal_record_with_fresh_stamps_exempts_nothing(self):
        # the recency window is gone with the hold: a
        # terminal record whose stamps are an hour old
        # (the family's cycle still warm, by the old
        # reading) exempts its transport branch exactly
        # as much as a stale one — not at all.
        self.add_origin()
        self.add_contained("feat/pin", NOW - 80000)
        _git(self.main, "push", "origin", "main", "feat/pin",
             env=self.env)
        recent = _iso(NOW - 3600)
        self.add_record(
            "run-1", "complete", "feat/pin",
            stamps={"last_evidence_at": recent,
                    "terminal_event_at": recent,
                    "finished_at": recent},
            mtime=NOW - 600)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/pin scope=local", out.stdout)
        self.assertFalse(self.branch_exists("feat/pin"))
        self.assertNotIn("feat/pin", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_malformed_records_are_inert(self):
        # a truncated record, a record whose transport
        # names no branch, and a file that is not JSON at
        # all: the pass never opens them — it completes
        # and the contained branch trims as if the
        # records were absent.
        self.add_origin()
        self.add_contained("feat/pin", NOW - 80000)
        _git(self.main, "push", "origin", "main", "feat/pin",
             env=self.env)
        self.add_record(
            "truncated", None, None,
            raw='{"run_id": "truncated", "state": "running", '
                '"transport": {"kind": "branch", '
                '"repo": "repo-a", "branch": "feat/pin"')
        self.add_record(
            "nobranch", None, None,
            raw='{"run_id": "nobranch", "state": "running", '
                '"transport": {"kind": "branch", '
                '"repo": "repo-a"}}')
        self.add_record("junk", None, None,
                        raw="not json at all\n")
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/pin scope=local", out.stdout)
        self.assertFalse(self.branch_exists("feat/pin"))
        self.assertNotIn("feat/pin", self.remote_branches())

    def test_transport_pin_takes_the_cap_cut_like_any_orphan(self):
        # population 5 per side, branch cap 3: the pin is
        # the OLDEST tip in the population and a running
        # record names it. The cap takes the two oldest —
        # the pin first — and the excess is covered, so
        # no BRANCH-CAP-OVER is reported.
        self.add_origin()
        pin = "feat/pin"
        self.add_orphan(pin, NOW - 90000)
        names = [f"feat/o{i}" for i in range(3)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 80000 + i * 10000)
        _git(self.main, "push", "origin", "main", pin, *names,
             env=self.env)
        self.add_record("run-1", "running", pin, mtime=NOW - 600)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP_REPO_A": "3"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("HELD", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=local "
                      "live=5 cap=3 archived=2", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin "
                      "live=5 cap=3 archived=2", out.stdout)
        self.assertNotIn("BRANCH-CAP-OVER", out.stdout)
        self.assertFalse(self.branch_exists(pin))
        remote = self.remote_branches()
        self.assertNotIn(pin, remote)
        self.assertFalse(self.branch_exists(names[0]))
        self.assertTrue(self.branch_exists(names[1]))
        self.assertTrue(self.branch_exists(names[2]))
        self.assertNotIn(names[0], remote)
        self.assertIn(names[1], remote)
        self.assertIn(names[2], remote)
        self.assertEqual(self.queue(), [])
        rows = self.cap_manifest_rows()
        # manifest rows list in ref order, not selection
        # order: the archived pair is the pin and o0
        self.assertEqual(sorted(r[0] for r in rows),
                         sorted([pin, names[0]]))
        # the package carries its purge manifest: the
        # bundle is inside the trim regime, expiring on
        # the archive's grace from this write
        cap_dirs = sorted((self.ws / "worktree-archive").glob(
            "*/repo-a-branch-cap"))
        purge_manifest = (cap_dirs[0] / "manifest.txt").read_text()
        self.assertIn(f"expiry_epoch={NOW + 3600}",
                      purge_manifest)
        self.assertIn("kind=branch-cap", purge_manifest)

    def test_drain_discharges_a_charge_naming_a_transport_branch(self):
        # a standing cap charge naming the pin, with a
        # running record naming it as transport base: the
        # drain discharges the charge on its merits — the
        # record is not consulted and no venue-transport
        # skip exists to refuse it.
        self.add_origin()
        self.add_contained("feat/pin", NOW - 80000)
        _git(self.main, "push", "origin", "main", "feat/pin",
             env=self.env)
        pin_tip = _git(self.main, "rev-parse", "feat/pin",
                       env=self.env).stdout.strip()
        self.seed_queue(f"feat/pin\t{pin_tip}\tcap")
        self.add_record("run-1", "running", "feat/pin",
                        mtime=NOW - 600)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("BRANCH-DRAIN-SKIP", out.stdout)
        self.assertNotIn("feat/pin", self.remote_branches())
        self.assertEqual(self.queue(), [])


if __name__ == "__main__":
    unittest.main()
