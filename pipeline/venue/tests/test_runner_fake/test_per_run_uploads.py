"""Per-run remote upload directories, end to end against
the fake CLI (branch transport plan, Step 5).

Two runs on ONE session whose manifests upload the SAME
basename with DIFFERENT bytes: each run's launch must read
its own run's bytes. Before Step 5 both uploads landed in
the shared /content/<basename> slot and the second launch
overwrote the first's file — sequential fires could not
show it in the outputs (each launch read after its own
upload), so the pins are the session's own state after
both fires: both runs' copies coexist under runs/<run_id>/
with their own bytes, and the shared root slot holds
nothing. The payloads also record the path they were
handed, pinning that the runner's args rewrite delivered
the per-run address. Deterministic by construction: no
concurrency, no timing — the live two-fire concurrency
proof is the parent's post-gate fire, and these pins are
what make it meaningful.
"""

import hashlib
import json
from pathlib import Path

from runner_harness import install_bare_job, run_verb, runner_env, runs_dir  # noqa: F401


def _install_data_job(env, name):
    """A bare job whose payload hashes the file its --data
    arg names and records both the arg and the hash. The
    payload resolves the /content address against its
    working directory when the absolute form does not
    resolve — the fake CLI's dual-world seam, the same one
    shell_job itself uses; on a real VM the absolute path
    resolves directly."""
    root = Path(env["TEST_REPO_ROOT"])
    jobs_dir = root / "adapters" / "colab" / "jobs"
    if jobs_dir.is_symlink():
        jobs_dir.unlink()
    job_dir = jobs_dir / name
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "payload.py").write_text(
        "import argparse, hashlib\n"
        "from pathlib import Path\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--out', required=True)\n"
        "ap.add_argument('--data', required=True)\n"
        "a = ap.parse_args()\n"
        "p = Path(a.data)\n"
        "if not p.is_file():\n"
        "    p = Path.cwd() / p.relative_to('/content')\n"
        "out = Path(a.out)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'result.txt').write_text(a.data + ' ' + hashlib.sha256(p.read_bytes()).hexdigest() + '\\n')\n"
    )
    manifest = {"name": name, "script": f"adapters/colab/jobs/{name}/payload.py",
                "args": ["--data", "/content/data.bin"], "uploads": ["var/data.bin"],
                "outputs": ["result.txt"], "shape": "cpu-highram",
                "checkpoint_pull_seconds": 1, "timeout": 180}
    (job_dir / "job.json").write_text(json.dumps(manifest))
    return job_dir


def _fire(env, name):
    r = run_verb(env, name)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["state"] == "complete", out
    return out


def _result(env, run_id):
    return (Path(env["TEST_REPO_ROOT"]) / "results" / run_id / "result.txt").read_text()


def _session_dir(env, run_id):
    rec = json.loads((runs_dir(env) / f"{run_id}.json").read_text())
    return Path(env["FAKE_COLAB_STATE"]) / "sessions" / rec["session"], rec


def test_two_runs_same_named_upload_each_read_their_own_bytes(tmp_path):
    env = runner_env(tmp_path)
    _install_data_job(env, "perrun")
    root = Path(env["TEST_REPO_ROOT"])
    (root / "var").mkdir(exist_ok=True)
    data = root / "var" / "data.bin"

    data.write_bytes(b"first-run-bytes" * 64)
    first = _fire(env, "perrun")
    data.write_bytes(b"second-run-bytes-different" * 64)
    second = _fire(env, "perrun")

    sha1 = hashlib.sha256(b"first-run-bytes" * 64).hexdigest()
    sha2 = hashlib.sha256(b"second-run-bytes-different" * 64).hexdigest()
    # Each payload was handed its own run's address and the
    # bytes at that address were its own upload's.
    assert _result(env, first["run_id"]) == f"/content/runs/{first['run_id']}/data.bin {sha1}\n"
    assert _result(env, second["run_id"]) == f"/content/runs/{second['run_id']}/data.bin {sha2}\n"
    # One session, both copies coexisting after both fires,
    # and nothing in the shared root slot.
    sdir1, rec1 = _session_dir(env, first["run_id"])
    sdir2, rec2 = _session_dir(env, second["run_id"])
    assert rec1["session"] == rec2["session"]
    assert (sdir1 / "runs" / first["run_id"] / "data.bin").read_bytes() == b"first-run-bytes" * 64
    assert (sdir2 / "runs" / second["run_id"] / "data.bin").read_bytes() == b"second-run-bytes-different" * 64
    assert not (sdir1 / "data.bin").exists()


def test_shell_job_pair_resolves_sibling_uploads_per_run(tmp_path):
    """The shell_job form of the same pin: the manifest's
    --script names the bare contract path, shell_job runs
    the run's own gate.sh copy, and the payload reads its
    sibling upload through $SHELL_JOB_UPLOADS — each fire's
    result is its own key's hash, and the run's script copy
    is the bytes that fire uploaded (the var/ sources are
    rewritten between fires)."""
    env = runner_env(tmp_path)
    root = Path(env["TEST_REPO_ROOT"])
    jobs_dir = root / "adapters" / "colab" / "jobs"
    if jobs_dir.is_symlink():
        jobs_dir.unlink()
    job_dir = jobs_dir / "perrunsh"
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"name": "perrunsh", "script": "adapters/colab/snippets/channels/shell_job.py",
                "args": ["--script", "/content/gate.sh"], "uploads": ["var/gate.sh", "var/key.bin"],
                "outputs": ["result.txt"], "shape": "cpu-highram",
                "checkpoint_pull_seconds": 1, "timeout": 180}
    (job_dir / "job.json").write_text(json.dumps(manifest))
    (root / "var").mkdir(exist_ok=True)
    (root / "var" / "gate.sh").write_text(
        'OUT="${SHELL_JOB_OUT:-}"\n'
        'case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac\n'
        'sha256sum "${SHELL_JOB_UPLOADS:?}/key.bin" | cut -d" " -f1 > "$OUT/result.txt"\n'
    )
    key = root / "var" / "key.bin"

    key.write_bytes(b"key-one" * 32)
    first = _fire(env, "perrunsh")
    key.write_bytes(b"key-two-longer" * 32)
    second = _fire(env, "perrunsh")

    assert _result(env, first["run_id"]).strip() == hashlib.sha256(b"key-one" * 32).hexdigest()
    assert _result(env, second["run_id"]).strip() == hashlib.sha256(b"key-two-longer" * 32).hexdigest()
    sdir1, rec1 = _session_dir(env, first["run_id"])
    sdir2, rec2 = _session_dir(env, second["run_id"])
    assert rec1["session"] == rec2["session"]
    assert (sdir1 / "runs" / first["run_id"] / "key.bin").read_bytes() == b"key-one" * 32
    assert (sdir2 / "runs" / second["run_id"] / "key.bin").read_bytes() == b"key-two-longer" * 32
    assert not (sdir1 / "key.bin").exists()
    assert not (sdir1 / "gate.sh").exists()
