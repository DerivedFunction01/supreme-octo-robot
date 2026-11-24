"""Manifest-shape totality at load (commissioned):
outputs tolerate totally — plain names or mapped entries
normalize once at load and every consumer works by local
name — while uploads / args entries that are not plain
strings refuse the launch loudly, before any session work,
naming the field and the offending entry. The wild specimens
were real consumer manifests: mapped outputs that crashed the
launch advisory, and dict-shaped uploads that crashed a
launch outright."""

import json
from pathlib import Path

from runner_harness import run_verb, runner_env, runs_dir


def install_shaped_job(env, name, manifest_extra):
    """One bare job (payload writes result.txt, exits 0) whose
    manifest carries the caller's shape overrides."""
    root = Path(env["TEST_REPO_ROOT"])
    jobs_dir = root / "adapters" / "colab" / "jobs"
    if jobs_dir.is_symlink():
        jobs_dir.unlink()
    job_dir = jobs_dir / name
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "payload.py").write_text(
        "import argparse, sys\n"
        "from pathlib import Path\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--out', required=True)\n"
        "a = ap.parse_args()\n"
        "out = Path(a.out)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'result.txt').write_text('shaped-result\\n')\n"
        "sys.exit(0)\n"
    )
    manifest = {"name": name, "script": f"adapters/colab/jobs/{name}/payload.py", "args": [], "outputs": ["result.txt"], "shape": "cpu-highram", "checkpoint_pull_seconds": 1, "timeout": 180}
    manifest.update(manifest_extra)
    (job_dir / "job.json").write_text(json.dumps(manifest))
    return job_dir


def test_dict_uploads_entry_refuses_the_launch_loudly(tmp_path):
    """The S2 specimen's shape: uploads declared as mapped
    entries. The launch refuses with exit 2, naming the field
    and the entry, and no run record is created — the refusal
    lands before any session work, not mid-launch."""
    env = runner_env(tmp_path)
    install_shaped_job(env, "baduploads", {"uploads": [{"local": "data.bin", "remote": "/content/data.bin"}]})
    r = run_verb(env, "baduploads")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "uploads" in r.stderr and "not a string" in r.stderr and "data.bin" in r.stderr, r.stderr
    assert list(runs_dir(env).glob("*.json")) == []


def test_dict_args_entry_refuses_the_launch_loudly(tmp_path):
    """Args interpolate into the launch command as quoted argv
    entries; a mapped entry has no string meaning there, so it
    takes the same loud refusal as uploads."""
    env = runner_env(tmp_path)
    install_shaped_job(env, "badargs", {"args": [{"flag": "--mode"}]})
    r = run_verb(env, "badargs")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "args" in r.stderr and "not a string" in r.stderr, r.stderr
    assert list(runs_dir(env).glob("*.json")) == []


def test_branch_transport_missing_sha_refuses_the_launch_loudly(tmp_path):
    """Branch transport (plan, Step 1): a branch
    declaration missing its sha refuses at load with exit 2,
    naming the field, and no run record is created — the
    refusal lands before any session work, like the other
    shape refusals in this module."""
    env = runner_env(tmp_path)
    install_shaped_job(env, "branchbad", {"transport": {"kind": "branch", "repo": "supreme-octo-robot", "branch": "cure/x-20261123"}})
    r = run_verb(env, "branchbad")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "transport" in r.stderr and "sha" in r.stderr and "missing" in r.stderr, r.stderr
    assert list(runs_dir(env).glob("*.json")) == []


def test_no_transport_regression_stamps_the_bundle_path(tmp_path):
    """The no-transport regression case (Step 1): a manifest
    naming no transport launches exactly as before the
    declaration existed, and its record stamps the bundle
    path it took — kind, the bytes the runner moved, and
    the claim→launch span — so the adoption census (Step 4)
    reads every record, not just branch-form ones."""
    env = runner_env(tmp_path)
    install_shaped_job(env, "plainjob", {})
    r = run_verb(env, "plainjob")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["state"] == "complete"
    rec = json.loads((runs_dir(env) / f"{out['run_id']}.json").read_text())
    assert rec["state"] == "complete"
    transport = rec["transport"]
    assert transport["kind"] == "bundle"
    assert transport["bytes_moved"] > 0
    assert transport["claim_to_launch_s"] >= 0


def test_mapped_outputs_run_and_pull_by_local_name(tmp_path):
    """Own-manifest mapped outputs (the mapped-output gate shape:
    local / remote / archive keys) launch, complete, and pull
    by the local name — normalization at load gives finalize
    and pull the plain-name contract."""
    env = runner_env(tmp_path)
    install_shaped_job(env, "mappedouts", {"outputs": [{"local": "result.txt", "remote": "/elsewhere/result.txt", "archive": "tar.gz"}]})
    r = run_verb(env, "mappedouts")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["state"] == "complete"
    assert any(p["path"] == "result.txt" for p in out["pulled"]), out
