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


class FreshnessTests(unittest.TestCase):
    """The handler-freshness pins (the handler-freshness
    plan, step 1): a verdict written through the API
    serves back inline on the registries payload; a
    handler with no record serves unresolvable, never
    current; a verdict older than the registry's stale
    window renders stale with the composed verdict
    beside it, while a retired-with-cause disposition
    does not decay; writes outside the registry's
    vocabularies refuse as problems."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._start(store_mod.empty_state())

    def _start(self, state):
        path = Path(self.tmp.name) / "state.json"
        path.write_text(json.dumps(state), encoding="utf-8")
        settings = Settings(data_path=path, host="127.0.0.1", port=0)
        store = server_mod.make_store(settings)
        mount, _workers = server_mod.build_mount(settings, store)
        self.listener = server_mod.serving.Listener(mount, "127.0.0.1", 0)
        self.port = self.listener.server_address[1]
        self.thread = threading.Thread(target=self.listener.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.listener.shutdown)
        self.addCleanup(self.listener.server_close)

    def call(self, method, path, body=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            method=method,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def _register(self, handle="@example-lane"):
        status, _payload = self.call(
            "POST", "/api/v1/handlers", {"handle": handle, "label": "Example"}
        )
        self.assertEqual(status, 201)

    def _served_freshness(self, handle="@example-lane"):
        status, payload = self.call("GET", "/api/v1/registries")
        self.assertEqual(status, 200)
        entry = next(h for h in payload["handlers"] if h["handle"] == handle)
        return payload, entry["freshness"]

    def test_write_serves_back_inline(self):
        self._register()
        status, payload = self.call(
            "POST",
            "/api/v1/handlers/@example-lane/freshness",
            {
                "verdict": "current",
                "binding_state": "live-seat",
                "bound_chat": "chat-a",
                "seat_chat": "chat-a",
                "last_evidence": {
                    "kind": "run",
                    "at": "2026-11-26T09:00:00+00:00",
                    "ref": "run-123",
                },
                "declaration_age_days": 1,
            },
        )
        self.assertEqual(status, 201)
        self.assertTrue(payload["recorded"])
        _registries, fresh = self._served_freshness()
        self.assertEqual(fresh["verdict"], "current")
        self.assertEqual(fresh["verdict_label"], "Current")
        self.assertEqual(fresh["binding_state"], "live-seat")
        self.assertEqual(fresh["binding_label"], "Live seat")
        self.assertEqual(fresh["bound_chat"], "chat-a")
        self.assertEqual(fresh["seat_chat"], "chat-a")
        self.assertIsNotNone(fresh["last_reconcile_at"])
        self.assertIsNotNone(fresh["reconcile_age_label"])
        self.assertEqual(fresh["last_evidence"]["kind"], "run")
        self.assertEqual(fresh["last_evidence"]["kind_label"], "Run")
        self.assertEqual(fresh["last_evidence"]["ref"], "run-123")
        self.assertEqual(fresh["declaration_age_days"], 1)

    def test_absent_record_serves_unresolvable(self):
        self._register()
        _registries, fresh = self._served_freshness()
        self.assertEqual(fresh["verdict"], "unresolvable")
        self.assertEqual(fresh["binding_state"], "unresolvable")
        self.assertIsNone(fresh["last_reconcile_at"])
        self.assertIsNone(fresh["last_evidence"])

    def test_freshness_registry_is_served(self):
        status, registries = self.call("GET", "/api/v1/registries")
        self.assertEqual(status, 200)
        codes = {e["code"] for e in registries["freshness"]["verdicts"]}
        self.assertEqual(
            codes,
            {"current", "stale", "dead-binding", "unresolvable", "retired-with-cause"},
        )
        self.assertEqual(registries["freshness"]["verdict_stale_after_hours"], 2)
        self.assertEqual(registries["freshness"]["evidence_window_seat_hours"], 24)
        self.assertEqual(registries["freshness"]["evidence_window_lane_hours"], 168)

    def test_aged_verdict_renders_stale_but_retirement_does_not_decay(self):
        state = store_mod.empty_state()
        state["handlers"] = [
            {"handle": "@aged", "label": "Aged"},
            {"handle": "@retired", "label": "Retired"},
        ]
        aged_at = "2026-11-26T00:00:00+00:00"
        state["handler_freshness"] = {
            "@aged": {
                "handle": "@aged",
                "verdict": "current",
                "binding_state": "live-seat",
                "bound_chat": "chat-a",
                "seat_chat": "chat-a",
                "last_reconcile_at": aged_at,
                "last_evidence": None,
                "declaration_age_days": None,
                "cause": None,
            },
            "@retired": {
                "handle": "@retired",
                "verdict": "retired-with-cause",
                "binding_state": "deleted",
                "bound_chat": "chat-gone",
                "seat_chat": None,
                "last_reconcile_at": aged_at,
                "last_evidence": None,
                "declaration_age_days": None,
                "cause": "seat-deleted",
            },
        }
        self.listener.shutdown()
        self.listener.server_close()
        self._start(state)
        _r, fresh = self._served_freshness("@aged")
        self.assertEqual(fresh["verdict"], "stale")
        self.assertEqual(fresh["composed_verdict"], "current")
        _r, fresh = self._served_freshness("@retired")
        self.assertEqual(fresh["verdict"], "retired-with-cause")
        self.assertEqual(fresh["cause"], "seat-deleted")
        self.assertEqual(fresh["cause_label"], "Seat deleted")

    def test_write_outside_the_vocabulary_refuses(self):
        self._register()
        status, payload = self.call(
            "POST",
            "/api/v1/handlers/@example-lane/freshness",
            {"verdict": "probably-fine", "binding_state": "live-seat"},
        )
        self.assertEqual(status, 422)
        self.assertEqual(payload["type"], "urn:problem:validation")
        status, _payload = self.call(
            "POST",
            "/api/v1/handlers/@example-lane/freshness",
            {"verdict": "retired-with-cause", "binding_state": "deleted"},
        )
        self.assertEqual(status, 422)

    def test_write_to_unknown_handler_is_a_problem(self):
        status, payload = self.call(
            "POST",
            "/api/v1/handlers/@absent/freshness",
            {"verdict": "current", "binding_state": "live-seat"},
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["type"], "urn:problem:not-found")


class CapacityPassCase(unittest.TestCase):
    """The capacity pass's failure discipline: a throw
    anywhere in the collection is recorded in the
    served state — the pass's instant and the
    exception's identity under capacity_pass_error —
    never swallowed into a silent freeze; the next
    clean pass clears the record as its merge lands."""

    def _run_pass(self, store, settings, unlanded):
        from unittest import mock

        from attention import capacity as capacity_mod

        def fake_capacity(state, _settings, now):
            state["capacity_snapshot"] = {"at": now, "sessions": []}
            state["capacity_error"] = None
            return True

        quiet = lambda *args: False  # noqa: E731
        with (
            mock.patch.object(capacity_mod.staffing, "collect_capacity", fake_capacity),
            mock.patch.object(capacity_mod.worktrees, "collect", quiet),
            mock.patch.object(capacity_mod.records, "collect", quiet),
            mock.patch.object(capacity_mod.lanes, "collect", quiet),
            mock.patch.object(capacity_mod.records, "collect_consumption", quiet),
            mock.patch.object(capacity_mod.records, "collect_unlanded", unlanded),
            mock.patch.object(capacity_mod.records, "collect_goals", quiet),
            mock.patch.object(capacity_mod.stamps, "collect", quiet),
            mock.patch.object(capacity_mod.venue, "collect", quiet),
            mock.patch.object(capacity_mod.venue, "collect_frontier", quiet),
            mock.patch.object(capacity_mod.plans, "collect", quiet),
            mock.patch.object(capacity_mod.contracts, "sync", quiet),
            mock.patch.object(capacity_mod.digest, "collect_wb_facts", quiet),
        ):
            capacity_mod._capacity_pass(store, settings, threading.Lock())

    def test_failure_is_recorded_and_success_clears_it(self):
        from datetime import UTC, datetime, timedelta

        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_path=_fixture_store(tmp))
            store = server_mod.make_store(settings)
            old = {
                "at": datetime(2026, 11, 22, 1, 0, tzinfo=UTC),
                "sessions": [],
            }
            state = store.load_state()
            state["capacity_snapshot"] = old
            state["capacity_error"] = "stale reason"
            store.save_state(state)

            def boom(*args):
                raise RuntimeError("boom")

            self._run_pass(store, settings, boom)
            state = store.load_state()
            record = state.get("capacity_pass_error")
            self.assertIsInstance(record, dict)
            self.assertEqual(record["error"], "RuntimeError: boom")
            self.assertGreater(record["at"], datetime.now(UTC) - timedelta(minutes=5))
            # The failed pass's merge never landed: the
            # snapshot is still the seeded one.
            self.assertEqual(state["capacity_snapshot"]["at"], old["at"])
            self.assertEqual(state["capacity_error"], "stale reason")

            self._run_pass(store, settings, lambda *args: False)
            state = store.load_state()
            self.assertIsNone(state.get("capacity_pass_error"))
            self.assertGreater(state["capacity_snapshot"]["at"], old["at"])
            self.assertIsNone(state["capacity_error"])


if __name__ == "__main__":
    unittest.main()
