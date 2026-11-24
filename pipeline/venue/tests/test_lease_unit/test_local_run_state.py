"""Lease unit tests: the local container run-state reader
(launch-path plan, Step 2).

read_run_state is the tri-state truth every local finalize
path reads: "exit" (exit file present — code, output tail,
and the completion time from the exit file's own mtime),
"running" (run dir present, no exit file yet), "absent"
(no run dir), and "unknown" for everything that is not a
reading — no target, a path-unsafe run id, a failed or
garbled SSH read. A lost read is never a verdict, so every
failure face lands on "unknown", and the reader is a pure
read: it never starts a transport.
"""

import subprocess
from datetime import datetime, timezone

from unit_harness import lease, repo  # noqa: F401

TARGET = {"host": "machine.invalid", "user": "agent"}
REC = {"run_id": "job-local-20261124T171326Z", "job": "job", "shape": "local"}


class _Done:
    def __init__(self, stdout: bytes, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def _script_run(monkeypatch, lv, done=None, raises=None):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if raises is not None:
            raise raises
        return done

    monkeypatch.setattr(lv.subprocess, "run", fake_run)
    return calls


def test_exit_reading_carries_code_mtime_and_tail(repo, monkeypatch):
    lv = lease.local_venue
    mtime = 1764000000
    out = f"KIND=exit\nCODE=0\nMTIME={mtime}\nTAIL\ngate ok\nsecond line\n".encode()
    calls = _script_run(monkeypatch, lv, _Done(out))
    reading = lv.read_run_state(repo, REC, target=TARGET)
    assert reading["reading"] == "exit"
    assert reading["exit_code"] == 0
    # The completion time is the exit file's mtime, not the read's.
    assert reading["finished_at"] == datetime.fromtimestamp(mtime, timezone.utc).isoformat()
    assert reading["output_tail"] == "gate ok\nsecond line\n"
    # One SSH read of the run's own dir, nothing launched.
    assert len(calls) == 1 and REC["run_id"] in calls[0][-1]


def test_exit_reading_nonzero_code(repo, monkeypatch):
    lv = lease.local_venue
    out = b"KIND=exit\nCODE=3\nMTIME=1764000000\nTAIL\nboom\n"
    _script_run(monkeypatch, lv, _Done(out))
    reading = lv.read_run_state(repo, REC, target=TARGET)
    assert reading["reading"] == "exit" and reading["exit_code"] == 3


def test_running_and_absent_readings(repo, monkeypatch):
    lv = lease.local_venue
    _script_run(monkeypatch, lv, _Done(b"KIND=running\n"))
    assert lv.read_run_state(repo, REC, target=TARGET) == {"reading": "running"}
    _script_run(monkeypatch, lv, _Done(b"KIND=absent\n"))
    assert lv.read_run_state(repo, REC, target=TARGET) == {"reading": "absent"}


def test_failed_reads_are_unknown_never_verdicts(repo, monkeypatch):
    lv = lease.local_venue
    _script_run(monkeypatch, lv, _Done(b"", returncode=255))
    assert lv.read_run_state(repo, REC, target=TARGET) == {"reading": "unknown"}
    _script_run(monkeypatch, lv, raises=subprocess.TimeoutExpired("ssh", 90))
    assert lv.read_run_state(repo, REC, target=TARGET) == {"reading": "unknown"}
    _script_run(monkeypatch, lv, _Done(b"garbage\n"))
    assert lv.read_run_state(repo, REC, target=TARGET) == {"reading": "unknown"}
    _script_run(monkeypatch, lv, _Done(b"KIND=exit\nCODE=NaN\nMTIME=1\nTAIL\n"))
    assert lv.read_run_state(repo, REC, target=TARGET) == {"reading": "unknown"}


def test_path_unsafe_run_id_never_reaches_ssh(repo, monkeypatch):
    lv = lease.local_venue
    calls = _script_run(monkeypatch, lv, _Done(b"KIND=exit\nCODE=0\nMTIME=1\nTAIL\n"))
    rec = dict(REC, run_id="../escape")
    assert lv.read_run_state(repo, rec, target=TARGET) == {"reading": "unknown"}
    assert calls == []


def test_no_target_resolves_unknown(repo, monkeypatch):
    """A repo with no local target configured: the reader
    reports unknown rather than guessing a machine."""
    lv = lease.local_venue
    calls = _script_run(monkeypatch, lv, _Done(b"KIND=running\n"))
    assert lv.read_run_state(repo, REC) == {"reading": "unknown"}
    assert calls == []
