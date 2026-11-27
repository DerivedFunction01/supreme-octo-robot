"""Local launch TMPDIR default (scratch-discipline cure):
the container's /tmp is a capped tmpfs shared across every
tenant, and a job shard whose scratch rides os.tmpdir()
can exhaust it for all of them — so the local launch puts
every job's scratch in its own run dir by construction.

The pins: the mkdir step creates the run dir's tmp subdir
before the script runs; the launch environment the job
sees names that subdir as TMPDIR ($PWD/tmp, expanded by
the launch wrapper's shell in the run dir), beside the
share stamp when one rides; the stamp is a default a job
overrides by exporting its own TMPDIR in its script —
ordinary shell semantics, stated here so the form is a
decision, not an accident. The envelope form carries the
same discipline per job: the generated launcher stamps
TMPDIR=$PWD/tmp into each job's env (expanded after the
job subshell's cd, naming the job's own subdir) and the
envelope's mkdir step creates each job's tmp subdir. The
entry point is loaded by path and its SSH seam scripted,
as in the root-pid suite.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

from sync.runner import envelope_dispatch  # noqa: E402

TARGET = {"host": "machine.invalid", "user": "agent"}
SCRIPT = b"#!/bin/sh\ntrue\n"


def _step_of(remote: str) -> str:
    if "mkdir" in remote:
        return "mkdir"
    if "cat >" in remote:
        return "upload"
    return "launch"


class FakeSSH:
    def __init__(self):
        self.calls = []

    def __call__(self, target, remote, input_bytes=None, timeout=90):
        step = _step_of(remote)
        self.calls.append((step, remote))
        out = b"launched\n" if step == "launch" else b""
        return subprocess.CompletedProcess(["ssh"], 0, out, b"")

    def remote(self, step):
        return next(remote for s, remote in self.calls if s == step)


def load_launch(monkeypatch, fake):
    mod = load_module("venue_run_tmpdir_unit", REPO / "bin" / "venue-run")
    monkeypatch.setattr(mod, "_ssh", fake)
    monkeypatch.setattr(mod, "LAUNCH_BACKOFF_S", (0, 0))
    return mod


def test_mkdir_creates_the_run_dirs_tmp_subdir(monkeypatch):
    """The tmp subdir exists before the job's script runs:
    the mkdir step — the launch sequence's first step —
    creates it beside the run dir itself."""
    fake = FakeSSH()
    mod = load_launch(monkeypatch, fake)
    rec = {"run_id": "job-local-20261127T120000Z"}
    assert mod._launch(rec, SCRIPT, TARGET) is None
    remote = fake.remote("mkdir")
    assert "mkdir -p " in remote
    assert "runs/job-local-20261127T120000Z/tmp" in remote
    steps = [s for s, _ in fake.calls]
    assert steps.index("mkdir") < steps.index("launch")


def test_launch_env_names_the_run_dir_tmpdir(monkeypatch):
    """The environment the job sees names the run dir's
    tmp subdir: TMPDIR rides the launch wrapper's env
    prefix ahead of bash run.sh, so os.tmpdir() in the
    job resolves there without the job doing anything."""
    fake = FakeSSH()
    mod = load_launch(monkeypatch, fake)
    rec = {"run_id": "job-local-20261127T120000Z"}
    assert mod._launch(rec, SCRIPT, TARGET) is None
    remote = fake.remote("launch")
    assert "TMPDIR=$PWD/tmp bash run.sh" in remote


def test_tmpdir_rides_beside_the_share_stamp(monkeypatch):
    """A dispatch the venue-state surface sized still
    carries the TMPDIR default, with the share stamp
    beside it in the same env prefix."""
    fake = FakeSSH()
    mod = load_launch(monkeypatch, fake)
    rec = {
        "run_id": "job-local-20261127T120000Z",
        "share": {"basis": "state", "workers": 6},
    }
    assert mod._launch(rec, SCRIPT, TARGET) is None
    remote = fake.remote("launch")
    assert "TMPDIR=$PWD/tmp GATE_WORKERS=6 bash run.sh" in remote


def _envelope_jobs():
    stamps = {"workers": 1, "thread_share": 384, "pool_cap": 384}
    return [
        {"name": "job-a", "index": 0, "stamps": dict(stamps)},
        {"name": "job-b", "index": 1, "stamps": dict(stamps)},
    ]


def test_envelope_launcher_stamps_tmpdir_per_job():
    """The generated launcher carries the discipline per
    job: every job's env names its own subdir's tmp —
    $PWD/tmp expanded after that job subshell's cd."""
    text = envelope_dispatch.envelope_launcher(_envelope_jobs()).decode()
    assert text.count("TMPDIR=$PWD/tmp") == 2
    for line in text.splitlines():
        if "exec env" in line:
            assert "TMPDIR=$PWD/tmp" in line


def test_envelope_mkdir_creates_each_jobs_tmp_subdir():
    """The envelope launch's mkdir step creates every
    job's tmp subdir before the launcher ships, so the
    stamped TMPDIR names a directory that exists."""
    fake = FakeSSH()
    jobs = [
        dict(job, script=SCRIPT, uploads=[]) for job in _envelope_jobs()
    ]
    rec = {"run_id": "env-20261127T120000Z"}

    def launch_step(step):
        return step(), False

    err = envelope_dispatch.launch_envelope(rec, jobs, TARGET, fake, launch_step)
    assert err is None
    remote = fake.remote("mkdir")
    assert "runs/env-20261127T120000Z/job-a/tmp" in remote
    assert "runs/env-20261127T120000Z/job-b/tmp" in remote
