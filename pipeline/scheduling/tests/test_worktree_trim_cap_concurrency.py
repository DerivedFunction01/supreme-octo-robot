"""Branch-cap archive concurrency specimens for the
worktree trim, sharing the fixture harness in
test_worktree_trim.py.

The pre-cure cap phase wrote its bundle through one
fixed temp path in the archive directory and renamed it
over the standing bundle, and rewrote the manifest in
place — all without a lock. The archive path is a
function of date+repo only, so an hourly pass and a deep
pass over the same repo collided on it: one pass could
rename a half-written bundle over the other's, or
replace the standing bundle with a union computed from
a stale read, losing the other pass's just-archived tips
— and the archive is a source of record, the only copy
of capped unlanded tips.

The cure: each pass bundles its own excess alone, staged
in a per-pass ref namespace, to a per-pass staged file
in the archive directory, and verifies it there; the
union with the standing archive happens under a
per-archive-directory flock — standing bundle and staged
bundle fetched in, union written to a fresh temp file,
verified, renamed over, manifest rewritten the same way
inside the same lock. A staged file is removed once
merged; on failure it is left in place and named in the
BRANCH-CAP-FAIL line, and the standing archive stands
untouched.
"""

import subprocess
import threading
import time
import unittest
from pathlib import Path

from tests.test_worktree_trim import NOW, TRIM, Fixture, _env, _git


class TestBranchCapConcurrency(Fixture):
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

    def remote_branch_names(self):
        names = set()
        for ln in self.remote_branches().splitlines():
            if "refs/heads/" in ln:
                names.add(ln.split("refs/heads/")[1])
        return names

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

    def bundle_head_shas(self):
        bundle = self.cap_dir() / "branches.bundle"
        out = _git(self.main, "bundle", "list-heads",
                   str(bundle), env=self.env).stdout
        return {ln.split()[0] for ln in out.splitlines() if ln}

    def launch_trim(self, cap):
        env = _env(self.ws,
                   {"WT_TRIM_BRANCH_CAP_REPO_A": str(cap)})
        return subprocess.Popen(
            ["bash", str(TRIM), "--tier", "soft"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env)

    def test_concurrent_cap_passes_union_the_archive(self):
        # two passes over the same repo at the same time,
        # with different caps, so their excess sets overlap
        # without being equal. Whatever the interleaving,
        # the standing archive ends as a verified union:
        # the earlier pass's tips still in it, every tip
        # either pass deleted recoverable from it, the
        # manifest rowing exactly the bundle's heads, and
        # no per-pass file left behind by a merged pass.
        # (A pass may still end partial on a drain race —
        # two drains pushing the same origin delete — which
        # is the queue's standing behaviour, not the
        # archive's; the settle pass below discharges what
        # a raced drain kept.)
        self.add_origin()
        first = [f"feat/c{i:02d}" for i in range(12)]
        for i, name in enumerate(first):
            self.add_orphan(name, NOW - 120000 + i * 1000)
        _git(self.main, "push", "origin", "main", *first,
             env=self.env)
        tips = {}
        for name in first:
            tips[name] = _git(self.main, "rev-parse", name,
                              env=self.env).stdout.strip()
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        standing = self.bundle_head_shas()
        self.assertEqual(len(standing), 3)
        more = [f"feat/c{i:02d}" for i in range(12, 18)]
        for i, name in enumerate(more):
            self.add_orphan(name, NOW - 106000 + i * 1000)
        _git(self.main, "push", "origin", "main", *more,
             env=self.env)
        for name in more:
            tips[name] = _git(self.main, "rev-parse", name,
                              env=self.env).stdout.strip()
        pa = self.launch_trim(9)
        pb = self.launch_trim(6)
        out_a, err_a = pa.communicate(timeout=600)
        out_b, err_b = pb.communicate(timeout=600)
        self.assertIn(pa.returncode, (0, 3), out_a + err_a)
        self.assertIn(pb.returncode, (0, 3), out_b + err_b)
        self.assertNotIn("BRANCH-CAP-FAIL", out_a)
        self.assertNotIn("BRANCH-CAP-FAIL", out_b)
        self.assertIn("BRANCH-ARCHIVED", out_a + out_b)
        bundle = self.cap_dir() / "branches.bundle"
        verify = _git(self.main, "bundle", "verify", str(bundle),
                      env=self.env, check=False)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        heads = self.bundle_head_shas()
        rows = self.manifest_rows()
        self.assertEqual(len(rows), len(heads))
        self.assertEqual({r[1] for r in rows}, heads)
        # the union never clobbers: the first pass's
        # archived tips survive the concurrent merges
        self.assertTrue(standing <= heads)
        # archive-before-delete, under concurrency: any
        # branch a pass deleted, on either side, has its
        # tip in the standing bundle
        local_now = self.local_branches()
        remote_now = self.remote_branch_names()
        for name, sha in tips.items():
            if name not in local_now or name not in remote_now:
                self.assertIn(sha, heads)
        # merged passes leave no per-pass files behind
        leftovers = [p.name for p in self.cap_dir().iterdir()
                     if "staged-" in p.name or ".merge-" in p.name]
        self.assertEqual(leftovers, [])
        # a serial settle pass discharges any charge a
        # raced drain kept, and re-derives the rest
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.queue(), [])

    def test_corrupt_staged_bundle_leaves_standing_archive(self):
        # a staged bundle corrupted after its creation —
        # garbage hammered over its head for as long as the
        # pass runs, so whatever the pass reads, at the
        # staged verify or at the merge fetch, is garbage —
        # fails the pass's archive step: the standing bundle
        # and manifest stand byte-identical, no ref is
        # deleted on either side, nothing is queued, and
        # the corrupt staged file is left in place, named
        # in the BRANCH-CAP-FAIL line as the pass's only
        # copy of its excess.
        self.add_origin()
        names = [f"feat/g{i:02d}" for i in range(12)]
        for i, name in enumerate(names):
            self.add_orphan(name, NOW - 120000 + i * 1000)
        _git(self.main, "push", "origin", "main", *names,
             env=self.env)
        out = self.run_trim("--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        capdir = self.cap_dir()
        bundle = capdir / "branches.bundle"
        manifest = capdir / "manifest.tsv"
        bundle_bytes = bundle.read_bytes()
        manifest_text = manifest.read_text()
        more = [f"feat/h{i}" for i in range(4)]
        for i, name in enumerate(more):
            self.add_orphan(name, NOW - 106000 + i * 1000)
        _git(self.main, "push", "origin", *more, env=self.env)
        local_before = self.local_branches()
        remote_before = self.remote_branch_names()
        stop = threading.Event()

        def corrupt():
            while not stop.is_set():
                for staged in capdir.glob(
                        "branches.bundle.staged-*"):
                    try:
                        with open(staged, "r+b") as fh:
                            fh.write(b"\x00" * 8192)
                    except OSError:
                        pass
                time.sleep(0.001)

        worker = threading.Thread(target=corrupt, daemon=True)
        worker.start()
        try:
            out = self.run_trim("--tier", "soft")
        finally:
            stop.set()
            worker.join(timeout=10)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        fail = [ln for ln in out.stdout.splitlines()
                if "BRANCH-CAP-FAIL" in ln]
        self.assertEqual(len(fail), 1)
        self.assertIn("staged=", fail[0])
        staged_path = Path(fail[0].split("staged=")[1].split()[0])
        self.assertTrue(staged_path.exists())
        self.assertEqual(bundle.read_bytes(), bundle_bytes)
        self.assertEqual(manifest.read_text(), manifest_text)
        self.assertEqual(self.local_branches(), local_before)
        self.assertEqual(self.remote_branch_names(), remote_before)
        self.assertEqual(self.queue(), [])


if __name__ == "__main__":
    unittest.main()
