"""Local launch root-pid stamp (venue-state plan, step 2):
the job starts in the background inside the launch wrapper
so its pid is stamped to root.pid in the run dir before the
wrapper waits on it — root.pid is the root the venue-state
sampler's process-tree reads walk from — and the launch's
own SSH call reads the stamp back and carries it onto the
run record as root_pid.

The pins: the composed launch command carries the stamp
form (background start, $! captured, root.pid written
before the wait, the exit write after the wait — so the
exit file still lands only when the job finishes, with
the job's own status); a stamp the launch reads back
lands on the record as an int; a launch whose read-back
carries no pid (the stamp never landed) still confirms
and stamps nothing. The entry point is loaded by path and
its SSH seam scripted, as in the warmup suite.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

TARGET = {"host": "machine.invalid", "user": "agent"}
SCRIPT = b"#!/bin/sh\ntrue\n"


def _step_of(remote: str) -> str:
    if "mkdir" in remote:
        return "mkdir"
    if "cat >" in remote:
        return "upload"
    return "launch"


class FakeSSH:
    """A scripted _ssh seam, as in the warmup suite: the
    launch step answers with the given stdout, every other
    step with a plain success."""

    def __init__(self, launch_stdout=b"launched\n"):
        self.launch_stdout = launch_stdout
        self.calls = []

    def __call__(self, target, remote, input_bytes=None, timeout=90):
        step = _step_of(remote)
        self.calls.append((step, remote))
        out = self.launch_stdout if step == "launch" else b"launched\n"
        return subprocess.CompletedProcess(["ssh"], 0, out, b"")

    def remote(self, step):
        return next(remote for s, remote in self.calls if s == step)


def load_launch(monkeypatch, fake):
    mod = load_module("venue_run_root_pid_unit", REPO / "bin" / "venue-run")
    monkeypatch.setattr(mod, "_ssh", fake)
    monkeypatch.setattr(mod, "LAUNCH_BACKOFF_S", (0, 0))
    return mod


def test_launch_command_carries_the_pid_stamp(monkeypatch):
    """The composed launch remote stamps the job's pid:
    the job starts in the background inside the wrapper,
    $! is captured and written to root.pid, and the
    wrapper then waits on that pid. The marker guard and
    the nohup detachment are the old form's, unchanged,
    and the launch reads root.pid back in the same call."""
    fake = FakeSSH()
    mod = load_launch(monkeypatch, fake)
    rec = {"run_id": "job-local-20261126T120000Z"}
    assert mod._launch(rec, SCRIPT, TARGET) is None
    remote = fake.remote("launch")
    assert "if [ ! -f .launched ]" in remote and "touch .launched" in remote
    assert "nohup bash -c '" in remote
    assert (
        "bash run.sh > output.log 2>&1 & pid=$!; echo $pid > root.pid; wait $pid; echo $? > exit"
        in remote
    )
    assert "echo launched; cat root.pid" in remote


def test_exit_write_stays_after_the_wait(monkeypatch):
    """Exit-file semantics unchanged: root.pid is written
    before the wait (at launch), and the exit write comes
    after it — the exit file appears only when the job
    finishes, carrying the job's own status."""
    fake = FakeSSH()
    mod = load_launch(monkeypatch, fake)
    rec = {"run_id": "job-local-20261126T120000Z"}
    assert mod._launch(rec, SCRIPT, TARGET) is None
    remote = fake.remote("launch")
    assert remote.index("echo $pid > root.pid") < remote.index("wait $pid")
    assert remote.index("wait $pid") < remote.index("echo $? > exit")


def test_record_gains_root_pid_when_the_stamp_is_read(monkeypatch):
    """A launch whose read-back carries the pid stamps it
    on the record as an int — the record the dispatch
    saves as running right after _launch returns."""
    fake = FakeSSH(launch_stdout=b"launched\n4242\n")
    mod = load_launch(monkeypatch, fake)
    rec = {"run_id": "job-local-20261126T120000Z"}
    assert mod._launch(rec, SCRIPT, TARGET) is None
    assert rec["root_pid"] == 4242


def test_launch_without_a_pid_line_stamps_nothing(monkeypatch):
    """A stamp that never lands is not a launch failure:
    the launch confirms on "launched" alone and the
    record carries no root_pid."""
    fake = FakeSSH(launch_stdout=b"launched\n")
    mod = load_launch(monkeypatch, fake)
    rec = {"run_id": "job-local-20261126T120000Z"}
    assert mod._launch(rec, SCRIPT, TARGET) is None
    assert "root_pid" not in rec
