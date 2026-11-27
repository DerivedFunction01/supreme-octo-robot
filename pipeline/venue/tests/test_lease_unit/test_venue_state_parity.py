"""Colab venue-state parity (sync/lease/lifecycle/venue_state.py):
the reap pass's classification of Colab sessions from its
existing reads, into the local mechanism's state-file shape.

The pins drive pass_colab over a fixture repo: a lease
record whose live-jobs projection is backed by run records
on disk, the session snapshot's verdict passed in as the
live map — no Colab traffic, exactly the reap pass's own
inputs. The verdicts must be the classifier's own:
evidence advancing across two passes is advancing, evidence
frozen past the grace is wedged, no live jobs is idle, an
absent session's trees are gone. The fleet aggregate lands
at the "colab" key the dispatch entry reads.
"""

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unit_harness import lease, repo  # noqa: F401

venue_state = importlib.import_module("lease.lifecycle.venue_state")
foundation = importlib.import_module("lease.core.foundation")

BASE = datetime(2026, 11, 26, 20, 0, tzinfo=timezone.utc)
SESSION = "sess-parity"


def _iso(dt):
    return dt.isoformat()


def _run_record(repo, run_id, *, evidence_at, started_at=None):
    runs = Path(repo) / "results" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    rec = {
        "run_id": run_id,
        "job": "gatejob",
        "caller": "lane-a",
        "state": "running",
        "started_at": _iso(started_at or (BASE - timedelta(hours=1))),
        "last_evidence_at": _iso(evidence_at),
    }
    (runs / f"{run_id}.json").write_text(json.dumps(rec))
    return rec


def _lease_rec(run_ids):
    return {"session": SESSION, "venue": "colab", "jobs": list(run_ids)}


def _state(repo, key):
    path = foundation.var_dir(Path(repo)) / f"venue-state-{key}.json"
    return json.loads(path.read_text())


def test_advancing_evidence_verdicts_advancing(repo):
    run_id = "gatejob-20261126T190000Z"
    _run_record(repo, run_id, evidence_at=BASE - timedelta(seconds=60))
    rec = _lease_rec([run_id])
    venue_state.pass_colab(repo, [rec], {SESSION: True}, _iso(BASE))
    first = _state(repo, SESSION)
    assert first["venue"] == SESSION
    assert first["state"] == "advancing"
    assert first["jobs"][0]["verdict"] == "stalled"  # first sample: no delta yet
    _run_record(repo, run_id, evidence_at=BASE + timedelta(seconds=540))
    venue_state.pass_colab(
        repo, [rec], {SESSION: True}, _iso(BASE + timedelta(seconds=600))
    )
    second = _state(repo, SESSION)
    assert second["state"] == "advancing"
    job = second["jobs"][0]
    assert job["verdict"] == "advancing"
    assert job["cpu_delta_s"] == 600.0
    assert job["caller"] == "lane-a"
    fleet = _state(repo, "colab")
    assert fleet["venue"] == "colab" and fleet["state"] == "advancing"
    assert fleet["pids_current"] == 1


def test_frozen_evidence_past_grace_verdicts_wedged(repo):
    run_id = "gatejob-20261126T190000Z"
    _run_record(repo, run_id, evidence_at=BASE - timedelta(seconds=60))
    rec = _lease_rec([run_id])
    venue_state.pass_colab(repo, [rec], {SESSION: True}, _iso(BASE))
    venue_state.pass_colab(
        repo, [rec], {SESSION: True}, _iso(BASE + timedelta(seconds=700))
    )
    state = _state(repo, SESSION)
    assert state["state"] == "wedged"
    assert state["jobs"][0]["verdict"] == "wedged"
    assert state["jobs"][0]["cpu_delta_s"] == 0.0


def test_no_live_jobs_verdicts_idle(repo):
    rec = _lease_rec([])
    venue_state.pass_colab(repo, [rec], {SESSION: True}, _iso(BASE))
    state = _state(repo, SESSION)
    assert state["state"] == "idle"
    assert state["jobs"] == []
    assert state["pids_current"] == 0
    assert state["pids_capacity"] is None


def test_absent_session_trees_are_gone(repo):
    run_id = "gatejob-20261126T190000Z"
    _run_record(repo, run_id, evidence_at=BASE - timedelta(seconds=60))
    rec = _lease_rec([run_id])
    venue_state.pass_colab(repo, [rec], {SESSION: False}, _iso(BASE))
    state = _state(repo, SESSION)
    assert state["state"] == "idle"
    assert state["jobs"][0]["tree_alive"] is False
    assert state["jobs"][0]["verdict"] == "gone"
