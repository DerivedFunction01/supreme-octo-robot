"""Direct pins for the unified writer's staged protocol
(contract 15, pipeline/platform/writer.py::staged_write).

The protocol's standing evidence was the S9 P4 closure
drill; the mega repo carried no direct unit pin for the
seam itself. These tests land with the S11 resync port of
the original workbench seam's mode preservation
(resync census, workbench items 2-3): the mode pin is
adapted from the original's tests/lib/test_util.py
(commit a24d5d6), and the round-trip and failed-stage
pins are the two direct seam pins the census found
missing repo-wide.
"""

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM))

import writer  # noqa: E402


class TestStagedWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _target(self, name="note.md"):
        return os.path.join(self.dir, name)

    def test_staged_write_round_trip(self):
        target = self._target()
        writer.staged_write(target, b"first\n")
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"first\n")
        writer.staged_write(target, b"second\n")
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"second\n")
        # no staging litter remains
        self.assertEqual(os.listdir(self.dir), ["note.md"])

    def test_failed_stage_leaves_target_untouched(self):
        target = self._target()
        with open(target, "wb") as fh:
            fh.write(b"original\n")
        # Occupy the writer's own staging path with a
        # directory: the staged open fails before any byte
        # can land, and the target is never touched.
        staging = os.path.join(
            self.dir,
            ".{}.sched-tmp-{}-{}".format("note.md", os.getpid(), threading.get_ident()),
        )
        os.mkdir(staging)
        with self.assertRaises(writer.WriterError):
            writer.staged_write(target, b"replacement\n")
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"original\n")

    def test_existing_mode_is_preserved(self):
        # The original seam's pin (0o640 round-trip),
        # adapted: rename-over must not reset the target's
        # mode to the umask default.
        target = self._target()
        with open(target, "wb") as fh:
            fh.write(b"original\n")
        os.chmod(target, 0o640)
        writer.staged_write(target, b"replacement\n")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o640)
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"replacement\n")

    def test_existing_restrictive_mode_is_preserved(self):
        # A 0o600 target stays 0o600 through staged_write.
        target = self._target("secret.md")
        with open(target, "wb") as fh:
            fh.write(b"original\n")
        os.chmod(target, 0o600)
        writer.staged_write(target, b"replacement\n")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"replacement\n")

    def test_explicit_mode_stamped_on_fresh_target(self):
        # The E5 extension (register E5): a credential-class
        # target recreated from nothing has no mode to carry;
        # the caller's explicit mode is stamped instead of
        # the umask default.
        target = self._target("fresh-secret.md")
        writer.staged_write(target, b"credential\n", mode=0o600)
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"credential\n")

    def test_explicit_mode_overrides_carried_mode(self):
        target = self._target("widened.md")
        with open(target, "wb") as fh:
            fh.write(b"original\n")
        os.chmod(target, 0o644)
        writer.staged_write(target, b"replacement\n", mode=0o600)
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)


class TestOpWriteMode(unittest.TestCase):
    """The write op's mode field (the protocol extension
    that carries the mode discipline through the /ops
    service): perform() stamps an explicit mode, carries
    the existing mode without one, and rejects a malformed
    mode without writing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.values = {"workspace_root": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content, **extra):
        req = {"caller": "test", "op": "write", "path": name, "content": content}
        req.update(extra)
        return writer.perform(None, self.values, req)

    def test_mode_stamped_through_perform(self):
        code, payload = self._write("s.txt", "x", mode=0o600)
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        target = os.path.join(self.tmp.name, "s.txt")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)

    def test_no_mode_carries_existing(self):
        target = os.path.join(self.tmp.name, "c.txt")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("old")
        os.chmod(target, 0o640)
        code, _payload = self._write("c.txt", "new")
        self.assertEqual(code, 200)
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o640)

    def test_bad_mode_rejected(self):
        code, payload = self._write("b.txt", "x", mode="600")
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "bad_request")
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "b.txt")))


if __name__ == "__main__":
    unittest.main()
