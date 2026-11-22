"""Single-flight claims: one run id, one execution.

The 2026-11-21 twin-execution root: a daemonized claim landed
after its parent's wait had declared it dead, and a resume
relaunched the id — two executions, one record. These pins
drive claims.py against a stub foundation rooted in a tmp dir:
the parent's pre-claim, the decidable-lost test, the resume
attach verdict, and the child's adoption.
"""

import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

BASE = "job-20261121T200238Z"
STARTED = "2026-11-21T20:02:38+00:00"


def load_claims(runs: Path):
    package = types.ModuleType("runner_claims_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_claims_unit"] = package
    foundation = types.ModuleType("runner_claims_unit.foundation")
    foundation.REPO = REPO
    foundation.RUNS = runs
    foundation.now = lambda: STARTED
    foundation.VENUE = "test-venue"
    foundation.staged_write = lambda path, data: Path(path).write_bytes(data)
    sys.modules["runner_claims_unit.foundation"] = foundation
    load_module("runner_claims_unit.records", REPO / "sync" / "runner" / "records.py", register=True)
    return load_module("runner_claims_unit.claims", REPO / "sync" / "runner" / "claims.py", register=True)


def _reaped_pid() -> int:
    import subprocess as sp

    p = sp.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def claiming_rec(**over):
    rec = {
        "run_id": BASE,
        "job": "job",
        "state": "claiming",
        "started_at": STARTED,
        "claim_by": "daemonize-parent",
        "claim_deadline": (datetime.now(timezone.utc) + timedelta(seconds=180)).isoformat(),
    }
    rec.update(over)
    return rec


def past_deadline() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()


def test_pre_claim_writes_a_claiming_record(tmp_path):
    claims = load_claims(tmp_path)
    rec = claims.pre_claim("job", BASE, None, "workhorse")
    assert rec["run_id"] == BASE
    on_disk = json.loads((tmp_path / f"{BASE}.json").read_text())
    assert on_disk["state"] == "claiming"
    assert on_disk["claim_by"] == "daemonize-parent"
    assert on_disk["caller"] == "workhorse"
    deadline = datetime.fromisoformat(on_disk["claim_deadline"])
    assert deadline > datetime.now(timezone.utc)


def test_pre_claim_suffixes_past_an_existing_record(tmp_path):
    claims = load_claims(tmp_path)
    (tmp_path / f"{BASE}.json").write_text(json.dumps({"run_id": BASE, "marker": "occupied"}))
    rec = claims.pre_claim("job", BASE, None, None)
    assert rec["run_id"] == f"{BASE}-2"
    assert json.loads((tmp_path / f"{BASE}.json").read_text())["marker"] == "occupied"


def test_claim_lost_needs_deadline_and_dead_pid(tmp_path):
    claims = load_claims(tmp_path)
    assert claims.claim_lost(claiming_rec(claim_deadline=past_deadline(), daemon_child_pid=_reaped_pid()))
    assert not claims.claim_lost(claiming_rec(claim_deadline=past_deadline(), daemon_child_pid=os.getpid()))
    assert not claims.claim_lost(claiming_rec(daemon_child_pid=_reaped_pid()))
    assert not claims.claim_lost(claiming_rec(state="running", claim_deadline=past_deadline(), daemon_child_pid=_reaped_pid()))


def test_attach_verdict_keys_on_state(tmp_path):
    claims = load_claims(tmp_path)
    live_claim = claims.attach_verdict(claiming_rec(daemon_child_pid=os.getpid()))
    assert live_claim == {"attached": True, "state": "claiming", "reason": "claim-outstanding"}
    assert claims.attach_verdict(claiming_rec(claim_deadline=past_deadline(), daemon_child_pid=_reaped_pid())) is None
    running = {"run_id": BASE, "state": "running", "launch_confirmed_at": STARTED}
    verdict = claims.attach_verdict(running)
    assert verdict["attached"] and verdict["collect_via"] == "--poll"
    assert claims.attach_verdict({"run_id": BASE, "state": "starting"}) is None
    assert claims.attach_verdict({"run_id": BASE, "state": "complete"}) is None


def test_adopt_moves_only_a_parents_claim(tmp_path):
    claims = load_claims(tmp_path)
    (tmp_path / f"{BASE}.json").write_text(json.dumps(claiming_rec()))
    rec = claims.adopt(BASE, "cpu-highram")
    assert rec["state"] == "starting"
    assert rec["claim_adopted_at"] == STARTED
    assert rec["shape"] == "cpu-highram"
    foreign = claiming_rec(claim_by="someone-else")
    (tmp_path / f"{BASE}.json").write_text(json.dumps(foreign))
    assert claims.adopt(BASE, "cpu-highram") is None


def test_stamp_takeover_keeps_the_prior_claims_facts(tmp_path):
    claims = load_claims(tmp_path)
    rec = claiming_rec(daemon_child_pid=4242)
    claims.stamp_takeover(rec)
    assert rec["claim_takeover_from"] == 4242
    assert rec["claim_takeover_at"] == STARTED
