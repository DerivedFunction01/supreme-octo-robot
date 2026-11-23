"""Pins for the /ops client (pipeline/platform/ops_client.py):
the library form of contract 04's endpoint, for in-process
callers whose writes must be PERFORMED by the server
process (the venue writer seam).

The fixture is a real loopback HTTP server running the
genuine endpoint (the scheduling server's ops.perform over
this tree's platform writer) against a temp workspace
root — the process separation the client exists for is
real here, not doubled: the client's own process could be
write-denied wall to wall and the write would still land.
Authentication mirrors the HTTP layer's contract: the
bearer token's SHA-256 is the only thing the server side
holds; a match authenticates the fixture caller with the
write-state scope.
"""

import hashlib
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
PIPELINE = PLATFORM.parent
sys.path.insert(0, str(PLATFORM))
sys.path.insert(0, str(PIPELINE / "scheduling"))

import ops_client  # noqa: E402
import writer  # noqa: E402
from server.serving import ops as sched_ops  # noqa: E402

CALLER = "venue"
TOKEN = "fixture-token-for-ops-client-tests"
TOKEN_SHA256 = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the suite quiet
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        self.server.requests.append(
            {"headers": dict(self.headers), "body": body})
        try:
            req = json.loads(body.decode("utf-8"))
        except ValueError:
            req = {}
        auth = None
        presented = self.headers.get("Authorization") or ""
        if presented.startswith("Bearer "):
            digest = hashlib.sha256(
                presented[len("Bearer "):].encode("utf-8")).hexdigest()
            if digest == TOKEN_SHA256:
                auth = (CALLER, ["write-state"])
        code, payload = sched_ops.perform(
            None, self.server.values, req, auth=auth)
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class OpsClientCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.token_dir = os.path.join(self.root, "ops-tokens")
        os.makedirs(self.token_dir)
        with open(os.path.join(self.token_dir, f"{CALLER}.token"),
                  "w", encoding="utf-8") as fh:
            fh.write(TOKEN + "\n")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.values = {"workspace_root": self.root,
                              "capture_cap_bytes": 65536}
        self.server.requests = []
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        self.env = {"SCHEDULER_HOST": "127.0.0.1",
                    "SCHEDULER_PORT": str(port),
                    "SCHED_OPS_TOKEN_DIR": self.token_dir}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def target(self, name="state.json"):
        return os.path.join(self.root, name)

    def test_write_lands_byte_identical_through_the_service(self):
        payload = ops_client.staged_write(
            CALLER, self.target(), b'{"a": 1}\n', env=self.env)
        self.assertEqual(payload["bytes"], 9)
        with open(self.target(), "rb") as fh:
            self.assertEqual(fh.read(), b'{"a": 1}\n')
        # No staging litter: the server's staged sibling was
        # renamed over, nothing of the client's own exists.
        self.assertEqual(sorted(os.listdir(self.root)),
                         ["ops-tokens", "state.json"])

    def test_token_and_caller_are_presented(self):
        ops_client.staged_write(CALLER, self.target(), b"{}", env=self.env)
        self.assertEqual(len(self.server.requests), 1)
        seen = self.server.requests[0]
        self.assertEqual(seen["headers"].get("Authorization"),
                         f"Bearer {TOKEN}")
        self.assertEqual(json.loads(seen["body"])["caller"], CALLER)

    def test_flap_local_writer_dead_but_the_route_lands(self):
        # The flap simulation: every in-process staged write
        # in the caller's process is denied (EPERM), as the
        # reaper's process was. The client attempts no local
        # write at all — rig its writer module to explode on
        # any use — and the performed write still lands.
        def denied(*a, **k):
            raise PermissionError(1, "Operation not permitted")

        orig_client_writer = ops_client._writer.staged_write
        orig_local_writer = writer.staged_write
        ops_client._writer.staged_write = denied
        writer.staged_write = denied
        try:
            ops_client.staged_write(
                CALLER, self.target(), b"landed\n", env=self.env)
        finally:
            ops_client._writer.staged_write = orig_client_writer
            writer.staged_write = orig_local_writer
        with open(self.target(), "rb") as fh:
            self.assertEqual(fh.read(), b"landed\n")

    def test_mode_0600_survives_the_route(self):
        target = self.target("secret.json")
        ops_client.staged_write(
            CALLER, target, b"{}", mode=0o600, env=self.env)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
        # And restamped on a recreate at the umask default.
        os.chmod(target, 0o644)
        ops_client.staged_write(
            CALLER, target, b'{"v": 2}', mode=0o600, env=self.env)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)

    def test_unreachable_raises_io_error_and_target_untouched(self):
        # A port nothing listens on: bind, take the number,
        # close — the connect is refused, provably pre-send.
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]
        sock.close()
        env = dict(self.env, SCHEDULER_PORT=str(dead_port))
        target = self.target()
        with open(target, "wb") as fh:
            fh.write(b"standing")
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.staged_write(CALLER, target, b"new", env=env)
        self.assertEqual(ctx.exception.name, "io_error")
        self.assertIn("nothing was performed", ctx.exception.detail)
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"standing")
        fresh = self.target("fresh.json")
        with self.assertRaises(ops_client.WriterError):
            ops_client.staged_write(CALLER, fresh, b"new", env=env)
        self.assertFalse(os.path.exists(fresh))

    def test_server_refusal_carries_the_endpoint_error_name(self):
        outside = os.path.join(os.path.dirname(self.root), "escape.txt")
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.staged_write(CALLER, outside, b"x", env=self.env)
        self.assertEqual(ctx.exception.name, "outside_scope")
        self.assertFalse(os.path.exists(outside))

    def test_no_token_is_unauthenticated_and_writes_nothing(self):
        empty_dir = os.path.join(self.root, "empty-tokens")
        os.makedirs(empty_dir)
        env = dict(self.env, SCHED_OPS_TOKEN_DIR=empty_dir)
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.staged_write(CALLER, self.target(), b"x", env=env)
        self.assertEqual(ctx.exception.name, "unauthenticated")
        self.assertFalse(os.path.exists(self.target()))

    def test_non_utf8_is_refused_before_anything_is_sent(self):
        with self.assertRaises(ops_client.WriterError) as ctx:
            ops_client.staged_write(
                CALLER, self.target(), b"\xff\xfe\x00", env=self.env)
        self.assertEqual(ctx.exception.name, "bad_request")
        self.assertEqual(self.server.requests, [])
        self.assertFalse(os.path.exists(self.target()))


if __name__ == "__main__":
    unittest.main()
