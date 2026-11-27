"""Resume and the pull cadence, against the fake colab CLI:
a resume preserves the record's launch facts, a torn prior
starts fresh, declared outputs pull at every checkpoint
during the run, a timed-out poll degrades instead of killing
the poller, and a shrinking re-pull rotates the held copy."""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from runner_harness import FAKE, cli_calls, logging_wrapper, run_bin, runner_env, runs_dir  # noqa: F401


def _wait_for(predicate, what, timeout=180):
    """Rendezvous on a guaranteed effect: poll the predicate
    until it holds. The timeout is a hang guard only — every
    predicate used below is an effect the choreography makes
    inevitable, so the outcome never depends on how long the
    machine takes to produce it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


def _install_gated_job(env, name, payload_source, outputs):
    """Install one job whose payload advances only when the
    test opens a gate file in its out dir — the fake cadence
    seam for this leaf. Mirrors the bare-job installer: the
    fixture repo's jobs symlink gives way to a real dir
    holding just this job. The payload speaks the runner's
    completion protocol with its heartbeat's 'complete' line
    as the terminal leg, written only after the last gate."""
    root = Path(env["TEST_REPO_ROOT"])
    jobs_dir = root / "adapters" / "colab" / "jobs"
    if jobs_dir.is_symlink():
        jobs_dir.unlink()
    job_dir = jobs_dir / name
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "payload.py").write_text(payload_source)
    manifest = {"name": name, "script": f"adapters/colab/jobs/{name}/payload.py", "args": [], "outputs": outputs, "shape": "cpu-highram", "checkpoint_pull_seconds": 1, "timeout": 300}
    (job_dir / "job.json").write_text(json.dumps(manifest))
    return job_dir


def _launched_record(env, job_name):
    """The foreground launcher saves the run record before
    its poll loop starts; discover it by job name (the runs
    dir in a fresh env holds only this run's record)."""
    runs = runs_dir(env)

    def find():
        if not runs.exists():
            return None
        for path in sorted(runs.glob("*.json")):
            try:
                rec = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            # The record is saved progressively from launch;
            # only a save carrying the launch facts (session,
            # remote_out) is the discovery this returns.
            if rec.get("job") == job_name and rec.get("session") and rec.get("remote_out"):
                return rec
        return None

    found = []
    _wait_for(lambda: found.append(find()) or found[-1] is not None, f"the {job_name} run record to appear")
    return found[-1]


def _rc_journal_wrapper(tmp_path):
    """A COLAB_BIN wrapper that journals every invocation's
    argv WITH its exit code (the harness's logging wrapper
    journals argv only) and delegates to the real fake — so a
    test can count the downloads that actually succeeded and
    a failed attempt (e.g. a pull that raced a not-yet-written
    output) can never inflate the count."""
    wrapper = tmp_path / "rc_wrapper_colab.py"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        "state = Path(os.environ['FAKE_COLAB_STATE'])\n"
        "state.mkdir(parents=True, exist_ok=True)\n"
        "rc = subprocess.run([sys.executable, os.environ['FAKE_COLAB_REAL'], *sys.argv[1:]]).returncode\n"
        "with (state / 'cli-calls-rc.jsonl').open('a') as fh:\n"
        "    fh.write(json.dumps({'argv': sys.argv[1:], 'rc': rc}) + '\\n')\n"
        "sys.exit(rc)\n"
    )
    wrapper.chmod(0o755)
    return wrapper


def _successful_downloads(env, name):
    log = Path(env["FAKE_COLAB_STATE"]) / "cli-calls-rc.jsonl"
    if not log.exists():
        return []
    calls = []
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        call = json.loads(line)
        argv = call["argv"]
        if call["rc"] == 0 and "download" in argv and any(a.startswith("/content/") and a.endswith("/" + name) for a in argv):
            calls.append(argv)
    return calls


_CADENCE_PAYLOAD = (
    "import argparse, hashlib, json, time\n"
    "from pathlib import Path\n"
    "ap = argparse.ArgumentParser()\n"
    "ap.add_argument('--out', required=True)\n"
    "a = ap.parse_args()\n"
    "out = Path(a.out)\n"
    "out.mkdir(parents=True, exist_ok=True)\n"
    "unit0 = hashlib.sha256(b'cadenceprobe:0').hexdigest().encode() * 64\n"
    "(out / 'unit-0.bin.stage').write_bytes(unit0)\n"
    "(out / 'unit-0.bin.stage').replace(out / 'unit-0.bin')\n"
    "(out / 'heartbeat.log.stage').write_text('unit 0 done\\n')\n"
    "(out / 'heartbeat.log.stage').replace(out / 'heartbeat.log')\n"
    "(out / 'checkpoint.json').write_text(json.dumps({'completed_units': 0}))\n"
    "def wait_gate(name):\n"
    "    while not (out / name).exists():\n"
    "        time.sleep(0.05)\n"
    "wait_gate('gate-1')\n"
    "with open(out / 'heartbeat.log', 'a') as fh:\n"
    "    fh.write('unit 1 done\\n')\n"
    "wait_gate('gate-2')\n"
    "with open(out / 'heartbeat.log', 'a') as fh:\n"
    "    fh.write('complete\\n')\n"
)


_SHRINK_PAYLOAD = (
    "import argparse, hashlib, time\n"
    "from pathlib import Path\n"
    "ap = argparse.ArgumentParser()\n"
    "ap.add_argument('--out', required=True)\n"
    "a = ap.parse_args()\n"
    "out = Path(a.out)\n"
    "out.mkdir(parents=True, exist_ok=True)\n"
    "unit0 = hashlib.sha256(b'shrinkprobe:0').hexdigest().encode() * 64\n"
    "(out / 'unit-0.bin.stage').write_bytes(unit0)\n"
    "(out / 'unit-0.bin.stage').replace(out / 'unit-0.bin')\n"
    "(out / 'heartbeat.log').write_text('unit 0 done\\n')\n"
    "def wait_gate(name):\n"
    "    while not (out / name).exists():\n"
    "        time.sleep(0.05)\n"
    "wait_gate('gate-1')\n"
    "with open(out / 'heartbeat.log', 'a') as fh:\n"
    "    fh.write('complete\\n')\n"
)


def test_resume_preserves_the_original_started_at(tmp_path):
    """--resume continues a run; it does not relaunch it. The
    record's launch facts (started_at above all — the field
    concurrency evidence reads) survive a resume byte-identical;
    the resume adds its own facts. (Live defect: a
    resumed hold came back stamped with the resume moment.)"""
    env = runner_env(tmp_path)
    runs = runs_dir(env)
    runs.mkdir(parents=True, exist_ok=True)
    run_id = "smoke-resumeproof"
    rec_path = runs / f"{run_id}.json"
    rec_path.write_text(json.dumps({"run_id": run_id, "job": "smoke", "state": "orphaned", "started_at": "2000-01-01T00:00:00+00:00", "session": "ghost-session-absent"}))
    try:
        r = subprocess.run([sys.executable, str(run_bin(env)), "smoke", "--resume", run_id], capture_output=True, text=True, env=env, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        rec = json.loads(rec_path.read_text())
        assert rec["state"] == "complete"
        assert rec["started_at"] == "2000-01-01T00:00:00+00:00", "resume overwrote the launch time"
        assert rec.get("resumed") is True and rec.get("resumed_at")
    finally:
        rec_path.unlink(missing_ok=True)


def test_resume_over_a_torn_record_starts_fresh_instead_of_crashing(tmp_path):
    """A flap-killed fire can leave a 0-byte run record. The
    sweep already skips torn records; the resume path must too
    — a torn prior holds nothing to preserve, so the run starts
    fresh (its damaged file replaced by a valid record) rather
    than every later entry dying on JSONDecodeError (the
    geodata lane's block)."""
    env = runner_env(tmp_path)
    runs = runs_dir(env)
    runs.mkdir(parents=True, exist_ok=True)
    run_id = "smoke-tornprior"
    rec_path = runs / f"{run_id}.json"
    rec_path.write_bytes(b"")
    try:
        r = subprocess.run([sys.executable, str(run_bin(env)), "smoke", "--resume", run_id], capture_output=True, text=True, env=env, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "torn" in r.stderr
        rec = json.loads(rec_path.read_text())
        assert rec["state"] == "complete"
    finally:
        rec_path.unlink(missing_ok=True)


def test_checkpoint_pull_lands_outputs_during_the_run(tmp_path):
    """checkpoint_pull_seconds is a pull cadence, not only a poll
    cadence: declared outputs download at every checkpoint while
    the job runs, so a long job's growing outputs (the venue
    keeper's log is the live case) reach local readers mid-run
    instead of only at completion. (Live defect: the
    relay waiting on the keeper's log starved for the job's whole
    12 h timeout because pulls happened only after the loop.)

    E6 change detection rides the same cadence: a CHANGING
    output (heartbeat.log grows every unit) is pulled at multiple
    cadences, while a STABLE output (unit-0.bin, written once at
    its unit and never touched again) is pulled exactly once —
    its reader stat never changes, so later cadences skip it.

    The payload is gate-driven, not clock-driven (the determinism
    cure): the smoke payload's 1 s units raced the
    poll loop's cadence — on a slow machine the payload finished
    before the first cadence pull fired, and heartbeat arrived
    only at the final pull. Here the payload changes state only
    when the test opens a gate, and the test opens the next
    gate only after observing the pull the previous state
    earned — so a mid-run pull is proven by observation while
    the run is still gated, never inferred from wall-clock
    ordering. Downloads are counted from the rc journal, so a
    failed attempt can never inflate a count."""
    wrapper = _rc_journal_wrapper(tmp_path)
    env = runner_env(tmp_path)
    env.update(COLAB_BIN=str(wrapper), FAKE_COLAB_REAL=str(FAKE))
    _install_gated_job(env, "cadenceprobe", _CADENCE_PAYLOAD, ["unit-0.bin", "heartbeat.log"])
    proc = subprocess.Popen([sys.executable, str(run_bin(env)), "cadenceprobe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        launched = _launched_record(env, "cadenceprobe")
        results = Path(env["TEST_REPO_ROOT"]) / "results" / launched["run_id"]
        sandbox = Path(env["FAKE_COLAB_STATE"]) / "sessions" / launched["session"] / launched["remote_out"]
        unit0 = hashlib.sha256(b"cadenceprobe:0").hexdigest().encode() * 64

        def landed(name, content):
            path = results / name
            return path.exists() and path.read_bytes() == content

        _wait_for(lambda: landed("unit-0.bin", unit0) and landed("heartbeat.log", b"unit 0 done\n"),
                  "the first cadence pull to land unit-0.bin and heartbeat v1")
        assert proc.poll() is None, "the run ended before the first gate opened"
        (sandbox / "gate-1").write_text("go\n")
        _wait_for(lambda: landed("heartbeat.log", b"unit 0 done\nunit 1 done\n"),
                  "a cadence pull to land heartbeat v2 during the run")
        assert proc.poll() is None, "the run ended before the second gate opened: the v2 pull was not mid-run"
        assert len(_successful_downloads(env, "unit-0.bin")) == 1, "the stable output was re-pulled at a cadence"
        (sandbox / "gate-2").write_text("go\n")
        stdout, stderr = proc.communicate(timeout=300)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, stdout + stderr
    out = json.loads(stdout)
    assert out["state"] == "complete"
    heartbeat = _successful_downloads(env, "heartbeat.log")
    unit0_calls = _successful_downloads(env, "unit-0.bin")
    assert len(heartbeat) >= 2, f"heartbeat.log downloaded {len(heartbeat)} time(s): the final pull only, no checkpoint pull during the run"
    assert len(unit0_calls) == 1, f"unit-0.bin downloaded {len(unit0_calls)} time(s): an unchanged output must be pulled once and skipped thereafter"
    rec = json.loads((runs_dir(env) / f"{out['run_id']}.json").read_text())
    assert rec.get("last_checkpoint_pull_at"), "the run record carries no checkpoint pull stamp"
    assert rec.get("output_stats", {}).get("unit-0.bin"), "the run record carries no output stat for the skipped output"


def test_poll_timeout_degrades_instead_of_killing_the_poller(tmp_path):
    """A checkpoint poll whose CLI call exceeds its timeout is a
    failed poll, not a dead poller: the loop notes it on the
    record and continues to the next cadence. (Live defect:
    an uncaught TimeoutExpired killed the poller and
    stranded the run at polling while its payload completed.)"""
    wrapper = tmp_path / "wrapper_colab.py"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "state = Path(os.environ['FAKE_COLAB_STATE'])\n"
        "marker = state / 'read-delayed'\n"
        "args = sys.argv[1:]\n"
        "if 'exec' in args and any('read-' in a for a in args) and not marker.exists():\n"
        "    state.mkdir(parents=True, exist_ok=True)\n"
        "    marker.write_text('1')\n"
        "    time.sleep(5)\n"
        "sys.exit(subprocess.run([sys.executable, os.environ['FAKE_COLAB_REAL'], *args]).returncode)\n"
    )
    wrapper.chmod(0o755)
    env = runner_env(tmp_path)
    env.update(COLAB_BIN=str(wrapper), FAKE_COLAB_REAL=str(FAKE), VENUE_RUN_POLL_TIMEOUT_S="2")
    r = subprocess.run([sys.executable, str(run_bin(env)), "smoke"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["state"] == "complete"
    rec = json.loads((runs_dir(env) / f"{out['run_id']}.json").read_text())
    assert rec.get("last_poll_error"), "the timed-out poll left no note on the record"


def test_shrinking_repull_rotates_the_held_copy(tmp_path):
    """A remote output that restarts smaller must not erase the
    history already pulled: the re-pull rotates the held copy
    aside under a stamped sibling name, the live file takes the
    new content, and the rotation is noted on the pull entry and
    the run record. (Live defect: after a wrapper
    resume, the venue keeper's pulled log shrank to its first
    line and the accumulated record was gone.)

    The shrink is staged by the test, not by a download-counting
    wrapper (the determinism cure): the old shape shrank
    the remote on the first checkpoint.json download and needed
    a whole cadence ordering — unit-0 pulled before that
    download, then re-pulled after it — to occur inside one
    run; on a slow machine the run's only pull pass was the
    final one, the shrink fired mid-pass after unit-0 had
    already been processed, and no re-pull ever happened. Here
    the payload waits at a gate: the test shrinks the remote
    file directly in the fake sandbox (the remote filesystem)
    only after observing the original pull landed, then opens
    the gate — the re-pull that follows is the loop's next
    cadence or the final pull, and either rotates."""
    env = runner_env(tmp_path)
    _install_gated_job(env, "shrinkprobe", _SHRINK_PAYLOAD, ["unit-0.bin", "heartbeat.log"])
    proc = subprocess.Popen([sys.executable, str(run_bin(env)), "shrinkprobe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        launched = _launched_record(env, "shrinkprobe")
        results = Path(env["TEST_REPO_ROOT"]) / "results" / launched["run_id"]
        sandbox = Path(env["FAKE_COLAB_STATE"]) / "sessions" / launched["session"] / launched["remote_out"]
        payload = hashlib.sha256(b"shrinkprobe:0").hexdigest().encode() * 64

        def landed_original():
            path = results / "unit-0.bin"
            return path.exists() and path.read_bytes() == payload

        _wait_for(landed_original, "the first pull to land the original unit-0.bin")
        assert proc.poll() is None, "the run ended before the shrink was staged"
        (sandbox / "unit-0.bin").write_bytes(b"shrunk\n")
        (sandbox / "gate-1").write_text("go\n")
        stdout, stderr = proc.communicate(timeout=300)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, stdout + stderr
    out = json.loads(stdout)
    assert out["state"] == "complete"
    results = Path(env["TEST_REPO_ROOT"]) / "results" / out["run_id"]
    assert (results / "unit-0.bin").read_bytes() == b"shrunk\n", "the live file does not hold the new, smaller content"
    rotated = sorted(results.glob("unit-0.bin.rotated-*"))
    assert len(rotated) == 1, [p.name for p in results.iterdir()]
    assert rotated[0].read_bytes() == payload, "the rotated sibling lost the previously pulled content"
    assert not list(results.glob("*.pulling")), "a staging file was left behind"
    rec = json.loads((runs_dir(env) / f"{out['run_id']}.json").read_text())
    assert "unit-0.bin" in (rec.get("last_pull_rotation") or ""), "the rotation is not noted on the run record"
    entry = next(e for e in rec["pulled"] if e["path"] == "unit-0.bin")
    assert entry["rotated"]["bytes"] == len(payload), "the rotation is not noted on the pull entry"
