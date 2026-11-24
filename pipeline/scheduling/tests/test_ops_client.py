"""The ops client's exit-4 contract: a
transport failure is reported as non-performance ONLY
when the request provably never left (connection refused,
name unresolvable). A sent request whose response was
lost — a timeout, a reset — reports UNKNOWN: the op may
have performed, and the caller must verify before
repeating. The earlier form printed "nothing was
performed" for both faces and was attested three times
in one night by callers repeating work that had run.
urlopen is mocked throughout; no live server is touched."""

import io
import socket
import sys
import os
import unittest
import urllib.error
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import ops_client  # noqa: E402


class PreSendCase(unittest.TestCase):
    def test_refused_and_unresolvable_are_pre_send(self):
        self.assertTrue(ops_client._pre_send(ConnectionRefusedError("no")))
        self.assertTrue(ops_client._pre_send(socket.gaierror("dns")))

    def test_timeout_and_reset_are_not_pre_send(self):
        self.assertFalse(ops_client._pre_send(TimeoutError("slow")))
        self.assertFalse(ops_client._pre_send(ConnectionResetError("cut")))


class PostClassificationCase(unittest.TestCase):
    def post_with(self, exc):
        with mock.patch.object(
            ops_client.config_mod, "resolve",
            lambda: ({"host": "127.0.0.1", "port": 8796}, None),
        ), mock.patch.object(
            ops_client, "resolve_ops_token", lambda caller: None
        ), mock.patch(
            "urllib.request.urlopen", side_effect=exc
        ):
            return ops_client._ops_post({"caller": "test", "op": "exec"}, 5)

    def test_refused_is_unreachable(self):
        exc = urllib.error.URLError(ConnectionRefusedError("refused"))
        self.assertEqual(self.post_with(exc), ops_client.UNREACHABLE)

    def test_unresolvable_is_unreachable(self):
        exc = urllib.error.URLError(socket.gaierror("no host"))
        self.assertEqual(self.post_with(exc), ops_client.UNREACHABLE)

    def test_response_timeout_is_unknown(self):
        exc = urllib.error.URLError(TimeoutError("timed out"))
        self.assertEqual(self.post_with(exc), ops_client.UNKNOWN)

    def test_reset_is_unknown(self):
        self.assertEqual(
            self.post_with(ConnectionResetError("cut")), ops_client.UNKNOWN)


class ReportCase(unittest.TestCase):
    def report(self, payload):
        buf = io.StringIO()
        with redirect_stderr(buf):
            code = ops_client._ops_report("exec", payload)
        return code, buf.getvalue()

    def test_unreachable_reports_non_performance(self):
        code, err = self.report(ops_client.UNREACHABLE)
        self.assertEqual(code, 4)
        self.assertIn("nothing was performed", err)

    def test_null_payload_reports_unknown(self):
        code, err = self.report(None)
        self.assertEqual(code, 4)
        self.assertIn("UNKNOWN", err)
        self.assertNotIn("nothing was performed", err)

    def test_unknown_never_claims_non_performance(self):
        code, err = self.report(ops_client.UNKNOWN)
        self.assertEqual(code, 4)
        self.assertIn("UNKNOWN", err)
        self.assertNotIn("nothing was performed", err)

    def test_payload_faces_unchanged(self):
        self.assertEqual(self.report({"ok": True})[0], 0)
        code, err = self.report({"ok": False, "error": "denied", "detail": "no"})
        self.assertEqual(code, 1)
        self.assertIn("denied", err)


if __name__ == "__main__":
    unittest.main()
