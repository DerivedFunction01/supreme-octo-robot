"""shell_job.py functional tests, run locally (bash + stdlib only).

The snippet's contract: a heredoc on stdin (or --script file) is
executed as a shell script — not Python — under the runner's
heartbeat contract: job.sh preserved verbatim, heartbeat.log streamed
and closed with a "complete" line, checkpoint.json ends at
completed_units 1 with the shell exit code, and the launcher's exit
code is the shell script's.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SNIPPET = REPO / "adapters" / "colab" / "snippets" / "channels" / "shell_job.py"


def run_job(tmp_path, stdin_text=None, extra=()):
    out = tmp_path / "job"
    r = subprocess.run(
        [sys.executable, str(SNIPPET), "--out", str(out), "--cwd", str(tmp_path), *extra],
        input=stdin_text, capture_output=True, text=True, timeout=60,
    )
    return r, out


def test_heredoc_runs_as_shell_and_propagates_exit_code(tmp_path):
    r, out = run_job(tmp_path, stdin_text="echo hello-from-shell\nexit 3\n")
    assert r.returncode == 3
    assert (out / "job.sh").read_text() == "echo hello-from-shell\nexit 3\n"
    log = (out / "heartbeat.log").read_text()
    assert "hello-from-shell" in log
    assert "complete exit_code=3" in log
    ck = json.loads((out / "checkpoint.json").read_text())
    assert ck == {"completed_units": 1, "exit_code": 3}


def test_heredoc_is_not_executed_as_python(tmp_path):
    # Python syntax in the payload must reach bash untouched: a shell
    # comment and a variable expansion prove the interpreter is bash.
    r, out = run_job(tmp_path, stdin_text="X=41\necho value=$((X + 1))\n")
    assert r.returncode == 0
    assert "value=42" in (out / "heartbeat.log").read_text()


def test_script_file_variant(tmp_path):
    payload = tmp_path / "payload.sh"
    payload.write_text("echo from-file\n")
    r, out = run_job(tmp_path, extra=("--script", str(payload)))
    assert r.returncode == 0
    assert "from-file" in (out / "heartbeat.log").read_text()


def test_empty_script_is_refused(tmp_path):
    r, _ = run_job(tmp_path, stdin_text="\n")
    assert r.returncode == 2


def test_per_run_env_from_out_name(tmp_path):
    # The runner's out dir is <job>-out-<run_id>: the payload
    # receives the run id, a per-run port base, and the work
    # root, so two runs sharing a session never share state
    # (the fixed-state half of the 2026-11-21 twin execution).
    import importlib.util

    spec = importlib.util.spec_from_file_location("shell_job_unit", SNIPPET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run_id = "gate-20261121T200238Z"
    out = tmp_path / f"gate-out-{run_id}"
    r = subprocess.run(
        [sys.executable, str(SNIPPET), "--out", str(out), "--cwd", str(tmp_path)],
        input='echo "rid=$SHELL_JOB_RUN_ID base=$SHELL_JOB_PORT_BASE work=$SHELL_JOB_WORK"\n',
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0
    log = (out / "heartbeat.log").read_text()
    assert f"rid={run_id}" in log
    assert f"base={mod.port_base_for(run_id)}" in log
    assert f"work={out}" in log
    base = mod.port_base_for(run_id)
    assert 20000 <= base < 40000 and base % 10 == 0
    assert mod.port_base_for(run_id) == base
    assert mod.run_id_for(out) == run_id
    assert mod.run_id_for(tmp_path / "job") is None
