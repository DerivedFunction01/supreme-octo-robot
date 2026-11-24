"""Pins for the /ops client's transient retry
(pipeline/platform/ops_client.py): a provably unsent
request is retried on the bounded ladder by every perform;
a lost response is retried only inside staged_write, whose
op is a full replace of identical bytes verified on the
result; a well-formed server answer — success or refusal —
is never retried.

The seam stubbed here is the client's own post(): the
retry policy lives above it, so a scripted sequence of
post faces pins the policy exactly (attempt counts
included) without a server. The classification of raw
bodies (empty or garbled → the lost face) is pinned at
post() itself against a stubbed urlopen. Backoff is
zeroed throughout: the ladder's shape is the constants',
the counts are what's pinned.
"""

import hashlib
import sys
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

PLATFORM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM))

import ops_client  # noqa: E402

CALLER = "venue"
CONTENT = b'{"a": 1}\n'
WRITE_OK = {
    "ok": True,
    "bytes": len(CONTENT),
    "sha256": hashlib.sha256(CONTENT).hexdigest(),
}


class ScriptedPost:
    """A post() double answering a scripted face sequence
    (the last face repeats if the script runs out) and
    counting its calls."""

    def __init__(self, *faces):
        self.faces = list(faces)
        self.calls = 0

    def __call__(self, req, http_timeout, env=None):
        self.calls += 1
        if len(self.faces) > 1:
            return self.faces.pop(0)
        return self.faces[0]


class RetryCase(unittest.TestCase):
    def setUp(self):
        self._backoff = ops_client.TRANSIENT_BACKOFF_S
        ops_client.TRANSIENT_BACKOFF_S = (0, 0, 0)
        self._post = ops_client.post

    def tearDown(self):
        ops_client.TRANSIENT_BACKOFF_S = self._backoff
        ops_client.post = self._post

    def script(self, *faces):
        stub = ScriptedPost(*faces)
        ops_client.post = stub
        return stub


class PerformRetryTest(RetryCase):
    def test_unreachable_then_valid_succeeds(self):
        stub = self.script(ops_client.UNREACHABLE, ops_client.UNREACHABLE, {"ok": True, "v": 1})
        payload = ops_client.perform(CALLER, {"op": "exec"}, http_timeout=5)
        self.assertEqual(payload, {"ok": True, "v": 1})
        self.assertEqual(stub.calls, 3)

    def test_persistent_unreachable_raises_after_exactly_the_bound(self):
        stub = self.script(ops_client.UNREACHABLE)
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.perform(CALLER, {"op": "exec"}, http_timeout=5)
        self.assertEqual(ctx.exception.name, "io_error")
        self.assertIn("nothing was performed", ctx.exception.detail)
        self.assertEqual(stub.calls, ops_client.TRANSIENT_ATTEMPTS)

    def test_lost_response_is_never_retried_by_perform(self):
        stub = self.script(ops_client.UNKNOWN)
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.perform(CALLER, {"op": "exec"}, http_timeout=5)
        self.assertEqual(ctx.exception.name, "io_error")
        self.assertIn("response was lost", ctx.exception.detail)
        self.assertEqual(stub.calls, 1)

    def test_wellformed_refusal_surfaces_immediately(self):
        refusal = {"ok": False, "error": "outside_scope", "detail": "path outside the workspace root"}
        stub = self.script(refusal)
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.perform(CALLER, {"op": "write"}, http_timeout=5)
        self.assertEqual(ctx.exception.name, "outside_scope")
        self.assertEqual(stub.calls, 1)


class StagedWriteRetryTest(RetryCase):
    def test_lost_response_then_valid_succeeds(self):
        stub = self.script(ops_client.UNKNOWN, ops_client.UNKNOWN, WRITE_OK)
        payload = ops_client.staged_write(CALLER, "/tmp/target.json", CONTENT)
        self.assertEqual(payload["bytes"], len(CONTENT))
        self.assertEqual(stub.calls, 3)

    def test_persistent_lost_raises_after_exactly_its_bound(self):
        stub = self.script(ops_client.UNKNOWN)
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.staged_write(CALLER, "/tmp/target.json", CONTENT)
        self.assertEqual(ctx.exception.name, "io_error")
        self.assertIn("response was lost", ctx.exception.detail)
        self.assertIn("verify before repeating", ctx.exception.detail)
        self.assertEqual(stub.calls, ops_client.LOST_ATTEMPTS)

    def test_refusal_is_not_retried_by_staged_write(self):
        refusal = {"ok": False, "error": "unauthenticated", "detail": "nope"}
        stub = self.script(refusal)
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.staged_write(CALLER, "/tmp/target.json", CONTENT)
        self.assertEqual(ctx.exception.name, "unauthenticated")
        self.assertEqual(stub.calls, 1)

    def test_unreachable_then_valid_succeeds(self):
        stub = self.script(ops_client.UNREACHABLE, WRITE_OK)
        payload = ops_client.staged_write(CALLER, "/tmp/target.json", CONTENT)
        self.assertEqual(payload["sha256"], WRITE_OK["sha256"])
        self.assertEqual(stub.calls, 2)


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class PostClassificationTest(unittest.TestCase):
    """The raw-body faces at post(): an empty or garbled
    success body is the lost face (UNKNOWN) — never a
    payload, never an exception escaping the client."""

    def post_with_body(self, body):
        def fake_urlopen(request, timeout=None):
            return _FakeResponse(body)

        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            return ops_client.post({"caller": CALLER, "op": "exec"}, 5, env={})

    def test_empty_body_classifies_as_lost(self):
        self.assertEqual(self.post_with_body(b""), ops_client.UNKNOWN)

    def test_garbled_body_classifies_as_lost(self):
        self.assertEqual(self.post_with_body(b"not json"), ops_client.UNKNOWN)

    def test_valid_body_is_the_payload(self):
        self.assertEqual(self.post_with_body(b'{"ok": true}'), {"ok": True})


if __name__ == "__main__":
    unittest.main()
