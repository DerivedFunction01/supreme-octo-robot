"""The platform serving core: routing, reply forms, error
containment, and the supervision separation (a route fault
never reaches a worker; a worker fault surfaces and stops
the serve — it never silently stops)."""

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import serving  # noqa: E402


def _router():
    router = serving.Router()
    router.add("GET", "/health", lambda req: {"ok": True})
    router.add("GET", "/items/{item_id}",
               lambda req: (200, {"id": req.params["item_id"]}))
    router.add("GET", "/files/{path...}",
               lambda req: (200, {"path": req.params["path"]}))
    router.add("POST", "/echo",
               lambda req: (201, {"got": req.json_object()}))

    def boom(req):
        raise RuntimeError("kaboom")

    router.add("GET", "/boom", boom)

    def domain(req):
        raise ValueError("domain-shaped")

    router.add("GET", "/domain", domain)
    return router


def _mount():
    def mapper(exc):
        if isinstance(exc, ValueError):
            return serving.Reply.json(
                422, {"error": str(exc)}, serving._default_dumps)
        return None

    return serving.Mount("test", _router(), error_mapper=mapper,
                         body_cap=64)


def _fetch(url, data=None, method=None):
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


class ServingCoreTests(unittest.TestCase):
    def setUp(self):
        self.listener = serving.Listener(_mount(), "127.0.0.1", 0)
        self.port = self.listener.server_address[1]
        self.thread = self.listener.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.listener.shutdown()
        self.listener.server_close()

    def test_routes_params_and_wildcard(self):
        self.assertEqual(_fetch(self.base + "/health"),
                         (200, {"ok": True}))
        self.assertEqual(_fetch(self.base + "/items/abc"),
                         (200, {"id": "abc"}))
        self.assertEqual(_fetch(self.base + "/files/a/b/c.txt"),
                         (200, {"path": "a/b/c.txt"}))

    def test_no_route_is_the_mounts_404(self):
        status, payload = _fetch(self.base + "/nope")
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "not found"})

    def test_json_body_round_trip_and_bad_body(self):
        status, payload = _fetch(
            self.base + "/echo",
            data=json.dumps({"a": 1}).encode(), method="POST")
        self.assertEqual((status, payload), (201, {"got": {"a": 1}}))
        status, payload = _fetch(
            self.base + "/echo", data=b"[1, 2]", method="POST")
        self.assertEqual(status, 400)

    def test_body_cap_refuses_before_the_handler(self):
        status, _ = _fetch(self.base + "/echo",
                           data=b"x" * 100, method="POST")
        self.assertEqual(status, 413)

    def test_domain_error_maps_and_route_fault_is_contained(self):
        self.assertEqual(_fetch(self.base + "/domain"),
                         (422, {"error": "domain-shaped"}))
        status, payload = _fetch(self.base + "/boom")
        self.assertEqual(status, 500)
        self.assertIn("kaboom", payload["error"])
        # The listener is unharmed by the fault.
        self.assertEqual(_fetch(self.base + "/health"),
                         (200, {"ok": True}))


class SupervisionSeparationTests(unittest.TestCase):
    def test_route_faults_never_reach_the_worker(self):
        listener = serving.Listener(_mount(), "127.0.0.1", 0)
        port = listener.server_address[1]
        ticks = []
        release = threading.Event()

        def tick(stop):
            while not stop.is_set():
                ticks.append(1)
                stop.wait(0.02)
            release.set()

        outcome = {}
        stop = threading.Event()

        def run():
            outcome["code"] = serving.serve(
                [listener], workers={"tick": tick}, stop=stop,
                log=lambda *a: None)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        for _ in range(5):
            status, _ = _fetch(f"http://127.0.0.1:{port}/boom")
            self.assertEqual(status, 500)
        self.assertGreater(len(ticks), 0)
        self.assertTrue(thread.is_alive())
        stop.set()
        thread.join(timeout=10)
        self.assertEqual(outcome.get("code"), 0)

    def test_worker_fault_surfaces_and_stops_the_serve(self):
        listener = serving.Listener(_mount(), "127.0.0.1", 0)
        port = listener.server_address[1]

        def bad_tick(stop):
            raise RuntimeError("tick died")

        logs = []
        code = serving.serve([listener], workers={"tick": bad_tick},
                              log=logs.append)
        self.assertEqual(code, 3)
        self.assertTrue(any("tick" in line for line in logs))
        # The listener is down: the port no longer answers.
        with self.assertRaises(Exception):
            _fetch(f"http://127.0.0.1:{port}/health")


if __name__ == "__main__":
    unittest.main()
