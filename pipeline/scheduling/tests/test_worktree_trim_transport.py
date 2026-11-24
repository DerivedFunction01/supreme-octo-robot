"""Venue-transport specimens for the worktree trim (the
2026-11-23 cure): a branch a venue run record names as
its transport base is not trim material while the run
family is live — non-terminal, or active within the
6-hour window — in either scope. The held set derives
from the run records at pass start, never a name list.
Shares the fixture harness in test_worktree_trim.py.
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


class TestVenueTransportHolds(Fixture):
    """Venue-transport branch holds (2026-11-23 cure).
    The hourly pass twice deleted edgar-sec's
    pperb-base-pin from origin while the PPE packet was
    in flight on it — the packet's emit/check family
    cycles on the pin at ~30-minute intervals — and the
    lane had to restore it server-side both times before
    it could fire. A run record names its transport
    exactly (transport = {kind: branch, repo, branch}),
    so the cure derives the held set from the records
    themselves: a branch is held while any record naming
    it is non-terminal, or while the record's newest
    activity (file mtime maxed with its
    last_evidence_at / terminal_event_at / finished_at
    stamps) is within 6 hours of the pass. The hold
    lapses mechanically when the family's records age
    past the window."""

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
        sweep's containment verdict is its only judge
        unless a hold stands."""
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
        dir (the trim's WORKTREE_TRIM_RUNS_DIR seam), in
        the runner's pretty-printed form. The record
        file's mtime is always set explicitly: the pass
        reads it as activity, and the fixture's fake
        clock is not the wall clock."""
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

    def test_running_record_holds_contained_transport_branch(self):
        # the defect's exact shape: the pin is strictly
        # contained in main, so containment alone would
        # sweep it in both scopes; a non-terminal record
        # naming it as transport base holds it, with a
        # HELD line in each scope.
        self.add_origin()
        self.add_contained("feat/pin", NOW - 80000)
        _git(self.main, "push", "origin", "main", "feat/pin",
             env=self.env)
        self.add_record("run-1", "running", "feat/pin",
                        mtime=NOW - 600)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("HELD repo=repo-a branch=feat/pin "
                      "scope=local reasons=venue-transport",
                      out.stdout)
        self.assertIn("HELD repo=repo-a branch=feat/pin "
                      "scope=origin reasons=venue-transport",
                      out.stdout)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a "
                         "branch=feat/pin", out.stdout)
        self.assertTrue(self.branch_exists("feat/pin"))
        self.assertIn("feat/pin", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_recent_terminal_record_holds_by_its_stamps(self):
        # a terminal record still holds its transport
        # branch inside the window: the packet family
        # cycles, and one member's completion is not the
        # family's end. The stamps (1h old) govern even
        # though the record file's mtime is 7h old — the
        # activity is the max of the two shapes.
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
            mtime=NOW - WINDOW - 3600)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("HELD repo=repo-a branch=feat/pin "
                      "scope=origin reasons=venue-transport",
                      out.stdout)
        self.assertTrue(self.branch_exists("feat/pin"))
        self.assertIn("feat/pin", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_recent_mtime_holds_despite_old_stamps(self):
        # the other half of the max(): the record's
        # stamps are 7h old but the file itself moved
        # 10 minutes ago (a collector's late evidence
        # landing) — the branch is held.
        self.add_origin()
        self.add_contained("feat/pin", NOW - 80000)
        _git(self.main, "push", "origin", "main", "feat/pin",
             env=self.env)
        stale = _iso(NOW - WINDOW - 3600)
        self.add_record(
            "run-1", "failed", "feat/pin",
            stamps={"last_evidence_at": stale,
                    "terminal_event_at": stale,
                    "finished_at": stale},
            mtime=NOW - 600)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("HELD repo=repo-a branch=feat/pin "
                      "scope=origin reasons=venue-transport",
                      out.stdout)
        self.assertTrue(self.branch_exists("feat/pin"))
        self.assertIn("feat/pin", self.remote_branches())

    def test_stale_terminal_record_releases_transport_branch(self):
        # the family's last record is terminal and 7h
        # old by every activity shape: the hold has
        # lapsed mechanically and the contained branch
        # is ordinary trim material again, in both
        # scopes.
        self.add_origin()
        self.add_contained("feat/pin", NOW - 80000)
        _git(self.main, "push", "origin", "main", "feat/pin",
             env=self.env)
        stale = _iso(NOW - WINDOW - 3600)
        self.add_record(
            "run-1", "complete", "feat/pin",
            stamps={"last_evidence_at": stale,
                    "terminal_event_at": stale,
                    "finished_at": stale},
            mtime=NOW - WINDOW - 3600)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("HELD repo=repo-a branch=feat/pin",
                         out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/pin scope=local", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/pin scope=origin", out.stdout)
        self.assertFalse(self.branch_exists("feat/pin"))
        self.assertNotIn("feat/pin", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_transport_for_another_repo_holds_nothing_here(self):
        # a record naming the same branch name as the
        # transport base of a DIFFERENT repo's run holds
        # nothing in this repo: the held set is keyed by
        # the record's repo, matched against the repo
        # being capped.
        self.add_origin()
        self.add_contained("feat/pin", NOW - 80000)
        _git(self.main, "push", "origin", "main", "feat/pin",
             env=self.env)
        self.add_record("run-1", "running", "feat/pin",
                        repo="repo-b", mtime=NOW - 600)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("HELD repo=repo-a branch=feat/pin",
                         out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/pin scope=local", out.stdout)
        self.assertFalse(self.branch_exists("feat/pin"))
        self.assertNotIn("feat/pin", self.remote_branches())

    def test_malformed_records_are_skipped(self):
        # a truncated record (its transport object never
        # closes), a record whose transport names no
        # branch, and a file that is not JSON at all:
        # none holds anything, none is fatal — the pass
        # completes and the contained branch trims as if
        # the records were absent.
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
        self.assertNotIn("HELD repo=repo-a branch=feat/pin",
                         out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a "
                      "branch=feat/pin scope=local", out.stdout)
        self.assertFalse(self.branch_exists("feat/pin"))
        self.assertNotIn("feat/pin", self.remote_branches())

    def test_held_pin_under_cap_pressure_no_cap_over(self):
        # population 5 per side, branch cap 3: the pin —
        # the OLDEST tip in the population, so ranking
        # alone would take it first — is blocked as
        # venue-transport, and the excess comes from the
        # selectable orphans alone. Because the selectable
        # population covers the excess, no BRANCH-CAP-OVER
        # is reported and the pass is complete.
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
        self.assertIn("HELD repo=repo-a branch=feat/pin "
                      "scope=local reasons=venue-transport",
                      out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=local "
                      "live=5 cap=3 archived=2", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin "
                      "live=5 cap=3 archived=2", out.stdout)
        self.assertNotIn("BRANCH-CAP-OVER", out.stdout)
        self.assertTrue(self.branch_exists(pin))
        remote = self.remote_branches()
        self.assertIn(pin, remote)
        self.assertFalse(self.branch_exists(names[0]))
        self.assertFalse(self.branch_exists(names[1]))
        self.assertTrue(self.branch_exists(names[2]))
        self.assertNotIn(names[0], remote)
        self.assertNotIn(names[1], remote)
        self.assertIn(names[2], remote)
        self.assertEqual(self.queue(), [])
        rows = self.cap_manifest_rows()
        self.assertEqual([r[0] for r in rows], names[:2])

    def test_cap_over_reports_transport_held_survivor(self):
        # the other face of the census transfer: the
        # selectable population cannot cover the excess —
        # population 3 per side (main + the held pin +
        # one orphan), branch cap 1. The orphan is
        # archived and trimmed; each side ends over the
        # bound, reported as BRANCH-CAP-OVER whose
        # survivors name venue-transport — the OVER
        # line's reasons are read from the same laid
        # marks the selection consults, so a transfer
        # that laid no mark would take the pin instead
        # of reporting it as a blocked survivor (the
        # 2026-11-24 escape's shape, from the other
        # side). The pass ends partial.
        self.add_origin()
        pin = "feat/pin"
        self.add_orphan(pin, NOW - 90000)
        self.add_orphan("feat/o0", NOW - 80000)
        _git(self.main, "push", "origin", "main", pin,
             "feat/o0", env=self.env)
        self.add_record("run-1", "running", pin, mtime=NOW - 600)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_BRANCH_CAP_REPO_A": "1"})
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("HELD repo=repo-a branch=feat/pin "
                      "scope=local reasons=venue-transport",
                      out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=local "
                      "live=3 cap=1 archived=1", out.stdout)
        self.assertIn("BRANCH-CAP repo=repo-a side=origin "
                      "live=3 cap=1 archived=1", out.stdout)
        self.assertIn("BRANCH-CAP-OVER repo=repo-a side=local "
                      "live=3 cap=1 over=1 "
                      "survivors=principal,venue-transport",
                      out.stdout)
        self.assertIn("BRANCH-CAP-OVER repo=repo-a side=origin "
                      "live=3 cap=1 over=1 "
                      "survivors=principal,venue-transport",
                      out.stdout)
        self.assertNotIn("BRANCH-ARCHIVED repo=repo-a "
                         "branch=feat/pin", out.stdout)
        self.assertTrue(self.branch_exists(pin))
        remote = self.remote_branches()
        self.assertIn(pin, remote)
        self.assertFalse(self.branch_exists("feat/o0"))
        self.assertNotIn("feat/o0", remote)
        self.assertEqual(self.queue(), [])
        rows = self.cap_manifest_rows()
        self.assertEqual([r[0] for r in rows], ["feat/o0"])

    def test_drain_refuses_transport_held_charge(self):
        # a standing cap charge naming the pin — written
        # before the run family's hold stood: the drain
        # refuses it with reason=venue-transport and
        # drops it; no delete is attempted against the
        # fixture remote.
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
        self.assertIn("BRANCH-DRAIN-SKIP repo=repo-a "
                      "branch=feat/pin scope=origin "
                      "reason=venue-transport", out.stdout)
        self.assertNotIn("BRANCH-TRIMMED repo=repo-a "
                         "branch=feat/pin", out.stdout)
        self.assertIn("feat/pin", self.remote_branches())
        self.assertEqual(self.queue(), [])


if __name__ == "__main__":
    unittest.main()
