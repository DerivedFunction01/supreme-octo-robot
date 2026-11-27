"""Envelope dispatch pins for bin/venue-run: the --envelope
form composes the declared jobs into one launch — the
envelope record carries its constituents in order with
their stamps, each job's launch payload carries its
stamps, the generated launcher starts every tree before
waiting, and defective declarations refuse before any
launch work. The seam form mirrors the union dispatch
pins: the entry loads by path and its seams are stubbed,
never raw argv past the unified parse."""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

TARGET = {"host": "machine.invalid", "user": "agent"}


def load_venue_run():
    return load_module("venue_run_envelope_unit", REPO / "bin" / "venue-run")


def _write_job(jobs, name, timeout_s=300):
    job_dir = jobs / name
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "script": "run.sh",
                "caller": "workhorse",
                "shape": "local-hp",
                "timeout_s": timeout_s,
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "run.sh").write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")


def _fixture(tmp_path, monkeypatch, spec):
    mod = load_venue_run()
    jobs = tmp_path / "jobs"
    _write_job(jobs, "job-a", timeout_s=300)
    _write_job(jobs, "job-b", timeout_s=600)
    env_dir = jobs / "my-env"
    env_dir.mkdir(parents=True)
    (env_dir / "envelope.json").write_text(json.dumps(spec), encoding="utf-8")
    saved = []
    launched = {}

    def fake_launch(rec, job_payload, target, ssh=None, launch_step=None):
        launched["rec"] = dict(rec)
        launched["jobs"] = job_payload
        launched["target"] = target
        return None

    monkeypatch.setattr(mod, "JOBS", jobs)
    monkeypatch.setattr(mod.sealed, "load_register", lambda repo: {})
    monkeypatch.setattr(mod.sealed, "entry_for", lambda register, job: None)
    monkeypatch.setattr(mod.lease, "caller_claim_error", lambda repo, flag, env: None)
    monkeypatch.setattr(
        mod.lease, "resolve_caller", lambda repo, flag, env: "workhorse"
    )
    monkeypatch.setattr(
        mod.lease,
        "acquire_local",
        lambda repo, shape, caller, hours: {
            "action": "created",
            "record": {"session": "local-hp", "target": "machine"},
        },
    )
    monkeypatch.setattr(mod, "_record_target", lambda rec: TARGET)
    monkeypatch.setattr(mod.local_venue, "ensure_transport", lambda target: True)
    monkeypatch.setattr(
        mod, "save_record", lambda rec: saved.append(json.loads(json.dumps(rec)))
    )
    monkeypatch.setattr(mod.envelope_dispatch, "launch_envelope", fake_launch)
    return mod, saved, launched


SPEC = {
    "shape": "local-hp",
    "jobs": [
        "job-a",
        {"name": "job-b", "connections": 5, "threads_per_connection": 39},
    ],
    "caller": "workhorse",
}


def test_envelope_dispatch_records_constituents_in_order_with_stamps(
    tmp_path, monkeypatch, capsys
):
    mod, saved, launched = _fixture(tmp_path, monkeypatch, SPEC)
    monkeypatch.setattr(sys, "argv", ["venue-run", "--envelope", "my-env", "--detach"])
    assert mod.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "running"
    rec = saved[-1]
    assert rec["envelope"] is True
    assert rec["job"] == "my-env"
    assert rec["run_id"].startswith("my-env-")
    assert rec["envelope_budget"] == 768
    assert rec["timeout_s"] == 600  # the max constituent timeout
    constituents = rec["constituents"]
    assert [c["job"] for c in constituents] == ["job-a", "job-b"]
    # hp-envy: 768 budget over 2 jobs — 384 shares. job-a
    # prices by the flat burst (384 // 860 -> 1 worker);
    # job-b declares its connection pool (5 x 39 + 150 =
    # 345; 384 // 345 -> 1 worker), and the record carries
    # the declared worst case that priced it.
    assert constituents[0]["thread_share"] == 384
    assert constituents[0]["workers"] == 1
    assert constituents[0]["pool_cap"] == 384
    assert "per_worker_worst_case" not in constituents[0]
    assert constituents[1]["thread_share"] == 384
    assert constituents[1]["workers"] == 1
    assert constituents[1]["per_worker_worst_case"] == 345
    payload = launched["jobs"]
    assert [j["name"] for j in payload] == ["job-a", "job-b"]
    assert [j["index"] for j in payload] == [0, 1]
    assert payload[0]["stamps"] == {
        "workers": 1,
        "thread_share": 384,
        "pool_cap": 384,
    }


def test_envelope_launcher_starts_all_trees_then_waits(tmp_path, monkeypatch):
    mod, _saved, launched = _fixture(tmp_path, monkeypatch, SPEC)
    monkeypatch.setattr(sys, "argv", ["venue-run", "--envelope", "my-env", "--detach"])
    assert mod.main() == 0
    text = mod.envelope_dispatch.envelope_launcher(launched["jobs"]).decode()
    for needle in (
        "GATE_WORKERS=1",
        "ENVELOPE_THREADS=384",
        "ENVELOPE_JOB_INDEX=0",
        "ENVELOPE_JOB_INDEX=1",
        "ENVELOPE_JOB_COUNT=2",
        "OMP_THREAD_LIMIT=384",
        "OPENBLAS_NUM_THREADS=384",
        "MKL_NUM_THREADS=384",
        "NUMEXPR_NUM_THREADS=384",
        "echo $! > job-a/root.pid",
        "echo $! > job-b/root.pid",
        'echo $code > "${names[$i]}/exit"',
        "exit $envelope_code",
    ):
        assert needle in text, needle
    # Concurrency: both launches precede the wait loop.
    assert text.index("job-b/root.pid") < text.index('wait "${pids[$i]}"')


def test_envelope_record_settles_through_the_standing_poll(tmp_path, monkeypatch):
    mod = load_venue_run()
    rec = {"run_id": "my-env-20261126T000000Z", "venue": "local", "state": "running"}
    reading = {"reading": "exit", "exit_code": 0, "output_tail": "", "finished_at": "t"}
    monkeypatch.setattr(
        mod.local_venue, "read_run_state", lambda repo, r, target=None: reading
    )
    monkeypatch.setattr(mod, "finalize_local_record", lambda r, rd: "complete")
    out = mod._poll(rec, TARGET)
    assert out == {"state": "complete", "exit_code": 0}


def test_envelope_refuses_a_sealed_constituent(tmp_path, monkeypatch, capsys):
    mod, saved, launched = _fixture(tmp_path, monkeypatch, SPEC)
    monkeypatch.setattr(
        mod.sealed,
        "entry_for",
        lambda register, job: {"job": job} if job == "job-b" else None,
    )
    monkeypatch.setattr(sys, "argv", ["venue-run", "--envelope", "my-env", "--detach"])
    assert mod.main() == 2
    assert "sealed" in capsys.readouterr().err
    assert launched == {}
    assert saved == []


def test_envelope_refuses_an_undeclared_shape(tmp_path, monkeypatch, capsys):
    bad = dict(SPEC, shape="nope")
    mod, saved, launched = _fixture(tmp_path, monkeypatch, bad)
    monkeypatch.setattr(sys, "argv", ["venue-run", "--envelope", "my-env", "--detach"])
    assert mod.main() == 2
    assert "declares no capacity" in capsys.readouterr().err
    assert launched == {}


def test_envelope_refuses_a_positional_and_a_missing_declaration(
    tmp_path, monkeypatch, capsys
):
    mod, _saved, launched = _fixture(tmp_path, monkeypatch, SPEC)
    monkeypatch.setattr(
        sys, "argv", ["venue-run", "job-a", "--envelope", "my-env", "--detach"]
    )
    assert mod.main() == 2
    assert "does not ride it" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["venue-run", "--envelope", "ghost", "--detach"])
    assert mod.main() == 2
    assert "no envelope declaration" in capsys.readouterr().err
    assert launched == {}
