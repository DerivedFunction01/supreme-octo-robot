"""The card-watch cadence groundwork (permission-card plan,
Step 5): the registry entry's form, the dedicated caller's
provisioning shape, and the scope-refusal pin — the caller
holds read scope only, reads the card sources, and every
resolving or mutating attempt is refused before performing.

Deterministic throughout: fixture tokens in temp homes, the
shipped fake bridge transport and fake clock for the source
seam, injected core runners for the exit alphabet. No live
server, no wall clock, no timing assertions."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.connector_token import apply_mint  # noqa: E402
from ops.watches import card_watch  # noqa: E402
from server import registry  # noqa: E402
from server.serving import connector  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY_PATH = os.path.join(ROOT, "jobs", "card-watch.yaml")
FIXTURE_TOKEN = "fixture-token-for-the-card-watch-caller"


class EntryFormTest(unittest.TestCase):
    def _load_entry(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        jobs = os.path.join(tmp, "jobs")
        os.makedirs(jobs)
        with open(ENTRY_PATH, encoding="utf-8") as fh:
            text = fh.read()
        with open(os.path.join(jobs, "card-watch.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(text)
        entries, errors = registry.load_dir(jobs, ROOT)
        self.assertEqual(errors, [])
        return entries["card-watch"]

    def test_entry_validates_in_the_registry_form(self):
        entry = self._load_entry()
        self.assertEqual(entry.kind, "scripted")
        self.assertEqual(entry.status, "active")
        self.assertEqual(entry.cadence, {"type": "interval", "every": "15m"})
        self.assertEqual(entry.data["owner"], "none")

    def test_entry_argv_targets_the_adapter(self):
        entry = self._load_entry()
        argv = entry.data["run"]["argv"]
        self.assertEqual(argv[0], "python3")
        self.assertEqual(argv[1], os.path.join(
            ROOT, "ops", "watches", "card_watch.py"))
        self.assertTrue(os.path.isfile(argv[1]))

    def test_entry_exit_alphabet_and_defect_pattern(self):
        entry = self._load_entry()
        report = entry.report
        self.assertEqual(report["ok_exit_codes"], [0, 3, 4])
        self.assertIn(card_watch.DEFECT_MARKER, report["fail_patterns"])
        self.assertEqual(
            set(card_watch.OUTCOME_EXIT_CODES.values()), {0, 3, 4})

    def test_entry_state_paths_name_the_bridge_and_token_file(self):
        entry = self._load_entry()
        joined = " ".join(entry.data["state_paths"])
        self.assertIn("connector-bridge", joined)
        self.assertIn("card-watch.token", joined)


class CallerProvisioningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.values = {"home": self.tmp,
                       "workspace_root": os.path.join(self.tmp, "ws")}

    def _write_config(self, config):
        with open(os.path.join(self.tmp, "config.json"), "w") as fh:
            json.dump(config, fh)

    def test_provisioning_shape_is_read_only_and_secret_free(self):
        spec = card_watch.caller_provisioning()
        self.assertEqual(spec["name"], "card-watch")
        self.assertEqual(spec["scopes"], ["read"])
        self.assertEqual(spec["source_tools"],
                         ["permissions_list", "permissions_history"])
        self.assertIn("connector-token", spec["mint_argv"])
        self.assertIn("card-watch", spec["mint_argv"])
        blob = json.dumps(spec)
        self.assertNotIn("token_sha256", blob)
        self.assertNotIn(FIXTURE_TOKEN, blob)

    def test_mint_with_the_provisioning_shape_authenticates(self):
        spec = card_watch.caller_provisioning()
        config = {}
        token = apply_mint(config, spec["name"], spec["scopes"])
        self._write_config(config)
        self.assertEqual(connector.authenticate(self.values, token),
                         ("card-watch", ["read"]))
        summary = connector.health_summary(self.values)
        self.assertEqual(summary, {"callers": {"card-watch": ["read"]}})

    def test_token_file_resolution_forms(self):
        token_file = os.path.join(self.tmp, "card-watch.token")
        with open(token_file, "w", encoding="utf-8") as fh:
            fh.write(FIXTURE_TOKEN + "\n")
        env = {card_watch.TOKEN_FILE_ENV: token_file}
        self.assertEqual(card_watch.token_file_path(env), token_file)
        self.assertEqual(card_watch.read_token(env), FIXTURE_TOKEN)

    def test_token_home_form_and_absence(self):
        home = os.path.join(self.tmp, "ops-tokens")
        os.makedirs(home)
        with open(os.path.join(home, "card-watch.token"), "w",
                  encoding="utf-8") as fh:
            fh.write(FIXTURE_TOKEN)
        env = {card_watch.TOKEN_DIR_ENV: home}
        self.assertEqual(card_watch.read_token(env), FIXTURE_TOKEN)
        self.assertIsNone(card_watch.read_token(
            {card_watch.TOKEN_DIR_ENV: os.path.join(self.tmp, "empty")}))


class ScopeRefusalTest(unittest.TestCase):
    """The hard-stop pin: authenticated as the card-watch
    caller, the card source read performs; everything that
    would resolve, send, mutate, or fulfill is refused
    before performing — and nothing but the one read ever
    reaches the bridge queue."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = os.path.join(self.tmp, "repo")
        os.makedirs(self.home)
        digest = hashlib.sha256(FIXTURE_TOKEN.encode()).hexdigest()
        callers = {"card-watch": {"token_sha256": digest,
                                  "scopes": ["read"]}}
        with open(os.path.join(self.home, "config.json"), "w") as fh:
            json.dump({"connector": {"callers": callers}}, fh)
        self.values = {"home": self.home,
                       "workspace_root": os.path.join(self.tmp, "ws")}
        self.engine = types.SimpleNamespace(outbox=None, ledger=None)
        auth = connector.authenticate(self.values, FIXTURE_TOKEN)
        self.assertEqual(auth, ("card-watch", ["read"]))
        self.caller, self.scopes = auth

    def call(self, tool, args=None):
        return connector.call_tool(
            self.engine, self.values, self.caller, self.scopes,
            tool, args or {})

    def test_card_source_read_performs(self):
        code, payload = self.call("permissions_list")
        self.assertEqual(code, 202)
        self.assertEqual(payload["status"], "queued")
        record = connector._read_request(self.values, payload["request_id"])
        self.assertEqual(record["tool"], "permissions_list")
        self.assertEqual(record["caller"], "card-watch")

    def test_history_read_is_read_scoped_when_the_extension_lands(self):
        # Step 1's bridge extension: the moment the tool
        # exists on the surface, the provisioning already
        # covers it — at read scope, like the list read.
        scopes = connector.tool_scopes()
        if "permissions_history" in scopes:
            self.assertEqual(scopes["permissions_history"], "read")
        self.assertIn("permissions_history",
                      card_watch.caller_provisioning()["source_tools"])

    def test_every_non_read_tool_is_scope_refused(self):
        for tool, args in (
                ("chat_send", {"chat_id": "chat-fixture", "text": "x"}),
                ("ping_ack", {"ping_id": "p1"}),
                ("bridge_poll", {}),
                ("bridge_fulfill", {"request_id": "r1", "ok": True})):
            with self.assertRaises(connector.ToolError) as ctx:
                self.call(tool, args)
            self.assertEqual(ctx.exception.name, "scope_refused", tool)
            self.assertEqual(ctx.exception.status, 403, tool)

    def test_approve_and_deny_do_not_exist_on_the_surface(self):
        for tool in ("approve_permission", "deny_permission",
                     "permission_approve", "permission_deny"):
            with self.assertRaises(connector.ToolError) as ctx:
                self.call(tool, {"approval_id": "appr-fixture-001"})
            self.assertEqual(ctx.exception.name, "unknown_tool", tool)

    def test_refusals_performed_nothing(self):
        _code, payload = self.call("permissions_list")
        for tool in ("chat_send", "ping_ack", "bridge_poll",
                     "approve_permission", "deny_permission"):
            with self.assertRaises(connector.ToolError):
                self.call(tool, {"chat_id": "c", "text": "x",
                                 "ping_id": "p1",
                                 "approval_id": "appr-fixture-001"})
        bridge_dir = connector._bridge_dir(self.values)
        queued = [name for name in os.listdir(bridge_dir)
                  if name.endswith(".json")]
        self.assertEqual(len(queued), 1)
        record = connector._read_request(self.values, payload["request_id"])
        self.assertEqual(record["tool"], "permissions_list")


class AdapterPassTest(unittest.TestCase):
    def test_source_seam_over_the_fake_bridge_and_clock(self):
        from registry.cards import cardwatch_fakes as fakes

        transport = fakes.FakeBridgeTransport().script(
            "permissions_list", {"cards": list(fakes.RAW_PENDING)})
        source = card_watch.build_source(
            transport=transport, clock=fakes.FakeClock())
        snap = source.pending_snapshot()
        self.assertEqual(snap.taken_at, fakes.SEED_NOW)
        self.assertEqual([c.approval_id for c in snap.cards],
                         ["appr-fixture-001", "appr-fixture-002"])

    def test_outcome_mapping(self):
        source = object()
        self.assertEqual(
            card_watch.run_once(source, lambda s, now: "pass_complete", "t"),
            (0, None))
        self.assertEqual(
            card_watch.run_once(source, lambda s, now: "source_stale", "t"),
            (3, None))
        self.assertEqual(
            card_watch.run_once(
                source,
                lambda s, now: {"outcome": "partial_history",
                                "line": "CARD_WATCH_PARTIAL appr-1"},
                "t"),
            (4, "CARD_WATCH_PARTIAL appr-1"))

    def test_missing_core_is_a_loud_defect_not_a_pass(self):
        code, line = card_watch.run_once(object(), None, "t")
        self.assertEqual(code, card_watch.EXIT_CORE_UNAVAILABLE)
        self.assertIn("CARD_WATCH_CORE_UNAVAILABLE", line)

    def test_unknown_outcome_is_a_core_contract_defect(self):
        code, line = card_watch.run_once(
            object(), lambda s, now: "everything_is_fine", "t")
        self.assertEqual(code, card_watch.EXIT_CORE_UNAVAILABLE)
        self.assertIn(card_watch.DEFECT_MARKER, line)

    def test_main_maps_and_speaks_through_the_fake_clock(self):
        from registry.cards import cardwatch_fakes as fakes

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = card_watch.main(
                source=object(),
                core_runner=lambda s, now: {"outcome": "source_stale",
                                            "line": "CARD_WATCH_DEFECT: stale"},
                clock=fakes.FakeClock())
        self.assertEqual(code, 3)
        self.assertEqual(out.getvalue().strip(), "CARD_WATCH_DEFECT: stale")


if __name__ == "__main__":
    unittest.main()
