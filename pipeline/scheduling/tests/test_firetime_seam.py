"""The fire-time config seam (contract 09): a config block's
saved knobs reach the fired job's environment.

Covered by layer:
- the mapping's declaration — a knob's optional `env` field,
  validated beside the block schema in registry.py, served
  beside the value by configblocks.view_of, and preserved by
  the guarded save's block rewrite;
- the resolver — registry.config_env maps a block to exactly
  the declared variables, and to {} for an entry with no
  block or no declared variable (such an entry fires with
  exactly today's environment);
- the delivery — executor._build_env applies the mapping
  over the inherited environment, and an engine fire carries
  a value saved after the previous fire, with no restart;
- the consumption — ops/watches/storage_watch.py reads its home
  tiers from the variables the landed storage-watch block
  declares, falling back to the compiled constants when
  they are absent: the watch's verdict flips at the saved
  threshold, not the compiled one.
"""
import importlib.util
import io
import os
import shutil
import tempfile
import unittest
from collections import namedtuple
from contextlib import redirect_stdout
from unittest import mock

from server import registry
from server.entries import configblocks
from server.firing import executor
from server.firing.engine import Engine
from tests.helpers import (T0, Clock, make_home, scripted_yaml,
                           seed_tracked_fleet, write_entry, write_script)

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GB = 1024 ** 3
MB = 1024 ** 2

SPEC = importlib.util.spec_from_file_location(
    "storage_watch_firetime", os.path.join(PKG_ROOT, "ops", "watches", "storage_watch.py")
)
sw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sw)

Usage = namedtuple("usage", "total used free")

BLOCK_WITH_ENV = (
    "config:\n"
    "  version: 1\n"
    "  knobs:\n"
    "    home_low_free_gb:\n"
    "      label: Low tier\n"
    "      type: integer\n"
    "      unit: GB\n"
    "      value: 50\n"
    "      min: 1\n"
    "      max: 500\n"
    "      env: STORAGE_WATCH_HOME_LOW_GB\n"
    "    home_critical_free_gb:\n"
    "      label: Critical tier\n"
    "      type: integer\n"
    "      unit: GB\n"
    "      value: 45\n"
    "      min: 1\n"
    "      max: 500\n"
    "      env: STORAGE_WATCH_HOME_CRIT_GB\n"
    "  constraints:\n"
    "    critical_below_low:\n"
    "      kind: lt\n"
    "      left: home_critical_free_gb\n"
    "      right: home_low_free_gb\n"
    "      message: The critical tier must sit below the low tier.\n"
)


class DeclarationTests(unittest.TestCase):
    def _load(self, tmp, extra):
        values, _sources = make_home(tmp)
        write_entry(tmp, "job-cfg",
                    scripted_yaml("job-cfg", "/bin/true", extra=extra))
        return registry.load_dir(os.path.join(tmp, "jobs"), values["home"])

    def test_knob_with_env_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries, errors = self._load(tmp, BLOCK_WITH_ENV)
            self.assertEqual(errors, [])
            self.assertIn("job-cfg", entries)

    def test_bad_env_name_rejected(self):
        bad = BLOCK_WITH_ENV.replace("STORAGE_WATCH_HOME_LOW_GB",
                                     "not-an-env-name")
        with tempfile.TemporaryDirectory() as tmp:
            _entries, errors = self._load(tmp, bad)
            self.assertTrue(any("env" in e for e in errors), errors)

    def _landed_entries(self):
        # The tracked fleet, seeded into a fixture home (the
        # bodies its entries reference are instance data and
        # are stubbed by the seed) — never the live registry.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        seed_tracked_fleet(tmp, PKG_ROOT)
        return registry.load_dir(os.path.join(tmp, "jobs"), tmp)

    def test_landed_blocks_declare_the_scripts_variables(self):
        entries, errors = self._landed_entries()
        self.assertEqual(errors, [])
        self.assertEqual(
            registry.config_env(entries["storage-watch"]),
            {"STORAGE_WATCH_HOME_LOW_GB": "50",
             "STORAGE_WATCH_HOME_CRIT_GB": "45"})
        self.assertEqual(
            registry.config_env(entries["memory-index-watchdog"]),
            {"SCHEDULER_TOPIC_FILE_MAX_BYTES": "40960",
             "SCHEDULER_TOPIC_PER_FILE_BYTES": "12800"})

    def test_served_view_carries_env_beside_the_value(self):
        entries, _errors = self._landed_entries()
        view = configblocks.view_of(entries["storage-watch"])
        by_key = {k["key"]: k for k in view["knobs"]}
        self.assertEqual(by_key["home_low_free_gb"]["env"],
                         "STORAGE_WATCH_HOME_LOW_GB")
        self.assertEqual(by_key["home_critical_free_gb"]["env"],
                         "STORAGE_WATCH_HOME_CRIT_GB")


class ResolverTests(unittest.TestCase):
    def _entry(self, tmp, extra=""):
        values, _sources = make_home(tmp)
        write_entry(tmp, "job-x",
                    scripted_yaml("job-x", "/bin/true", extra=extra))
        entries, errors = registry.load_dir(os.path.join(tmp, "jobs"),
                                            values["home"])
        self.assertEqual(errors, [])
        return entries["job-x"]

    def test_no_block_maps_to_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(registry.config_env(self._entry(tmp)), {})

    def test_block_without_env_maps_to_nothing(self):
        block = BLOCK_WITH_ENV.replace("      env: STORAGE_WATCH_HOME_LOW_GB\n", "") \
                              .replace("      env: STORAGE_WATCH_HOME_CRIT_GB\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(tmp, block)
            self.assertEqual(registry.config_env(entry), {})

    def test_values_render_as_the_script_reads_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(tmp, BLOCK_WITH_ENV)
            self.assertEqual(registry.config_env(entry),
                             {"STORAGE_WATCH_HOME_LOW_GB": "50",
                              "STORAGE_WATCH_HOME_CRIT_GB": "45"})


class BuildEnvTests(unittest.TestCase):
    def _entry(self, tmp, extra="", run_extra=""):
        text = scripted_yaml("job-x", "/bin/true", extra=extra)
        if run_extra:
            text = text.replace("    - /bin/true\n", "    - /bin/true\n" + run_extra)
        values, _sources = make_home(tmp)
        write_entry(tmp, "job-x", text)
        entries, errors = registry.load_dir(os.path.join(tmp, "jobs"),
                                            values["home"])
        self.assertEqual(errors, [])
        return entries["job-x"]

    def test_no_block_entry_fires_with_todays_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(tmp)
            with mock.patch.dict(os.environ, {"FIRETIME_SENTINEL": "x"}):
                self.assertEqual(executor._build_env(entry),
                                 dict(os.environ))

    def test_config_wins_over_the_inherited_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(tmp, BLOCK_WITH_ENV)
            with mock.patch.dict(
                    os.environ, {"STORAGE_WATCH_HOME_LOW_GB": "999"}):
                env = executor._build_env(entry)
            self.assertEqual(env["STORAGE_WATCH_HOME_LOW_GB"], "50")
            self.assertEqual(env["STORAGE_WATCH_HOME_CRIT_GB"], "45")


class SavePreservesMappingTests(unittest.TestCase):
    def test_save_rewrite_keeps_env_and_the_new_value_resolves(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        values, _sources = make_home(tmp)
        write_entry(tmp, "job-cfg",
                    scripted_yaml("job-cfg", "/bin/true",
                                  extra=BLOCK_WITH_ENV))
        engine = Engine(values, now_fn=Clock(T0), inline=True)
        code, payload = configblocks.save_config(
            engine, "job-cfg", 1, {"home_low_free_gb": 60}, "test")
        self.assertEqual(code, 200, payload)
        with open(os.path.join(tmp, "jobs", "job-cfg.yaml"),
                  encoding="utf-8") as fh:
            self.assertIn("env: STORAGE_WATCH_HOME_LOW_GB", fh.read())
        entries, errors = registry.load_dir(os.path.join(tmp, "jobs"),
                                            values["home"])
        self.assertEqual(errors, [])
        self.assertEqual(
            registry.config_env(entries["job-cfg"])
            ["STORAGE_WATCH_HOME_LOW_GB"], "60")


class StorageWatchTierTests(unittest.TestCase):
    def test_absent_variable_is_the_compiled_constant(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(sw.home_tier_bytes(sw.HOME_LOW_ENV, sw.HOME_LOW),
                             50 * GB)
            self.assertEqual(sw.home_tier_bytes(sw.HOME_CRIT_ENV, sw.HOME_CRIT),
                             45 * GB)

    def test_present_variable_governs_and_garbage_falls_back(self):
        with mock.patch.dict(os.environ, {sw.HOME_LOW_ENV: "70"}):
            self.assertEqual(sw.home_tier_bytes(sw.HOME_LOW_ENV, sw.HOME_LOW),
                             70 * GB)
        with mock.patch.dict(os.environ, {sw.HOME_LOW_ENV: "soon"}):
            self.assertEqual(sw.home_tier_bytes(sw.HOME_LOW_ENV, sw.HOME_LOW),
                             50 * GB)

    def test_default_labels_are_byte_identical(self):
        self.assertEqual(sw.gb_label(50 * GB), "50 GB")
        self.assertEqual(sw.gb_label(45 * GB), "45 GB")
        self.assertEqual(sw.gb_label(70 * GB), "70 GB")


class StorageWatchVerdictTests(unittest.TestCase):
    """Behavioral: the same free-space drop is silent under the
    compiled tiers and a LOW report under the saved tiers the
    engine would deliver (low 70 / critical 55 GB)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.frees = {"/fakehome": 80 * GB, "/faketmp": 512 * MB}
        self.env = {
            "STORAGE_WATCH_STATE_DIR": os.path.join(self.tmp, "state"),
            "STORAGE_WATCH_HOME_PATH": "/fakehome",
            "STORAGE_WATCH_TMP_PATH": "/faketmp",
            "STORAGE_WATCH_STORES": "",
        }

    def run_watch(self, extra_env=None):
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        def fake_usage(path):
            free = self.frees[path]
            return Usage(total=free * 2, used=free, free=free)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(shutil, "disk_usage", fake_usage):
                with redirect_stdout(buf):
                    rc = sw.main()
        return rc, buf.getvalue()

    def test_drop_crosses_only_at_the_saved_threshold(self):
        saved = {"STORAGE_WATCH_HOME_LOW_GB": "70",
                 "STORAGE_WATCH_HOME_CRIT_GB": "55"}
        # Baseline adoption at 80 GB free under both tier sets.
        self.assertEqual(self.run_watch()[1], "")
        self.assertEqual(self.run_watch(saved)[1], "")
        # Drop to 60 GB: healthy under the compiled 50/45 tiers…
        self.frees["/fakehome"] = 60 * GB
        rc, out = self.run_watch()
        self.assertEqual((rc, out), (0, ""))
        # …but below the saved low tier — the verdict flips at
        # the saved threshold, and the report names it.
        rc, out = self.run_watch(saved)
        self.assertEqual(rc, 0)
        self.assertIn("STORAGE LOW", out)
        self.assertIn("below the 70 GB low threshold", out)


class EngineFireTests(unittest.TestCase):
    """End-to-end through a real engine fire of the real
    storage_watch.py: a config saved between two fires of the
    same engine instance governs the second fire — the drop
    that was healthy under the entry's starting tiers reports
    CRITICAL at the saved ones, with no restart anywhere."""

    def test_saved_tiers_govern_the_next_fire(self):
        root = tempfile.mkdtemp(dir=os.path.expanduser("~"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        values, _sources = make_home(root)
        clock = Clock(T0)
        shutil.copy(os.path.join(PKG_ROOT, "ops", "watches", "storage_watch.py"),
                    os.path.join(root, "storage_watch.py"))
        shutil.copy(os.path.join(PKG_ROOT, "ops", "paths.py"),
                    os.path.join(root, "paths.py"))
        # The fired watch's free-space reading enters as a
        # fixture through its env seam (STORAGE_WATCH_FREE_BYTES),
        # never from the host's disk: 450 GB is the regime a live
        # reading cannot calibrate against (the knob ceiling is
        # 500), and the tiers below straddle the fixture on both
        # sides — starting tiers below it, saved tiers above it.
        free_gb = 450
        low0, crit0 = free_gb - 5, free_gb - 10
        block = (
            "config:\n"
            "  version: 1\n"
            "  knobs:\n"
            "    home_low_free_gb:\n"
            "      label: Low tier\n"
            "      type: integer\n"
            "      unit: GB\n"
            f"      value: {low0}\n"
            "      min: 1\n"
            "      max: 500\n"
            "      env: STORAGE_WATCH_HOME_LOW_GB\n"
            "    home_critical_free_gb:\n"
            "      label: Critical tier\n"
            "      type: integer\n"
            "      unit: GB\n"
            f"      value: {crit0}\n"
            "      min: 1\n"
            "      max: 500\n"
            "      env: STORAGE_WATCH_HOME_CRIT_GB\n"
            "  constraints:\n"
            "    critical_below_low:\n"
            "      kind: lt\n"
            "      left: home_critical_free_gb\n"
            "      right: home_low_free_gb\n"
            "      message: The critical tier must sit below the low tier.\n"
        )
        script = os.path.join(root, "storage_watch.py")
        write_entry(root, "storage-fixture",
                    scripted_yaml("storage-fixture", script,
                                  report="  when: on_output\n",
                                  extra=block))
        env = {
            "STORAGE_WATCH_STATE_DIR": os.path.join(root, "watch-state"),
            "STORAGE_WATCH_HOME_PATH": root,
            "STORAGE_WATCH_TMP_PATH": root,
            "STORAGE_WATCH_STORES": "",
            "STORAGE_WATCH_FREE_BYTES": str(free_gb * GB),
            "STORAGE_WATCH_TRASH_DIR": os.path.join(root, "trash"),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            engine = Engine(values, now_fn=clock, inline=True)
            clock.advance(minutes=6)
            engine.tick()
            runs = engine.ledger.query(job_id="storage-fixture",
                                       kinds=["run"])
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["status"], "ok")
            self.assertNotIn("STORAGE", runs[0]["stdout_tail"])
            # Save tiers above the actual free space, then fire
            # the same engine again: the saved critical tier is
            # what the run crosses.
            low1, crit1 = free_gb + 20, free_gb + 10
            code, payload = configblocks.save_config(
                engine, "storage-fixture", 1,
                {"home_low_free_gb": low1, "home_critical_free_gb": crit1},
                "test")
            self.assertEqual(code, 200, payload)
            clock.advance(minutes=6)
            engine.tick()
        runs = engine.ledger.query(job_id="storage-fixture", kinds=["run"])
        self.assertEqual(len(runs), 2)
        self.assertIn("STORAGE CRITICAL", runs[0]["stdout_tail"])
        self.assertIn(f"below the {crit1} GB critical threshold",
                      runs[0]["stdout_tail"])
        reports = [p for p in engine.outbox.pending()
                   if p["job_id"] == "storage-fixture"
                   and p["kind"] == "report"]
        self.assertEqual(len(reports), 1)


class MemoryWatchdogDeliveryTests(unittest.TestCase):
    """The memory watchdog's record side: its block declares
    the variables its check script already takes, and a fire
    delivers the saved values to the process."""

    def test_fire_delivers_the_saved_topic_thresholds(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        values, _sources = make_home(tmp)
        clock = Clock(T0)
        marker = os.path.join(tmp, "seen.txt")
        script = write_script(
            tmp, "probe.py",
            "import os\n"
            f"open({marker!r}, 'w').write("
            "os.environ.get('SCHEDULER_TOPIC_FILE_MAX_BYTES', '<absent>')"
            " + ' ' + os.environ.get('SCHEDULER_TOPIC_PER_FILE_BYTES',"
            " '<absent>'))\n")
        block = (
            "config:\n"
            "  version: 1\n"
            "  knobs:\n"
            "    topic_file_max_bytes:\n"
            "      label: Topic file cap\n"
            "      type: integer\n"
            "      unit: bytes\n"
            "      value: 40960\n"
            "      min: 1024\n"
            "      max: 1048576\n"
            "      env: SCHEDULER_TOPIC_FILE_MAX_BYTES\n"
            "    topic_per_file_bytes:\n"
            "      label: Topic set register\n"
            "      type: integer\n"
            "      unit: bytes\n"
            "      value: 12800\n"
            "      min: 128\n"
            "      max: 1048576\n"
            "      env: SCHEDULER_TOPIC_PER_FILE_BYTES\n"
        )
        write_entry(tmp, "memory-fixture",
                    scripted_yaml("memory-fixture", script, extra=block))
        engine = Engine(values, now_fn=clock, inline=True)
        clock.advance(minutes=6)
        engine.tick()
        with open(marker, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "40960 12800")


if __name__ == "__main__":
    unittest.main()
