"""Re-placement end to end against the fake colab CLI
(VENUE DEFECT 2, leg a): a resume whose recorded binding
names a reaped session re-places onto the shape's live lease
and completes, journaling the move; a resume whose bound
session is absent-but-unconfirmed refuses pin-unavailable
and launches nothing.

The reaped state is planted at the record level, as the
reaper leaves it: the session stopped, its lease record
deleted (the confirmed-absent deletion), a sibling lease
standing live at the shape. The unconfirmed state keeps the
record standing with no absence stamp — one flicker reading,
which is not a death.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from runner_harness import FAKE, _fire_smoke, run_bin, runs_dir, runner_env  # noqa: F401

PEER = "peer-session-7"


def _first_session(env):
    first = _fire_smoke(env)
    return json.loads((runs_dir(env) / f"{first['run_id']}.json").read_text())["session"]


def _plant_peer_lease(env, session):
    """A second live lease at the shape, a different lineage:
    the fake session created, its record copied from the
    first lease's shape."""
    var = Path(env["VENUE_RUNNER_VAR"])
    rec = json.loads((var / f"lease-{session}.json").read_text())
    r = subprocess.run([sys.executable, str(FAKE), "new", "-s", PEER, "--high-mem"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    (var / f"lease-{PEER}.json").write_text(json.dumps(dict(rec, session=PEER)))
    return PEER


def _stop_fake(env, session):
    r = subprocess.run([sys.executable, str(FAKE), "stop", "-s", session], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def _plant_bound_run(env, session):
    runs = runs_dir(env)
    (runs / "planted-run.json").write_text(json.dumps({
        "run_id": "planted-run", "job": "smoke", "session": session, "session_pin": session,
        "caller": "test", "state": "starting",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }))


def _resume(env):
    return subprocess.run([sys.executable, str(run_bin(env)), "smoke", "--resume", "planted-run"], capture_output=True, text=True, env=env, timeout=300)


def test_resume_replaces_a_reaped_binding(tmp_path):
    env = runner_env(tmp_path)
    session = _first_session(env)
    peer = _plant_peer_lease(env, session)
    # The reap: the bound session stopped, its lease record
    # deleted on the confirmed-absent reading.
    _stop_fake(env, session)
    (Path(env["VENUE_RUNNER_VAR"]) / f"lease-{session}.json").unlink()
    _plant_bound_run(env, session)
    r = _resume(env)
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.loads((runs_dir(env) / "planted-run.json").read_text())
    assert rec["state"] == "complete"
    assert rec["session"] == peer, "the resume stayed bound to the reaped session"
    journal = rec["binding_replaced"]
    assert journal["from"] == session and journal["to"] == peer
    assert "no lease record" in journal["evidence"]
    assert rec["session_pin"] == peer


def test_resume_refuses_an_unconfirmed_absence(tmp_path):
    env = runner_env(tmp_path)
    session = _first_session(env)
    _plant_peer_lease(env, session)
    # Absent from the live list but unconfirmed: the lease
    # record stands and no absence stamp exists — a flicker
    # reading, which must refuse, never re-place.
    _stop_fake(env, session)
    _plant_bound_run(env, session)
    r = _resume(env)
    assert r.returncode == 1, r.stdout + r.stderr
    rec = json.loads((runs_dir(env) / "planted-run.json").read_text())
    assert rec["state"] == "failed"
    assert "pin-unavailable" in rec["error"]
    assert "binding_replaced" not in rec
    assert not rec.get("launch_confirmed_at"), "a refused resume launched anyway"
