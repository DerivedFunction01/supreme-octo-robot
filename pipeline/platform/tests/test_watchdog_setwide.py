"""The watchdog ladder's SET-survival proof (the boot
re-render wiring cure): the ladder is
driven end-to-end against a simulated systemd — a stub
systemctl on PATH whose state is per-unit flag files —
with the ops tree copied into a temp root and the unit
dir behind the installer's WORKHORSE_UNIT_DIR seam.
The proof never touches a live unit, a live port, or
live state: every write lands in the test's temp dirs.

The incident these scenarios pin (the
05:05Z reboot): /etc was wiped; the only boot-reachable
driver, the scheduler keeper hook, invokes the ladder
bare (its own unit, workhorse), and the per-unit
survival rung healed workhorse only — workbench,
venue, and all six watchdog units stayed missing until
a hand restore at 05:16Z, because the per-unit drivers
are /etc units themselves. The set-survival rung is
the cure, and these scenarios pin its shape:

  * the whole set stands: the rung is silent, no
    install pass runs, no systemctl act is issued —
    the per-invocation cost of the cure is the
    sentinel's spec read and one stat per unit file;
  * one unit file missing (another unit's watchdog
    timer): any unit's ladder restores it via the
    full install pass and arms the inactive timer —
    and starts no service doing it;
  * the keeper's own shape — a bare invocation with
    no WORKHORSE_UNIT, another unit's service file
    missing: the set is healed by the call that used
    to heal workhorse alone;
  * the install pass failing against an incomplete
    set: the ladder fails loud, in its UNKNOWN-state
    voice, and issues no service act at all.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parents[1] / "ops"

STUB_SYSTEMCTL = """\
#!/usr/bin/env bash
# Simulated systemctl: state is per-unit flag files in
# $STUB_DIR (active-<unit>, failed-<unit>,
# limit-<unit>); every invocation is appended to
# $STUB_DIR/calls.log. A verb's unit is its last
# argument. Timers arm on start; a service start
# against a spent limit is refused until reset-failed,
# as in the ladder scenarios.
set -u
echo "$*" >> "$STUB_DIR/calls.log"
verb="${1:-}"
unit="${@: -1}"
case "$verb" in
    is-active)
        [ -f "$STUB_DIR/active-$unit" ] && exit 0 \\
            || exit 1 ;;
    is-failed)
        [ -f "$STUB_DIR/failed-$unit" ] && exit 0 \\
            || exit 1 ;;
    cat)
        exit 0 ;;
    reset-failed)
        rm -f "$STUB_DIR/failed-$unit" \\
            "$STUB_DIR/limit-$unit"
        exit 0 ;;
    start)
        case "$unit" in
            *.timer)
                touch "$STUB_DIR/active-$unit"
                exit 0 ;;
        esac
        if [ -f "$STUB_DIR/limit-$unit" ]; then
            echo "Failed to start: start request repeated too quickly" >&2
            exit 1
        fi
        touch "$STUB_DIR/active-$unit"
        [ -f "$STUB_DIR/heal_on_start-$unit" ] && \\
            touch "$STUB_DIR/healed"
        exit 0 ;;
    restart)
        if [ -f "$STUB_DIR/limit-$unit" ]; then
            echo "Failed to restart: start request repeated too quickly" >&2
            exit 1
        fi
        touch "$STUB_DIR/active-$unit"
        [ -f "$STUB_DIR/heal_on_start-$unit" ] && \\
            touch "$STUB_DIR/healed"
        exit 0 ;;
    *)
        exit 0 ;;
esac
"""

FAKE_PYTHON = """\
#!/usr/bin/env bash
# Behind the ladder's WORKHORSE_PYTHON seam: only the
# healthcheck.py invocation is simulated — exit 0 iff
# the stub's healed flag stands. Anything else is
# refused, so the proof can never fall through to a
# real interpreter and pass by accident.
case "$*" in
    *healthcheck.py*)
        [ -f "$STUB_DIR/healed" ] && exit 0 || exit 1 ;;
    *)
        echo "fake-python: unexpected: $*" >&2
        exit 1 ;;
esac
"""

TIMERS = ("workhorse-watchdog.timer",
          "workbench-watchdog.timer",
          "venue-watchdog.timer")
UNITS = ("workhorse", "workbench", "venue")


class WatchdogSetSurvivalTests(unittest.TestCase):
    """One fixture per class: the ops copy and the
    scratch unit install are scenario-independent; each
    test resets the stub's flags, the calls log, and
    the copied tree's episode markers, and removes at
    most one installed unit file."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(
            prefix="watchdog-setwide-"))
        cls.root = cls.tmp / "repo"
        cls.ops = (cls.root / "pipeline" / "platform"
                   / "ops")
        shutil.copytree(
            OPS_DIR, cls.ops,
            ignore=shutil.ignore_patterns("__pycache__"))
        # the ops tree's durable writer reaches the
        # platform writer through the paths spine, and
        # the ops scripts and the cutover renderer load
        # the argv pair by relative path; the fixture
        # tree carries them all at their production
        # relative locations
        for name in ("paths.py", "writer.py", "argv.sh",
                     "argv.py"):
            shutil.copy2(OPS_DIR.parent / name,
                         cls.ops.parent / name)
        cls.units_dir = cls.tmp / "units"
        cls.units_dir.mkdir()
        cls.stub_dir = cls.tmp / "stub"
        cls.stub_dir.mkdir()
        cls.bin_dir = cls.tmp / "bin"
        cls.bin_dir.mkdir()
        stub = cls.bin_dir / "systemctl"
        stub.write_text(STUB_SYSTEMCTL, encoding="utf-8")
        stub.chmod(0o755)
        fake = cls.bin_dir / "fake-python"
        fake.write_text(FAKE_PYTHON, encoding="utf-8")
        fake.chmod(0o755)
        cls.calls_log = cls.stub_dir / "calls.log"
        proc = subprocess.run(
            ["bash", str(cls.ops / "install-units.sh")],
            env=cls._env(), capture_output=True,
            text=True, timeout=600)
        cls.install_output = proc.stdout + proc.stderr
        cls.install_rc = proc.returncode

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _env(cls):
        env = dict(os.environ)
        env["PATH"] = (str(cls.bin_dir) + os.pathsep
                       + env["PATH"])
        env["HOME"] = str(cls.tmp / "home")
        env["STUB_DIR"] = str(cls.stub_dir)
        env["WORKHORSE_UNIT_DIR"] = str(cls.units_dir)
        env["WORKHORSE_SYSTEMCTL"] = str(
            cls.bin_dir / "systemctl")
        env["WORKHORSE_PYTHON"] = str(
            cls.bin_dir / "fake-python")
        env["WORKHORSE_WATCHDOG_RESTORE_WINDOW_S"] = "3"
        return env

    def setUp(self):
        self.assertEqual(self.install_rc, 0,
                         self.install_output)
        for path in self.stub_dir.iterdir():
            path.unlink()
        var = self.root / "pipeline" / "platform" / "var"
        if var.exists():
            for path in var.glob("watchdog-*"):
                path.unlink()
        # The fixture's installed set stands whole at
        # the start of every scenario; a test removes
        # the one file its scenario is about.
        installed = {path.name
                     for path in self.units_dir.iterdir()}
        for unit in UNITS:
            self.assertIn(f"{unit}.service", installed)
            self.assertIn(f"{unit}-watchdog.service",
                          installed)
            self.assertIn(f"{unit}-watchdog.timer",
                          installed)

    def set_flags(self, *flags):
        for flag in flags:
            (self.stub_dir / flag).touch()

    def calls(self):
        if not self.calls_log.exists():
            return []
        return self.calls_log.read_text(
            encoding="utf-8").splitlines()

    def acts(self):
        """Mutating systemctl calls, in issue order."""
        return [call for call in self.calls()
                if call.split(" ", 1)[0]
                in ("start", "restart", "reset-failed",
                    "enable", "daemon-reload")]

    def run_ladder(self, unit=None, **overrides):
        env = self._env()
        env.pop("WORKHORSE_UNIT", None)
        if unit is not None:
            env["WORKHORSE_UNIT"] = unit
        env.update(overrides)
        return subprocess.run(
            ["bash", str(self.ops / "watchdog.sh")],
            env=env, capture_output=True, text=True,
            timeout=300)

    def test_whole_set_is_silent_and_acts_never(self):
        self.set_flags("active-venue", "healed")
        proc = self.run_ladder("venue")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(self.acts(), [], self.calls())

    def test_missing_timer_file_restored_and_armed(self):
        (self.units_dir
         / "workbench-watchdog.timer").unlink()
        self.set_flags(
            "active-venue", "healed",
            "active-workhorse-watchdog.timer",
            "active-venue-watchdog.timer")
        proc = self.run_ladder("venue")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("unit set incomplete", proc.stderr)
        self.assertIn("workbench-watchdog.timer",
                      proc.stderr)
        self.assertTrue(
            (self.units_dir
             / "workbench-watchdog.timer").exists())
        calls = self.calls()
        # The install pass ran (it enables as it goes)
        # and the one inactive timer was armed; the
        # already-active timers were left alone.
        self.assertIn("enable workbench-watchdog.timer",
                      calls)
        self.assertIn("start workbench-watchdog.timer",
                      calls)
        self.assertNotIn("start workhorse-watchdog.timer",
                         calls)
        self.assertNotIn("start venue-watchdog.timer",
                         calls)
        # The rung starts no service — not another
        # unit's, and not the ladder's own.
        self.assertNotIn("start venue", calls)
        self.assertNotIn("restart venue", calls)
        self.assertNotIn("start workbench", calls)

    def test_bare_invocation_heals_the_set(self):
        # The keeper's shape exactly: no WORKHORSE_UNIT,
        # the ladder defaults to its own unit — and a
        # different unit's service file is the one
        # missing. Before the cure this call healed
        # workhorse alone and venue stayed down.
        (self.units_dir / "venue.service").unlink()
        self.set_flags(
            "active-workhorse", "healed",
            "active-workhorse-watchdog.timer",
            "active-workbench-watchdog.timer",
            "active-venue-watchdog.timer")
        proc = self.run_ladder()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("venue.service", proc.stderr)
        self.assertTrue(
            (self.units_dir / "venue.service").exists())
        calls = self.calls()
        self.assertIn("enable venue.service", calls)
        # Venue's service is restored as a file; its
        # start belongs to venue's own ladder, driven
        # by venue's timer — never to this rung.
        self.assertNotIn("start venue", calls)
        self.assertNotIn("restart venue", calls)

    def test_failed_install_pass_fails_loud(self):
        # The unit dir is a regular file: every unit
        # reads missing and every staged install fails
        # against it, whoever runs the test.
        not_a_dir = self.tmp / "units-as-file"
        not_a_dir.write_text("not a directory",
                             encoding="utf-8")
        self.set_flags("active-venue", "healed")
        proc = self.run_ladder(
            "venue",
            WORKHORSE_UNIT_DIR=str(not_a_dir))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("unit set incomplete", proc.stderr)
        self.assertIn("install pass failed", proc.stderr)
        self.assertIn("failing loud", proc.stderr)
        service_acts = [
            call for call in self.calls()
            if call.split(" ", 1)[0]
            in ("start", "restart", "reset-failed")]
        self.assertEqual(service_acts, [], self.calls())


if __name__ == "__main__":
    unittest.main()
