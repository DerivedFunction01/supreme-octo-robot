"""The attention shell's pins: the explicit store binding
refuses (never defaults), and the mount answers the
pinned route cycle against a fixture store — a post is
readable after it lands (the one-lock discipline), an
unknown handler is a problem 404 in the surface's own
error language, every reply carries the security
baseline, and the retired static routes (AC-10) answer
that same problem 404 — the shell serves the API only.
Fixture state only: a scratch store file built from the
store seam's empty state, never a live store.
"""

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention import server as server_mod  # noqa: E402
from attention.infra import store as store_mod  # noqa: E402
from attention.settings import Settings  # noqa: E402


def _fixture_store(tmp):
    path = Path(tmp) / "state.json"
    path.write_text(json.dumps(store_mod.empty_state()), encoding="utf-8")
    return path


class BindingTests(unittest.TestCase):
    def test_unset_data_path_refuses(self):
        settings = Settings(data_path=None)
        with self.assertRaises(server_mod.StoreBindingError):
            server_mod.make_store(settings)

    def test_missing_store_file_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_path=Path(tmp) / "absent.json")
            with self.assertRaises(server_mod.StoreBindingError):
                server_mod.make_store(settings)

    def test_explicit_store_binds(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_path=_fixture_store(tmp))
            store = server_mod.make_store(settings)
            self.assertEqual(store.load_state()["handlers"], [])


class MountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = Settings(
            data_path=_fixture_store(self.tmp.name), host="127.0.0.1", port=0
        )
        store = server_mod.make_store(settings)
        mount, _workers = server_mod.build_mount(settings, store)
        self.listener = server_mod.serving.Listener(mount, "127.0.0.1", 0)
        self.port = self.listener.server_address[1]
        self.thread = threading.Thread(target=self.listener.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.listener.shutdown()
        self.listener.server_close()
        self.tmp.cleanup()

    def call(self, method, path, body=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, e.headers, json.loads(e.read())

    def test_health_and_security_baseline(self):
        status, headers, payload = self.call("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["contract"], "api/1")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_post_is_readable_after_it_lands(self):
        status, _h, payload = self.call(
            "POST",
            "/api/v1/handlers",
            {
                "handle": "@example-lane",
                "label": "Example lane",
            },
        )
        self.assertEqual(status, 201)
        status, _h, payload = self.call("GET", "/api/v1/handlers/@example-lane")
        self.assertEqual(status, 200)
        self.assertEqual(payload["handle"], "@example-lane")
        self.assertEqual(payload["label"], "Example lane")

    def test_retired_static_routes_are_problems(self):
        for path in ("/", "/index.html", "/app.js", "/app.css", "/fonts/x.woff2"):
            status, _h, payload = self.call("GET", path)
            self.assertEqual(status, 404, path)
            self.assertEqual(payload["type"], "urn:problem:not-found", path)

    def test_unknown_handler_is_a_problem(self):
        status, headers, payload = self.call("GET", "/api/v1/handlers/@absent")
        self.assertEqual(status, 404)
        self.assertEqual(payload["type"], "urn:problem:not-found")
        self.assertEqual(headers.get("Content-Type"), "application/problem+json")
        self.assertTrue(headers.get("X-Correlation-Id"))

    def test_unknown_route_is_a_problem(self):
        status, _h, payload = self.call("GET", "/api/v1/nope")
        self.assertEqual(status, 404)
        self.assertEqual(payload["type"], "urn:problem:not-found")

    def test_options_is_answered_by_the_shell(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/v1/today", method="OPTIONS"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")


if __name__ == "__main__":
    unittest.main()
