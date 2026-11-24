"""Option-like run ids refuse at parse, before any record
is written: a flag token consumed as a value —
`--resume --detach`, `--resume --session` — otherwise
reaches the claim with the flag as its run id and writes a
record named for it; results/runs/ carried exactly those
two records for days before a hand quarantine. The refusal
is the claim seam's (claims.option_like_refusal), fired in
main() at parse for both the creation and resume entries.
"""

import json
import os

from runner_harness import run_verb, runner_env, runs_dir  # noqa: F401


def _record_names(env):
    runs = runs_dir(env)
    if not runs.exists():
        return []
    return sorted(p.name for p in runs.glob("*.json"))


def test_resume_detach_flag_value_refused_before_any_record(tmp_path):
    env = runner_env(tmp_path)
    r = run_verb(env, "smoke", "--resume", "--detach")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "option-like" in r.stderr and "--detach" in r.stderr
    assert _record_names(env) == []


def test_resume_session_flag_value_refused_before_any_record(tmp_path):
    env = runner_env(tmp_path)
    r = run_verb(env, "smoke", "--resume", "--session")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "option-like" in r.stderr and "--session" in r.stderr
    assert _record_names(env) == []


def test_option_like_job_name_refused(tmp_path):
    env = runner_env(tmp_path)
    r = run_verb(env, "--bogus")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "option-like" in r.stderr and "--bogus" in r.stderr
    assert _record_names(env) == []


def test_ordinary_resume_id_reaches_the_claim_machinery(tmp_path):
    """The positive half: an ordinary run id is not refused —
    the resume reaches the claims discipline and attaches to
    the outstanding claim, leaving the record exactly as
    found. The claim's child pid is this test process's: it
    is alive for the whole subprocess run (the harness waits
    on it), so the claim is outstanding, never decidable."""
    env = runner_env(tmp_path)
    runs = runs_dir(env)
    runs.mkdir(parents=True, exist_ok=True)
    run_id = "smoke-20261123T000000Z"
    rec = {
        "run_id": run_id,
        "job": "smoke",
        "state": "claiming",
        "started_at": "2026-11-23T00:00:00+00:00",
        "claim_by": "daemonize-parent",
        "claim_deadline": "2999-01-01T00:00:00+00:00",
        "daemon_child_pid": os.getpid(),
    }
    (runs / f"{run_id}.json").write_text(json.dumps(rec))
    r = run_verb(env, "smoke", "--resume", run_id)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["attached"] is True and out["run_id"] == run_id
    assert json.loads((runs / f"{run_id}.json").read_text())["state"] == "claiming"
