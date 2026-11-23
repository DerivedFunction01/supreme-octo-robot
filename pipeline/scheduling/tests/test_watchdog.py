"""Suite coverage for the watchdog restore ladder (survival
pattern contract v1, rung 11): the ladder runs against a fake
systemctl and a fake curl, both steered by flag files, inside a
scratch root built from the repo's real watchdog + template.

Covered by name: presence-before-health quiet reinstall (rung 3),
render-when-invalid in the healthy branch (rung 4), the load-state
repair verb — start when not loaded, restart when loaded (rung 6),
the fresh-restore path for a missing unit (rung 7), and the
one-attempt episode cap (rung 8 / EC-13). The flap regression
is covered too: a failed/denied render classifies the
unit unknown — never stale — so no reinstall is attempted against
a healthy unit and the watchdog exits 0 while the server is up.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT_NAME = "scheduler-server.service"

FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_SYSTEMCTL_LOG"
case "$1" in
  daemon-reload) exit 0 ;;
  show) cat "$FAKE_LOAD_STATE_FILE" ;;
  start|restart)
    if [[ -z "${FAKE_NO_RECOVER:-}" ]]; then
      echo 1 > "$FAKE_HEALTH_FILE"
    fi
    exit 0 ;;
esac
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
if [[ "$(cat "$FAKE_HEALTH_FILE" 2>/dev/null)" == "1" ]]; then
  echo '{"status": "ok"}'
  exit 0
fi
exit 7
"""

# A render whose flush is denied: partial output, then failure —
# the write-denial flap's signature on the old landing-render path.
FAILING_SED = """#!/usr/bin/env bash
echo "partial render, flush denied"
exit 1
"""


class WatchdogCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="watchdog-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.root, "ops", "server-care"))
        for name in ("watchdog.sh", "scheduler-server.service.tmpl"):
            shutil.copy(os.path.join(REPO, "ops", "server-care", name),
                        os.path.join(self.root, "ops", "server-care", name))
        shutil.copy(os.path.join(REPO, "ops", "paths.sh"),
                    os.path.join(self.root, "ops", "paths.sh"))
        with open(os.path.join(self.root, "config.json"), "w") as fh:
            fh.write('{"port": 8796}')
        self.unit_dir = os.path.join(self.tmp, "units")
        os.makedirs(self.unit_dir)
        self.unit_file = os.path.join(self.unit_dir, UNIT_NAME)
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        self.systemctl = os.path.join(bindir, "systemctl")
        self.curl = os.path.join(bindir, "curl")
        for path, text in ((self.systemctl, FAKE_SYSTEMCTL),
                           (self.curl, FAKE_CURL)):
            with open(path, "w") as fh:
                fh.write(text)
            os.chmod(path, 0o755)
        self.failing_sed = os.path.join(bindir, "sed-fail")
        with open(self.failing_sed, "w") as fh:
            fh.write(FAILING_SED)
        os.chmod(self.failing_sed, 0o755)
        self.log = os.path.join(self.tmp, "systemctl.log")
        self.load_file = os.path.join(self.tmp, "load-state")
        self.health_file = os.path.join(self.tmp, "health")
        self.set_load("loaded")
        self.set_health(1)

    # -- fixture helpers -------------------------------------------------
    def set_load(self, value):
        with open(self.load_file, "w") as fh:
            fh.write(value + "\n")

    def set_health(self, value):
        with open(self.health_file, "w") as fh:
            fh.write(str(value))

    def render(self):
        with open(os.path.join(self.root, "ops", "server-care",
                               "scheduler-server.service.tmpl")) as fh:
            text = fh.read()
        home = os.path.dirname(os.path.dirname(self.root))
        return (text.replace("@ROOT@", self.root)
                    .replace("@PYTHON@", shutil.which("python3"))
                    .replace("@HOME@", home))

    def write_unit(self, text):
        with open(self.unit_file, "w") as fh:
            fh.write(text)

    def systemctl_log(self):
        if not os.path.exists(self.log):
            return ""
        with open(self.log) as fh:
            return fh.read()

    def run_watchdog(self, extra_env=None):
        env = dict(os.environ)
        env.update({
            "SCHEDULER_ROOT": self.root,
            "SCHEDULER_UNIT_DIR": self.unit_dir,
            "SCHEDULER_SYSTEMCTL": self.systemctl,
            "SCHEDULER_CURL": self.curl,
            "SCHEDULER_POLL_SECS": "2",
            "SCHEDULER_FRESH_POLL_SECS": "4",
            "FAKE_SYSTEMCTL_LOG": self.log,
            "FAKE_LOAD_STATE_FILE": self.load_file,
            "FAKE_HEALTH_FILE": self.health_file,
        })
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", os.path.join(self.root, "ops", "server-care", "watchdog.sh")],
            capture_output=True, text=True, env=env, timeout=60)

    # -- rung 3: presence before health ----------------------------------
    def test_healthy_missing_unit_reinstalled_quietly(self):
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(os.path.isfile(self.unit_file))
        self.assertIn("daemon-reload", self.systemctl_log())
        self.assertNotIn("start", self.systemctl_log())
        self.assertIn("missing", result.stdout)

    # -- rung 4: render-when-invalid --------------------------------------
    def test_healthy_stale_unit_rerendered(self):
        self.write_unit("garbage from an older template\n")
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout)
        with open(self.unit_file) as fh:
            self.assertEqual(fh.read(), self.render())
        self.assertIn("re-rendered", result.stdout)

    def test_healthy_current_unit_untouched(self):
        self.write_unit(self.render())
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.systemctl_log(), "")

    # -- rung 6: load-state repair verb -----------------------------------
    def test_down_unloaded_unit_gets_start(self):
        self.write_unit(self.render())
        self.set_load("not-found")
        self.set_health(0)
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout)
        log = self.systemctl_log()
        self.assertIn(f"start {UNIT_NAME}", log)
        self.assertNotIn(f"restart {UNIT_NAME}", log)
        # Unit present and current: not a fresh restore, so the
        # confirmation window is the ordinary poll window.
        self.assertIn("(start, 2s window)", result.stdout)

    def test_down_loaded_unit_gets_restart(self):
        self.write_unit(self.render())
        self.set_load("loaded")
        self.set_health(0)
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"restart {UNIT_NAME}", self.systemctl_log())

    # -- rung 7: fresh-restore path ---------------------------------------
    def test_down_missing_unit_installed_and_started(self):
        self.set_load("not-found")
        self.set_health(0)
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(os.path.isfile(self.unit_file))
        self.assertIn(f"start {UNIT_NAME}", self.systemctl_log())
        self.assertIn("restored and verified healthy", result.stdout)

    def test_restored_line_reports_verb_and_window(self):
        # No unit file: a fresh restore — the confirmation window
        # is the long fresh-restore window, not the poll window.
        self.set_load("not-found")
        self.set_health(0)
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("restored and verified healthy (start, 4s window)",
                      result.stdout)

    # -- flap regression: a failed render is unknown, never stale --------
    def test_render_failure_healthy_unit_left_alone(self):
        self.write_unit(self.render())
        with open(self.unit_file) as fh:
            before = fh.read()
        result = self.run_watchdog({"SCHEDULER_SED": self.failing_sed})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("unknown", result.stdout)
        self.assertEqual(self.systemctl_log(), "")
        with open(self.unit_file) as fh:
            self.assertEqual(fh.read(), before)

    def test_render_failure_healthy_missing_unit_no_false_alarm(self):
        result = self.run_watchdog({"SCHEDULER_SED": self.failing_sed})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(os.path.exists(self.unit_file))
        self.assertNotIn("daemon-reload", self.systemctl_log())

    def test_render_failure_down_unit_present_proceeds_as_is(self):
        self.write_unit(self.render())
        self.set_health(0)
        result = self.run_watchdog({"SCHEDULER_SED": self.failing_sed})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("as-is", result.stdout)
        self.assertIn(f"restart {UNIT_NAME}", self.systemctl_log())

    def test_render_failure_down_unit_missing_fails_honestly(self):
        self.set_health(0)
        result = self.run_watchdog({"SCHEDULER_SED": self.failing_sed})
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn("start", self.systemctl_log())

    # -- rung 8: one attempt per episode ----------------------------------
    def test_unrecoverable_ladder_spends_one_attempt(self):
        self.write_unit(self.render())
        self.set_health(0)
        env = {"FAKE_NO_RECOVER": "1"}
        first = self.run_watchdog(env)
        self.assertEqual(first.returncode, 1, first.stdout)
        episode = os.path.join(self.root, "state", "keeper-episode")
        self.assertTrue(os.path.isfile(episode))
        second = self.run_watchdog(env)
        self.assertEqual(second.returncode, 1, second.stdout)
        self.assertIn("already attempted", second.stdout)
        starts = [ln for ln in self.systemctl_log().splitlines()
                  if ln.startswith(("start ", "restart "))]
        self.assertEqual(len(starts), 1)


if __name__ == "__main__":
    unittest.main()
