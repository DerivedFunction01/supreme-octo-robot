"""Local transport warmup (launch-path plan, Step 3):
bin/venue-run's launch steps retry a timeout — the
warmup signature of a managed transport still coming up —
with bounded backoff inside the same fire, and a refusal
after the bound names the warmup, not the venue.

The specimens are the five recorded dispatches whose SSH
launch timed out with the path healthy minutes later (two
uniongate dispatches; greenfield decswi T153626Z, decopco
T152912Z, decwork T150723Z), and the companion face the
plan names: records folded FAILED "venue unreachable" on
this signature over runs that had in fact landed. The
entry point is loaded by path and its SSH seam scripted:
a timeout is subprocess.TimeoutExpired out of the seam,
an answered failure is a non-zero return, and a client
that cannot run at all is OSError — the three faces the
discipline partitions on.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

REC = {"run_id": "job-local-20261124T150723Z"}
TARGET = {"host": "machine.invalid", "user": "agent"}
SCRIPT = b"#!/bin/sh\ntrue\n"


def _step_of(remote: str) -> str:
    if "mkdir" in remote:
        return "mkdir"
    if "cat >" in remote:
        return "upload"
    return "launch"


class FakeSSH:
    """A scripted _ssh seam: outcomes per step, consumed in
    order — "timeout" raises TimeoutExpired, "oserror"
    raises OSError, ("fail", stderr) answers non-zero, and
    anything past the script answers success."""

    def __init__(self, script=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls = []

    def __call__(self, target, remote, input_bytes=None, timeout=90):
        step = _step_of(remote)
        self.calls.append((step, remote))
        outcomes = self.script.get(step) or []
        outcome = outcomes.pop(0) if outcomes else "ok"
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=timeout)
        if outcome == "oserror":
            raise OSError("No such file or directory: 'ssh'")
        if isinstance(outcome, tuple):
            return subprocess.CompletedProcess(["ssh"], 1, b"", outcome[1].encode())
        return subprocess.CompletedProcess(["ssh"], 0, b"launched\n", b"")

    def count(self, step):
        return sum(1 for s, _ in self.calls if s == step)


def load_launch(monkeypatch, fake):
    mod = load_module("venue_run_warmup_unit", REPO / "bin" / "venue-run")
    monkeypatch.setattr(mod, "_ssh", fake)
    monkeypatch.setattr(mod, "LAUNCH_BACKOFF_S", (0, 0))
    return mod


def test_timeout_on_any_step_recovers_inside_the_same_fire(monkeypatch):
    """Each launch step, timed out once, is retried inside
    the fire and the launch confirms: the step that timed
    out runs twice, the steps that answered run once — a
    retry resumes the sequence where the timeout fell."""
    for step in ("mkdir", "upload", "launch"):
        fake = FakeSSH({step: ["timeout"]})
        mod = load_launch(monkeypatch, fake)
        assert mod._launch(REC, SCRIPT, TARGET) is None
        assert fake.count(step) == 2, step
        for other in ("mkdir", "upload", "launch"):
            if other != step:
                assert fake.count(other) == 1, (step, other)


def test_the_five_specimen_timeouts_all_land_on_retry(monkeypatch):
    """The five recorded specimens' shared shape — one
    timeout somewhere in the launch sequence, the path
    healthy on the next attempt — succeeds on retry in the
    fake, five fires in a row."""
    steps = ["mkdir", "upload", "launch", "mkdir", "launch"]
    for step in steps:
        fake = FakeSSH({step: ["timeout", "timeout"]})
        mod = load_launch(monkeypatch, fake)
        assert mod._launch(REC, SCRIPT, TARGET) is None, step
        assert fake.count(step) == 3, step


def test_warmup_exhaustion_refuses_naming_the_warmup(monkeypatch):
    """A step that times out on every attempt refuses —
    and the refusal names the warmup, never the venue:
    "unreachable" is a different face and must not certify
    a healthy venue dead. The sequence stops at the
    exhausted step; later steps never run."""
    fake = FakeSSH({"mkdir": ["timeout"] * 10})
    mod = load_launch(monkeypatch, fake)
    err = mod._launch(REC, SCRIPT, TARGET)
    assert err is not None and err.startswith("venue warmup:"), err
    assert "unreachable" not in err
    assert fake.count("mkdir") == mod.LAUNCH_ATTEMPTS
    assert fake.count("upload") == 0 and fake.count("launch") == 0


def test_client_failure_is_unreachable_not_warmup(monkeypatch):
    """OSError out of the seam — the ssh client itself
    could not run — is not the warmup signature: it refuses
    at once, unretried, under the unreachable name, and
    the warmup is named only when the signature matches."""
    fake = FakeSSH({"mkdir": ["oserror"]})
    mod = load_launch(monkeypatch, fake)
    err = mod._launch(REC, SCRIPT, TARGET)
    assert err is not None and err.startswith("venue unreachable:"), err
    assert "warmup" not in err
    assert len(fake.calls) == 1


def test_answered_failure_refuses_without_retry(monkeypatch):
    """A step that answers non-zero has spoken: its own
    refusal stands, unretried — the warmup discipline
    retries silence (a timeout), not answers."""
    fake = FakeSSH({"mkdir": [("fail", "permission denied")]})
    mod = load_launch(monkeypatch, fake)
    err = mod._launch(REC, SCRIPT, TARGET)
    assert err is not None and err.startswith("venue mkdir failed:"), err
    assert fake.count("mkdir") == 1


def test_launch_step_is_marker_guarded_against_a_double_start(monkeypatch):
    """A launch attempt that timed out client-side may
    have started the job on the venue; the launch step's
    remote is guarded by the .launched marker, so the
    retry confirms that launch instead of starting a
    second copy beside it."""
    fake = FakeSSH({"launch": ["timeout"]})
    mod = load_launch(monkeypatch, fake)
    assert mod._launch(REC, SCRIPT, TARGET) is None
    launch_remotes = [remote for step, remote in fake.calls if step == "launch"]
    assert len(launch_remotes) == 2
    for remote in launch_remotes:
        assert "if [ ! -f .launched ]" in remote and "touch .launched" in remote
