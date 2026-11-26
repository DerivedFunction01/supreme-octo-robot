"""Venue-state classification (sync/runner/venue_classify.py):
the two-sample classifier and the state-file writer.

The pins drive the classifier over hand-built sample pairs —
the dummy form the plan rules for this mechanism: no live
venue, no SSH, the samples are the recorded-shape fixtures.
Each case names the state the pair must verdict: advancing,
frozen within grace (stalled), frozen past grace (wedged),
past the record's timeout (wedged), saturated, idle,
tree-gone, the mixed pair (venue advancing, the wedged job
still carrying its verdict), and the first sample ever (no
deltas, no wedged verdicts — a classification issues on two
samples). The writer pins ride the foundation stub whose
staged_write emulates the unified writer's protocol (stage
beside, rename over): a failed write leaves the standing
state file byte-identical.
"""

import json
import os
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

T_PREV = "2026-11-26T20:00:00+00:00"
T_NOW = "2026-11-26T20:02:00+00:00"
SEEN_RECENT = "2026-11-26T19:57:00+00:00"  # age 300 s at T_NOW
SEEN_OLD = "2026-11-26T19:40:00+00:00"  # age 1320 s at T_NOW


def _load_classify():
    package = types.ModuleType("runner_vc_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_vc_unit"] = package
    foundation = types.ModuleType("runner_vc_unit.foundation")

    def _epoch(value):
        # The production foundation's epoch, mirrored.
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except (TypeError, ValueError):
            return None

    def _staged_write(path, data, mode=None):
        # The unified writer's protocol, emulated: stage the
        # complete bytes beside the target, rename over.
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.test-tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    foundation.epoch = _epoch
    foundation.staged_write = _staged_write
    sys.modules["runner_vc_unit.foundation"] = foundation
    return load_module(
        "runner_vc_unit.venue_classify",
        REPO / "sync" / "runner" / "venue_classify.py",
        register=True,
    )


vc = _load_classify()
classify = vc.classify


def _job(run_id, ticks, alive=True, pid=4242):
    return {"run_id": run_id, "root_pid": pid, "tree_alive": alive, "cpu_ticks": ticks}


def _sample(jobs, at=T_NOW, pids_current=40, pids_max=1024, **extra):
    sample = {
        "venue": "test-venue",
        "at": at,
        "pids_current": pids_current,
        "pids_max": pids_max,
        "jobs": jobs,
    }
    sample.update(extra)
    return sample


def _rec(caller="workhorse", first_seen=SEEN_RECENT, **extra):
    rec = {"caller": caller, "first_seen_at": first_seen}
    rec.update(extra)
    return rec


def test_advancing():
    prev = _sample([_job("run-a", 1000)], at=T_PREV)
    cur = _sample([_job("run-a", 1500)])
    state = classify(prev, cur, {"run-a": _rec()})
    assert state["state"] == "advancing"
    (job,) = state["jobs"]
    assert job["verdict"] == "advancing"
    assert job["cpu_s"] == 15.0
    assert job["cpu_delta_s"] == 5.0
    assert job["caller"] == "workhorse"
    assert job["root_pid"] == 4242
    assert job["tree_alive"] is True
    assert state["venue"] == "test-venue"
    assert state["sampled_at"] == T_NOW
    assert state["pids_current"] == 40
    assert state["pids_capacity"] == 1024


def test_frozen_within_grace_is_stalled():
    prev = _sample([_job("run-a", 1000)], at=T_PREV)
    cur = _sample([_job("run-a", 1000)])
    state = classify(prev, cur, {"run-a": _rec(first_seen=SEEN_RECENT)})
    (job,) = state["jobs"]
    assert job["verdict"] == "stalled"
    assert job["cpu_delta_s"] == 0.0
    # A live tree, neither wedged nor advancing-driven:
    # the venue reads advancing by the otherwise rule.
    assert state["state"] == "advancing"


def test_frozen_past_grace_is_wedged():
    prev = _sample([_job("run-a", 1000)], at=T_PREV)
    cur = _sample([_job("run-a", 1000)])
    state = classify(prev, cur, {"run-a": _rec(first_seen=SEEN_OLD)})
    (job,) = state["jobs"]
    assert job["verdict"] == "wedged"
    assert state["state"] == "wedged"


def test_frozen_past_record_timeout_is_wedged():
    # Age 300 s is inside the 600 s grace; the record's own
    # 120 s timeout is the limb that verdicts it.
    prev = _sample([_job("run-a", 1000)], at=T_PREV)
    cur = _sample([_job("run-a", 1000)])
    state = classify(prev, cur, {"run-a": _rec(first_seen=SEEN_RECENT, timeout_s=120)})
    (job,) = state["jobs"]
    assert job["verdict"] == "wedged"
    assert state["state"] == "wedged"


def test_saturated_outranks_job_states():
    prev = _sample([_job("run-a", 1000)], at=T_PREV, pids_current=880)
    cur = _sample([_job("run-a", 1500)], pids_current=900)
    state = classify(prev, cur, {"run-a": _rec()})
    assert state["state"] == "saturated"
    (job,) = state["jobs"]
    assert job["verdict"] == "advancing"
    assert state["pids_capacity"] == 1024


def test_declared_capacity_wins_over_pids_max():
    prev = _sample([], at=T_PREV, pids_current=80)
    cur = _sample([], pids_current=90, pids_declared=100)
    state = classify(prev, cur, {})
    assert state["pids_capacity"] == 100
    assert state["state"] == "saturated"


def test_idle_when_no_jobs():
    state = classify(_sample([], at=T_PREV), _sample([]), {})
    assert state["state"] == "idle"
    assert state["jobs"] == []


def test_tree_gone():
    prev = _sample([_job("run-a", 1000)], at=T_PREV)
    cur = _sample([_job("run-a", 1000, alive=False)])
    state = classify(prev, cur, {"run-a": _rec()})
    (job,) = state["jobs"]
    assert job["verdict"] == "gone"
    assert job["tree_alive"] is False
    assert job["cpu_delta_s"] is None
    assert state["state"] == "idle"


def test_mixed_advancing_and_wedged():
    prev = _sample([_job("run-a", 1000), _job("run-b", 2000, pid=5151)], at=T_PREV)
    cur = _sample([_job("run-a", 1600), _job("run-b", 2000, pid=5151)])
    records = {"run-a": _rec(), "run-b": _rec(caller="edgar", first_seen=SEEN_OLD)}
    state = classify(prev, cur, records)
    assert state["state"] == "advancing"
    verdicts = {j["run_id"]: j["verdict"] for j in state["jobs"]}
    assert verdicts == {"run-a": "advancing", "run-b": "wedged"}


def test_first_sample_ever_no_deltas_no_wedged():
    # Even a job whose stamps are past grace and timeout
    # verdicts nothing on the first sample: no delta exists
    # and a classification issues on two samples.
    cur = _sample([_job("run-a", 5000)])
    state = classify(None, cur, {"run-a": _rec(first_seen=SEEN_OLD, timeout_s=60)})
    (job,) = state["jobs"]
    assert job["verdict"] == "stalled"
    assert job["cpu_delta_s"] is None
    assert job["cpu_s"] == 50.0
    assert state["state"] == "advancing"


def test_job_absent_now_is_omitted():
    prev = _sample([_job("run-a", 1000), _job("run-b", 2000, pid=5151)], at=T_PREV)
    cur = _sample([_job("run-b", 2100, pid=5151)])
    state = classify(prev, cur, {"run-b": _rec()})
    assert [j["run_id"] for j in state["jobs"]] == ["run-b"]


def test_new_job_in_second_sample_is_stalled():
    prev = _sample([], at=T_PREV)
    cur = _sample([_job("run-a", 700)])
    state = classify(prev, cur, {"run-a": _rec(first_seen=SEEN_OLD, timeout_s=60)})
    (job,) = state["jobs"]
    assert job["verdict"] == "stalled"
    assert job["cpu_delta_s"] is None


def test_sample_hz_overrides_default():
    prev = _sample([_job("run-a", 2000)], at=T_PREV)
    cur = _sample([_job("run-a", 2500)], hz=1000)
    state = classify(prev, cur, {"run-a": _rec()})
    (job,) = state["jobs"]
    assert job["cpu_s"] == 2.5
    assert job["cpu_delta_s"] == 0.5
    assert job["verdict"] == "advancing"


def test_write_state_schema_and_name(tmp_path):
    state = classify(
        _sample([], at=T_PREV), _sample([_job("run-a", 1500)]), {"run-a": _rec()}
    )
    target = vc.write_state(state, tmp_path)
    assert target == tmp_path / "venue-state-test-venue.json"
    written = json.loads(target.read_text())
    assert set(written) == {
        "venue",
        "state",
        "sampled_at",
        "pids_current",
        "pids_capacity",
        "jobs",
    }
    (job,) = written["jobs"]
    assert set(job) == {
        "run_id",
        "caller",
        "root_pid",
        "tree_alive",
        "cpu_s",
        "cpu_delta_s",
        "verdict",
    }


def test_write_state_failure_leaves_standing_file(tmp_path):
    state = classify(None, _sample([]), {})
    target = vc.write_state(state, tmp_path)
    before = target.read_bytes()

    def _denied(path, data, mode=None):
        raise PermissionError("write denied")

    original = vc.staged_write
    vc.staged_write = _denied
    try:
        with pytest.raises(PermissionError):
            vc.write_state({**state, "state": "saturated"}, tmp_path)
    finally:
        vc.staged_write = original
    assert target.read_bytes() == before
