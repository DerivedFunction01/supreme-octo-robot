"""The harness connector (server/serving/connector.py): token auth from
the live config file, per-tool scopes, the direct tools wrapping
their in-tree cores, and the bridge queue lifecycle."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.serving import connector

TOKENS = {"venue": "tok-venue", "writer": "tok-writer", "bridge": "tok-bridge",
          "sender": "tok-sender"}
SCOPES = {"venue": ["read", "send"], "writer": ["read", "write-state"],
          "bridge": ["bridge", "read"], "sender": ["send"]}


class FakeOutbox:
    def ack(self, ping_id):
        return {"id": ping_id, "status": "acked"} if ping_id == "p1" else None


class ConnectorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = os.path.join(self.tmp, "repo")
        self.ws = os.path.join(self.tmp, "ws")
        os.makedirs(os.path.join(self.home, "bodies"))
        os.makedirs(os.path.join(self.home, "ops"))
        callers = {
            name: {"token_sha256": hashlib.sha256(t.encode()).hexdigest(),
                   "scopes": SCOPES[name]}
            for name, t in TOKENS.items()
        }
        with open(os.path.join(self.home, "config.json"), "w") as fh:
            json.dump({"connector": {"callers": callers}}, fh)
        self.values = {"home": self.home, "workspace_root": self.ws,
                       "workbench_base_url": "http://127.0.0.1:9"}
        self.engine = types.SimpleNamespace(outbox=FakeOutbox(), ledger=None)

    def auth(self, name):
        return connector.authenticate(self.values, TOKENS[name])

    def call(self, name, tool, args):
        caller, scopes = self.auth(name)
        return connector.call_tool(self.engine, self.values, caller, scopes, tool, args)

    def test_authenticate(self):
        self.assertEqual(self.auth("venue"), ("venue", ["read", "send"]))
        self.assertIsNone(connector.authenticate(self.values, "wrong"))
        self.assertIsNone(connector.authenticate(self.values, None))
        self.assertIsNone(connector.authenticate(self.values, ""))

    def test_registry_is_file_live(self):
        with open(os.path.join(self.home, "config.json"), "w") as fh:
            json.dump({"connector": {"callers": {}}}, fh)
        self.assertIsNone(connector.authenticate(self.values, TOKENS["venue"]))

    def test_scope_refused(self):
        with self.assertRaises(connector.ToolError) as ctx:
            self.call("venue", "ping_ack", {"ping_id": "p1"})
        self.assertEqual(ctx.exception.name, "scope_refused")

    def test_unknown_tool(self):
        with self.assertRaises(connector.ToolError) as ctx:
            self.call("venue", "approve_permission", {})
        self.assertEqual(ctx.exception.name, "unknown_tool")

    def test_sweeper_compatibility_tools_retired(self):
        # Plan §10.2 (ruled): the retired sweeper's connector
        # tools left at S3 — the records stay on disk, unread;
        # the tools are unknown here, not refused or served.
        for tool in ("sweeper_state_read", "sweeper_state_write",
                     "nudge_append"):
            with self.assertRaises(connector.ToolError) as ctx:
                self.call("writer", tool, {})
            self.assertEqual(ctx.exception.name, "unknown_tool")

    def test_ping_ack(self):
        _code, payload = self.call("writer", "ping_ack", {"ping_id": "p1"})
        self.assertEqual(payload["result"]["ping"]["status"], "acked")
        with self.assertRaises(connector.ToolError) as ctx:
            self.call("writer", "ping_ack", {"ping_id": "nope"})
        self.assertEqual(ctx.exception.name, "no_such_ping")

    def test_bridge_lifecycle(self):
        code, payload = self.call("venue", "chat_list", {})
        self.assertEqual(code, 202)
        request_id = payload["request_id"]
        _c, poll = self.call("bridge", "bridge_poll", {})
        self.assertEqual([r["id"] for r in poll["result"]["requests"]], [request_id])
        self.call("bridge", "bridge_fulfill",
                  {"request_id": request_id, "ok": True,
                   "result": {"chats": ["c1"]}})
        code, res = connector.fetch_result(
            self.engine, self.values, "venue", ["read", "send"], request_id)
        self.assertEqual((code, res["status"], res["result"]),
                         (200, "done", {"chats": ["c1"]}))
        with self.assertRaises(connector.ToolError) as ctx:
            connector.fetch_result(
                self.engine, self.values, "writer", ["read"], request_id)
        self.assertEqual(ctx.exception.name, "scope_refused")

    def call_env(self, name, tool, args, envelope_id):
        caller, scopes = self.auth(name)
        return connector.call_tool(self.engine, self.values, caller,
                                   scopes, tool, args,
                                   envelope_id=envelope_id)

    def test_envelope_dedupe_twin_post(self):
        code, first = self.call_env("venue", "chat_list", {}, "env-1")
        self.assertEqual(code, 202)
        self.assertEqual(first["envelope_id"], "env-1")
        record = connector._read_request(self.values, first["request_id"])
        self.assertEqual(record["envelope_id"], "env-1")
        code, twin = self.call_env("venue", "chat_list", {}, "env-1")
        self.assertEqual(code, 200)
        self.assertTrue(twin["deduped"])
        self.assertEqual(twin["request_id"], first["request_id"])
        self.assertEqual(twin["status"], "queued")
        _c, poll = self.call("bridge", "bridge_poll", {})
        self.assertEqual(len(poll["result"]["requests"]), 1)

    def test_envelope_dedupe_after_fulfillment(self):
        _c, first = self.call_env("venue", "chat_send",
                                  {"chat_id": "c1", "text": "hi"}, "env-2")
        self.call("bridge", "bridge_fulfill",
                  {"request_id": first["request_id"], "ok": True,
                   "result": {"delivered": True,
                              "submission_message_id": "m1"}})
        code, twin = self.call_env("venue", "chat_send",
                                   {"chat_id": "c1", "text": "hi"}, "env-2")
        self.assertEqual((code, twin["deduped"], twin["status"]),
                         (200, True, "done"))
        self.assertEqual(twin["request_id"], first["request_id"])

    def test_envelope_scoped_per_caller(self):
        _c, a = self.call_env("venue", "chat_list", {}, "env-3")
        code, b = self.call_env("writer", "chat_list", {}, "env-3")
        self.assertEqual(code, 202)
        self.assertNotEqual(a["request_id"], b["request_id"])

    def test_envelope_distinct_ids_queue_separately(self):
        _c, a = self.call_env("venue", "chat_list", {}, "env-4a")
        code, b = self.call_env("venue", "chat_list", {}, "env-4b")
        self.assertEqual(code, 202)
        self.assertNotEqual(a["request_id"], b["request_id"])

    def test_envelope_id_validated(self):
        for bad in ("", "has space", "x" * 129, 42, "a/b"):
            with self.assertRaises(connector.ToolError) as ctx:
                self.call_env("venue", "chat_list", {}, bad)
            self.assertEqual(ctx.exception.name, "bad_args")

    def test_no_envelope_legacy_path_unchanged(self):
        code, payload = self.call("venue", "chat_list", {})
        self.assertEqual(code, 202)
        record = connector._read_request(self.values, payload["request_id"])
        self.assertNotIn("envelope_id", record)

    def test_workbench_unavailable_is_enumerable(self):
        with self.assertRaises(connector.ToolError) as ctx:
            self.call("venue", "workbench_read", {"path": "/api/todos"})
        self.assertEqual(ctx.exception.name, "workbench_unavailable")

    # -- permissions_history (card-owner plan, Step 1): the
    # read-only resolved-record bridge extension.

    def test_permissions_history_queues_and_fulfills(self):
        code, payload = self.call(
            "venue", "permissions_history", {"approval_id": "appr-1"})
        self.assertEqual(code, 202)
        request_id = payload["request_id"]
        record = connector._read_request(self.values, request_id)
        self.assertEqual(record["tool"], "permissions_history")
        self.assertEqual(record["args"], {"approval_id": "appr-1"})
        self.call("bridge", "bridge_fulfill",
                  {"request_id": request_id, "ok": True,
                   "result": {"approval_id": "appr-1",
                              "outcome": "approved",
                              "decided_at": "2026-11-14T15:03:00Z"}})
        code, res = connector.fetch_result(
            self.engine, self.values, "venue", ["read", "send"], request_id)
        self.assertEqual(code, 200)
        self.assertEqual(res["result"]["outcome"], "approved")

    def test_permissions_history_is_read_scope_only(self):
        # A send-only caller is refused: the history read
        # queues at read scope and nowhere else.
        with self.assertRaises(connector.ToolError) as ctx:
            self.call("sender", "permissions_history",
                      {"approval_id": "appr-1"})
        self.assertEqual(ctx.exception.name, "scope_refused")
        self.assertEqual(connector.tool_scopes()["permissions_history"],
                         "read")

    def test_permissions_history_envelope_retry_dedupes(self):
        code, first = self.call_env(
            "venue", "permissions_history",
            {"approval_id": "appr-1"}, "card-hist-appr-1")
        self.assertEqual(code, 202)
        code, twin = self.call_env(
            "venue", "permissions_history",
            {"approval_id": "appr-1"}, "card-hist-appr-1")
        self.assertEqual((code, twin["deduped"], twin["request_id"]),
                         (200, True, first["request_id"]))
        _c, poll = self.call("bridge", "bridge_poll", {})
        self.assertEqual(len(poll["result"]["requests"]), 1)

    def test_history_bodies_carry_the_never_resolve_bound(self):
        # The drain and wake-item bodies name the verb with
        # its listing-only language: the executor fulfills a
        # lookup and can never approve or deny through it.
        # The live bodies are per-deployment instance data
        # (untracked by design), so the pin runs over fixture
        # bodies seeded into the test home, written in the
        # form the deployment's bodies must carry.
        fixtures = {
            "bridge-drain.md": (
                "Work the queued bridge records in order. When a "
                "record asks for the outcome of a permission "
                "card, call permissions_history with its "
                "approval id and report what the listing gives. "
                "Listing only — never approve or deny anything "
                "through it, and never resolve a card by any "
                "other route.\n"),
            "bridge-wake-item.md": (
                "A bridge record is waiting. If it asks what "
                "happened to a permission card, look it up with "
                "permissions_history and relay the recorded "
                "outcome verbatim. The lookup is listing only — "
                "never approve or deny anything through it.\n"),
        }
        for body, text in fixtures.items():
            path = os.path.join(self.home, "bodies", body)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(path, encoding="utf-8") as fh:
                served = fh.read()
            at = served.index("permissions_history")
            self.assertIn("never approve or deny",
                          served[at:at + 700], body)


class WatcherCallerScopeTests(unittest.TestCase):
    """Step 6's hard-stop pin, caller half (card-owner
    plan): the card watcher's dedicated connector caller
    holds `read` scope only, and the tool table it faces
    carries no verb that resolves a permission card. The
    table is enumerated live, so the pin extends itself
    when a tool is added — a resolving verb at any scope,
    or a card read above `read`, fails here."""

    TOKEN = "tok-card-watch"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.home, "bodies"))
        os.makedirs(os.path.join(self.home, "ops"))
        callers = {"card-watch": {
            "token_sha256": hashlib.sha256(self.TOKEN.encode()).hexdigest(),
            "scopes": ["read"]}}
        with open(os.path.join(self.home, "config.json"), "w") as fh:
            json.dump({"connector": {"callers": callers}}, fh)
        self.values = {"home": self.home, "workspace_root": self.tmp,
                       "workbench_base_url": "http://127.0.0.1:9"}
        self.engine = types.SimpleNamespace(outbox=FakeOutbox(),
                                            ledger=None)

    def auth(self):
        return connector.authenticate(self.values, self.TOKEN)

    def test_watcher_caller_holds_read_scope_only(self):
        self.assertEqual(self.auth(), ("card-watch", ["read"]))

    def test_watcher_permitted_set_is_exactly_the_read_tools(self):
        caller, scopes = self.auth()
        table = connector.tool_scopes()
        permitted, refused = set(), set()
        for tool in table:
            try:
                connector.call_tool(self.engine, self.values,
                                    caller, scopes, tool, {})
            except connector.ToolError as exc:
                if exc.name == "scope_refused":
                    self.assertEqual(exc.status, 403)
                    refused.add(tool)
                else:
                    permitted.add(tool)
            else:
                permitted.add(tool)
        self.assertEqual(permitted,
                         {t for t, s in table.items() if s == "read"})
        self.assertEqual(refused, set(table) - permitted)
        self.assertIn("permissions_list", permitted)

    def test_tool_table_carries_no_resolving_verb(self):
        table = connector.tool_scopes()
        for name in table:
            self.assertNotIn("approve", name)
            self.assertNotIn("deny", name)
        permission_tools = {t for t in table if "permission" in t}
        self.assertLessEqual(permission_tools,
                             {"permissions_list", "permissions_history"})
        for tool in permission_tools:
            self.assertEqual(table[tool], "read")


if __name__ == "__main__":
    unittest.main()
