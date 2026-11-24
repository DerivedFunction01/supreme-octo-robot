"""Per-run remote upload directories (branch transport
plan, Step 5; the lock strip).

The pins: an upload addressed with the run's directory
lands at /content/runs/<run_id>/<name> — plain and chunked
alike — while the no-directory form keeps the bare slot
byte-identically (test_upload_probe_retry pins that form);
the directory is created by one named exec before any
upload; manifest args naming an upload are rewritten to
the run's copy and nothing else is; the branch drive's
substrate upload and driver both address the run's
directory, and the drive's clone lands in the run's own
dest under it; and no launch lock exists anywhere on the
launch path — the per-session flock Step 5 narrowed was
stripped outright under the owner's no-sync-blocker
ruling, its three remaining legs (branch drive, seed
apply, launch-confirm) cured by per-run isolation of the
state they used to share. The no-lock pin is a source pin
because an absence has no other observable.
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
        if outcome[0] == "fail":
            return subprocess.CompletedProcess(argv, 1, "", outcome[1])
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


def test_ensure_run_dir_ok_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("COLAB_RUN_DIR_BACKOFF_S", "0")
    colab = ScriptedColab([("stdout", '{"ok": true}\n')])
    launch, _journal = load_launch(tmp_path, colab)
    assert launch.ensure_run_dir("sess", "run-9") is None
    assert colab.exec_calls == 1
    # The far-side create is idempotent: an existing directory
    # is success (makedirs exist_ok), so a retry after a
    # timed-out create completes rather than failing on the
    # partial directory the first attempt may have left.
    script_text = (tmp_path / "var" / "run-dir-run-9.py").read_text()
    assert "exist_ok=True" in script_text
    # A timeout is a stall signature, retried to the attempt
    # bound (default 3) before the stage fails.
    colab2 = ScriptedColab([("timeout",), ("timeout",), ("timeout",)])
    launch2, _journal2 = load_launch(tmp_path, colab2)
    err = launch2.ensure_run_dir("sess", "run-9")
    assert err is not None and "runs/run-9" in err and "timed out" in err
    assert colab2.exec_calls == 3


def test_ensure_run_dir_retries_stalls_then_lands(tmp_path, monkeypatch):
    """VENUE DEFECT 2, leg b: the exec proxy's read timeout
    (~10 s, inside the CLI's HTTP transport) killed launches
    whose sessions were healthy — one attempt, no retry. Each
    stall form now retries and the create lands."""
    monkeypatch.setenv("COLAB_RUN_DIR_BACKOFF_S", "0")
    # A subprocess timeout, then success.
    colab = ScriptedColab([("timeout",), ("stdout", '{"ok": true}\n')])
    launch, _journal = load_launch(tmp_path, colab)
    assert launch.ensure_run_dir("sess", "run-9") is None
    assert colab.exec_calls == 2
    # The proxy's own failure form: rc 1 carrying the
    # transport's ReadTimeout, then success.
    colab2 = ScriptedColab([("fail", "HTTPSConnectionPool: ReadTimeout (read timeout=10)\n"), ("stdout", '{"ok": true}\n')])
    launch2, _journal2 = load_launch(tmp_path, colab2)
    assert launch2.ensure_run_dir("sess", "run-9") is None
    assert colab2.exec_calls == 2
    # An unreadable response (the channel ate the answer) is
    # the same stall class, not a far-side failure.
    colab3 = ScriptedColab([("stdout", "channel noise, no verdict\n"), ("stdout", '{"ok": true}\n')])
    launch3, _journal3 = load_launch(tmp_path, colab3)
    assert launch3.ensure_run_dir("sess", "run-9") is None
    assert colab3.exec_calls == 2


def test_ensure_run_dir_real_failure_returns_at_once(tmp_path, monkeypatch):
    """A far-side failure with no stall signature is a real
    refusal: it returns on the first attempt, never retried
    into a different verdict."""
    monkeypatch.setenv("COLAB_RUN_DIR_BACKOFF_S", "0")
    colab = ScriptedColab([("fail", "PermissionError: [Errno 13] Permission denied\n")])
    launch, _journal = load_launch(tmp_path, colab)
    err = launch.ensure_run_dir("sess", "run-9")
    assert err is not None and "failed (rc 1)" in err
    assert colab.exec_calls == 1


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
    # The clone itself lands in the run's own dest under its
    # directory — never the shared per-registry dest two
    # drives would interleave on. The returned dest keeps
    # naming the registry dest (the stamp's shape).
    assert "'/content/runs/run-1/dest'" in driver


def test_launch_path_takes_no_session_lock():
    # The strip's pin (owner ruling: no sync
    # blocker on the venue job path): neither the launch
    # front end nor main() defines or takes a per-session
    # launch lock, in any form — the flock Step 5 narrowed
    # is gone, not renamed. A source pin because an absence
    # has no other observable.
    launch_text = (REPO / "sync" / "runner" / "launch.py").read_text()
    main_text = (REPO / "sync" / "runner" / "main.py").read_text()
    for text in (launch_text, main_text):
        assert "session_launch_lock" not in text
        assert "launch_lock" not in text
        assert "flock" not in text


def test_launch_module_exports_no_lock(tmp_path):
    launch, _journal = load_launch(tmp_path, ScriptedColab([]))
    assert not hasattr(launch, "session_launch_lock")
