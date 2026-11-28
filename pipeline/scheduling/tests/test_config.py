import json
import os
import tempfile
import threading
import unittest
import urllib.request

from server import config as config_mod
from server.firing.engine import Engine
from server.serving.http import make_server
from tests.helpers import T0, Clock, agent_yaml, make_home, write_body, write_entry


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _resolve(self, file_text=None, env=None):
        path = os.path.join(self.tmp, "config.json")
        if file_text is not None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(file_text)
        return config_mod.resolve(path, env=env or {})

    def test_defaults(self):
        values, sources = self._resolve("{}")
        self.assertEqual(values["port"], 8796)
        self.assertEqual(values["tick_secs"], 20)
        self.assertEqual(values["default_timezone"], "UTC")
        self.assertEqual(values["outbox_ack_timeout_secs"], 3600)
        self.assertEqual(values["ledger_retention_days"], 90)
        self.assertEqual(values["capture_cap_bytes"], 65536)
        self.assertEqual(values["home"], self.tmp)
        self.assertTrue(all(s == "default" for s in sources.values()))

    def test_file_layer(self):
        values, sources = self._resolve('{"port": 9001}')
        self.assertEqual(values["port"], 9001)
        self.assertEqual(sources["port"], "config")
        self.assertEqual(sources["tick_secs"], "default")

    def test_env_beats_file(self):
        values, sources = self._resolve('{"port": 9001}', env={"SCHEDULER_PORT": "9002"})
        self.assertEqual(values["port"], 9002)
        self.assertEqual(sources["port"], "env")

    def test_unknown_key_rejected(self):
        with self.assertRaises(config_mod.ConfigError):
            self._resolve('{"bogus": 1}')

    def test_shipped_example_resolves_through_the_file_layer(self):
        # The example is the live config's shape of record
        # (contract 04): it must validate, and its keys must
        # land from the file layer — never silently coincide
        # with defaults.
        values, sources = config_mod.resolve(
            config_mod.example_config_path(), env={})
        self.assertEqual(values["port"], 8796)
        self.assertEqual(sources["port"], "config")
        self.assertEqual(values["connector"], {"callers": {}})

    def test_require_live_config_refuses_absence(self):
        absent = os.path.join(self.tmp, "config.json")
        with self.assertRaises(config_mod.ConfigError) as ctx:
            config_mod.require_live_config(absent)
        self.assertIn("live config absent", str(ctx.exception))
        with open(absent, "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        self.assertEqual(config_mod.require_live_config(absent), absent)

    def test_server_main_refuses_to_start_without_a_live_config(self):
        import io
        from contextlib import redirect_stderr
        from server.main import main
        absent = os.path.join(self.tmp, "config.json")
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(["--config", absent])
        self.assertEqual(rc, 2)
        self.assertIn("live config absent", err.getvalue())


class HealthTests(unittest.TestCase):
    def test_health_reports_config_sources_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            values, sources = make_home(tmp)
            write_body(tmp, "agent-a")
            write_entry(tmp, "agent-a", agent_yaml("agent-a"))
            engine = Engine(values, now_fn=Clock(T0), inline=True)
            server = make_server(engine, values, sources, host="127.0.0.1", port=0)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
                    health = json.loads(resp.read())
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/pings", timeout=5) as resp:
                    pings = json.loads(resp.read())
            finally:
                server.shutdown()
                server.server_close()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["registry_count"], 1)
        self.assertEqual(health["outbox_depth"], 0)
        self.assertEqual(health["config"]["port"], {"value": 8796, "source": "default"})
        self.assertEqual(health["config"]["default_timezone"]["value"], "UTC")
        self.assertEqual(pings, {"pings": []})


if __name__ == "__main__":
    unittest.main()
