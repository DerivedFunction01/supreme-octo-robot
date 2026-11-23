"""The lease-UI test harness: a UiServer fixture-repo boot
of ui/server.py against a stub lease CLI (no login, no
network, no real lease state), plus the free-port pick.

Split from test_ui_server.py at the file-size cap:
the harness is one seam, the tests that
drive it are the other. The boot copies the server into
a fixture repo rooted like the consolidated tree (the
platform serving core linked as a pipeline sibling) so
repo_config() serves fixture caps, never the checkout's.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent.parent
STUB_SRC = REPO / "tests" / "fixtures" / "stub_lease_bin.py"
SERVER = REPO / "ui" / "server.py"

sys.path.insert(0, str(REPO / "tests" / "fixtures"))
import repo_fixture  # noqa: E402

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class UiServer:
    def __init__(self, tmp_path: Path, extra_env: dict | None = None):
        self.var = tmp_path / "var"
        self.log = tmp_path / "invocations.log"
        stub = tmp_path / "stub_lease_bin.py"
        stub.write_text(STUB_SRC.read_text())
        stub.chmod(0o755)
        # The server derives its repo root from its own location:
        # run a copy rooted at a fixture repo (authored config in
        # the test tree) so repo_config() serves the fixture caps,
        # never the checkout's operator config.
        root = tmp_path / "repo"
        ui_dir = root / "ui"
        ui_dir.mkdir(parents=True)
        shutil.copy(SERVER, ui_dir / "server.py")
        shutil.copy(REPO / "ui" / "stackdump.py", ui_dir / "stackdump.py")
        # The panel's own sibling seams load by location from
        # beside server.py — they ride the copy like stackdump.py.
        shutil.copy(REPO / "ui" / "state_reads.py", ui_dir / "state_reads.py")
        shutil.copy(REPO / "ui" / "state_surface.py", ui_dir / "state_surface.py")
        shutil.copy(REPO / "ui" / "shape_store.py", ui_dir / "shape_store.py")
        shutil.copy(REPO / "ui" / "route_surface.py", ui_dir / "route_surface.py")
        shutil.copy(REPO / "ui" / "bounded_server.py", ui_dir / "bounded_server.py")
        shutil.copy(REPO / "ui" / "config.json", ui_dir / "config.json")
        (ui_dir / "static").symlink_to(REPO / "ui" / "static")
        # Mirror the pipeline layout: the platform sibling, linked.
        link = root.parent / "platform"
        link.exists() or link.symlink_to(REPO.parent / "platform")
        repo_fixture.write_config(root)
        self.port = free_port()
        env = dict(
            os.environ,
            COLAB_LEASE_BIN=str(stub),
            COLAB_RUNNER_VAR=str(self.var),
            COLAB_LEASE_UI_PORT=str(self.port),
            COLAB_LEASE_UI_STACKDUMP="0",
            STUB_LEASE_LOG=str(self.log),
        )
        env.update(extra_env or {})
        self.proc = subprocess.Popen(
            [sys.executable, str(ui_dir / "server.py")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                self.get("/")
                return
            except OSError:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"server exited early: {self.proc.stdout.read()}")
                time.sleep(0.1)
        raise RuntimeError("server did not come up")

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path: str):
        with urllib.request.urlopen(self.url(path), timeout=10) as resp:
            body = resp.read().decode()
            return resp.status, body

    def get_json(self, path: str):
        _, body = self.get(path)
        return json.loads(body)

    def post(self, path: str, payload: dict):
        req = urllib.request.Request(
            self.url(path),
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode() or "{}")

    def invocations(self) -> list[str]:
        if not self.log.exists():
            return []
        return self.log.read_text().splitlines()

    def outbox_events(self) -> list[dict]:
        return self.get_json("/api/outbox?after=0")["events"]

