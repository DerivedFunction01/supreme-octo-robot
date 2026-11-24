"""Adoption liveness (2026-11-24) against the fake colab CLI:
a pin written before a renewal adopts the lineage's live
generation, a pin on a dead kernel channel fails fast at the
bind with the probe on the run record, and a resume keeps its
recorded lineage without being re-pinned by hand.

The renewal is simulated at the record level — the swap's own
footprint: the lease record stands under the child's name,
the parent's record is a superseded tombstone pointing at it,
and the fake venue holds the child (the parent stopped).
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from runner_harness import FAKE, _fire_smoke, run_bin, runs_dir, runner_env  # noqa: F401


def _renew_lease(env, session):
    """Move the fixture's lease to its lineage's next
    generation, exactly as a renewal swap leaves it."""
    var = Path(env["COLAB_RUNNER_VAR"])
    rec = json.loads((var / f"lease-{session}.json").read_text())
    stem = session
    while re.search(r"-r\d+$", stem):
        stem = re.sub(r"-r\d+$", "", stem)
    new = f"{stem}-r1799999999"
    for argv in (["new", "-s", new, "--high-mem"], ["stop", "-s", session]):
        r = subprocess.run([sys.executable, str(FAKE), *argv], capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr
    tomb = dict(rec, retired=True, superseded_by=new, superseded_at="2026-11-24T00:00:00+00:00")
    (var / f"lease-{session}.json.superseded-20261124T000000Z").write_text(json.dumps(tomb))
    (var / f"lease-{session}.json").unlink()
    (var / f"lease-{new}.json").write_text(json.dumps(dict(rec, session=new)))
    return new


def _first_session(env):
    first = _fire_smoke(env)
    return json.loads((runs_dir(env) / f"{first['run_id']}.json").read_text())["session"]


def test_pin_named_before_a_renewal_adopts_the_live_generation(tmp_path):
    env = runner_env(tmp_path)
    session = _first_session(env)
    new = _renew_lease(env, session)
    r = subprocess.run([sys.executable, str(run_bin(env)), "smoke", "--session", session], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    rec = json.loads((runs_dir(env) / f"{out['run_id']}.json").read_text())
    assert rec["session"] == new and rec["session_pin"] == session
    assert rec["pin_resolved"] == {"from": session, "to": new, "via": "superseded"}
    assert rec["bind_probe"]["live"] is True


def _dead_probe_wrapper(tmp_path):
    """A COLAB_BIN wrapper whose bind-probe execs refuse —
    the dead kernel channel — delegating everything else to
    the real fake (the flaky wrappers' shape)."""
    wrapper = tmp_path / "dead_probe_colab.py"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import os, subprocess, sys\n"
        "args = sys.argv[1:]\n"
        "if 'exec' in args and any('bind-probe' in a for a in args):\n"
        "    print('dead probe wrapper: kernel channel unreachable', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "sys.exit(subprocess.run([sys.executable, os.environ['FAKE_COLAB_REAL'], *args]).returncode)\n"
    )
    wrapper.chmod(0o755)
    return wrapper


def test_pin_on_a_dead_channel_fails_fast_with_the_probe_on_the_record(tmp_path):
    env = runner_env(tmp_path)
    session = _first_session(env)
    _renew_lease(env, session)
    env.update(COLAB_BIN=str(_dead_probe_wrapper(tmp_path)), FAKE_COLAB_REAL=str(FAKE))
    r = subprocess.run([sys.executable, str(run_bin(env)), "smoke", "--session", session], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 1, r.stdout + r.stderr
    out = json.loads(r.stdout)
    rec = json.loads((runs_dir(env) / f"{out['run_id']}.json").read_text())
    assert rec["state"] == "failed"
    assert "pin-lineage-unhealthy" in rec["error"]
    assert rec["bind_probe"]["live"] is False
    assert not rec.get("session"), "a refused bind adopted a session anyway"
    assert not rec.get("launch_confirmed_at"), "a refused bind reached the launch"


def test_resume_keeps_its_recorded_lineage_across_a_renewal(tmp_path):
    env = runner_env(tmp_path)
    session = _first_session(env)
    new = _renew_lease(env, session)
    runs = runs_dir(env)
    (runs / "planted-run.json").write_text(json.dumps({
        "run_id": "planted-run", "job": "smoke", "session": session, "session_pin": session,
        "caller": "test", "state": "starting",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }))
    r = subprocess.run([sys.executable, str(run_bin(env)), "smoke", "--resume", "planted-run"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.loads((runs / "planted-run.json").read_text())
    assert rec["state"] == "complete"
    assert rec["session"] == new, "the resume wandered off its recorded lineage"
    assert rec["pin_resolved"]["to"] == new
