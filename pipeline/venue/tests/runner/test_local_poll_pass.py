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
    mod = load_module("local_run_poll_unit", REPO / "bin" / "local-run")
    finalized = []

    def fake_finalize(r, rd):
        finalized.append((r["run_id"], rd["exit_code"]))
        state = "complete" if rd["exit_code"] == 0 else "failed"
        r.update(state=state, exit_code=rd["exit_code"], finished_at=rd.get("finished_at"))
        return state

    monkeypatch.setattr(mod, "load_run_record", lambda run_id: rec)
    monkeypatch.setattr(mod, "_record_target", lambda r: TARGET)
    monkeypatch.setattr(mod, "finalize_local_record", fake_finalize)
    monkeypatch.setattr(mod.local_venue, "ensure_transport", lambda target: True)
    monkeypatch.setattr(mod.local_venue, "read_run_state", lambda repo, r, target=None: reading)
    return mod, finalized


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


def test_poll_running_and_unreachable_readings(tmp_path, monkeypatch, capsys):
    """No exit file yet reads "running"; an unreadable
    container reads "running" with the unreachable flag —
    neither finalizes anything."""
    rec = {"run_id": RID, "job": "job", "venue": "local", "state": "running"}
    mod, finalized = load_local_run(monkeypatch, rec, {"reading": "running"})
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 0 and out == {"run_id": RID, "state": "running"}
    mod, finalized = load_local_run(monkeypatch, rec, {"reading": "unknown"})
    rc, out = _poll(monkeypatch, mod, capsys)
    assert rc == 0 and out == {"run_id": RID, "state": "running", "venue_unreachable": True}
    assert finalized == []
