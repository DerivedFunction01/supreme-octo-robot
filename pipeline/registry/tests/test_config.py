"""The unified config contract (plan §4.4) as this
package applies it: env > live > defaults, per-key source
reporting."""

import unittest

from registry import config


class ConfigTests(unittest.TestCase):
    def test_defaults_when_nothing_speaks(self):
        values, sources = config.resolve_config(live={}, env={})
        self.assertEqual(sources, {"store_path": "default",
                                   "claims_journal": "default"})
        self.assertTrue(str(values["store_path"]).endswith(
            "var/registry.json"))

    def test_live_beats_default(self):
        values, sources = config.resolve_config(
            live={"store_path": "elsewhere/store.json"}, env={})
        self.assertEqual(sources["store_path"], "live")
        self.assertTrue(str(values["store_path"]).endswith(
            "elsewhere/store.json"))
        self.assertEqual(sources["claims_journal"], "default")

    def test_env_beats_live(self):
        values, sources = config.resolve_config(
            live={"store_path": "elsewhere/store.json"},
            env={"PIPELINE_REGISTRY_STORE": "/abs/store.json"})
        self.assertEqual(sources["store_path"], "env")
        self.assertEqual(str(values["store_path"]), "/abs/store.json")


if __name__ == "__main__":
    unittest.main()
