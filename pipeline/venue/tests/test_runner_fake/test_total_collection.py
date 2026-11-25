"""Total collection shortfall (launch-path plan, Step 4):
a run that collected none of its declared outputs has no
complete verdict to give.

The specimen: parallel runs on one session declaring the
same output names — both lanes' drives wrote their one
declared name cwd-relative, the shared root file was
contended, and the loser closed complete with pulled []
and an empty results dir, a record indistinguishable from
a successful run that landed nothing. The cure is the
terminal tail's partition: a partial collection still
completes with its shortfall named (the pull-gap pins),
but a total shortfall closes failed, the shortfall itself
as the error. The positive half pins the specimen's other
side: two parallel runs whose payloads honour the out-dir
contract collect their own outputs, each in its own
results dir.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from runner_harness import run_bin, run_verb, runner_env, runs_dir


def _install(env, name, payload, outputs, timeout=300):
    root = Path(env["TEST_REPO_ROOT"])
    jobs_dir = root / "adapters" / "colab" / "jobs"
    if jobs_dir.is_symlink():
        jobs_dir.unlink()
    job_dir = jobs_dir / name
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "payload.py").write_text(payload)
    manifest = {"name": name, "script": f"adapters/colab/jobs/{name}/payload.py", "args": [], "outputs": outputs, "shape": "cpu-highram", "checkpoint_pull_seconds": 1, "timeout": timeout}
    (job_dir / "job.json").write_text(json.dumps(manifest))
    return job_dir


def install_outdir_job(env, name):
    """A contract payload: its declared output lands in its
    own out dir, stamped with the out dir's name — so two
    runs' copies of the same declared name are told apart
    by content, not just by location."""
    return _install(env, name, (
        "import argparse, sys\n"
        "from pathlib import Path\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--out', required=True)\n"
        "a = ap.parse_args()\n"
        "out = Path(a.out)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'result.txt').write_text(out.name + '\\n')\n"
        "sys.exit(0)\n"
    ), ["result.txt"], timeout=180)


def install_sleepy_root_job(env, name):
    """A live co-tenant: declares the shared root name and
    sleeps, writing nothing — its execution window is what
    makes a co-tenant's root write of that name contended."""
    return _install(env, name, (
        "import argparse, sys, time\n"
        "from pathlib import Path\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--out', required=True)\n"
        "a = ap.parse_args()\n"
        "out = Path(a.out)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "time.sleep(120)\n"
        "sys.exit(0)\n"
    ), ["drive-result.json"])


def install_root_only_job(env, name):
    """The drive shape: the payload's one declared output
    is written cwd-relative, to the session's shared root,
    and nothing lands in its out dir."""
    return _install(env, name, (
        "import argparse, sys\n"
        "from pathlib import Path\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--out', required=True)\n"
        "a = ap.parse_args()\n"
        "out = Path(a.out)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "Path('drive-result.json').write_text('drive\\n')\n"
        "sys.exit(0)\n"
    ), ["drive-result.json"], timeout=180)


def install_empty_job(env, name):
    """A payload that exits 0 writing none of its declared
    outputs anywhere — no out-dir file, no root file."""
    return _install(env, name, (
        "import argparse, sys\n"
        "from pathlib import Path\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--out', required=True)\n"
        "a = ap.parse_args()\n"
        "out = Path(a.out)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "sys.exit(0)\n"
    ), ["ghost.txt"], timeout=180)


def _poll_to_terminal(env, run_id):
    rc = 3
    deadline = time.time() + 180
    while rc == 3 and time.time() < deadline:
        rc = run_verb(env, "--poll", run_id).returncode
    return rc


def test_parallel_runs_with_the_same_output_names_both_collect(tmp_path):
    """The specimen's positive half: two parallel runs of
    one job, one declared name between them — each collects
    its own output into its own results dir and closes
    complete on its own bytes."""
    env = runner_env(tmp_path)
    install_outdir_job(env, "parjob")
    runs = []
    for _ in range(2):
        r = subprocess.run([sys.executable, str(run_bin(env)), "parjob", "--detach"], capture_output=True, text=True, env=env, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        runs.append(json.loads(r.stdout)["run_id"])
    assert runs[0] != runs[1]
    for run_id in runs:
        assert _poll_to_terminal(env, run_id) == 0
        rec = json.loads((runs_dir(env) / f"{run_id}.json").read_text())
        assert rec["state"] == "complete", rec
        assert [e["path"] for e in rec["pulled"]] == ["result.txt"], rec
        landed = Path(env["TEST_REPO_ROOT"]) / "results" / run_id / "result.txt"
        assert landed.read_text() == f"{rec['remote_out']}\n"


def test_contended_total_shortfall_closes_failed_not_complete(tmp_path):
    """The loser of the specimen, exactly: its one declared
    output sits at the shared root, contended by a live
    co-tenant, and nothing else it declared exists to
    collect. Before the cure this closed complete with
    pulled []; now it closes failed, the error naming the
    output and the run it is contended with, and no file
    lands in its results dir."""
    env = runner_env(tmp_path)
    install_sleepy_root_job(env, "holder")
    install_root_only_job(env, "drive")
    ra = subprocess.run([sys.executable, str(run_bin(env)), "holder", "--detach"], capture_output=True, text=True, env=env, timeout=300)
    assert ra.returncode == 0, ra.stdout + ra.stderr
    holder_run = json.loads(ra.stdout)["run_id"]
    rb = subprocess.run([sys.executable, str(run_bin(env)), "drive"], capture_output=True, text=True, env=env, timeout=300)
    assert rb.returncode == 1, rb.stdout + rb.stderr
    out = json.loads(rb.stdout)
    assert out["state"] == "failed", out
    assert out["pulled"] == []
    assert "collected none of its 1 declared outputs" in out["error"], out
    assert "drive-result.json" in out["error"] and holder_run in out["error"], out
    rec = json.loads((runs_dir(env) / f"{out['run_id']}.json").read_text())
    assert rec["state"] == "failed" and rec["pulled"] == []
    misplaced = rec.get("misplaced_outputs") or []
    assert misplaced and misplaced[0]["contended"] is True and misplaced[0]["collected"] is False, rec
    results = Path(env["TEST_REPO_ROOT"]) / "results" / out["run_id"]
    assert not (results / "drive-result.json").exists()


def test_total_absence_closes_failed_not_complete(tmp_path):
    """The empty-collection-complete shape cannot be
    constructed by absence either: a payload that exits 0
    and writes none of its declared outputs anywhere
    closes failed with the shortfall as the error, not
    complete over an empty collection."""
    env = runner_env(tmp_path)
    install_empty_job(env, "emptyjob")
    r = subprocess.run([sys.executable, str(run_bin(env)), "emptyjob"], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 1, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["state"] == "failed", out
    assert out["pulled"] == []
    assert "collected none of its 1 declared outputs: ghost.txt" in out["error"], out
    rec = json.loads((runs_dir(env) / f"{out['run_id']}.json").read_text())
    assert rec["state"] == "failed" and rec.get("missing_outputs") == ["ghost.txt"]
