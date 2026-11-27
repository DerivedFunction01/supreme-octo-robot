"""The stale-"running" verdict reads before it writes off
(VENUE DEFECT 2, leg c).

The pins: a stale "running" record is decided by one reader
pass over the session its launch landed on (launch_session),
never by the record's current binding and never by time
alone. A footprint rescues the record to "polling" with the
confirmation stamped; a readable total absence is the proven
no-launch and the launch-lost write-off proceeds; an
unreadable pass (a timeout is a lost response, not a proven
negative) leaves the record exactly as it stood, collectable
by a later pass. And the orphan test itself keys on the
launch session: a launched record whose binding was
re-stamped by a dead resume is not orphaned while its launch
session lives. These drive sweep.py + reader.py against a
stub foundation rooted in a tmp dir, test_daemon_orphans'
loader shape.
"""

import json
import os
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402


def _json_object_from_output(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON object in output")


class _LeaseFoundation:
    ABSENT_CONFIRM_S = 900

    def __init__(self):
        self.stamped = []

    def clear_absent_stamp(self, repo, session):
        pass

    def absent_since(self, repo, session):
        return None

    def stamp_absent(self, repo, session, since, at):
        self.stamped.append(session)


class _Lease:
    def __init__(self, live):
        self._live = live
        self.foundation = _LeaseFoundation()

    def live_sessions(self, colab, repo):
        return [{"session": s} for s in self._live]


class ReaderColab:
    """Answers the reader exec from a scripted outcome:
    ("state", dict) renders the reader's JSON, ("timeout",)
    raises — the lost response."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.sessions = []

    def __call__(self, *argv, timeout=None):
        assert argv[0] == "exec", argv
        self.sessions.append(argv[argv.index("-s") + 1])
        if self.outcome[0] == "timeout":
            raise subprocess.TimeoutExpired(argv, timeout)
        return subprocess.CompletedProcess(argv, 0, json.dumps(self.outcome[1]) + "\n", "")


def load_sweep(runs: Path, root: Path, live: set, colab):
    os.environ["VENUE_RUNNER_VAR"] = str(root / "var")
    package = types.ModuleType("runner_rescue_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_rescue_unit"] = package
    foundation = types.ModuleType("runner_rescue_unit.foundation")
    foundation.REPO = root
    foundation.RUNS = runs
    foundation.VENUE = "test-venue"
    foundation.now = lambda: "2026-11-24T13:00:00+00:00"
    foundation.staged_write = lambda path, data: Path(path).write_bytes(data)
    foundation.epoch = lambda v: datetime.fromisoformat(str(v)).timestamp() if v else None
    foundation.colab = colab
    foundation.json_object_from_output = _json_object_from_output
    foundation.lease = _Lease(live)
    sys.modules["runner_rescue_unit.foundation"] = foundation
    load_module("runner_rescue_unit.records", REPO / "sync" / "runner" / "records.py", register=True)
    load_module("runner_rescue_unit.claims", REPO / "sync" / "runner" / "claims.py", register=True)
    load_module("runner_rescue_unit.reader", REPO / "sync" / "runner" / "reader.py", register=True)
    sweep = load_module("runner_rescue_unit.sweep", REPO / "sync" / "runner" / "sweep.py", register=True)
    return sweep, foundation.lease


def _plant(runs: Path, rec: dict) -> None:
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{rec['run_id']}.json").write_text(json.dumps(rec))


def _read(runs: Path, run_id: str) -> dict:
    return json.loads((runs / f"{run_id}.json").read_text())


def _stale_running(run_id, **over):
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    rec = {
        "run_id": run_id, "job": "job", "state": "running",
        "session": "live-session", "remote_out": f"out-{run_id}",
        "started_at": old, "last_evidence_at": old,
    }
    rec.update(over)
    return rec


FOOTPRINT = {"job_pids": ["4242"], "exit_stamp": None, "job_log_tail": [], "checkpoint": None}
ABSENT = {"job_pids": [], "exit_stamp": None, "job_log_tail": [], "checkpoint": None}


def test_footprint_on_the_launch_session_rescues_the_record(tmp_path):
    """The storm form: the launch landed, the confirming
    client died, and a later resume re-stamped the record's
    binding with a dead name. The sweep's reader pass reads
    the LAUNCH session, finds the footprint, and the record
    moves to polling — not failed."""
    runs = tmp_path / "runs"
    colab = ReaderColab(("state", FOOTPRINT))
    sweep, _lease = load_sweep(runs, tmp_path, {"live-session"}, colab)
    rid = "job-20261124T100000Z"
    _plant(runs, _stale_running(rid, session="dead-binding", launch_session="live-session"))
    findings, live_ok = sweep.orphan_sweep()
    assert live_ok
    assert colab.sessions == ["live-session"], "the reader pass read the binding, not the launch session"
    rec = _read(runs, rid)
    assert rec["state"] == "polling"
    assert rec["launch_confirmed_at"] == "2026-11-24T13:00:00+00:00"
    assert "launch_lost" not in rec
    assert any(f["run_id"] == rid and "launch confirmed" in f["action"] for f in findings)


def test_readable_absence_writes_off_launch_lost(tmp_path):
    """The proven no-launch: the launch session reads back
    with no footprint at all, so the stale-running write-off
    proceeds as before, its error now naming the read."""
    runs = tmp_path / "runs"
    colab = ReaderColab(("state", ABSENT))
    sweep, _lease = load_sweep(runs, tmp_path, {"live-session"}, colab)
    rid = "job-20261124T100100Z"
    _plant(runs, _stale_running(rid, launch_session="live-session"))
    findings, live_ok = sweep.orphan_sweep()
    assert live_ok
    rec = _read(runs, rid)
    assert rec["state"] == "failed"
    assert rec["launch_lost"] is True
    assert "no job footprint" in rec["error"]
    assert any(f["run_id"] == rid and "launch-lost" in f["action"] for f in findings)


def test_unreadable_pass_leaves_the_record_collectable(tmp_path):
    """The confirmation timeout alone: the reader pass loses
    its response, the verdict is unknown, and the record
    stands exactly as it was — still "running", unwritten
    off, for a later pass to decide."""
    runs = tmp_path / "runs"
    colab = ReaderColab(("timeout",))
    sweep, _lease = load_sweep(runs, tmp_path, {"live-session"}, colab)
    rid = "job-20261124T100200Z"
    _plant(runs, _stale_running(rid, launch_session="live-session"))
    findings, live_ok = sweep.orphan_sweep()
    assert live_ok
    rec = _read(runs, rid)
    assert rec["state"] == "running"
    assert "launch_lost" not in rec and "error" not in rec
    assert not any(f["run_id"] == rid for f in findings)


def test_orphan_test_keys_on_the_launch_session(tmp_path):
    """A polling record whose binding names a dead session
    but whose launch session is live is not orphaned and
    starts no absence clock: the launch session is the
    record's session for reconcile purposes."""
    runs = tmp_path / "runs"
    colab = ReaderColab(("state", FOOTPRINT))
    sweep, lease = load_sweep(runs, tmp_path, {"live-session"}, colab)
    rid = "job-20261124T100300Z"
    fresh = datetime.now(timezone.utc).isoformat()
    _plant(runs, {
        "run_id": rid, "job": "job", "state": "polling",
        "session": "dead-binding", "launch_session": "live-session",
        "remote_out": f"out-{rid}", "started_at": fresh, "last_evidence_at": fresh,
    })
    findings, live_ok = sweep.orphan_sweep()
    assert live_ok
    rec = _read(runs, rid)
    assert rec["state"] == "polling"
    assert "orphan_noted_at" not in rec
    assert lease.foundation.stamped == [], "an absence clock started against the dead binding"
