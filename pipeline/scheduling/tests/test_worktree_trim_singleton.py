"""Pass-singleton specimens for the worktree trim (the
pass-singleton cure), sharing the fixture harness in
test_worktree_trim.py: a second parent finding the pass
lock held exits 0 silently and spawns no workers, worker
mode never touches the lock, and a dry run is never
blocked by it.

The lock is held from the specimen by flocking the
lockfile directly — the honest equivalent of a standing
pass, whose subject is the script's lock behaviour, not
the scheduler that fires it.
"""

import fcntl
import subprocess
import unittest

from tests.test_worktree_trim import NOW, TRIM, Fixture


class _LockHeld:
    """An exclusive flock on the pass lockfile, held on an
    open fd for the block's whole span — the state a
    standing pass's parent presents to a second parent."""

    def __init__(self, ws):
        self.path = ws / "state" / "trim-pass.lock"
        self._fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self.path, "w")
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self._fd.close()
        self._fd = None


class TestSingleton(Fixture):
    def test_second_pass_exits_silently_when_lock_held(self):
        # A landed tree at cap 0: a real pass would census
        # and archive it, printing CENSUS and ARCHIVED
        # lines. The locked-out pass must do none of that.
        elder = self.add_landed_tree(
            "repo-a-e-wt", "feat/e", [("e.txt", "e\n")],
            NOW - 9000)
        with _LockHeld(self.ws):
            out = self.run_trim(
                "--tier", "soft",
                extra_env={"WT_TRIM_CAP_REPO_A": "0"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, "")
        self.assertEqual(out.stderr, "")
        self.assertTrue(elder.exists())
        self.assertEqual(self.archives(), [])

    def test_worker_mode_never_touches_the_lock(self):
        # Workers are the standing pass's own children: a
        # worker invocation runs to completion while the
        # lockfile stands flocked.
        result = self.ws / "worker.out"
        ledger = self.ws / "worker.ledger"
        with _LockHeld(self.ws):
            out = subprocess.run(
                ["bash", str(TRIM), "--worker", "repo-a",
                 "--tier", "soft",
                 "--result-file", str(result),
                 "--ledger-file", str(ledger)],
                capture_output=True, text=True, env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(result.exists())

    def test_dry_run_is_not_blocked_by_held_lock(self):
        # A dry run takes no lock: with the lockfile
        # flocked it still censuses and reports.
        self.add_tree("repo-a-a-wt", "feat/a",
                      [("a.txt", "a\n")], NOW - 3000)
        with _LockHeld(self.ws):
            out = self.run_trim("--dry-run", "--tier", "soft")
        self.assertEqual(out.returncode, 0, out.stderr)
        census = [ln for ln in out.stdout.splitlines()
                  if ln.startswith("CENSUS")]
        self.assertEqual(len(census), 1)
        self.assertIn("tree=repo-a-a-wt", census[0])


if __name__ == "__main__":
    unittest.main()
