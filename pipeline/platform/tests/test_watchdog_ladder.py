"""The watchdog ladder's actuation proof (the
actuation-gap cure, 2026-11-15): the ladder is driven
end-to-end against a simulated systemd — a stub
systemctl on PATH whose state machine (active / failed
/ start-limit-spent flag files) models the one property
the incident turned on, that a start against a spent
start limit is refused until reset-failed clears it —
with the ops tree copied into a temp root and the
health probe simulated behind the ladder's own
WORKHORSE_PYTHON seam. The proof never touches a live
unit, a live port, or live state: every write lands in
the test's temp dirs.

The incident these scenarios pin (2026-11-16,
workhorse.service in start-limit exhaustion): the old
ladder had no failed-state classification and no
reset-failed act, so even a live driver could not have
recovered the unit — and its driver, a scheduler job
inside the failed unit, never ran at all. The driver
half is pinned by test_units_spec.py's watchdog-pair
coverage and the install-shape test below; the ladder
half is pinned here:

  * a failed unit with its start limit spent is
    recovered by reset-failed THEN start (in that
    order; a bare restart is never issued against it)
    and the run exits 0 once its surfaces answer;
  * the same unit with its tree still broken still
    gets the act on the very next run — the rung is
    gated by cadence, not by the 900s repair episode;
  * a healthy, active unit: silent 0, no mutating
    systemctl call;
  * an active unit with dead surfaces keeps the
    pre-existing down-path behaviour exactly — one
    restart per episode, no reset-failed, and a run
    inside the episode escalates without re-acting —
    but only once the down-streak rung is satisfied.

The second incident these scenarios pin (2026-11-16,
the false fire): the ladder's probe budget was 5s and
a single failed probe was a restart. A serve
mid-assembly on a contended box can take longer than
that to answer a health route that itself never
computes, so the ladder restarted healthy units all
day — the workbench unit 28 times, 26 of them
"restored" by the restart itself, including a clean
stop of a mid-assembly serve at 23:50Z (journal:
stopped and started 23:50:05-06Z, NRestarts=0, no
crash). The cure pinned here:

  * the down act requires three consecutive failed
    probes across ladder runs; a serve that answers
    even once inside that window is never restarted,
    and any answering verdict clears the streak (the
    count is consecutive, never cumulative);
  * the failed-unit rung is NOT streak-gated: a unit
    in the failed state is recovered on the first run
    that sees it, exactly as the scenarios above pin;
  * the ladder probes with a 20s budget (the probe's
    own 5s default stands for hand runs), recorded by
    the fake probe below from its environment.

The third incident these scenarios pin (2026-11-18,
boot ab0acf72): the host was replaced, the survival
rungs reinstalled the unit set and enabled every
unit — and the ladder then counted its own freshly
installed, never-started service as a down serve:
"consecutive failure 1 of 3; not acting", until a
hand start (reset-failed + start, 15:29:24Z)
recovered it. Install is presence, not motion; the
down-streak rung gates the ladder's inference from a
silent probe — a running serve that may only be
slow — and a unit with no process at all is not an
inference. The cure restores the originals' shape
separation (the starter kit's ladder;
survival-contract v1 rung 6, the load-state repair
verb): load state is read at ladder entry, and a
unit that is not active is acted on the pass that
sees it — STARTED when it was never loaded,
RESTARTED when it stood loaded — confirmed on the
restore window, one attempt per repair episode:

  * a never-loaded unit with dead surfaces is
    started on the first pass and the run exits 0
    once its surfaces answer; no streak is recorded;
  * a loaded-but-stopped unit is restarted on the
    first pass, under the same no-streak rule;
  * a start that does not take is episode-capped:
    the next pass inside the episode escalates
    instead of starting the unit again.
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
# Simulated systemctl: state is flag files in $STUB_DIR
# (active, failed, limit, healed, heal_on_start); every
# invocation is appended to $STUB_DIR/calls.log.
set -u
echo "$*" >> "$STUB_DIR/calls.log"
case "${1:-}" in
    is-active)
        [ -f "$STUB_DIR/active" ] && exit 0 || exit 1 ;;
    is-failed)
        [ -f "$STUB_DIR/failed" ] && exit 0 || exit 1 ;;
    cat)
        exit 0 ;;
    show)
        [ -f "$STUB_DIR/loaded" ] && echo "loaded" \\
            || echo "not-found"
        exit 0 ;;
    reset-failed)
        rm -f "$STUB_DIR/failed" "$STUB_DIR/limit"
        exit 0 ;;
    start)
        if [ -f "$STUB_DIR/limit" ]; then
            echo "Failed to start: start request repeated too quickly" >&2
            exit 1
        fi
        if [ -f "$STUB_DIR/heal_on_start" ]; then
            touch "$STUB_DIR/active" "$STUB_DIR/healed"
            rm -f "$STUB_DIR/failed"
        else
            # The process dies at once and systemd spends
            # its burst again: straight back to failed
            # with the limit spent.
            touch "$STUB_DIR/failed" "$STUB_DIR/limit"
            rm -f "$STUB_DIR/active"
        fi
        exit 0 ;;
    restart)
        if [ -f "$STUB_DIR/limit" ]; then
            echo "Failed to restart: start request repeated too quickly" >&2
            exit 1
        fi
        touch "$STUB_DIR/active"
        [ -f "$STUB_DIR/heal_on_start" ] && \\
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
# the stub's healed flag stands, and the probe budget
# the ladder exported is recorded to probe.log so the
# suite can pin it. Anything else is refused, so the
# proof can never fall through to a real interpreter
# and pass by accident.
case "$*" in
    *healthcheck.py*)
        echo "timeout=${WORKHORSE_HEALTH_TIMEOUT_S:-unset}" \\
            >> "$STUB_DIR/probe.log"
        [ -f "$STUB_DIR/healed" ] && exit 0 || exit 1 ;;
    *)
        echo "fake-python: unexpected: $*" >&2
        exit 1 ;;
esac
"""

FLAGS = ("active", "failed", "limit", "healed",
         "heal_on_start", "loaded")


class WatchdogLadderTests(unittest.TestCase):
    """One fixture per class: the ops copy and the
    scratch unit install are scenario-independent; each
    test resets only the stub's flags and the copied
    tree's episode markers."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(
            prefix="watchdog-ladder-"))
        cls.root = cls.tmp / "repo"
        cls.ops = (cls.root / "pipeline" / "platform"
                   / "ops")
        shutil.copytree(
            OPS_DIR, cls.ops,
            ignore=shutil.ignore_patterns("__pycache__"))
        # the ops tree's durable writer reaches the
        # platform writer through the paths spine; the
        # fixture tree carries both at their production
        # relative locations
        for name in ("paths.py", "writer.py"):
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
        cls.probe_log = cls.stub_dir / "probe.log"
        env = cls._env()
        proc = subprocess.run(
            ["bash", str(cls.ops / "install-units.sh")],
            env=env, capture_output=True, text=True,
            timeout=600)
        cls.install_output = proc.stdout + proc.stderr
        cls.install_rc = proc.returncode
        cls.install_calls = (
            cls.calls_log.read_text(encoding="utf-8")
            if cls.calls_log.exists() else "")

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
        for flag in FLAGS:
            (self.stub_dir / flag).unlink(missing_ok=True)
        self.calls_log.unlink(missing_ok=True)
        self.probe_log.unlink(missing_ok=True)
        var = self.root / "pipeline" / "platform" / "var"
        if var.exists():
            for path in var.glob("watchdog-*"):
                path.unlink()

    def set_flags(self, *flags):
        for flag in flags:
            (self.stub_dir / flag).touch()

    def calls(self):
        if not self.calls_log.exists():
            return []
        return self.calls_log.read_text(
            encoding="utf-8").splitlines()

    def probe_budgets(self):
        if not self.probe_log.exists():
            return []
        return self.probe_log.read_text(
            encoding="utf-8").splitlines()

    def var_file(self, name):
        return (self.root / "pipeline" / "platform"
                / "var" / name)

    def run_ladder(self, unit):
        env = self._env()
        env["WORKHORSE_UNIT"] = unit
        return subprocess.run(
            ["bash", str(self.ops / "watchdog.sh")],
            env=env, capture_output=True, text=True,
            timeout=300)

    def test_install_shape_enables_timers_not_services(self):
        self.assertEqual(self.install_rc, 0,
                         self.install_output)
        installed = {path.name
                     for path in self.units_dir.iterdir()}
        for unit in ("workhorse", "workbench", "venue"):
            self.assertIn(f"{unit}.service", installed)
            self.assertIn(f"{unit}-watchdog.service",
                          installed)
            self.assertIn(f"{unit}-watchdog.timer",
                          installed)
            self.assertIn(f"enable {unit}.service",
                          self.install_calls)
            self.assertIn(f"enable {unit}-watchdog.timer",
                          self.install_calls)
            self.assertNotIn(
                f"enable {unit}-watchdog.service",
                self.install_calls)
        timer_text = (self.units_dir
                      / "workhorse-watchdog.timer").read_text(
                      encoding="utf-8")
        self.assertIn("OnUnitActiveSec=60", timer_text)
        self.assertIn("Unit=workhorse-watchdog.service",
                      timer_text)

    def test_failed_unit_recovers_via_reset_failed(self):
        self.set_flags("failed", "limit", "heal_on_start")
        proc = self.run_ladder("workhorse")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("failed state", proc.stderr)
        self.assertIn("restored", proc.stderr)
        calls = self.calls()
        self.assertIn("reset-failed workhorse", calls)
        self.assertIn("start workhorse", calls)
        self.assertLess(calls.index("reset-failed workhorse"),
                        calls.index("start workhorse"))
        self.assertNotIn("restart workhorse", calls)

    def test_failed_unit_actuates_every_tick(self):
        # The tree stays broken: the start lands the unit
        # straight back in failed + limit. The rung must
        # act again on the next run — the 900s repair
        # episode must not gate failed-unit recovery.
        self.set_flags("failed", "limit")
        first = self.run_ladder("workhorse")
        self.assertEqual(first.returncode, 1, first.stderr)
        self.assertIn("failed-unit recovery", first.stderr)
        second = self.run_ladder("workhorse")
        self.assertEqual(second.returncode, 1, second.stderr)
        resets = [call for call in self.calls()
                  if call == "reset-failed workhorse"]
        self.assertEqual(len(resets), 2, self.calls())

    def test_healthy_unit_is_silent_and_acts_never(self):
        self.set_flags("active", "healed")
        proc = self.run_ladder("venue")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        mutating = [call for call in self.calls()
                    if call.split(" ", 1)[0]
                    in ("start", "restart", "reset-failed")]
        self.assertEqual(mutating, [], self.calls())
        # The ladder probes with its own 20s budget, not
        # the probe's 5s interactive default.
        self.assertEqual(self.probe_budgets(), ["timeout=20"])

    def test_down_unit_keeps_the_episode_ladder(self):
        # The down act stands behind the down-streak
        # rung: the first two consecutive failed probes
        # record the streak and act never (no restart,
        # no episode marker); the third reaches the
        # pre-existing episode behaviour exactly — one
        # restart per episode, no reset-failed. The act
        # clears the streak, so the runs that follow are
        # streak-gated again until the streak completes
        # and the fresh episode's escalation speaks.
        self.set_flags("active")
        marker = self.var_file("watchdog-episode-workbench")
        for _ in range(2):
            proc = self.run_ladder("workbench")
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("not acting", proc.stderr)
            self.assertFalse(marker.exists())
        self.assertNotIn("restart workbench", self.calls())
        third = self.run_ladder("workbench")
        self.assertEqual(third.returncode, 1, third.stderr)
        self.assertTrue(marker.exists())
        for _ in range(2):
            proc = self.run_ladder("workbench")
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("not acting", proc.stderr)
        sixth = self.run_ladder("workbench")
        self.assertEqual(sixth.returncode, 1, sixth.stderr)
        self.assertIn("escalating", sixth.stderr)
        calls = self.calls()
        self.assertEqual(
            calls.count("restart workbench"), 1, calls)
        self.assertNotIn("reset-failed workbench", calls)

    def test_slow_but_alive_is_never_restarted(self):
        # The 2026-11-16 false fire in verdict space: the
        # probe fails while the serve is saturated, then
        # the serve answers again before the streak
        # completes. No mutating call is ever issued and
        # the answering run clears the streak.
        self.set_flags("active")
        for _ in range(2):
            proc = self.run_ladder("workbench")
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("not acting", proc.stderr)
        self.set_flags("healed")
        proc = self.run_ladder("workbench")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        mutating = [call for call in self.calls()
                    if call.split(" ", 1)[0]
                    in ("start", "restart", "reset-failed")]
        self.assertEqual(mutating, [], self.calls())
        self.assertFalse(self.var_file(
            "watchdog-downstreak-workbench").exists())

    def test_down_streak_is_consecutive_not_cumulative(self):
        # Two failures, a recovery, two more failures:
        # still no act — the tally restarts at every
        # answering verdict. A third consecutive failure
        # after the recovery acts, exactly once.
        self.set_flags("active")
        self.run_ladder("workbench")
        self.run_ladder("workbench")
        self.set_flags("healed")
        proc = self.run_ladder("workbench")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        (self.stub_dir / "healed").unlink()
        self.run_ladder("workbench")
        self.run_ladder("workbench")
        self.assertNotIn("restart workbench", self.calls())
        self.run_ladder("workbench")
        self.assertEqual(
            self.calls().count("restart workbench"), 1,
            self.calls())

    def test_never_started_unit_is_started_on_first_pass(self):
        # The 2026-11-18 incident (boot ab0acf72): the
        # survival rungs reinstalled the unit set after
        # the host replacement and enabled every unit,
        # but install is presence — the service stood
        # never loaded, never started, surfaces down.
        # The ladder read it as a down serve and counted
        # probe failures ("consecutive failure 1 of 3;
        # not acting") until a hand start at 15:29:24Z.
        # The originals' shape separation (survival-
        # contract v1, rung 6): a unit that was never
        # loaded is STARTED on the pass that sees it —
        # the streak gates the ladder's inference about
        # a running serve, never systemd's own state.
        # Here: no flags at entry (never loaded, not
        # active, not failed); the start heals.
        self.set_flags("heal_on_start")
        proc = self.run_ladder("workhorse")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("not active", proc.stderr)
        self.assertIn("restored", proc.stderr)
        calls = self.calls()
        self.assertIn("start workhorse", calls)
        self.assertNotIn("restart workhorse", calls)
        self.assertFalse(self.var_file(
            "watchdog-downstreak-workhorse").exists())

    def test_stopped_unit_is_restarted_on_first_pass(self):
        # The verb keying's other half: a unit systemd
        # had already loaded at ladder entry (it ran
        # earlier and stopped) is RESTARTED on the
        # first pass — again no streak: there is no
        # process whose slow answer needs protecting.
        self.set_flags("loaded", "heal_on_start")
        proc = self.run_ladder("workhorse")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("restored", proc.stderr)
        calls = self.calls()
        self.assertIn("restart workhorse", calls)
        self.assertNotIn("start workhorse", calls)
        self.assertFalse(self.var_file(
            "watchdog-downstreak-workhorse").exists())

    def test_not_active_act_is_episode_capped(self):
        # One start attempt per repair episode, the
        # originals' episode cap: the start is issued,
        # the unit dies clean at once (inactive again,
        # not failed), and the next pass inside the
        # episode escalates instead of starting it
        # again — the ladder never becomes a start loop.
        self.run_ladder("workhorse")
        self.assertEqual(
            self.calls().count("start workhorse"), 1,
            self.calls())
        self.assertTrue(self.var_file(
            "watchdog-episode-workhorse").exists())
        # The stub's spent start left the unit failed
        # with its limit spent; a clean death leaves it
        # merely inactive — clear those flags so the
        # second pass sees the not-active shape again.
        (self.stub_dir / "failed").unlink()
        (self.stub_dir / "limit").unlink()
        proc = self.run_ladder("workhorse")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("escalating", proc.stderr)
        self.assertEqual(
            self.calls().count("start workhorse"), 1,
            self.calls())


if __name__ == "__main__":
    unittest.main()
