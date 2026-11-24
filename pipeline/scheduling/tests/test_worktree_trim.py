"""Deterministic fixture tests for the worktree trim job.

Real git repos are built in temporary directories; the two
bash scripts (ops/worktree_trim.sh, ops/worktree_archive_clean.sh)
run against them with the fake-clock seam (WORKTREE_TRIM_NOW)
and path overrides, never against the live workspace.

The archive is a folder holding the worktree directory itself
(moved with mv), its git admin directory (the index moves
with it, so a move-back restores the tree whole), and a
manifest. Restoration is mechanical: ops/worktree_restore.sh.

Held set: a tree that is dirty, unlanded
(ahead of base / unmerged), live (a process holds it, or a
non-terminal run record names it), or explicitly held
(.trim-hold / holds.txt) is never archived and never counts
against the cap. An archived tree's branch is not trimmed
while the archive stands; the purge (worktree_archive_clean.sh)
trims it — locally and via the origin retry queue — only when
it still points at the manifest's recorded head and that head
is landed in base.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parent.parent / "ops"
TRIM = OPS / "worktree_trim.sh"
CLEAN = OPS / "worktree_archive_clean.sh"

NOW = 1795000000  # fixed fake clock for every fixture pass
HOUR = 3600


def _env(ws, extra=None):
    env = dict(os.environ)
    env.update({
        "SCHEDULER_WORKSPACE": str(ws),
        "WORKTREE_ARCHIVE_ROOT": str(ws / "worktree-archive"),
        "WORKTREE_TRIM_STATE_DIR": str(ws / "state"),
        "WORKTREE_TRIM_NOW": str(NOW),
        "WORKTREE_TRIM_REPOS": "repo-a",
        # hermetic held-set seams: fixture passes never read
        # the real /proc or the real venue run records
        "WORKTREE_TRIM_PROC_ROOT": str(ws / "proc"),
        "WORKTREE_TRIM_RUNS_DIR": str(ws / "runs"),
        # the branch leg's code default is exercised as-is;
        # the stand-down test pins WT_TRIM_BRANCH_TRIM=off
        # explicitly so the kill-switch stays tested
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    })
    if extra:
        for key, value in extra.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
    return env


def _git(cwd, *args, epoch=None, env=None, check=True):
    e = dict(env or os.environ)
    if epoch is not None:
        e["GIT_AUTHOR_DATE"] = f"@{epoch} +0000"
        e["GIT_COMMITTER_DATE"] = f"@{epoch} +0000"
    out = subprocess.run(
        ["git", "-c", "core.fsync=none", "-C", str(cwd), *args],
        capture_output=True, text=True, env=e)
    if check and out.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed: {out.stderr}")
    return out


def _touch_tree(root, epoch):
    for p in Path(root).rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            os.utime(p, (epoch, epoch))


def _archive_dir(manifest):
    return manifest.parent


class Fixture(unittest.TestCase):
    slug = "repo-a"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        self.env = _env(self.ws)
        self.main = self.ws / self.slug
        self.main.mkdir(parents=True)
        _git(self.ws, "init", "-b", "main", self.slug, env=self.env)
        (self.main / "base.txt").write_text("base\n")
        _git(self.main, "add", ".", env=self.env)
        _git(self.main, "commit", "-m", "base", epoch=NOW - 100000,
             env=self.env)
        _touch_tree(self.main, NOW - 100000)

    def tearDown(self):
        self._tmp.cleanup()

    def add_tree(self, name, branch, files, activity):
        """files: list of (filename, content). One commit, dated
        and touched at `activity`. The tree is UNLANDED (its
        commit sits ahead of main) until land() is called."""
        path = self.ws / name
        _git(self.main, "worktree", "add", "-b", branch, str(path),
             "main", env=self.env)
        for fname, content in files:
            (path / fname).write_text(content)
        _git(path, "add", ".", env=self.env)
        _git(path, "commit", "-m", f"work on {branch}", epoch=activity,
             env=self.env)
        _touch_tree(path, activity)
        return path

    def land(self, branch):
        """Fast-forward main onto the branch's tip: the tree's
        work is landed (ahead=0, merged), so the held set's
        unlanded reason no longer stands for it."""
        _git(self.main, "merge", "--ff-only", branch, env=self.env)

    def add_landed_tree(self, name, branch, files, activity):
        path = self.add_tree(name, branch, files, activity)
        self.land(branch)
        return path

    def run_trim(self, *args, extra_env=None):
        extra = dict(extra_env or {})
        if self.slug != "repo-a":
            extra.setdefault("WORKTREE_TRIM_REPOS", self.slug)
        env = _env(self.ws, extra)
        return subprocess.run(
            ["bash", str(TRIM), *args],
            capture_output=True, text=True, env=env)

    def archives(self):
        root = self.ws / "worktree-archive"
        if not root.is_dir():
            return []
        return sorted(root.glob("*/*/manifest.txt"))

    def queue(self):
        qf = self.ws / "state" / f"remote-pending-{self.slug}.txt"
        if not qf.exists():
            return []
        return [ln for ln in qf.read_text().splitlines() if ln]

    def add_origin(self):
        origin = self.ws / "origin.git"
        _git(self.ws, "init", "--bare", str(origin), env=self.env)
        _git(self.main, "remote", "add", "origin", str(origin),
             env=self.env)
        return origin

    def remote_branches(self):
        return _git(self.main, "ls-remote", "--heads", "origin",
                    env=self.env).stdout

    def branch_exists(self, branch):
        out = _git(self.main, "show-ref", "--verify", "--quiet",
                   f"refs/heads/{branch}", env=self.env, check=False)
        return out.returncode == 0


class TestClean(unittest.TestCase):
    def test_purges_only_expired(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            root = ws / "worktree-archive" / "2026-11-16"
            # retired layout: manifest inside the archive dir
            for name, expiry, branch in (
                    ("repo-a__old", NOW - 1, "feat/old"),
                    ("repo-a__fresh", NOW + HOUR, "feat/fresh")):
                d = root / name
                d.mkdir(parents=True)
                (d / "manifest.txt").write_text(
                    f"repo=repo-a\ntree={name.split('__')[1]}\n"
                    f"branch={branch}\nexpiry_epoch={expiry}\n")
                (d / "worktree.bundle").write_bytes(b"x" * 100)
            # current layout: the moved tree + sibling manifest
            sib = root / "repo-a__sib"
            sib.mkdir(parents=True)
            (sib / "sib.txt").write_text("sib\n")
            (root / "repo-a__sib.manifest.txt").write_text(
                "repo=repo-a\ntree=sib\nbranch=feat/sib\n"
                f"expiry_epoch={NOW - 1}\n")
            out = subprocess.run(
                ["bash", str(CLEAN)], capture_output=True, text=True,
                env=_env(ws))
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("PURGED repo=repo-a tree=old", out.stdout)
            self.assertIn("PURGED repo=repo-a tree=sib", out.stdout)
            self.assertFalse((root / "repo-a__old").exists())
            self.assertFalse(sib.exists())
            self.assertFalse(
                (root / "repo-a__sib.manifest.txt").exists())
            self.assertTrue((root / "repo-a__fresh").exists())
            # These manifests record no head,
            # so their branches are unverifiable — the purge
            # charges NO branch act for them (branch_local=
            # no-repo here: the fixture workspace holds no
            # repo-a checkout) and queues nothing. A purge
            # charges the branch trim only for a branch proven
            # to be the archive's own (see TestPurgeBranch).
            self.assertIn("branch_local=no-repo", out.stdout)
            queue = (ws / "state" / "remote-pending-repo-a.txt")
            self.assertFalse(queue.exists() and queue.read_text().strip())


class TestTrim(Fixture):
    def test_dry_run_census_no_changes(self):
        self.add_tree("repo-a-a-wt", "feat/a",
                      [("a.txt", "a\n")], NOW - 3000)
        self.add_tree("repo-a-b-wt", "feat/b",
                      [("b.txt", "b\n")], NOW - 2000)
        out = self.run_trim("--dry-run", "--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stderr)
        census = [ln for ln in out.stdout.splitlines()
                  if ln.startswith("CENSUS")]
        self.assertEqual(len(census), 2)
        self.assertIn("tree=repo-a-b-wt", census[0])  # newest first
        self.assertTrue((self.ws / "repo-a-a-wt").exists())
        self.assertEqual(self.archives(), [])

    def test_cut_trims_oldest_to_cap(self):
        paths = []
        for i in range(5):
            paths.append(self.add_landed_tree(
                f"repo-a-t{i}-wt", f"feat/t{i}",
                [(f"t{i}.txt", f"{i}\n")], NOW - 5000 + i * 1000))
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_CAP_REPO_A": "2"})
        self.assertEqual(out.returncode, 0, out.stderr)
        archived = [ln for ln in out.stdout.splitlines()
                    if ln.startswith("ARCHIVED")]
        self.assertEqual(len(archived), 3)
        for ln in archived:
            self.assertIn("expires=", ln)
            self.assertIn("note=branch-kept-until-purge", ln)
        self.assertFalse(paths[0].exists())
        self.assertFalse(paths[2].exists())
        self.assertTrue(paths[3].exists())
        self.assertTrue(paths[4].exists())
        manifests = self.archives()
        self.assertEqual(len(manifests), 3)
        for m in manifests:
            self.assertIn(f"expiry_epoch={NOW + HOUR}", m.read_text())
            self.assertIn("dirty=0", m.read_text())
            # the archive holds the tree itself: its own
            # file moved with it (later trees also carry
            # the earlier landed files — the fixture lands
            # each tree into main before growing the next),
            # admin directory alongside
            adir = _archive_dir(m)
            fields = dict(ln.split("=", 1) for ln in
                          m.read_text().splitlines() if "=" in ln)
            own = fields["tree"].removeprefix("repo-a-").removesuffix("-wt")
            self.assertTrue((adir / "tree" / f"{own}.txt").exists())
            self.assertTrue((adir / "worktree-admin").is_dir())
        # Branches are NOT trimmed while
        # their archives stand — the branch is the restore's
        # registration; the purge trims it (TestPurgeBranch)
        self.assertNotIn("BRANCH-TRIMMED", out.stdout)
        for i in range(5):
            self.assertTrue(self.branch_exists(f"feat/t{i}"))
        self.assertEqual(self.queue(), [])
        ledger = (self.ws / "state" / "ledger.jsonl").read_text()
        self.assertEqual(ledger.count("act=trim"), 3)

    def test_archive_failure_keeps_tree(self):
        tree = self.add_landed_tree("repo-a-x-wt", "feat/x",
                                    [("x.txt", "x\n")], NOW - 4000)
        blocker = self.ws / "archive-blocker"
        blocker.write_text("not a directory")
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_CAP_REPO_A": "0",
                       "WORKTREE_ARCHIVE_ROOT": str(blocker)})
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("ARCHIVE-FAIL repo=repo-a tree=repo-a-x-wt",
                      out.stdout)
        self.assertTrue(tree.exists())
        self.assertTrue(self.branch_exists("feat/x"))

    def test_dirty_tree_is_held(self):
        # A dirty tree is held, not archived whole:
        # uncommitted state is the held set's first reason
        # (the W-P3NORM-1 loss class —
        # an uncommitted cure archived, then purged). The
        # tree stands, unarchived, branch intact, at cap 0.
        tree = self.add_tree("repo-a-d-wt", "feat/d",
                             [("d.txt", "committed\n")], NOW - 4000)
        (tree / "d.txt").write_text("dirty change\n")
        (tree / "notes.txt").write_text("untracked notes\n")
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("HELD repo=repo-a tree=repo-a-d-wt", out.stdout)
        held = [ln for ln in out.stdout.splitlines()
                if ln.startswith("HELD")][0]
        self.assertIn("dirty", held)
        self.assertNotIn("ARCHIVED", out.stdout)
        self.assertTrue(tree.exists())
        self.assertEqual((tree / "d.txt").read_text(), "dirty change\n")
        self.assertTrue(self.branch_exists("feat/d"))
        self.assertEqual(self.archives(), [])

    def test_branch_trimmed_on_origin(self):
        # The branch trim rides the PURGE,
        # not the trim — at trim time the branch stands in
        # both scopes; when the archive expires, the clean
        # phase deletes the local branch (tip == recorded
        # head, head landed) and queues the origin deletion,
        # which the same pass drains.
        origin = self.ws / "origin.git"
        _git(self.ws, "init", "--bare", str(origin), env=self.env)
        _git(self.main, "remote", "add", "origin", str(origin),
             env=self.env)
        self.add_landed_tree("repo-a-o-wt", "feat/o",
                             [("o.txt", "o\n")], NOW - 4000)
        _git(self.main, "push", "origin", "feat/o", env=self.env)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("ARCHIVED repo=repo-a", out.stdout)
        self.assertNotIn("BRANCH-TRIMMED", out.stdout)
        self.assertTrue(self.branch_exists("feat/o"))
        self.assertIn("feat/o", self.remote_branches())
        self.assertEqual(self.queue(), [])
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_TRIM_NOW": str(NOW + HOUR + 1)})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("PURGED repo=repo-a tree=repo-a-o-wt", out.stdout)
        self.assertIn("branch_local=trimmed", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a branch=feat/o "
                      "scope=origin", out.stdout)
        self.assertFalse(self.branch_exists("feat/o"))
        remote = _git(self.main, "ls-remote", "--heads", "origin",
                      env=self.env).stdout
        self.assertNotIn("feat/o", remote)
        self.assertEqual(self.queue(), [])

    def test_remote_failure_queues_and_retries(self):
        # The queue/drain machinery, driven through the
        # purge: the purge queues the origin deletion locally
        # (no origin contact); the drain then fails against
        # the missing origin and keeps the obligation queued;
        # the next pass with origin back drains it.
        origin = self.ws / "origin.git"
        _git(self.ws, "init", "--bare", str(origin), env=self.env)
        _git(self.main, "remote", "add", "origin", str(origin),
             env=self.env)
        self.add_landed_tree("repo-a-r-wt", "feat/r",
                             [("r.txt", "r\n")], NOW - 4000)
        _git(self.main, "push", "origin", "feat/r", env=self.env)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("ARCHIVED repo=repo-a", out.stdout)
        origin.rename(self.ws / "origin-gone.git")
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_TRIM_NOW": str(NOW + HOUR + 1)})
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("PURGED repo=repo-a tree=repo-a-r-wt", out.stdout)
        self.assertIn("branch_local=trimmed", out.stdout)
        self.assertIn("BRANCH-REMOTE-FAIL repo=repo-a branch=feat/r",
                      out.stdout)
        # the local branch was trimmed at the purge; the
        # origin obligation waits in the queue
        self.assertFalse(self.branch_exists("feat/r"))
        self.assertEqual(self.queue(), ["feat/r"])
        # origin back: the next pass drains the queue on its own
        (self.ws / "origin-gone.git").rename(origin)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_TRIM_NOW": str(NOW + HOUR + 2)})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("BRANCH-TRIMMED repo=repo-a branch=feat/r "
                      "scope=origin", out.stdout)
        self.assertEqual(self.queue(), [])
        remote = _git(self.main, "ls-remote", "--heads", "origin",
                      env=self.env).stdout
        self.assertNotIn("feat/r", remote)

    def test_standdown_keeps_all_branches(self):
        self.add_origin()
        self.add_landed_tree("repo-a-s-wt", "feat/s",
                             [("s.txt", "s\n")], NOW - 4000)
        _git(self.main, "push", "origin", "feat/s", env=self.env)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_CAP_REPO_A": "0",
                       "WT_TRIM_BRANCH_TRIM": "off"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # the tree is archived; its branch is untouched in
        # both scopes and nothing is queued
        self.assertIn("ARCHIVED repo=repo-a", out.stdout)
        self.assertNotIn("BRANCH-TRIMMED", out.stdout)
        self.assertTrue(self.branch_exists("feat/s"))
        self.assertIn("feat/s", self.remote_branches())
        self.assertEqual(self.queue(), [])
        ledger = (self.ws / "state" / "ledger.jsonl").read_text()
        self.assertIn("act=branch-standdown", ledger)

    def test_pins_file_has_no_effect(self):
        # owner's ruling: no carve-out by name — a branch
        # named in a .worktree-trim-pins file is
        # treated exactly like any other: its landed tree
        # archives at the cut, and its branch trims at the
        # purge. (The held set is work state, not a name
        # list; a pins file confers no hold.)
        self.add_origin()
        (self.main / ".worktree-trim-pins").write_text("feat/p\n")
        self.add_landed_tree("repo-a-p-wt", "feat/p",
                             [("p.txt", "p\n")], NOW - 4000)
        _git(self.main, "push", "origin", "feat/p", env=self.env)
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("ARCHIVED repo=repo-a", out.stdout)
        self.assertNotIn("BRANCH-EXEMPT", out.stdout)
        self.assertNotIn("HELD repo=repo-a tree=repo-a-p-wt", out.stdout)
        self.assertTrue(self.branch_exists("feat/p"))
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_TRIM_NOW": str(NOW + HOUR + 1)})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("branch_local=trimmed", out.stdout)
        self.assertFalse(self.branch_exists("feat/p"))
        self.assertNotIn("feat/p", self.remote_branches())
        self.assertEqual(self.queue(), [])

    def test_dirty_tree_is_held_pins_or_not(self):
        # The held set binds by work state, not by name: a
        # dirty tree on a pins-named branch is held exactly
        # like any other dirty tree (the pre-cure pin — that
        # it archives whole — is the defect's own specimen).
        (self.main / ".worktree-trim-pins").write_text("feat/k\n")
        tree = self.add_tree("repo-a-k-wt", "feat/k",
                             [("k.txt", "committed\n")], NOW - 4000)
        (tree / "k.txt").write_text("uncommitted gate work\n")
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("HELD repo=repo-a tree=repo-a-k-wt", out.stdout)
        self.assertNotIn("ARCHIVED", out.stdout)
        self.assertTrue(tree.exists())
        self.assertEqual(self.archives(), [])
        self.assertTrue(self.branch_exists("feat/k"))

    def test_queued_branches_all_drained(self):
        self.add_origin()
        (self.main / ".worktree-trim-pins").write_text("feat/p\n")
        self.add_tree("repo-a-p-wt", "feat/p",
                      [("p.txt", "p\n")], NOW - 4000)
        self.add_tree("repo-a-q-wt", "feat/q",
                      [("q.txt", "q\n")], NOW - 3000)
        _git(self.main, "push", "origin", "feat/p", "feat/q",
             env=self.env)
        # both branches sit in the queue; the drain deletes
        # both on origin — the pins file drops neither
        state = self.ws / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "remote-pending-repo-a.txt").write_text(
            "feat/p\nfeat/q\n")
        out = self.run_trim("--tier", "soft",
                            extra_env={"WT_TRIM_CAP_REPO_A": "10"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        remote = self.remote_branches()
        self.assertNotIn("feat/p", remote)
        self.assertNotIn("feat/q", remote)
        self.assertIn("BRANCH-TRIMMED repo=repo-a branch=feat/p "
                      "scope=origin", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-a branch=feat/q "
                      "scope=origin", out.stdout)
        self.assertEqual(self.queue(), [])

    def test_deterministic_report(self):
        def build_and_run(ws):
            env = _env(ws)
            main = ws / "repo-a"
            main.mkdir(parents=True)
            _git(ws, "init", "-b", "main", "repo-a", env=env)
            (main / "base.txt").write_text("base\n")
            _git(main, "add", ".", env=env)
            _git(main, "commit", "-m", "base", epoch=NOW - 100000,
                 env=env)
            for i in range(3):
                path = ws / f"repo-a-t{i}-wt"
                _git(main, "worktree", "add", "-b", f"feat/t{i}",
                     str(path), "main", env=env)
                (path / f"t{i}.txt").write_text(f"{i}\n")
                _git(path, "add", ".", env=env)
                _git(path, "commit", "-m", f"t{i}",
                     epoch=NOW - 3000 + i * 1000, env=env)
                _touch_tree(path, NOW - 3000 + i * 1000)
                # landed, so the held set does not stand for
                # it and the cut is what the report exercises
                _git(main, "merge", "--ff-only", f"feat/t{i}",
                     env=env)
            out = subprocess.run(
                ["bash", str(TRIM), "--tier", "soft"],
                capture_output=True, text=True,
                env=_env(ws, {"WT_TRIM_CAP_REPO_A": "1"}))
            return out.stdout.replace(str(ws), "$WS")

        with tempfile.TemporaryDirectory() as a, \
                tempfile.TemporaryDirectory() as b:
            first = build_and_run(Path(a))
            second = build_and_run(Path(b))
        self.assertEqual(first, second)
        self.assertEqual(first.count("ARCHIVED"), 2)


    def test_targets_and_caps_from_config_file(self):
        # no WORKTREE_TRIM_REPOS env and no cap env: the
        # target set and the cap come from the deployment
        # config file in the state dir (repos.conf:
        # <slug> <soft-cap> <deep-cap>)
        self.add_landed_tree("repo-a-c-wt", "feat/c",
                             [("c.txt", "c\n")], NOW - 4000)
        state = self.ws / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "repos.conf").write_text("repo-a 0 0\n")
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_TRIM_REPOS": None})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("ARCHIVED repo=repo-a tree=repo-a-c-wt",
                      out.stdout)
        self.assertEqual(len(self.archives()), 1)


class TestTrimSecondRepo(Fixture):
    slug = "repo-b"

    def test_union_branch_trimmed_like_any_other(self):
        # owner's ruling: no carve-out by name — a
        # form/union-* branch is treated exactly like any
        # other: archived at the cut, branch trimmed at the
        # purge, in both scopes
        self.add_origin()
        self.add_landed_tree("repo-b-u-wt", "form/union-x",
                             [("u.txt", "u\n")], NOW - 4000)
        _git(self.main, "push", "origin", "form/union-x",
             env=self.env)
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WT_TRIM_CAP_REPO_B": "0"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("ARCHIVED repo=repo-b", out.stdout)
        self.assertNotIn("BRANCH-EXEMPT", out.stdout)
        self.assertTrue(self.branch_exists("form/union-x"))
        out = self.run_trim(
            "--tier", "soft",
            extra_env={"WORKTREE_TRIM_NOW": str(NOW + HOUR + 1),
                       "WORKTREE_TRIM_REPOS": "repo-b"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("branch_local=trimmed", out.stdout)
        self.assertIn("BRANCH-TRIMMED repo=repo-b "
                      "branch=form/union-x scope=origin", out.stdout)
        self.assertFalse(self.branch_exists("form/union-x"))
        self.assertNotIn("form/union-x", self.remote_branches())
        self.assertEqual(self.queue(), [])


if __name__ == "__main__":
    unittest.main()
