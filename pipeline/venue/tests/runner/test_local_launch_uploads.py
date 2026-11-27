"""Local launch uploads (the mfa-drop binding): a manifest's
"uploads" stage beside the script into the run dir, each
under its own warmup-disciplined step, between the script
upload and the launch — the local form of the Colab job's
uploads, whose standing consumer is the code drop (the code
file must reach the container as a staged file, and a drop
fired without it must fail loud, never land as a no-op).

The entry point is loaded by path and its SSH seam scripted,
as in the warmup suite: a timeout is TimeoutExpired out of
the seam, an answered failure is a non-zero return.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

REC = {"run_id": "mfa-drop-local-20261125T120000Z"}
TARGET = {"host": "machine.invalid", "user": "agent"}
SCRIPT = b"#!/bin/sh\ntrue\n"
UPLOADS = [("mfa-code.txt", b"123456"), ("extra.txt", b"x")]


def _step_of(remote: str) -> str:
    if "mkdir" in remote:
        return "mkdir"
    if "mfa-code.txt" in remote:
        return "upload:mfa-code.txt"
    if "extra.txt" in remote:
        return "upload:extra.txt"
    if "cat >" in remote:
        return "upload"
    return "launch"


class FakeSSH:
    """A scripted _ssh seam, as in the warmup suite, keyed
    on the finer step names above and recording the bytes
    each step carried."""

    def __init__(self, script=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls = []

    def __call__(self, target, remote, input_bytes=None, timeout=90):
        step = _step_of(remote)
        self.calls.append((step, remote, input_bytes))
        outcomes = self.script.get(step) or []
        outcome = outcomes.pop(0) if outcomes else "ok"
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=timeout)
        if isinstance(outcome, tuple):
            return subprocess.CompletedProcess(["ssh"], 1, b"", outcome[1].encode())
        return subprocess.CompletedProcess(["ssh"], 0, b"launched\n", b"")

    def steps(self):
        return [s for s, _remote, _data in self.calls]


def load_launch(monkeypatch, fake):
    mod = load_module("venue_run_uploads_unit", REPO / "bin" / "venue-run")
    monkeypatch.setattr(mod, "_ssh", fake)
    monkeypatch.setattr(mod, "LAUNCH_BACKOFF_S", (0, 0))
    return mod


def test_uploads_stage_in_order_between_script_and_launch(monkeypatch):
    """The sequence is mkdir, script, each upload in
    manifest order under its basename with its own bytes,
    then the launch — the payload starts only once every
    staged file is in the run dir."""
    fake = FakeSSH()
    mod = load_launch(monkeypatch, fake)
    assert mod._launch(REC, SCRIPT, TARGET, UPLOADS) is None
    assert fake.steps() == [
        "mkdir",
        "upload",
        "upload:mfa-code.txt",
        "upload:extra.txt",
        "launch",
    ]
    carried = {s: data for s, _remote, data in fake.calls}
    assert carried["upload"] == SCRIPT
    assert carried["upload:mfa-code.txt"] == b"123456"
    assert carried["upload:extra.txt"] == b"x"
    for step, remote, _data in fake.calls:
        if step.startswith("upload:"):
            name = step.split(":", 1)[1]
            assert remote.startswith("cat > ")
            assert remote.endswith(f"/runs/{REC['run_id']}/{name}")


def test_upload_timeout_retries_under_the_warmup_discipline(monkeypatch):
    """An upload step that times out once is retried inside
    the same fire, like every launch step; the steps that
    answered are not repeated."""
    fake = FakeSSH({"upload:mfa-code.txt": ["timeout"]})
    mod = load_launch(monkeypatch, fake)
    assert mod._launch(REC, SCRIPT, TARGET, UPLOADS) is None
    steps = fake.steps()
    assert steps.count("upload:mfa-code.txt") == 2
    assert steps.count("mkdir") == 1
    assert steps.count("upload") == 1
    assert steps.count("launch") == 1


def test_upload_failure_refuses_naming_the_file_and_never_launches(monkeypatch):
    """An answered upload failure refuses the launch,
    naming the file that failed; the launch step never
    runs, so no payload starts half-staged."""
    fake = FakeSSH({"upload:extra.txt": [("fail", "disk full")]})
    mod = load_launch(monkeypatch, fake)
    err = mod._launch(REC, SCRIPT, TARGET, UPLOADS)
    assert err is not None and err.startswith("upload extra.txt failed:"), err
    assert "disk full" in err
    assert "launch" not in fake.steps()
