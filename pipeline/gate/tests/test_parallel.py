"""The parallel test machinery (tests always run
parallel): worker derivation, module
sharding, shard-output parsing, and the sharded run's
aggregation — a parallel failure is named, never
retried into green."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gate import runner


class DeriveWorkersTests(unittest.TestCase):
    def test_default_is_two(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runner.derive_workers(), 2)

    def test_decl_then_leg_then_env(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                runner.derive_workers({"workers": 4}), 4)
            self.assertEqual(
                runner.derive_workers(
                    {"workers": 4}, {"workers": 3}), 3)
        with mock.patch.dict(
                os.environ, {"GATE_WORKERS": "8"}, clear=True):
            self.assertEqual(
                runner.derive_workers(
                    {"workers": 4}, {"workers": 3}), 8)

    def test_bad_values_fall_through(self):
        with mock.patch.dict(
                os.environ, {"GATE_WORKERS": "many"}, clear=True):
            self.assertEqual(
                runner.derive_workers({"workers": "x"}), 2)
            self.assertEqual(
                runner.derive_workers({"workers": 0}), 1)


class ShardModulesTests(unittest.TestCase):
    def test_disjoint_complete_balanced(self):
        modules = [f"m{i}" for i in range(11)]
        shards = runner.shard_modules(modules, 2)
        self.assertEqual(len(shards), 2)
        flat = [m for shard in shards for m in shard]
        self.assertEqual(sorted(flat), sorted(modules))
        self.assertLessEqual(
            abs(len(shards[0]) - len(shards[1])), 1)

    def test_more_workers_than_modules(self):
        shards = runner.shard_modules(["a", "b"], 8)
        self.assertEqual(shards, [["a"], ["b"]])


class ParseShardOutputTests(unittest.TestCase):
    def test_ran_and_failure_names(self):
        text = (
            "FAIL: test_nope (tests.test_x.TestY)\n"
            "----------------------------------------------------------------------\n"
            "Traceback ...\n\n"
            "----------------------------------------------------------------------\n"
            "Ran 12 tests in 0.101s\n\nFAILED (failures=1)\n")
        ran, names = runner.parse_shard_output(text)
        self.assertEqual(ran, 12)
        self.assertEqual(
            names, ["FAIL: test_nope (tests.test_x.TestY)"])

    def test_clean_output(self):
        ran, names = runner.parse_shard_output(
            "..........\nRan 10 tests in 0.1s\n\nOK\n")
        self.assertEqual((ran, names), (10, []))


class ShardedRunTests(unittest.TestCase):
    def _write_module(self, root: Path, name: str,
                      body: str) -> None:
        (root / f"{name}.py").write_text(body, encoding="utf-8")

    def test_aggregation_names_the_failure(self):
        root = Path(tempfile.mkdtemp(prefix="gate-shard-"))
        self._write_module(root, "test_pass_a", (
            "import unittest\n"
            "class A(unittest.TestCase):\n"
            "    def test_one(self): pass\n"
            "    def test_two(self): pass\n"))
        self._write_module(root, "test_fail_b", (
            "import unittest\n"
            "class B(unittest.TestCase):\n"
            "    def test_bad(self): self.fail('boom')\n"))
        self._write_module(root, "test_pass_c", (
            "import unittest\n"
            "class C(unittest.TestCase):\n"
            "    def test_three(self): pass\n"))
        # The nested run's output is captured, not leaked:
        # a shard's own summary lines riding the outer
        # suite's stream would corrupt its aggregate count.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = runner._run_unittest_sharded(
                sys.executable,
                ["test_pass_a", "test_fail_b", "test_pass_c"],
                2, root)
        self.assertEqual(code, 1)
        text = out.getvalue()
        self.assertIn("parallel suite total: 4 test(s)", text)
        self.assertIn(
            "FAIL: test_bad (test_fail_b.B.test_bad)", text)
        self.assertIn("PARALLEL FAILURES", text)

    def test_all_pass_is_zero(self):
        root = Path(tempfile.mkdtemp(prefix="gate-shard-"))
        for name in ("test_pa", "test_pb", "test_pc"):
            self._write_module(root, name, (
                "import unittest\n"
                "class P(unittest.TestCase):\n"
                "    def test_ok(self): pass\n"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = runner._run_unittest_sharded(
                sys.executable, ["test_pa", "test_pb", "test_pc"],
                2, root)
        self.assertEqual(code, 0)
        self.assertIn("parallel suite total: 3 test(s)",
                      out.getvalue())


if __name__ == "__main__":
    unittest.main()
