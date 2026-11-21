"""The denial-tolerant writer (ops/cutover/durable_write.py):
it delegates the write to the platform's unified writer and
retries denials (a bare PermissionError, or the writer's
WriterError wrapping one) until the write lands; a
persistent denial raises after the attempts run out; other
errors propagate unretried; the landed bytes are exactly
the text.
"""

import builtins
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

OPS = Path(__file__).resolve().parents[1] / "ops" / "cutover"


def _load(attempts="6", base_delay="0"):
    os.environ["DURABLE_WRITE_ATTEMPTS"] = attempts
    os.environ["DURABLE_WRITE_BASE_DELAY_S"] = base_delay
    spec = importlib.util.spec_from_file_location(
        "durable_write_under_test", OPS / "durable_write.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DurableWriteTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_plain_write_lands_exact_bytes(self):
        mod = _load()
        target = self.dir / "out.txt"
        mod.write_text(str(target), "hello\n")
        self.assertEqual(target.read_text(encoding="utf-8"),
                         "hello\n")
        self.assertEqual(list(self.dir.iterdir()), [target])

    def test_transient_denial_is_retried_until_it_lands(self):
        mod = _load()
        target = self.dir / "out.txt"
        real_open = builtins.open
        calls = {"n": 0}

        def flaky(file, mode="r", *a, **kw):
            # the unified writer's staging opens carry its
            # sched-tmp marker; deny the first three
            if "w" in mode and ".sched-tmp-" in str(file):
                calls["n"] += 1
                if calls["n"] <= 3:
                    raise PermissionError(1, "denied (fixture)")
            return real_open(file, mode, *a, **kw)

        with mock.patch("builtins.open", flaky):
            mod.write_text(str(target), "landed")
        self.assertEqual(calls["n"], 4)
        self.assertEqual(target.read_text(encoding="utf-8"),
                         "landed")
        self.assertEqual(list(self.dir.iterdir()), [target])

    def test_persistent_denial_raises_after_the_attempts(self):
        mod = _load(attempts="3")
        target = self.dir / "out.txt"

        def denied(file, mode="r", *a, **kw):
            if "w" in mode:
                raise PermissionError(1, "denied (fixture)")
            return builtins.open(file, mode, *a, **kw)

        with mock.patch("builtins.open", denied):
            # the denial surfaces in the writer's form: a
            # WriterError whose cause is the PermissionError
            with self.assertRaises(Exception) as ctx:
                mod.write_text(str(target), "never")
            self.assertIsInstance(ctx.exception.__cause__,
                                  PermissionError)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_other_errors_are_not_retried(self):
        mod = _load()
        target = self.dir / "out.txt"
        calls = {"n": 0}

        def broken(file, mode="r", *a, **kw):
            if "w" in mode:
                calls["n"] += 1
                raise IsADirectoryError(21, "a directory (fixture)")
            return builtins.open(file, mode, *a, **kw)

        with mock.patch("builtins.open", broken):
            with self.assertRaises(Exception) as ctx:
                mod.write_text(str(target), "never")
            # unretried, and surfaced in the writer's form
            # with the original error as its cause
            self.assertIsInstance(ctx.exception.__cause__,
                                  IsADirectoryError)
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
