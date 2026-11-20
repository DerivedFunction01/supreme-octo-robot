"""Unit tests for ops/flap/flap_probe.py.

Verdict logic is tested against an injected fake ops surface —
never against live filesystem state (a suite that reads the
machine's real write-denial weather would pass and fail with
the wind). The fake keeps an in-memory file map and raises the
exact exceptions the live primitives raise.
"""
import importlib.util
import os
import sqlite3
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "flap_probe", os.path.join(ROOT, "ops", "flap", "flap_probe.py")
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class FakeOps:
    def __init__(self):
        self.files = {}
        self.fail = set()        # primitive names that raise EPERM
        self.truncate = set()    # write primitives that land empty
        self.git_mode = "ok"     # ok | denied | missing
        self.sqlite_mode = "ok"  # ok | io | other

    def _maybe_fail(self, name):
        if name in self.fail:
            raise PermissionError(1, "Operation not permitted")

    def write_new(self, path, content):
        self._maybe_fail("write_new")
        self.files[path] = "" if "write_new" in self.truncate else content

    def overwrite(self, path, content):
        self._maybe_fail("overwrite")
        self.files[path] = "" if "overwrite" in self.truncate else content

    def read(self, path):
        return self.files.get(path)

    def exists(self, path):
        return path in self.files

    def shell_write(self, path, content):
        if "shell_write" in self.fail:
            return (1, "printf: write error: Operation not permitted")
        self.files[path] = content
        return (0, "")

    def git_write(self, repo, payload):
        if self.git_mode == "missing":
            raise FileNotFoundError(2, "No such file or directory", "git")
        if self.git_mode == "denied":
            return ("denied", "hash-object: Operation not permitted")
        return ("ok", "abc123")

    def sqlite_write(self, path, value):
        if self.sqlite_mode == "io":
            raise sqlite3.OperationalError("disk I/O error")
        if self.sqlite_mode == "other":
            raise sqlite3.OperationalError("no such table: t")
        return ("ok", "")

    def create(self, path, content):
        self._maybe_fail("create")
        self.files[path] = content

    def rename(self, src, dst):
        self._maybe_fail("rename")
        self.files[dst] = self.files.pop(src)

    def unlink(self, path):
        self._maybe_fail("unlink")
        self.files.pop(path, None)


def matrix(ops):
    return probe.run_matrix("/scratch", ops)


class VerdictTests(unittest.TestCase):
    def test_all_writable_is_down(self):
        results = matrix(FakeOps())
        self.assertTrue(
            all(m["status"] == "ok" for m in results.values()), results)
        self.assertEqual(probe.compute_verdict(results), ("down", 0))

    def test_one_core_denied_is_mixed(self):
        ops = FakeOps()
        ops.fail.add("write_new")
        results = matrix(ops)
        self.assertEqual(results["python_write_new"]["status"], "denied")
        self.assertEqual(probe.compute_verdict(results), ("mixed", 3))

    def test_all_core_denied_is_up(self):
        ops = FakeOps()
        ops.fail.update({"write_new", "overwrite", "shell_write"})
        ops.git_mode = "denied"
        ops.sqlite_mode = "io"
        results = matrix(ops)
        self.assertEqual(probe.compute_verdict(results), ("up", 3))

    def test_core_error_is_inconclusive(self):
        ops = FakeOps()
        ops.git_mode = "missing"
        results = matrix(ops)
        self.assertEqual(results["git_object_write"]["status"], "error")
        self.assertEqual(probe.compute_verdict(results), ("inconclusive", 4))

    def test_truncate_without_content_reads_as_denied(self):
        ops = FakeOps()
        ops.truncate.add("write_new")
        results = matrix(ops)
        self.assertEqual(results["python_write_new"]["status"], "denied")

    def test_sqlite_io_error_is_denied_other_is_error(self):
        ops = FakeOps()
        ops.sqlite_mode = "io"
        self.assertEqual(matrix(ops)["sqlite_row_write"]["status"], "denied")
        ops = FakeOps()
        ops.sqlite_mode = "other"
        results = matrix(ops)
        self.assertEqual(results["sqlite_row_write"]["status"], "error")
        self.assertEqual(probe.compute_verdict(results), ("inconclusive", 4))

    def test_non_core_failure_does_not_move_the_verdict(self):
        ops = FakeOps()
        ops.fail.add("create")  # rename_over and unlink staging
        results = matrix(ops)
        self.assertEqual(results["rename_over"]["status"], "denied")
        self.assertIn("at create", results["rename_over"]["detail"])
        self.assertEqual(probe.compute_verdict(results), ("down", 0))

    def test_overwrite_setup_denial_reads_as_denied(self):
        # Both seed paths (create, shell) denied by the flap: the
        # overwrite mechanism is denied, not merely unmeasurable.
        ops = FakeOps()
        ops.fail.update({"create", "shell_write"})
        results = matrix(ops)
        self.assertEqual(results["python_overwrite"]["status"], "denied")


class StateTests(unittest.TestCase):
    def sample(self, verdict, at="2026-11-08T00:00:00Z"):
        return {"at": at, "verdict": verdict, "mechanisms": {}}

    def test_since_survives_an_unchanged_verdict(self):
        prev = {"verdict": "up", "since": "2026-11-08T00:00:00Z"}
        state = probe.build_state(prev, self.sample("up", "2026-11-08T00:03:00Z"))
        self.assertEqual(state["since"], "2026-11-08T00:00:00Z")
        self.assertEqual(state["last_sample_at"], "2026-11-08T00:03:00Z")

    def test_since_resets_on_a_verdict_change(self):
        prev = {"verdict": "up", "since": "2026-11-08T00:00:00Z"}
        state = probe.build_state(prev, self.sample("down", "2026-11-08T00:03:00Z"))
        self.assertEqual(state["since"], "2026-11-08T00:03:00Z")

    def test_first_sample_starts_the_clock(self):
        state = probe.build_state(None, self.sample("mixed"))
        self.assertEqual(state["since"], "2026-11-08T00:00:00Z")

    def test_state_write_reports_a_denied_staging_write(self):
        ops = FakeOps()
        ops.fail.add("write_new")
        state = {"verdict": "up", "since": "x", "last_sample_at": "y",
                 "mechanisms": {}}
        self.assertFalse(probe.write_state("/state.json", state, ops))

    def test_state_round_trip(self):
        ops = FakeOps()
        state = {"verdict": "down", "since": "x", "last_sample_at": "y",
                 "mechanisms": {}}
        self.assertTrue(probe.write_state("/state.json", state, ops))
        self.assertEqual(probe.load_state("/state.json", ops), state)


if __name__ == "__main__":
    unittest.main()
