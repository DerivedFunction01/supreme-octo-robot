"""Union dispatch pins for bin/local-run: the union form
validates its constituent list before any dispatch work, the
generated constituents file rides the launch uploads seam,
and the run record carries the constituents in the order
given. Non-union invocations carry no union payload.

The validator's seam is the unified parse's repeatable-flag
lists: the pins hand it the parsed --union and --check-path
values directly, in order, never raw argv."""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

SHA_A = "a" * 40
SHA_B = "0123456789abcdef0123456789abcdef01234567"
TARGET = {"host": "machine.invalid", "user": "agent"}


def load_local_run():
    return load_module("local_run_union_unit", REPO / "bin" / "local-run")


def test_union_validator_preserves_constituent_and_check_path_order():
    mod = load_local_run()
    payload, error = mod._union_payload(
        [f"second={SHA_B}", f"first={SHA_A}"],
        ["pipeline/venue/tests", "pipeline/venue/bin"],
    )
    assert error is None
    assert payload == {
        "constituents": [
            {"branch": "second", "sha": SHA_B},
            {"branch": "first", "sha": SHA_A},
        ],
        "check_paths": ["pipeline/venue/tests", "pipeline/venue/bin"],
    }


def test_union_validator_refuses_fewer_than_two_constituents():
    mod = load_local_run()
    payload, error = mod._union_payload(
        [f"only={SHA_A}"],
        ["pipeline/venue/tests"],
    )
    assert payload is None
    assert "at least two" in error


def test_union_validator_refuses_malformed_shas():
    mod = load_local_run()
    for sha in ("abc123", "g" * 40, "a" * 39, "a" * 41):
        payload, error = mod._union_payload(
            [f"one={SHA_A}", f"two={sha}"],
            ["pipeline/venue/tests"],
        )
        assert payload is None
        assert "full 40-hex SHA" in error


def test_union_validator_refuses_an_unnamed_branch():
    mod = load_local_run()
    payload, error = mod._union_payload(
        [f"one={SHA_A}", f"={SHA_B}"],
        ["pipeline/venue/tests"],
    )
    assert payload is None
    assert "BRANCH=SHA" in error


def test_union_validator_refuses_a_missing_check_path():
    mod = load_local_run()
    payload, error = mod._union_payload(
        [f"one={SHA_A}", f"two={SHA_B}"],
        [],
    )
    assert payload is None
    assert "at least one --check-path" in error


def test_union_validator_refuses_a_non_relative_check_path():
    mod = load_local_run()
    for bad in ("/abs/path", "../up"):
        payload, error = mod._union_payload(
            [f"one={SHA_A}", f"two={SHA_B}"],
            [bad],
        )
        assert payload is None
        assert "repo-relative" in error


def test_non_union_invocation_has_no_union_payload():
    mod = load_local_run()
    assert mod._union_payload([], []) is None


def test_union_dispatch_stamps_record_and_stages_constituents(
    tmp_path, monkeypatch, capsys
):
    mod = load_local_run()
    jobs = tmp_path / "jobs"
    job_dir = jobs / "union-gate"
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "script": "run.sh",
                "caller": "workhorse",
                "shape": "local",
                "timeout_s": 300,
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "run.sh").write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")

    saved = []
    launched = {}

    def fake_launch(rec, script, target, uploads=()):
        launched["rec"] = dict(rec)
        launched["script"] = script
        launched["target"] = target
        launched["uploads"] = list(uploads)
        return None

    monkeypatch.setattr(mod, "JOBS", jobs)
    monkeypatch.setattr(mod.sealed, "load_register", lambda repo: {})
    monkeypatch.setattr(mod.sealed, "entry_for", lambda register, job: None)
    monkeypatch.setattr(mod.lease, "caller_claim_error", lambda repo, flag, env: None)
    monkeypatch.setattr(mod.lease, "resolve_caller", lambda repo, flag, env: "workhorse")
    monkeypatch.setattr(
        mod.lease,
        "acquire_local",
        lambda repo, shape, caller, hours: {
            "action": "created",
            "record": {"session": "local-main", "target": "machine"},
        },
    )
    monkeypatch.setattr(mod, "_record_target", lambda rec: TARGET)
    monkeypatch.setattr(mod.local_venue, "ensure_transport", lambda target: True)
    monkeypatch.setattr(
        mod, "save_record", lambda rec: saved.append(json.loads(json.dumps(rec)))
    )
    monkeypatch.setattr(mod, "_launch", fake_launch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "local-run",
            "union-gate",
            "--union",
            f"alpha={SHA_A}",
            "--union",
            f"beta={SHA_B}",
            "--check-path",
            "pipeline/venue/tests",
            "--caller",
            "workhorse",
            "--detach",
        ],
    )

    assert mod.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "running"
    expected = [
        {"branch": "alpha", "sha": SHA_A},
        {"branch": "beta", "sha": SHA_B},
    ]
    assert saved[-1]["constituents"] == expected
    assert saved[-1]["uploads"] == ["constituents.json"]
    assert [name for name, _data in launched["uploads"]] == ["constituents.json"]
    staged = json.loads(launched["uploads"][0][1])
    assert staged == {
        "constituents": expected,
        "check_paths": ["pipeline/venue/tests"],
    }
