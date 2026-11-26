"""Local poll reader pass (launch-path plan, Step 2b):
bin/local-run accepts no record face — not even a terminal
one — before the container's exit file has had its say.

The specimen is the decxc shape: the record face reads
"orphaned" while the run dir holds exit 0; the poll pass
finalizes it complete. The negative halves: a face the
exit file confirms stands untouched (no second finalize),
and a non-exit reading never rewrites a face.

The entry point is loaded by path and its seams stubbed:
the record store, the target resolution, the transport,
the container reader, and the shared finalize (whose own
pins live in test_local_record_truth.py).

The warmup pins: a poll's "unknown" readings retry inside
the call on the bounded backoff before the unreachable
face is served — the read-side sibling of the launch
path's Step 3 warmup retry (test_local_launch_warmup.py).

The confirmation pins: every terminal verdict — a poll's
finalize, a reader-pass re-derive — stands on two
independent reads of the run's own exit file agreeing on
the code; a contested read serves no verdict.

The attach pins: an invocation carrying --poll/--wait
attaches to an existing run (a run id, or a job name's
newest run) wherever the flag sits, and never dispatches
— the job-first form that once re-fired the job is the
headline case.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

RID = "greenfield-ci-decxc-lcheck-local-20261124T161808Z"
TARGET = {"host": "machine.invalid", "user": "agent"}


def load_local_run(monkeypatch, rec, reading):
    mod, finalized, _reads = load_local_run_seq(monkeypatch, rec, [reading])
    return mod, finalized


def load_local_run_seq(monkeypatch, rec, readings):
    """The poll harness over a readings sequence: each
    read_run_state call serves the next reading (the last
    repeats), the calls are logged, and the module's sleep
    is neutralized so the warmup backoff costs no wall
    time. A single-reading load is the one-element form."""
    mod = load_module("local_run_poll_unit", REPO / "bin" / "local-run")
    finalized = []
    reads = []

    def fake_finalize(r, rd):
        finalized.append((r["run_id"], rd["exit_code"]))
        state = "complete" if rd["exit_code"] == 0 else "failed"
        r.update(state=state, exit_code=rd["exit_code"], finished_at=rd.get("finished_at"))
        return state

    def fake_read(repo, r, target=None):
        reads.append(r["run_id"])
        return readings[min(len(reads) - 1, len(readings) - 1)]

    monkeypatch.setattr(mod, "load_run_record", lambda run_id: rec)
    monkeypatch.setattr(mod, "_record_target", lambda r: TARGET)
    monkeypatch.setattr(mod, "finalize_local_record", fake_finalize)
    monkeypatch.setattr(mod.local_venue, "ensure_transport", lambda target: True)
    monkeypatch.setattr(mod.local_venue, "read_run_state", fake_read)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    return mod, finalized, reads


def _poll(monkeypatch, mod, capsys):
    monkeypatch.setattr(sys, "argv", ["local-run", "--poll", RID])
    rc = mod.main()
    return rc, json.loads(capsys.readouterr().out)


def test_decxc_shape_orphan_face_rederived_complete(tmp_path, monkeypatch, capsys):
    """Face "orphaned", run dir holding exit 0: the poll
    re-derives the record complete from the container and
    serves the derived state, not the face."""
    rec = {"run_id": RID, "job": "greenfield-ci-decxc-lcheck", "venue": "local", "state": "orphaned"}
    reading = {"reading": "exit", "exit_code": 0, "finished_at": "2026-11-24T16:19:00+00:00", "output_tail": "ok\n"}
    mod, finalized = load_local_run(monkeypatch, rec, reading)
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 0
    assert out == {"run_id": RID, "state": "complete", "exit_code": 0, "rederived": True}
    assert finalized == [(RID, 0)]
    assert rec["state"] == "complete" and rec["finished_at"] == "2026-11-24T16:19:00+00:00"


def test_confirmed_face_stands_without_second_finalize(tmp_path, monkeypatch, capsys):
    """Face complete with exit 0, container agreeing: the
    face is served as written and the finalize never runs
    again (no second terminal transition)."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "complete", "exit_code": 0}
    reading = {"reading": "exit", "exit_code": 0, "finished_at": "2026-11-24T16:19:00+00:00", "output_tail": ""}
    mod, finalized = load_local_run(monkeypatch, rec, reading)
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 0
    assert out == {"run_id": RID, "state": "complete"}
    assert finalized == []


def test_non_exit_reading_leaves_face_alone(tmp_path, monkeypatch, capsys):
    """Container unreadable at poll time: the terminal
    face stands — a lost read is never a verdict in
    either direction."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "orphaned"}
    mod, finalized = load_local_run(monkeypatch, rec, {"reading": "unknown"})
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 1
    assert out == {"run_id": RID, "state": "orphaned"}
    assert finalized == []


def test_poll_finalizes_running_record_from_exit_file(tmp_path, monkeypatch, capsys):
    """The non-terminal poll: a running record whose run
    dir holds exit 3 finalizes failed through the shared
    finalize, and the poll reports the derived state."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "running"}
    reading = {"reading": "exit", "exit_code": 3, "finished_at": "2026-11-24T16:19:00+00:00", "output_tail": "boom\n"}
    mod, finalized = load_local_run(monkeypatch, rec, reading)
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 0
    assert out == {"run_id": RID, "state": "failed", "exit_code": 3}
    assert finalized == [(RID, 3)]


def test_poll_retries_an_unknown_reading_through_warmup(tmp_path, monkeypatch, capsys):
    """Warmup: the transport's port answers but SSH does
    not yet carry — the first reads come back "unknown"
    and the resolved reading behind them is the poll's
    answer, served inside the one call (the read-side
    sibling of the launch path's Step 3 retry)."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "running"}
    exit_reading = {"reading": "exit", "exit_code": 0, "finished_at": "2026-11-24T16:19:00+00:00", "output_tail": "ok\n"}
    mod, finalized, reads = load_local_run_seq(
        monkeypatch, rec, [{"reading": "unknown"}, {"reading": "unknown"}, exit_reading])
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 0
    assert out == {"run_id": RID, "state": "complete", "exit_code": 0}
    assert finalized == [(RID, 0)]
    # Three reads to the resolved reading, plus the one
    # confirmation read behind the verdict.
    assert len(reads) == 4


def test_poll_contested_exit_reading_serves_no_verdict(tmp_path, monkeypatch, capsys):
    """The phantom-verdict pin: a first read reporting an
    exit the confirmation read contradicts (a different
    code, or no exit file at all) finalizes nothing and
    is served as running with the unconfirmed flag — a
    single anomalous read never carries a verdict, and
    the next poll cycle reads the file again."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "running"}
    phantom = {"reading": "exit", "exit_code": 7, "finished_at": "2026-11-24T16:19:00+00:00", "output_tail": ""}
    truth_zero = {"reading": "exit", "exit_code": 0, "finished_at": "2026-11-24T16:20:00+00:00", "output_tail": ""}
    mod, finalized, _reads = load_local_run_seq(monkeypatch, rec, [phantom, truth_zero])
    rc, out = _poll(monkeypatch, mod, capsys)
    # BT5 (unified argv plan): the still-running poll exit is
    # 3 on both run twins — this pin read 0 before the token.
    assert rc == 3
    assert out == {"run_id": RID, "state": "running", "exit_unconfirmed": True}
    assert finalized == []
    mod, finalized, _reads = load_local_run_seq(monkeypatch, rec, [phantom, {"reading": "running"}])
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 3
    assert out == {"run_id": RID, "state": "running", "exit_unconfirmed": True}
    assert finalized == []


def test_poll_agreeing_confirmation_finalizes(tmp_path, monkeypatch, capsys):
    """Two independent reads agreeing on the code are
    the verdict: the finalize runs on the agreed code."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "running"}
    reading = {"reading": "exit", "exit_code": 7, "finished_at": "2026-11-24T16:19:00+00:00", "output_tail": "boom\n"}
    mod, finalized, reads = load_local_run_seq(monkeypatch, rec, [reading, dict(reading)])
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 0
    assert out == {"run_id": RID, "state": "failed", "exit_code": 7}
    assert finalized == [(RID, 7)]
    assert len(reads) == 2


def test_rederive_contested_exit_leaves_face_alone(tmp_path, monkeypatch, capsys):
    """The reader pass over a terminal face holds the
    same line: an exit reading the confirmation read
    contradicts does not rewrite the face."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "orphaned"}
    phantom = {"reading": "exit", "exit_code": 0, "finished_at": "2026-11-24T16:19:00+00:00", "output_tail": ""}
    mod, finalized, _reads = load_local_run_seq(monkeypatch, rec, [phantom, {"reading": "running"}])
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 1
    assert out == {"run_id": RID, "state": "orphaned"}
    assert finalized == []


def test_poll_unknown_reading_bounded_then_unreachable(tmp_path, monkeypatch, capsys):
    """A reading lost on every attempt is served as
    before — running with the unreachable flag, nothing
    finalized — and the retry is bounded: attempts are
    the backoff count plus the first read, never more."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "running"}
    mod, finalized, reads = load_local_run_seq(monkeypatch, rec, [{"reading": "unknown"}])
    rc, out = _poll(monkeypatch, mod, capsys)
    # BT5: still running exits 3 (was 0 before the token).
    assert rc == 3 and out == {"run_id": RID, "state": "running", "venue_unreachable": True}
    assert finalized == []
    assert len(reads) == len(mod.READ_BACKOFF_S) + 1


def load_local_run_jobs(monkeypatch, tmp_path, records, readings):
    """The attach-resolution harness: records is a
    {run_id: rec} dict the stubbed loader reads, the
    module's RUNS is a real directory holding one file
    per record (the job scan globs it), and the container
    reader serves the readings sequence like the poll
    harness. Returns (mod, finalized, runs_dir)."""
    mod = load_module("local_run_attach_unit", REPO / "bin" / "local-run")
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    for rid in records:
        (runs_dir / f"{rid}.json").write_text("{}")
    finalized = []
    reads = []

    def fake_finalize(r, rd):
        finalized.append((r["run_id"], rd["exit_code"]))
        state = "complete" if rd["exit_code"] == 0 else "failed"
        r.update(state=state, exit_code=rd["exit_code"], finished_at=rd.get("finished_at"))
        return state

    def fake_read(repo, r, target=None):
        reads.append(r["run_id"])
        return readings[min(len(reads) - 1, len(readings) - 1)]

    monkeypatch.setattr(mod, "RUNS", runs_dir)
    monkeypatch.setattr(mod, "load_run_record", lambda run_id: records.get(run_id))
    monkeypatch.setattr(mod, "_record_target", lambda r: TARGET)
    monkeypatch.setattr(mod, "finalize_local_record", fake_finalize)
    monkeypatch.setattr(mod.local_venue, "ensure_transport", lambda target: True)
    monkeypatch.setattr(mod.local_venue, "read_run_state", fake_read)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    return mod, finalized, runs_dir


JOB = "jobx"
OLD_ID = "jobx-20261126T010000Z"
NEW_ID = "jobx-20261126T020000Z"
EXIT0 = {"reading": "exit", "exit_code": 0, "finished_at": "2026-11-26T02:05:00+00:00", "output_tail": "ok\n"}


def _job_records():
    return {
        OLD_ID: {"run_id": OLD_ID, "job": JOB, "venue": "local", "state": "complete", "exit_code": 0,
                 "started_at": "2026-11-26T01:00:00+00:00"},
        NEW_ID: {"run_id": NEW_ID, "job": JOB, "venue": "local", "state": "running",
                 "started_at": "2026-11-26T02:00:00+00:00"},
    }


def test_job_first_wait_attaches_to_newest_and_dispatches_nothing(tmp_path, monkeypatch, capsys):
    """The re-dispatch defect's pin: `local-run <job>
    --wait` attaches to the job's newest run and settles
    it — no new run is minted (the runs dir's file set is
    byte-identical after the call)."""
    mod, finalized, runs_dir = load_local_run_jobs(monkeypatch, tmp_path, _job_records(), [EXIT0, EXIT0])
    before = sorted(p.name for p in runs_dir.iterdir())
    monkeypatch.setattr(sys, "argv", ["local-run", JOB, "--wait", "--max", "60"])
    rc = mod.main()
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out == {"run_id": NEW_ID, "state": "complete", "exit_code": 0}
    assert finalized == [(NEW_ID, 0)]
    assert sorted(p.name for p in runs_dir.iterdir()) == before


def test_wait_with_job_name_attaches_to_newest(tmp_path, monkeypatch, capsys):
    """`--wait <job>` resolves the job's newest run the
    same way — the flag-first form and the job-first form
    are the one attach."""
    mod, finalized, _runs = load_local_run_jobs(monkeypatch, tmp_path, _job_records(), [EXIT0, EXIT0])
    monkeypatch.setattr(sys, "argv", ["local-run", "--wait", JOB, "--max", "60"])
    rc = mod.main()
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out == {"run_id": NEW_ID, "state": "complete", "exit_code": 0}
    assert finalized == [(NEW_ID, 0)]


def test_job_first_poll_attaches(tmp_path, monkeypatch, capsys):
    """`local-run <job> --poll` is the same attach in its
    one-shot form."""
    mod, finalized, _runs = load_local_run_jobs(monkeypatch, tmp_path, _job_records(), [EXIT0, EXIT0])
    monkeypatch.setattr(sys, "argv", ["local-run", JOB, "--poll"])
    rc = mod.main()
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out == {"run_id": NEW_ID, "state": "complete", "exit_code": 0}
    assert finalized == [(NEW_ID, 0)]


def test_attach_unknown_target_fails_without_dispatch(tmp_path, monkeypatch, capsys):
    """An attach naming nothing resolvable fails with
    the attach contract — and dispatches nothing."""
    mod, finalized, runs_dir = load_local_run_jobs(monkeypatch, tmp_path, _job_records(), [EXIT0])
    monkeypatch.setattr(sys, "argv", ["local-run", "--wait", "no-such-run-or-job"])
    rc = mod.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "attach to an existing run" in err
    assert finalized == []
    assert sorted(p.name for p in runs_dir.iterdir()) == [f"{NEW_ID}.json", f"{OLD_ID}.json"]


def test_poll_running_and_unreachable_readings(tmp_path, monkeypatch, capsys):
    """No exit file yet reads "running"; an unreadable
    container reads "running" with the unreachable flag —
    neither finalizes anything."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "running"}
    mod, finalized = load_local_run(monkeypatch, rec, {"reading": "running"})
    rc, out = _poll(monkeypatch, mod, capsys)
    # BT5: still running exits 3 (was 0 before the token).
    assert rc == 3 and out == {"run_id": RID, "state": "running"}
    mod, finalized = load_local_run(monkeypatch, rec, {"reading": "unknown"})
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 3 and out == {"run_id": RID, "state": "running", "venue_unreachable": True}
    assert finalized == []
