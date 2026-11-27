"""Local record truth (launch-path plan, Step 2a): the
sweep reconciles local-venue records against their
container, never the Colab census.

The defect's shape: a local run's session ("local-main")
never appears in the Colab live list, so the census branch
orphaned every local run by construction — the specimens
are steampower-df-u1-gate-local-20261124T171326Z and
steampower-df124-probe3-local-20261124T171607Z, whose run
dirs completed with exit files (17:16Z / 17:20Z) while
their records froze at "running" and flipped to "orphaned"
at 17:35:41Z carrying neither exit code nor completion
time. Under the cure both finalize from their exit files
in one sweep pass, with the exit code and the exit file's
mtime as the completion time — and the census condition
that orphaned them (session absent from a readable live
list) is present in every specimen below.

The negative halves pin the bounds: an absent run dir
orphans only past the record's own timeout_s, a live run
dir freshens evidence without finalizing, and an
unreadable container reconciles nothing. These pins drive
sweep.py against a stub foundation rooted in a tmp dir,
test_stale_running_rescue's loader shape, with the lease
stub carrying a scripted local_venue reader.
"""

import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

NOW = "2026-11-24T17:40:00+00:00"


def _json_object_from_output(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON object in output")


class _LeaseFoundation:
    ABSENT_CONFIRM_S = 900

    def clear_absent_stamp(self, repo, session):
        pass

    def absent_since(self, repo, session):
        return None

    def stamp_absent(self, repo, session, since, at):
        pass


class _LocalVenue:
    def __init__(self, readings):
        self._readings = readings

    def read_run_state(self, repo, rec, target=None):
        return self._readings[rec["run_id"]]


class _Lease:
    foundation = _LeaseFoundation()

    def __init__(self, live, readings):
        self._live = live
        self.local_venue = _LocalVenue(readings)

    def live_sessions(self, colab, repo):
        if self._live is None:
            return None
        return [{"session": s} for s in self._live]


def load_sweep(runs: Path, var: Path, live, readings):
    os.environ["VENUE_RUNNER_VAR"] = str(var)
    package = types.ModuleType("runner_local_truth_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_local_truth_unit"] = package
    foundation = types.ModuleType("runner_local_truth_unit.foundation")
    foundation.REPO = REPO
    foundation.RUNS = runs
    foundation.VENUE = "test-venue"
    foundation.now = lambda: NOW
    foundation.staged_write = lambda path, data: Path(path).write_bytes(data)
    foundation.epoch = lambda v: datetime.fromisoformat(str(v)).timestamp() if v else None
    foundation.colab = None
    foundation.json_object_from_output = _json_object_from_output
    foundation.lease = _Lease(live, readings)
    sys.modules["runner_local_truth_unit.foundation"] = foundation
    load_module("runner_local_truth_unit.records", REPO / "sync" / "runner" / "records.py", register=True)
    load_module("runner_local_truth_unit.claims", REPO / "sync" / "runner" / "claims.py", register=True)
    load_module("runner_local_truth_unit.reader", REPO / "sync" / "runner" / "reader.py", register=True)
    return load_module("runner_local_truth_unit.sweep", REPO / "sync" / "runner" / "sweep.py", register=True)


def _plant(runs: Path, rec: dict) -> Path:
    runs.mkdir(parents=True, exist_ok=True)
    p = runs / f"{rec['run_id']}.json"
    p.write_text(json.dumps(rec))
    return p


def _read(runs: Path, run_id: str) -> dict:
    return json.loads((runs / f"{run_id}.json").read_text())


def _local_rec(run_id: str, job: str, started_at: str, **over) -> dict:
    rec = {"run_id": run_id, "job": job, "venue": "local", "session": "local-main",
           "state": "running", "started_at": started_at, "last_evidence_at": started_at,
           "timeout_s": 18000, "caller": "steampower"}
    rec.update(over)
    return rec


def test_u1_specimen_finalizes_from_exit_file(tmp_path):
    """steampower-df-u1-gate: run dir complete at 17:16Z
    with exit 0, record frozen at "running", session absent
    from the live census — the old sweep's orphan condition.
    The cure finalizes it complete in one pass, stamping the
    exit code and the exit file's mtime (17:16Z), not the
    sweep's clock."""
    runs = tmp_path / "runs"
    rid = "steampower-df-u1-gate-local-20261124T171326Z"
    readings = {rid: {"reading": "exit", "exit_code": 0, "finished_at": "2026-11-24T17:16:00+00:00", "output_tail": "gate ok\n"}}
    sweep = load_sweep(runs, tmp_path / "var", {"some-colab-session"}, readings)
    _plant(runs, _local_rec(rid, "steampower-df-u1-gate", "2026-11-24T17:13:26+00:00"))
    findings, live_ok = sweep.orphan_sweep()
    assert live_ok
    rec = _read(runs, rid)
    assert rec["state"] == "complete"
    assert rec["exit_code"] == 0
    assert rec["finished_at"] == "2026-11-24T17:16:00+00:00"
    assert rec["output_tail"] == "gate ok\n"
    assert any(f["run_id"] == rid and "finalized complete" in f["action"] for f in findings)


def test_probe3_specimen_finalizes_failed_with_code(tmp_path):
    """steampower-df124-probe3: same freeze, exit 1 in the
    run dir at 17:20Z. The cure finalizes it failed with
    its exit code and completion time — never orphaned."""
    runs = tmp_path / "runs"
    rid = "steampower-df124-probe3-local-20261124T171607Z"
    readings = {rid: {"reading": "exit", "exit_code": 1, "finished_at": "2026-11-24T17:20:00+00:00", "output_tail": "probe failed\n"}}
    sweep = load_sweep(runs, tmp_path / "var", {"some-colab-session"}, readings)
    _plant(runs, _local_rec(rid, "steampower-df124-probe3", "2026-11-24T17:16:07+00:00"))
    findings, _ = sweep.orphan_sweep()
    rec = _read(runs, rid)
    assert rec["state"] == "failed"
    assert rec["exit_code"] == 1
    assert rec["finished_at"] == "2026-11-24T17:20:00+00:00"
    assert any(f["run_id"] == rid and "finalized failed" in f["action"] for f in findings)


def test_local_record_finalizes_while_live_list_unreadable(tmp_path):
    """The local truth is local: an unreadable Colab census
    reconciles nothing Colab-side, but a local record still
    finalizes from its container in the same pass."""
    runs = tmp_path / "runs"
    rid = "job-local-20261124T170000Z"
    readings = {rid: {"reading": "exit", "exit_code": 0, "finished_at": "2026-11-24T17:05:00+00:00", "output_tail": ""}}
    sweep = load_sweep(runs, tmp_path / "var", None, readings)
    _plant(runs, _local_rec(rid, "job", "2026-11-24T17:00:00+00:00"))
    _plant(runs, {"run_id": "job-colab-20261124T170000Z", "job": "job", "state": "running",
                  "session": "some-colab-session", "started_at": "2026-11-24T17:00:00+00:00"})
    findings, live_ok = sweep.orphan_sweep()
    assert live_ok is False
    assert _read(runs, rid)["state"] == "complete"
    assert _read(runs, "job-colab-20261124T170000Z")["state"] == "running"
    assert any(f["run_id"] == rid for f in findings)


def test_running_reading_freshens_evidence_only(tmp_path):
    """A live run dir: the record stays "running", but its
    last_evidence_at advances on the real read — the stamp
    that never advanced is what let finished records read
    as abandoned."""
    runs = tmp_path / "runs"
    rid = "job-local-20261124T171000Z"
    readings = {rid: {"reading": "running"}}
    sweep = load_sweep(runs, tmp_path / "var", {"some-colab-session"}, readings)
    _plant(runs, _local_rec(rid, "job", "2026-11-24T17:10:00+00:00"))
    findings, _ = sweep.orphan_sweep()
    rec = _read(runs, rid)
    assert rec["state"] == "running"
    assert rec["last_evidence_at"] == NOW
    assert not any(f["run_id"] == rid for f in findings)


def test_absent_within_own_timeout_bound_spared(tmp_path):
    """No run dir yet (a launch still landing, a container
    mid-start): inside the record's own timeout_s the
    absence orphans nothing."""
    runs = tmp_path / "runs"
    rid = "job-local-20261124T173900Z"
    readings = {rid: {"reading": "absent"}}
    sweep = load_sweep(runs, tmp_path / "var", {"some-colab-session"}, readings)
    started = datetime.now(timezone.utc).isoformat()
    _plant(runs, _local_rec(rid, "job", started))
    findings, _ = sweep.orphan_sweep()
    assert _read(runs, rid)["state"] == "running"
    assert not any(f["run_id"] == rid for f in findings)


def test_absent_past_own_timeout_bound_orphans(tmp_path):
    """No run dir and the record's own budget spent: the
    orphan lands — keyed to timeout_s, not the Colab
    absence-confirm window (900 s in the stub, far below
    this record's age either way; the bound that governs
    is the record's 600 s)."""
    runs = tmp_path / "runs"
    rid = "job-local-20261124T100000Z"
    readings = {rid: {"reading": "absent"}}
    sweep = load_sweep(runs, tmp_path / "var", {"some-colab-session"}, readings)
    _plant(runs, _local_rec(rid, "job", "2026-11-24T10:00:00+00:00", timeout_s=600))
    findings, _ = sweep.orphan_sweep()
    rec = _read(runs, rid)
    assert rec["state"] == "orphaned"
    assert rec["orphan_noted_at"] == NOW
    assert rec["terminal_event_state"] == "orphaned"
    assert any(f["run_id"] == rid and "orphaned" in f["action"] for f in findings)


def test_unknown_reading_reconciles_nothing(tmp_path):
    """An unreadable container (SSH down, transport cold)
    is never a verdict: the record stands exactly as
    written, however old."""
    runs = tmp_path / "runs"
    rid = "job-local-20261124T100000Z"
    readings = {rid: {"reading": "unknown"}}
    sweep = load_sweep(runs, tmp_path / "var", {"some-colab-session"}, readings)
    _plant(runs, _local_rec(rid, "job", "2026-11-24T10:00:00+00:00", timeout_s=600))
    findings, _ = sweep.orphan_sweep()
    rec = _read(runs, rid)
    assert rec["state"] == "running"
    assert rec["last_evidence_at"] == "2026-11-24T10:00:00+00:00"
    assert not any(f["run_id"] == rid for f in findings)
