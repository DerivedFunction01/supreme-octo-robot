"""The suite's /ops service double.

The lease foundation's writer seam performs its writes
through the scheduler /ops service (the platform ops
client), so a suite that exercises the seam needs the
service to exist. This conftest stands up the genuine
endpoint — the scheduling server's ops.perform over the
platform writer — on a loopback port for the session,
rooted at the session's basetemp (every fixture repo and
scratch var in the suite lives under it), and points the
client's own resolution seams at it: SCHEDULER_HOST /
SCHEDULER_PORT for the endpoint, SCHED_OPS_TOKEN_DIR for
the venue caller's token. Authentication mirrors the
real HTTP layer's contract: the server side holds only
the token's SHA-256; a match authenticates the venue
machinery caller with the write-state scope.

Two honest absences: when the operator's environment
already names an endpoint (SCHEDULER_PORT set), the
double does not stand up — the named service is the
suite's to use; and in a standalone venue tree (no
scheduling package beside it) there is no endpoint code
to run, and the seam's own standalone-layout fallback is
what the suite exercises, as before.
"""

import hashlib
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

CHECKOUT = Path(__file__).resolve().parent.parent
SCHEDULING_ROOT = CHECKOUT.parent / "scheduling"
CALLER = "venue"


class _OpsHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the suite quiet
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        try:
            req = json.loads(body.decode("utf-8"))
        except ValueError:
            req = {}
        auth = None
        presented = self.headers.get("Authorization") or ""
        if presented.startswith("Bearer "):
            digest = hashlib.sha256(
                presented[len("Bearer ") :].encode("utf-8")
            ).hexdigest()
            if digest == self.server.token_sha256:
                auth = (CALLER, ["write-state"])
        code, payload = self.server.ops.perform(
            None, self.server.values, req, auth=auth
        )
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="session", autouse=True)
def ops_service_double(tmp_path_factory):
    if os.environ.get("SCHEDULER_PORT"):
        yield
        return
    if not (SCHEDULING_ROOT / "server" / "serving" / "ops.py").exists():
        yield
        return
    sys.path.insert(0, str(SCHEDULING_ROOT))
    try:
        from server.serving import ops
    except Exception:  # noqa: BLE001 - no endpoint, no double
        yield
        return
    basetemp = tmp_path_factory.getbasetemp()
    token = secrets.token_urlsafe(24)
    token_dir = basetemp / "ops-double-tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    token_file = token_dir / f"{CALLER}.token"
    token_file.write_text(token + "\n", encoding="utf-8")
    os.chmod(token_file, 0o600)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _OpsHandler)
    server.ops = ops
    server.values = {"workspace_root": str(basetemp), "capture_cap_bytes": 65536}
    server.token_sha256 = hashlib.sha256(token.encode("utf-8")).hexdigest()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    saved = {
        name: os.environ.get(name)
        for name in ("SCHEDULER_HOST", "SCHEDULER_PORT", "SCHED_OPS_TOKEN_DIR")
    }
    os.environ["SCHEDULER_HOST"] = "127.0.0.1"
    os.environ["SCHEDULER_PORT"] = str(server.server_address[1])
    os.environ["SCHED_OPS_TOKEN_DIR"] = str(token_dir)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        server.shutdown()
        server.server_close()
