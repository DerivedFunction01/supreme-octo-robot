"""Daemon-orphaned launches: the sweep's decidable cure for
daemonized fires whose daemon died silently.

A daemonized record carries its daemon child's pid as the
driver stamp. When that pid is provably dead and the launch
never began, the record is decidable as lost NOW — not after
the stale-starting branch's two-hour time proxy — and the
sweep closes it launch-lost. The negative half is the
opposite specimen: a daemon queued behind the session
launch lock sits in "starting" with its pid alive, healthy
at any age, and neither the new branch nor the time proxy
may touch it. These pins drive sweep.py against a stub
foundation rooted in a tmp dir, test_claims' loader shape.
"""

import json
import os
import subprocess as sp
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402


def _dead_pid() -> int:
    p = sp.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class _LeaseFoundation:
    ABSENT_CONFIRM_S = 900

    def clear_absent_stamp(self, repo, session):
        pass

    def absent_since(self, repo, session):
        return None

    def stamp_absent(self, repo, session, since, at):
        pass


class _Lease:
    foundation = _LeaseFoundation()

    def __init__(self, live):
        self._live = live

    def live_sessions(self, colab, repo):
        return [{"session": s} for s in self._live]


def load_sweep(runs: Path, var: Path, live: set):
    os.environ["COLAB_RUNNER_VAR"] = str(var)
    package = types.ModuleType("runner_sweep_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_sweep_unit"] = package
    foundation = types.ModuleType("runner_sweep_unit.foundation")
    foundation.REPO = REPO
    foundation.RUNS = runs
    foundation.VENUE = "test-venue"
    foundation.now = lambda: "2026-11-23T00:00:00+00:00"
    foundation.staged_write = lambda path, data: Path(path).write_bytes(data)
    foundation.epoch = lambda v: datetime.fromisoformat(str(v)).timestamp() if v else None

    def _json_object_from_output(stdout):
        # The production helper's shape, mirrored (sync/cli.py
        # via the foundation's re-export): the JSON object
        # starting at the output's first '{', exactly one
        # value, trailing chatter ignored; ValueError when no
        # complete object is present. reader.py — loaded in
        # this chain through sweep.py — imports it from the
        # foundation; the stub never carried it, and every
        # test in this file died at the load.
        data, _end = json.JSONDecoder().raw_decode(stdout[stdout.index("{"):])
        if not isinstance(data, dict):
            raise ValueError("CLI output's first JSON value is not an object")
        return data

    foundation.json_object_from_output = _json_object_from_output
    foundation.colab = None
    foundation.lease = _Lease(live)
    sys.modules["runner_sweep_unit.foundation"] = foundation
    load_module("runner_sweep_unit.records", REPO / "sync" / "runner" / "records.py", register=True)
    load_module("runner_sweep_unit.claims", REPO / "sync" / "runner" / "claims.py", register=True)
    return load_module("runner_sweep_unit.sweep", REPO / "sync" / "runner" / "sweep.py", register=True)


def _plant(runs: Path, rec: dict, age_file: bool = False) -> Path:
    runs.mkdir(parents=True, exist_ok=True)
    p = runs / f"{rec['run_id']}.json"
    p.write_text(json.dumps(rec))
    if age_file:
        old = datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp()
        os.utime(p, (old, old))
    return p


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(runs: Path, run_id: str) -> dict:
    return json.loads((runs / f"{run_id}.json").read_text())


def test_starting_dead_daemon_terminalized_promptly(tmp_path):
    """Fresh stamps, dead driver, no launch: the time proxy
    cannot fire (the record is seconds old), so only the
    daemon-orphan branch can close it — and it does."""
    runs = tmp_path / "runs"
    sweep = load_sweep(runs, tmp_path / "var", {"live-session"})
    pid = _dead_pid()
    rid = "job-20261123T100000Z"
    _plant(runs, {"run_id": rid, "job": "job", "state": "starting", "session": "live-session", "started_at": _now(), "daemon_child_pid": pid})
    findings, live_ok = sweep.orphan_sweep()
    assert live_ok
    rec = _read(runs, rid)
    assert rec["state"] == "failed"
    assert rec["launch_lost"] is True
    assert str(pid) in rec["error"] and "daemon driver" in rec["error"]
    assert any(f["run_id"] == rid and "daemon-orphaned" in f["action"] for f in findings)


def test_starting_live_daemon_untouched_at_any_age(tmp_path):
    """The opposite specimen: a daemon queued behind the
    session launch lock — pid alive, stamps ancient, file
    ancient. Neither the daemon-orphan branch nor the
    stale-starting time proxy may touch a live driver."""
    runs = tmp_path / "runs"
    sweep = load_sweep(runs, tmp_path / "var", {"live-session"})
    rid = "job-20261123T100001Z"
    _plant(
        runs,
        {"run_id": rid, "job": "job", "state": "starting", "session": "live-session", "started_at": "2000-01-01T00:00:00+00:00", "last_evidence_at": "2000-01-01T00:00:00+00:00", "daemon_child_pid": os.getpid()},
        age_file=True,
    )
    findings, _ = sweep.orphan_sweep()
    assert _read(runs, rid)["state"] == "starting"
    assert not any(f["run_id"] == rid for f in findings)


def test_claiming_lost_claim_terminalized(tmp_path):
    """An unadopted claim whose deadline passed with its
    child dead sat outside every sweep branch before the
    cure (the sweep keyed on starting/running/polling);
    the claim's own lost test now closes it in the sweep."""
    runs = tmp_path / "runs"
    sweep = load_sweep(runs, tmp_path / "var", set())
    rid = "job-20261123T100002Z"
    _plant(
        runs,
        {"run_id": rid, "job": "job", "state": "claiming", "started_at": _now(), "claim_by": "daemonize-parent", "claim_deadline": "2000-01-01T00:00:00+00:00", "daemon_child_pid": _dead_pid()},
    )
    findings, _ = sweep.orphan_sweep()
    rec = _read(runs, rid)
    assert rec["state"] == "failed"
    assert rec["launch_lost"] is True
    assert any(f["run_id"] == rid for f in findings)


def test_claiming_live_child_untouched(tmp_path):
    runs = tmp_path / "runs"
    sweep = load_sweep(runs, tmp_path / "var", set())
    rid = "job-20261123T100003Z"
    _plant(
        runs,
        {"run_id": rid, "job": "job", "state": "claiming", "started_at": _now(), "claim_by": "daemonize-parent", "claim_deadline": "2000-01-01T00:00:00+00:00", "daemon_child_pid": os.getpid()},
    )
    findings, _ = sweep.orphan_sweep()
    assert _read(runs, rid)["state"] == "claiming"
    assert not any(f["run_id"] == rid for f in findings)


def test_starting_dead_daemon_with_launch_begun_left_alone(tmp_path):
    """launch_at is stamped by the launch exec's own save:
    a record carrying it began its launch, and its truth is
    the running/polling reconciles' — the daemon-orphan
    branch never reaches past a begun launch."""
    runs = tmp_path / "runs"
    sweep = load_sweep(runs, tmp_path / "var", {"live-session"})
    rid = "job-20261123T100004Z"
    _plant(runs, {"run_id": rid, "job": "job", "state": "starting", "session": "live-session", "started_at": _now(), "launch_at": _now(), "daemon_child_pid": _dead_pid()})
    findings, _ = sweep.orphan_sweep()
    assert _read(runs, rid)["state"] == "starting"
    assert not any(f["run_id"] == rid for f in findings)


def test_starting_foreground_record_untouched(tmp_path):
    """No driver stamp, no daemon: a foreground launch's
    pre-launch record is governed by the time proxy exactly
    as before — fresh, it is untouched."""
    runs = tmp_path / "runs"
    sweep = load_sweep(runs, tmp_path / "var", {"live-session"})
    rid = "job-20261123T100005Z"
    _plant(runs, {"run_id": rid, "job": "job", "state": "starting", "session": "live-session", "started_at": _now()})
    findings, _ = sweep.orphan_sweep()
    assert _read(runs, rid)["state"] == "starting"
    assert not any(f["run_id"] == rid for f in findings)
