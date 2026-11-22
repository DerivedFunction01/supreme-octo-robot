"""The store prune's protections (owner ruling 2026-11-12):
records are never candidates, work in flight keeps its
staging, a complete transfer's parts and an old snapshot
bundle are the first reclaim classes."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "ops" / "store_prune.py"


def _sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "runner"
    (root / "var" / "chunks").mkdir(parents=True)
    (root / "results" / "runs").mkdir(parents=True)
    (root / "results" / "xfers").mkdir(parents=True)
    return root


def _write(path: Path, data: bytes = b"x" * 64, age_s: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if age_s:
        old = time.time() - age_s
        os.utime(path, (old, old))
    return path


def _record(root: Path, kind: str, name: str, rec: dict) -> None:
    (root / "results" / kind / name).write_text(json.dumps(rec))


def _plan_paths(root: Path) -> set:
    import importlib.util

    os.environ["COLAB_RUNNER_HOME"] = str(root)
    try:
        spec = importlib.util.spec_from_file_location("store_prune_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        chosen, _report = module.plan(1e15)
        return {str(p.relative_to(root)) for _o, p, _s, _c in chosen}
    finally:
        os.environ.pop("COLAB_RUNNER_HOME", None)


def test_records_and_in_flight_work_are_never_candidates(tmp_path):
    root = _sandbox(tmp_path)
    _record(root, "runs", "run-live.json", {"state": "polling", "session": "s1"})
    _record(root, "runs", "run-done.json", {"state": "complete", "session": "s1", "last_evidence_at": "2026-11-09T00:00:00+00:00"})
    done_rec = root / "results" / "runs" / "run-done.json"
    old = time.time() - 25 * 3600
    os.utime(done_rec, (old, old))  # terminal AND cold: past the output grace
    _record(root, "runs", "run-fresh.json", {"state": "complete", "session": "s1"})  # terminal but fresh: a collector may be mid-verdict
    _record(root, "xfers", "up-1.json", {
        "state": "complete", "remote_name": "done.bundle",
        "started_at": "2026-11-12T00:00:00+00:00", "finished_at": "2026-11-12T00:01:00+00:00",
    })
    _write(root / "var" / "done.bundle.part-000")            # complete transfer: prunable
    _write(root / "var" / "old.bundle", age_s=3 * 3600)       # old snapshot: prunable
    _write(root / "var" / "fresh.bundle", age_s=60)           # under the floor: kept
    _write(root / "var" / "stray.bundle.part-000", age_s=60)  # fresh staging: kept
    _write(root / "results" / "run-live" / "out.bin")         # in flight: kept
    _write(root / "results" / "run-done" / "out.bin")         # terminal + cold payload: prunable
    _write(root / "results" / "run-fresh" / "out.bin")        # terminal but inside the grace: kept
    chosen = _plan_paths(root)
    assert "var/done.bundle.part-000" in chosen
    assert "var/old.bundle" in chosen
    assert "results/run-done" in chosen
    assert "results/run-fresh" not in chosen, "the prune swept a fresh terminal run's outputs (the M1 mid-collection specimen)"
    assert "var/fresh.bundle" not in chosen
    assert "var/stray.bundle.part-000" not in chosen
    assert "results/run-live" not in chosen
    assert not any(c.startswith("results/runs") or c.startswith("results/xfers") for c in chosen)


def test_terminal_payload_inside_a_day_is_kept_and_removed_dirs_are_named(tmp_path):
    # The 2026-11-21/22 specimen: a whole evening's gate
    # pulls swept at the two-hour grace during a low-free
    # window, invisibly. Inside a day a terminal payload
    # is evidence, not cold storage; past it, the pass
    # names what it removed.
    import importlib.util

    root = _sandbox(tmp_path)
    _record(root, "runs", "run-evening.json", {"state": "complete", "session": "s1"})
    evening_rec = root / "results" / "runs" / "run-evening.json"
    aged = time.time() - 3 * 3600
    os.utime(evening_rec, (aged, aged))  # terminal, 3h cold: inside the day grace
    _write(root / "results" / "run-evening" / "gate.log")
    _record(root, "runs", "run-old.json", {"state": "complete", "session": "s1"})
    old_rec = root / "results" / "runs" / "run-old.json"
    aged = time.time() - 25 * 3600
    os.utime(old_rec, (aged, aged))  # terminal, past the day grace
    _write(root / "results" / "run-old" / "gate.log")
    os.environ["COLAB_RUNNER_HOME"] = str(root)
    try:
        spec = importlib.util.spec_from_file_location("store_prune_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        chosen, report = module.plan(1e15)
    finally:
        os.environ.pop("COLAB_RUNNER_HOME", None)
    paths = {str(p.relative_to(root)) for _o, p, _s, _c in chosen}
    assert "results/run-evening" not in paths
    assert "results/run-old" in paths
    assert report["payload_dirs"] == ["run-old"]
    assert report["payload_dirs_total"] == 1


def test_job_payload_archives_and_staging_tarballs_past_48h(tmp_path):
    root = _sandbox(tmp_path)
    job = root / "adapters" / "colab" / "jobs" / "some-job"
    _write(job / "job.json")                                   # the job's definition: never a candidate
    _write(job / "wrap.py")                                    # likewise retained (2026-11-18 precedent)
    _write(job / "payload-old.tar.gz", age_s=49 * 3600)        # past the 48h floor: prunable
    _write(job / "payload-fresh.tar.gz", age_s=3600)           # inside the floor: kept
    _write(job / "seed-old.bundle", age_s=49 * 3600)           # bundles ride the same class
    staging = root / "var" / "steampower-gates"
    _write(staging / "run1-tree.tar.gz", age_s=49 * 3600)      # launch staging past the floor: prunable
    _write(staging / "run2-tree.tar.gz", age_s=3600)           # fresh staging: kept
    _write(root / "var" / "loose-tree.tar.gz", age_s=49 * 3600)  # top-level var is not the subdir class
    chosen = _plan_paths(root)
    assert "adapters/colab/jobs/some-job/payload-old.tar.gz" in chosen
    assert "adapters/colab/jobs/some-job/seed-old.bundle" in chosen
    assert "var/steampower-gates/run1-tree.tar.gz" in chosen
    assert "adapters/colab/jobs/some-job/job.json" not in chosen
    assert "adapters/colab/jobs/some-job/wrap.py" not in chosen
    assert "adapters/colab/jobs/some-job/payload-fresh.tar.gz" not in chosen
    assert "var/steampower-gates/run2-tree.tar.gz" not in chosen
    assert "var/loose-tree.tar.gz" not in chosen
