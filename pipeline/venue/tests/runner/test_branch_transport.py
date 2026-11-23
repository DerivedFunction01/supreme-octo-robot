"""Branch transport (plan 2026-11-22, Steps 1–2): the
manifest declaration, the record stamp, and the base-clone
drive.

The declaration's pins: branch is the only declared kind;
kind branch requires repo, branch, and a full 40-hex sha,
each refusal naming its field; no transport at all is the
bundle path and validates clean. The drive's pins: the
session's base clone is driven to the declared tip and
its echoed HEAD is asserted against the announcement — a
mismatch or a fetch that never lands is a refusal here,
never a silent bundle substitution. Driven against a stub
foundation whose colab is scripted, in the upload-probe
suite's idiom.
"""

import hashlib
import json
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
BRANCH = {"kind": "branch", "repo": "supreme-octo-robot", "branch": "cure/x-20261123", "sha": SHA}


def _json_object_from_output(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON object in output")


class ScriptedColab:
    """Uploads land unless upload_rc says otherwise; exec
    outcomes follow the script: ("probe",) renders the
    verify probe's own output for the fixture base_clone.sh,
    ("stdout", text) returns text, ("timeout",) raises."""

    def __init__(self, script, probe_file, upload_rc=0):
        self.script = list(script)
        self.probe_file = probe_file
        self.upload_rc = upload_rc
        self.exec_calls = 0
        self.upload_calls = 0

    def __call__(self, *argv, timeout=None):
        if argv[0] == "upload":
            self.upload_calls += 1
            return subprocess.CompletedProcess(argv, self.upload_rc, "", "upload refused")
        assert argv[0] == "exec", argv
        self.exec_calls += 1
        outcome = self.script.pop(0)
        if outcome[0] == "timeout":
            raise subprocess.TimeoutExpired(argv, timeout)
        if outcome[0] == "probe":
            data = self.probe_file.read_bytes()
            body = json.dumps({"size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            return subprocess.CompletedProcess(argv, 0, body + "\n", "")
        if outcome[0] == "stdout":
            return subprocess.CompletedProcess(argv, 0, outcome[1], "")
        raise AssertionError(outcome)


def load_launch(tmp_path, colab):
    package = types.ModuleType("runner_branch_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_branch_unit"] = package
    foundation = types.ModuleType("runner_branch_unit.foundation")
    foundation.REPO = tmp_path
    foundation.colab = colab
    foundation.json_object_from_output = _json_object_from_output
    journal = []
    foundation.lease = types.SimpleNamespace(
        append_launch_outcome=lambda repo, session, stage, ok, detail="": journal.append(
            {"stage": stage, "ok": ok, "detail": detail}))
    foundation.transfer = types.SimpleNamespace(
        chunked_upload=lambda *a, **k: {"ok": True})
    sys.modules["runner_branch_unit.foundation"] = foundation
    launch = load_module(
        "runner_branch_unit.launch", REPO / "sync" / "runner" / "launch.py", register=True)
    return launch, foundation, journal


def make_base_clone(tmp_path):
    src = tmp_path / "sync" / "base_clone.sh"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"#!/usr/bin/env bash\necho base clone\n")
    return src


# --- the declaration (Step 1) ---


def test_no_transport_validates_clean(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    assert launch.transport_error({}) is None
    assert launch.transport_error({"uploads": []}) is None
    assert launch.parse_transport({}) is None


def test_valid_branch_declaration_validates_and_parses(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    job = {"transport": dict(BRANCH)}
    assert launch.transport_error(job) is None
    assert launch.parse_transport(job) == BRANCH


def test_missing_fields_refuse_naming_the_field(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    for field in ("repo", "branch", "sha"):
        declared = {k: v for k, v in BRANCH.items() if k != field}
        err = launch.transport_error({"transport": declared})
        assert err is not None and field in err and "missing" in err, (field, err)


def test_missing_and_unknown_kind_refuse(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    err = launch.transport_error({"transport": {"repo": "r", "branch": "b", "sha": SHA}})
    assert err is not None and "kind" in err
    err = launch.transport_error({"transport": {"kind": "bundle", "repo": "r", "branch": "b", "sha": SHA}})
    assert err is not None and "bundle" in err and "kind" in err


def test_short_sha_and_nonstring_fields_refuse(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    err = launch.transport_error({"transport": {**BRANCH, "sha": "0123abcd"}})
    assert err is not None and "sha" in err and "40-hex" in err
    err = launch.transport_error({"transport": {**BRANCH, "branch": 7}})
    assert err is not None and "branch" in err
    err = launch.transport_error({"transport": ["branch"]})
    assert err is not None and "transport" in err


# --- the record stamp ---


def test_stamp_transport_branch_and_bundle(tmp_path):
    launch, _foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))
    rec = {}
    parsed = launch.stamp_transport(rec, {"transport": dict(BRANCH)})
    assert parsed == BRANCH
    assert rec["transport"]["kind"] == "branch"
    assert rec["transport"]["sha"] == SHA
    assert rec["transport"]["bytes_moved"] == 0
    assert rec["transport"]["fetch_bytes"] is None
    rec2 = {}
    assert launch.stamp_transport(rec2, {}) is None
    assert rec2["transport"] == {"kind": "bundle", "bytes_moved": 0}


def test_stamp_transport_span(tmp_path):
    launch, foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))

    def _epoch(value):
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except (TypeError, ValueError):
            return None

    foundation.epoch = _epoch
    rec = {"transport": {"kind": "branch"}, "started_at": "2026-11-23T00:00:00+00:00",
           "launch_confirmed_at": "2026-11-23T00:01:30+00:00"}
    launch.stamp_transport_span(rec)
    assert rec["transport"]["claim_to_launch_s"] == 90.0
    rec2 = {"transport": {"kind": "bundle"}, "started_at": "2026-11-23T00:00:00+00:00"}
    launch.stamp_transport_span(rec2)
    assert "claim_to_launch_s" not in rec2["transport"]


# --- registry resolution ---


def test_resolve_branch_ctx(tmp_path):
    launch, foundation, _journal = load_launch(tmp_path, ScriptedColab([], Path(tmp_path)))

    class Registry:
        @staticmethod
        def load_local_registry(root):
            return {}

        @staticmethod
        def get_entry(registry, repo_id):
            if repo_id != "supreme-octo-robot":
                raise ValueError(f"unknown repo {repo_id!r}")
            return repo_id, {"clone_url": "https://example.invalid/r.git", "dest": "supreme-octo-robot"}

    foundation.repo_registry = Registry
    assert launch.resolve_branch_ctx(None, None) == (None, None)
    err, ctx = launch.resolve_branch_ctx(BRANCH, {"manifest": {}})
    assert err is not None and "both" in err and ctx is None
    err, ctx = launch.resolve_branch_ctx({**BRANCH, "repo": "nope"}, None)
    assert err is not None and err.startswith("branch transport:") and ctx is None
    err, ctx = launch.resolve_branch_ctx(BRANCH, None)
    assert err is None
    assert ctx == {"clone_url": "https://example.invalid/r.git", "dest": "supreme-octo-robot"}


# --- the drive (Step 2) ---


def test_prepare_branch_lands_at_the_announced_sha(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("probe",), ("stdout", f"base clone at {SHA} tree abc\n")], src)
    launch, _foundation, journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-1")
    assert err is None, err
    assert info == {"dest": "supreme-octo-robot", "head": SHA}
    assert {"stage": "branch", "ok": True, "detail": BRANCH["branch"]} in journal


def test_prepare_branch_refuses_a_mismatched_head(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("probe",), ("stdout", f"base clone at {OTHER} tree abc\n")], src)
    launch, _foundation, journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-2")
    assert err is not None and "!=" in err and OTHER in err and SHA in err
    assert info == {}
    assert {"stage": "branch", "ok": False, "detail": BRANCH["branch"]} in journal


def test_prepare_branch_refuses_a_fetch_that_never_lands(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([("probe",), ("stdout", "fatal: could not read from remote repository\n")], src)
    launch, _foundation, journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-3")
    assert err is not None and "did not land" in err
    assert info == {}
    assert {"stage": "branch", "ok": False, "detail": BRANCH["branch"]} in journal


def test_prepare_branch_refuses_when_the_substrate_upload_fails(tmp_path):
    src = make_base_clone(tmp_path)
    colab = ScriptedColab([], src, upload_rc=1)
    launch, _foundation, _journal = load_launch(tmp_path, colab)
    err, info = launch.prepare_branch("sess", BRANCH, "https://example.invalid/r.git", "supreme-octo-robot", "run-4")
    assert err is not None and "base_clone.sh upload" in err
    assert info == {}
    assert colab.exec_calls == 0
