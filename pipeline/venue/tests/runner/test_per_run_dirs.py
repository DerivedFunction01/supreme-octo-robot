"""Per-run remote upload directories (branch transport
plan, Step 5).

The pins: an upload addressed with the run's directory
lands at /content/runs/<run_id>/<name> — plain and chunked
alike — while the no-directory form keeps the bare slot
byte-identically (test_upload_probe_retry pins that form);
the directory is created by one named exec before any
upload; manifest args naming an upload are rewritten to
the run's copy and nothing else is; the branch drive's
substrate upload and driver both address the run's
directory; and in main() the uploads stand OUTSIDE the
launch lock while the branch drive stands inside it — the
narrowed lock's scope, pinned on the source order because
the lock itself is an flock whose coverage is the order
of the calls around it.
"""

import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

DEST = "wrap.py"
SIZE = 2788
SHA = "0123456789abcdef0123456789abcdef01234567"


def _json_object_from_output(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON object in output")


class ScriptedColab:
    """Uploads land and are recorded; exec outcomes follow
    the script: ("size", n) renders the verify probe's own
    output for the fixture source (b"x" * n), ("stdout",
    text) returns text, ("timeout",) raises."""

    def __init__(self, script):
        self.script = list(script)
        self.exec_calls = 0
        self.uploads = []

    def __call__(self, *argv, timeout=None):
        if argv[0] == "upload":
            self.uploads.append(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        assert argv[0] == "exec", argv
        self.exec_calls += 1
        outcome = self.script.pop(0)
        if outcome[0] == "timeout":
            raise subprocess.TimeoutExpired(argv, timeout)
        if outcome[0] == "stdout":
            return subprocess.CompletedProcess(argv, 0, outcome[1], "")
        if outcome[0] == "size":
            body = json.dumps({"size": outcome[1],
                               "sha256": hashlib.sha256(b"x" * outcome[1]).hexdigest()})
            return subprocess.CompletedProcess(argv, 0, body + "\n", "")
        raise AssertionError(outcome)


def load_launch(tmp_path, colab, chunked=None):
    package = types.ModuleType("runner_perrun_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_perrun_unit"] = package
    foundation = types.ModuleType("runner_perrun_unit.foundation")
    foundation.REPO = tmp_path
    foundation.colab = colab
    foundation.json_object_from_output = _json_object_from_output
    journal = []
    foundation.lease = types.SimpleNamespace(
        append_launch_outcome=lambda repo, session, stage, ok, detail="": journal.append(
            {"stage": stage, "ok": ok, "detail": detail}))
    foundation.transfer = types.SimpleNamespace(
        chunked_upload=chunked or (lambda *a, **k: {"ok": True}))
    sys.modules["runner_perrun_unit.foundation"] = foundation
    launch = load_module(
        "runner_perrun_unit.launch", REPO / "sync" / "runner" / "launch.py", register=True)
    return launch, journal


def make_src(tmp_path, name=DEST):
    src = tmp_path / name
    src.write_bytes(b"x" * SIZE)
    return src


def test_run_upload_dir_form(tmp_path):
    launch, _journal = load_launch(tmp_path, ScriptedColab([]))
    assert launch.run_upload_dir("run-9") == "runs/run-9"


def test_upload_one_remote_dir_plain_lands_in_the_run_dir(tmp_path):
    colab = ScriptedColab([("size", SIZE)])
    launch, journal = load_launch(tmp_path, colab)
    err = launch.upload_one("sess", make_src(tmp_path), DEST, "tag", remote_dir="runs/run-9")
    assert err is None, err
    # The upload addressed the run's slot; the verify probe
    # is the one exec; the journal keeps naming the bare
    # dest, exactly as the no-directory form does.
    assert colab.uploads[0][-1] == "/content/runs/run-9/wrap.py"
    assert colab.exec_calls == 1
    assert journal == [{"stage": "probe", "ok": True, "detail": DEST}]


def test_upload_one_remote_dir_chunked_carries_the_prefixed_name(tmp_path):
    captured = {}

    def chunked(session, src, remote_name, staging_token=None):
        captured.update(session=session, remote_name=remote_name, staging_token=staging_token)
        return {"ok": True}

    colab = ScriptedColab([])
    launch, journal = load_launch(tmp_path, colab, chunked=chunked)
    launch.UPLOAD_CHUNK_THRESHOLD_BYTES = 10
    err = launch.upload_one("sess", make_src(tmp_path, "big.bin"), "big.bin", "tag", remote_dir="runs/run-9")
    assert err is None, err
    assert captured == {"session": "sess", "remote_name": "runs/run-9/big.bin", "staging_token": "tag"}
    assert journal == [{"stage": "upload", "ok": True, "detail": "big.bin"}]
    assert colab.exec_calls == 0 and colab.uploads == []


def test_ensure_run_dir_ok_and_timeout(tmp_path):
    colab = ScriptedColab([("stdout", '{"ok": true}\n')])
    launch, _journal = load_launch(tmp_path, colab)
    assert launch.ensure_run_dir("sess", "run-9") is None
    assert colab.exec_calls == 1
    colab2 = ScriptedColab([("timeout",)])
    launch2, _journal2 = load_launch(tmp_path, colab2)
    err = launch2.ensure_run_dir("sess", "run-9")
    assert err is not None and "runs/run-9" in err


def test_rewrite_upload_args(tmp_path):
    launch, _journal = load_launch(tmp_path, ScriptedColab([]))
    rw = launch.rewrite_upload_args
    assert rw(["--script", "/content/gate.sh"], {"gate.sh"}, "run-9") == \
        ["--script", "/content/runs/run-9/gate.sh"]
    assert rw(["/content/gate.sh/sub"], {"gate.sh"}, "run-9") == ["/content/runs/run-9/gate.sh/sub"]
    # Not an upload of this run: verbatim, even under /content.
    assert rw(["/content/other.sh"], {"gate.sh"}, "run-9") == ["/content/other.sh"]
    # Relative and non-string args pass untouched.
    assert rw(["gate.sh", 7], {"gate.sh"}, "run-9") == ["gate.sh", 7]
    assert rw(["/content/gate.sh"], set(), "run-9") == ["/content/gate.sh"]


def test_prepare_branch_addresses_the_run_dir(tmp_path):
    src = tmp_path / "sync" / "base_clone.sh"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"#!/usr/bin/env bash\necho base clone\n")
    probe_ok = json.dumps(
        {"size": src.stat().st_size, "sha256": hashlib.sha256(src.read_bytes()).hexdigest()}) + "\n"
    colab = ScriptedColab([("stdout", probe_ok), ("stdout", f"base clone at {SHA} tree abc\n")])
    launch, _journal = load_launch(tmp_path, colab)
    branch = {"kind": "branch", "repo": "r", "branch": "b", "sha": SHA}
    err, info = launch.prepare_branch("sess", branch, "https://example.invalid/r.git", "dest", "run-1")
    assert err is None, err
    assert info == {"dest": "dest", "head": SHA}
    assert colab.uploads[0][-1] == "/content/runs/run-1/base_clone.sh"
    driver = (tmp_path / "var" / "branch-run-1.py").read_text()
    assert "runs/run-1/base_clone.sh" in driver


def test_main_uploads_stand_outside_the_narrowed_lock():
    # The lock's scope is the order of main()'s calls around
    # it: the run-dir creation and every upload precede the
    # lock's entry; the branch drive and the launch follow
    # it. Pinned on the source because an flock's coverage
    # has no other observable.
    text = (REPO / "sync" / "runner" / "main.py").read_text()
    entered = text.index("launch_lock.__enter__()")
    assert text.index("ensure_run_dir(session, run_id)") < entered
    assert text.index("upload_one(session, script, remote_script, run_id)") < entered
    assert text.index("remote_dir=run_upload_dir(run_id)") < entered
    assert entered < text.index("drive_branch_window(session, rec, transport, branch_ctx, run_id)")
