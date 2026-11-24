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


class TestExtraRoots(unittest.TestCase):
    """The server-configured extra write roots (the writer-
    route cure): resolve()/perform() accept a target under a
    root the SERVICE's values name — the venue funnel's
    credential directory is the standing entry — while a
    path outside root + extra roots is refused exactly as
    before, and a request can never name a root of its own:
    the allowance lives in values, and a request field
    claiming to carry it is ignored."""

    def setUp(self):
        self.ws = tempfile.TemporaryDirectory()
        self.cred = tempfile.TemporaryDirectory()
        self.elsewhere = tempfile.TemporaryDirectory()
        self.values = {
            "workspace_root": self.ws.name,
            "ops_extra_write_roots": [self.cred.name],
        }

    def tearDown(self):
        self.ws.cleanup()
        self.cred.cleanup()
        self.elsewhere.cleanup()

    def test_resolve_accepts_a_path_under_an_extra_root(self):
        target = os.path.join(self.cred.name, "token.json")
        resolved = writer.resolve(
            self.ws.name, target, extra_roots=[self.cred.name])
        self.assertEqual(resolved, os.path.realpath(target))

    def test_resolve_refuses_an_outside_path_with_extra_roots(self):
        target = os.path.join(self.elsewhere.name, "escape.txt")
        with self.assertRaises(writer.WriterError) as caught:
            writer.resolve(self.ws.name, target, extra_roots=[self.cred.name])
        self.assertEqual(caught.exception.name, "outside_scope")

    def test_perform_write_lands_under_an_extra_root(self):
        # The funnel's credential write, performed server-
        # side: the target lives outside the workspace, under
        # the configured credential root, and the mode
        # discipline rides it.
        target = os.path.join(self.cred.name, "token.json")
        req = {
            "caller": "test",
            "op": "write",
            "path": target,
            "content": "{}",
            "mode": 0o600,
        }
        code, payload = writer.perform(None, self.values, req)
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"{}")
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)

    def test_perform_refuses_a_non_allowlisted_outside_path(self):
        target = os.path.join(self.elsewhere.name, "escape.txt")
        req = {"caller": "test", "op": "write", "path": target, "content": "x"}
        code, payload = writer.perform(None, self.values, req)
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "outside_scope")
        self.assertFalse(os.path.exists(target))

    def test_a_request_cannot_name_its_own_root(self):
        # The request claims an extra root covering the
        # target; the service's values name none, so the
        # claim is ignored and the write is refused.
        target = os.path.join(self.elsewhere.name, "escape.txt")
        req = {
            "caller": "test",
            "op": "write",
            "path": target,
            "content": "x",
            "ops_extra_write_roots": [self.elsewhere.name],
        }
        code, payload = writer.perform(
            None, {"workspace_root": self.ws.name}, req)
        self.assertEqual(code, 403)
        self.assertEqual(payload["error"], "outside_scope")
        self.assertFalse(os.path.exists(target))


if __name__ == "__main__":
    unittest.main()
