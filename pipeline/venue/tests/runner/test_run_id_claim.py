"""claim_first_save: a fresh run's first save claims its id.

2026-11-14 specimen: run ids mint from a
second-resolution timestamp, so two launches of the
same job inside one second minted the identical id and the
second run's unconditional saves silently absorbed the
first's record and results dir. The claim writes the first
record with O_EXCL and suffixes -2, -3, … past any existing
file — these pins drive the claim directly against a stub
foundation rooted in a tmp dir, so the sequence is exact:
no wall clock, no timing window.
"""

import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

BASE = "job-20261114T200238Z"
STARTED = "2026-11-14T20:02:38+00:00"


def load_records(runs: Path):
    package = types.ModuleType("runner_claim_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_claim_unit"] = package
    foundation = types.ModuleType("runner_claim_unit.foundation")
    foundation.REPO = REPO
    foundation.RUNS = runs
    foundation.now = lambda: STARTED
    # Mega's records leaf binds the venue key and the unified
    # writer from its foundation; the stub binds both so the
    # import surface is satisfied (the claim stages its bytes
    # through the writer, then claims the name by hard link).
    foundation.VENUE = "test-venue"
    foundation.staged_write = lambda path, data: Path(path).write_bytes(data)
    sys.modules["runner_claim_unit.foundation"] = foundation
    return load_module(
        "runner_claim_unit.records", REPO / "sync" / "runner" / "records.py", register=True
    )


def fresh_rec(run_id=BASE):
    return {"run_id": run_id, "job": "job", "state": "starting", "started_at": STARTED}


def occupy(runs: Path, run_id: str) -> bytes:
    runs.mkdir(parents=True, exist_ok=True)
    marker = json.dumps({"run_id": run_id, "marker": "occupied"}).encode()
    (runs / f"{run_id}.json").write_bytes(marker)
    return marker


def test_free_base_claims_the_base(tmp_path):
    runs = tmp_path / "runs"
    records = load_records(runs)
    rec = fresh_rec()
    assert records.claim_first_save(rec) == BASE
    assert rec["run_id"] == BASE
    saved = json.loads((runs / f"{BASE}.json").read_text())
    assert saved["run_id"] == BASE
    # The claim prepares like a save: evidence stamp initialized.
    assert saved["last_evidence_at"] == STARTED


def test_occupied_base_suffixes_and_preserves_the_occupant(tmp_path):
    runs = tmp_path / "runs"
    marker = occupy(runs, BASE)
    records = load_records(runs)
    rec = fresh_rec()
    assert records.claim_first_save(rec) == f"{BASE}-2"
    assert (runs / f"{BASE}.json").read_bytes() == marker
    assert json.loads((runs / f"{BASE}-2.json").read_text())["run_id"] == f"{BASE}-2"


def test_two_occupied_claim_the_third(tmp_path):
    runs = tmp_path / "runs"
    occupy(runs, BASE)
    occupy(runs, f"{BASE}-2")
    records = load_records(runs)
    assert records.claim_first_save(fresh_rec()) == f"{BASE}-3"


def test_exhaustion_raises_and_restores_the_base_id(tmp_path):
    runs = tmp_path / "runs"
    occupy(runs, BASE)
    for n in range(2, 101):
        occupy(runs, f"{BASE}-{n}")
    records = load_records(runs)
    rec = fresh_rec()
    with pytest.raises(RuntimeError):
        records.claim_first_save(rec)
    assert rec["run_id"] == BASE


def test_denied_claim_consumes_no_id_and_leaves_no_file(tmp_path, monkeypatch):
    """2026-11-21 atomicity cure: the pre-cure claim wrote
    directly into the claimed file, so a write denied
    mid-write left a 0-byte record at the claimed name —
    the id consumed, the record a phantom. The link claim
    denied creates nothing: no file, no stage residue, and
    the same id answers the launch's retry."""
    runs = tmp_path / "runs"
    records = load_records(runs)
    monkeypatch.setattr(records, "CLAIM_LINK_RETRY_S", 0)

    def denied(src, dst):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(records.os, "link", denied)
    with pytest.raises(PermissionError):
        records.claim_first_save(fresh_rec())
    assert not (runs / f"{BASE}.json").exists()
    assert list(runs.iterdir()) == []
    monkeypatch.undo()
    assert records.claim_first_save(fresh_rec()) == BASE
    assert json.loads((runs / f"{BASE}.json").read_text())["run_id"] == BASE


def test_transient_link_denial_retries_the_same_candidate(tmp_path, monkeypatch):
    """The wave denies single operations: a link refused
    twice and then allowed still claims the base id —
    the retries spend no suffixes."""
    runs = tmp_path / "runs"
    records = load_records(runs)
    monkeypatch.setattr(records, "CLAIM_LINK_RETRY_S", 0)
    real_link = records.os.link
    attempts = {"n": 0}

    def flaky(src, dst):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise PermissionError(1, "Operation not permitted")
        return real_link(src, dst)

    monkeypatch.setattr(records.os, "link", flaky)
    assert records.claim_first_save(fresh_rec()) == BASE
    assert attempts["n"] == 3
    assert not (runs / f"{BASE}-2.json").exists()
    # No stage residue survives a settled claim.
    assert [p.name for p in runs.iterdir()] == [f"{BASE}.json"]
