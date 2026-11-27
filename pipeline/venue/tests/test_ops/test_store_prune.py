"""The store prune's protections (owner ruling):
records are never candidates, work in flight keeps its
staging, a complete transfer's parts and an old snapshot
bundle are the first reclaim classes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "ops" / "store_prune.py"


def _sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "runner"
    (root / "var" / "chunks").mkdir(parents=True)
    (root / "results" / "runs").mkdir(parents=True)
    (root / "results" / "xfers").mkdir(parents=True)
    # The script loads its foundation module (and the paths
    # spine it binds) from the store root it is pointed at —
    # a real store is a full venue tree, so the sandbox
    # carries those two files or the module never loads.
    core = root / "sync" / "lease" / "core"
    core.mkdir(parents=True)
    shutil.copy(REPO / "sync" / "lease" / "core" / "foundation.py", core / "foundation.py")
    shutil.copy(REPO / "paths.py", root / "paths.py")
    # The terminal-job class's exclusion config,
    # provisioned with no exclusions: the class runs in
    # the sandbox by default, and the named-exclusion
    # test writes its own list over it.
    (root / "var" / "store-prune-excluded-dirs.json").write_text("[]")
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

    os.environ["VENUE_RUNNER_HOME"] = str(root)
    try:
        spec = importlib.util.spec_from_file_location("store_prune_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        chosen, _report = module.plan(1e15)
        return {str(p.relative_to(root)) for _o, p, _s, _c in chosen}
    finally:
        os.environ.pop("VENUE_RUNNER_HOME", None)


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
    # The specimen: a whole evening's gate
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
    os.environ["VENUE_RUNNER_HOME"] = str(root)
    try:
        spec = importlib.util.spec_from_file_location("store_prune_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        chosen, report = module.plan(1e15)
    finally:
        os.environ.pop("VENUE_RUNNER_HOME", None)
    paths = {str(p.relative_to(root)) for _o, p, _s, _c in chosen}
    assert "results/run-evening" not in paths
    assert "results/run-old" in paths
    assert report["payload_dirs"] == ["run-old"]
    assert report["payload_dirs_total"] == 1


def test_job_payload_archives_and_staging_tarballs_past_48h(tmp_path):
    root = _sandbox(tmp_path)
    job = root / "adapters" / "colab" / "jobs" / "some-job"
    _write(job / "job.json")                                   # the job's definition: never a candidate
    _write(job / "wrap.py")                                    # likewise retained (the precedent)
    _write(job / "payload-old.tar.gz", age_s=49 * 3600)        # past the 48h floor: prunable
    _write(job / "payload-fresh.tar.gz", age_s=3600)           # inside the floor: kept
    _write(job / "seed-old.bundle", age_s=49 * 3600)           # bundles ride the same class
    staging = root / "var" / "program-gates"
    _write(staging / "run1-tree.tar.gz", age_s=49 * 3600)      # launch staging past the floor: prunable
    _write(staging / "run2-tree.tar.gz", age_s=3600)           # fresh staging: kept
    _write(root / "var" / "loose-tree.tar.gz", age_s=49 * 3600)  # top-level var is not the subdir class
    chosen = _plan_paths(root)
    assert "adapters/colab/jobs/some-job/payload-old.tar.gz" in chosen
    assert "adapters/colab/jobs/some-job/seed-old.bundle" in chosen
    assert "var/program-gates/run1-tree.tar.gz" in chosen
    assert "adapters/colab/jobs/some-job/job.json" not in chosen
    assert "adapters/colab/jobs/some-job/wrap.py" not in chosen
    assert "adapters/colab/jobs/some-job/payload-fresh.tar.gz" not in chosen
    assert "var/program-gates/run2-tree.tar.gz" not in chosen
    assert "var/loose-tree.tar.gz" not in chosen


def test_staging_subdir_bundles_and_suffixed_tree_tarballs_past_48h(tmp_path):
    # The measured store gap: formations staging in a named
    # var/ subdir drop snapshot bundles beside their tree
    # tarballs, and the tarballs often carry a suffixed name
    # (lane01-tree-<hash>.tar.gz). Neither matched a class:
    # class 2 globs only the var/ top level, and class 7's
    # glob reached only the plain *-tree.tar.gz form.
    root = _sandbox(tmp_path)
    staging = root / "var" / "program-gates"
    _write(staging / "task-next-085.bundle", age_s=85 * 3600)         # staging bundle past the floor: prunable
    _write(staging / "task-next-999.bundle", age_s=3600)              # inside the floor: kept
    _write(staging / "lane01-tree-deadbeef.tar.gz", age_s=61 * 3600)  # suffixed tree tarball past the floor: prunable
    _write(staging / "lane01-tree-fresh.tar.gz", age_s=3600)          # suffixed, inside the floor: kept
    _write(staging / "lease-some-session.json", age_s=200 * 3600)   # records are never candidates, at any age
    _write(staging / "run-record.json", age_s=200 * 3600)           # likewise
    _record(root, "runs", "run-live.json", {"state": "running", "bundle_seed": {"bundle": "staging-seed.bundle"}})
    _write(staging / "staging-seed.bundle", age_s=85 * 3600)        # an in-flight run's seed: protected, kept
    chosen = _plan_paths(root)
    assert "var/program-gates/task-next-085.bundle" in chosen
    assert "var/program-gates/lane01-tree-deadbeef.tar.gz" in chosen
    assert "var/program-gates/task-next-999.bundle" not in chosen
    assert "var/program-gates/lane01-tree-fresh.tar.gz" not in chosen
    assert "var/program-gates/lease-some-session.json" not in chosen
    assert "var/program-gates/run-record.json" not in chosen
    assert "var/program-gates/staging-seed.bundle" not in chosen


def _job_record(root: Path, run_id: str, job: str, state: str, age_s: int = 0) -> None:
    """A run record the funnel stamped with its job; the
    record's mtime carries its activity, aged as asked."""
    _record(root, "runs", f"{run_id}.json", {"state": state, "job": job, "session": "s1"})
    if age_s:
        rec = root / "results" / "runs" / f"{run_id}.json"
        old = time.time() - age_s
        os.utime(rec, (old, old))


def test_terminal_job_payload_files_past_the_grace(tmp_path):
    root = _sandbox(tmp_path)
    _job_record(root, "old-job-20260101T000000Z", "old-job", "complete", age_s=49 * 3600)
    job = root / "adapters" / "colab" / "jobs" / "old-job"
    _write(job / "payload.tar.gz", age_s=49 * 3600)      # archives ride along
    _write(job / "data.bin", age_s=49 * 3600)            # loose payload files: the new class
    _write(job / "job.json", age_s=49 * 3600)            # the manifest: never a candidate
    _write(job / "verdicts.json", age_s=49 * 3600)       # output-shaped json: never a candidate
    _write(job / "register.jsonl", age_s=49 * 3600)      # likewise jsonl
    _write(job / "nested" / "inner.bin", age_s=49 * 3600)  # subdirectories are left alone
    chosen = _plan_paths(root)
    assert "adapters/colab/jobs/old-job/payload.tar.gz" in chosen
    assert "adapters/colab/jobs/old-job/data.bin" in chosen
    assert "adapters/colab/jobs/old-job/job.json" not in chosen
    assert "adapters/colab/jobs/old-job/verdicts.json" not in chosen
    assert "adapters/colab/jobs/old-job/register.jsonl" not in chosen
    assert "adapters/colab/jobs/old-job/nested/inner.bin" not in chosen


def test_terminal_job_payload_files_at_the_evidence_grace_boundary(tmp_path):
    root = _sandbox(tmp_path)
    _job_record(root, "cold-job-20260101T000000Z", "cold-job", "complete", age_s=7 * 3600)
    cold = root / "adapters" / "colab" / "jobs" / "cold-job"
    _write(cold / "data.bin", age_s=7 * 3600)            # newest activity 7h past: beyond the 6h grace
    _job_record(root, "warm-job-20260101T000000Z", "warm-job", "complete", age_s=5 * 3600)
    warm = root / "adapters" / "colab" / "jobs" / "warm-job"
    _write(warm / "data.bin", age_s=5 * 3600)            # newest activity 5h past: inside the grace
    chosen = _plan_paths(root)
    assert "adapters/colab/jobs/cold-job/data.bin" in chosen
    assert "adapters/colab/jobs/warm-job/data.bin" not in chosen


def test_job_with_any_live_record_is_untouched(tmp_path):
    root = _sandbox(tmp_path)
    _job_record(root, "mixed-job-20260101T000000Z", "mixed-job", "complete", age_s=72 * 3600)
    _job_record(root, "mixed-job-20260102T000000Z", "mixed-job", "running", age_s=72 * 3600)
    job = root / "adapters" / "colab" / "jobs" / "mixed-job"
    _write(job / "data.bin", age_s=72 * 3600)
    chosen = _plan_paths(root)
    assert "adapters/colab/jobs/mixed-job/data.bin" not in chosen


def test_named_excluded_payload_dir_untouched_other_payload_dirs_reclaim(tmp_path):
    root = _sandbox(tmp_path)
    # The exclusion list is the store's untracked
    # config: the sandbox's copy names the fixture's
    # shared input store.
    (root / "var" / "store-prune-excluded-dirs.json").write_text(
        json.dumps(["greenfield-ci-sampleform-payload"]))
    _job_record(root, "sample-20260101T000000Z", "greenfield-ci-sampleform-payload", "complete", age_s=72 * 3600)
    excluded = root / "adapters" / "colab" / "jobs" / "greenfield-ci-sampleform-payload"
    _write(excluded / "store.bin", age_s=72 * 3600)      # a named shared input store: never entered
    _job_record(root, "unclaimed-20260101T000000Z", "greenfield-ci-unclaimed-payload", "failed", age_s=72 * 3600)
    ordinary = root / "adapters" / "colab" / "jobs" / "greenfield-ci-unclaimed-payload"
    _write(ordinary / "store.bin", age_s=72 * 3600)      # a closed lane's payload store: ordinary
    chosen = _plan_paths(root)
    assert "adapters/colab/jobs/greenfield-ci-sampleform-payload/store.bin" not in chosen
    assert "adapters/colab/jobs/greenfield-ci-unclaimed-payload/store.bin" in chosen


def test_terminal_job_class_does_not_run_without_the_exclusion_config(tmp_path):
    # The honest degradation: with the exclusion
    # config not provisioned the class cannot prove a
    # payload dir is not a shared input store, so it
    # does not run at all — and the report says so.
    import importlib.util

    root = _sandbox(tmp_path)
    (root / "var" / "store-prune-excluded-dirs.json").unlink()
    _job_record(root, "old-job-20260101T000000Z", "old-job", "complete", age_s=49 * 3600)
    job = root / "adapters" / "colab" / "jobs" / "old-job"
    _write(job / "data.bin", age_s=49 * 3600)            # would be a candidate with the config provisioned
    os.environ["VENUE_RUNNER_HOME"] = str(root)
    try:
        spec = importlib.util.spec_from_file_location("store_prune_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        chosen, report = module.plan(1e15)
    finally:
        os.environ.pop("VENUE_RUNNER_HOME", None)
    paths = {str(p.relative_to(root)) for _o, p, _s, _c in chosen}
    assert "adapters/colab/jobs/old-job/data.bin" not in paths
    assert report["skipped_classes"] == [
        "job payload files of terminal jobs (excluded-dirs config not provisioned)"]


def test_job_with_no_records_and_terminal_job_inside_the_grace_are_untouched(tmp_path):
    root = _sandbox(tmp_path)
    ghost = root / "adapters" / "colab" / "jobs" / "ghost-job"
    _write(ghost / "data.bin", age_s=72 * 3600)          # no run records: no evidence of terminality
    _job_record(root, "fresh-job-20260101T000000Z", "fresh-job", "complete", age_s=3600)
    fresh = root / "adapters" / "colab" / "jobs" / "fresh-job"
    _write(fresh / "data.bin", age_s=72 * 3600)          # terminal, but its newest activity is inside the grace
    chosen = _plan_paths(root)
    assert "adapters/colab/jobs/ghost-job/data.bin" not in chosen
    assert "adapters/colab/jobs/fresh-job/data.bin" not in chosen


def test_tracked_file_in_a_terminal_job_dir_is_untouched(tmp_path):
    root = _sandbox(tmp_path)
    _job_record(root, "tracked-job-20260101T000000Z", "tracked-job", "orphaned", age_s=72 * 3600)
    job = root / "adapters" / "colab" / "jobs" / "tracked-job"
    _write(job / "wrap-payload.bin", age_s=72 * 3600)    # tracked below: a definition, not a payload
    _write(job / "loose.bin", age_s=72 * 3600)           # untracked control: chosen
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "adapters/colab/jobs/tracked-job/wrap-payload.bin"], check=True)
    chosen = _plan_paths(root)
    assert "adapters/colab/jobs/tracked-job/wrap-payload.bin" not in chosen
    assert "adapters/colab/jobs/tracked-job/loose.bin" in chosen


def _job_manifest(root: Path, job: str, manifest: dict, adapter: str = "colab") -> Path:
    """A job's own manifest under adapters/<adapter>/jobs/;
    the declaration the protected-staging class reads."""
    path = root / "adapters" / adapter / "jobs" / job / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest))
    return path


def test_declared_staging_for_a_job_with_no_terminal_run_survives(tmp_path):
    # The pre-fire specimen: staging dropped for a gate
    # not yet fired carries no terminal run, so the prune
    # cannot tell it from dead staging by age. Declared
    # staging survives past the 48h floor in all three
    # declaration forms.
    root = _sandbox(tmp_path)
    # The "staging_dirs" field; the job has no run
    # records at all (declared, not yet fired).
    _job_manifest(root, "declared-job", {"name": "declared-job", "staging_dirs": ["var/declared-gates"]})
    _write(root / "var" / "declared-gates" / "run1-tree.tar.gz", age_s=72 * 3600)
    _write(root / "var" / "declared-gates" / "seed.bundle", age_s=72 * 3600)
    # An "uploads" entry under var/<dir>/ — the form
    # existing manifests already use; the job's only
    # run is non-terminal.
    _job_manifest(root, "upload-job", {"name": "upload-job", "uploads": ["var/shared-gates/upload-job-tree.tar.gz"]})
    _job_record(root, "upload-job-20260101T000000Z", "upload-job", "running", age_s=72 * 3600)
    _write(root / "var" / "shared-gates" / "upload-job-tree.tar.gz", age_s=72 * 3600)
    # The job's own home var/<job-name>/, on a local
    # adapter manifest, with a non-terminal latest run.
    _job_manifest(root, "home-job", {"name": "home-job"}, adapter="local")
    _job_record(root, "home-job-20260101T000000Z", "home-job", "starting", age_s=72 * 3600)
    _write(root / "var" / "home-job" / "home-tree.tar.gz", age_s=72 * 3600)
    _write(root / "var" / "home-job" / "home.bundle", age_s=72 * 3600)
    chosen = _plan_paths(root)
    assert "var/declared-gates/run1-tree.tar.gz" not in chosen
    assert "var/declared-gates/seed.bundle" not in chosen
    assert "var/shared-gates/upload-job-tree.tar.gz" not in chosen
    assert "var/home-job/home-tree.tar.gz" not in chosen
    assert "var/home-job/home.bundle" not in chosen


def test_declared_staging_prunes_once_the_latest_run_is_terminal(tmp_path):
    # The same declarations as the survival specimen,
    # but the declaring job's latest run is terminal:
    # the declaration lapses and every form prunes
    # under the existing 48h floor.
    root = _sandbox(tmp_path)
    _job_manifest(root, "declared-job", {
        "name": "declared-job",
        "staging_dirs": ["var/declared-gates"],
        "uploads": ["var/shared-gates/declared-tree.tar.gz"],
    })
    _job_record(root, "declared-job-20260101T000000Z", "declared-job", "complete", age_s=72 * 3600)
    _write(root / "var" / "declared-gates" / "run1-tree.tar.gz", age_s=72 * 3600)
    _write(root / "var" / "declared-gates" / "seed.bundle", age_s=72 * 3600)
    _write(root / "var" / "shared-gates" / "declared-tree.tar.gz", age_s=72 * 3600)
    _write(root / "var" / "declared-job" / "home-tree.tar.gz", age_s=72 * 3600)
    chosen = _plan_paths(root)
    assert "var/declared-gates/run1-tree.tar.gz" in chosen
    assert "var/declared-gates/seed.bundle" in chosen
    assert "var/shared-gates/declared-tree.tar.gz" in chosen
    assert "var/declared-job/home-tree.tar.gz" in chosen


def test_declared_staging_follows_the_latest_run_not_any_run(tmp_path):
    root = _sandbox(tmp_path)
    # An older terminal run superseded by a newer
    # non-terminal one: the job is live again.
    _job_manifest(root, "revived-job", {"name": "revived-job", "staging_dirs": ["var/revived-gates"]})
    _job_record(root, "revived-job-20260101T000000Z", "revived-job", "complete", age_s=96 * 3600)
    _job_record(root, "revived-job-20260102T000000Z", "revived-job", "running", age_s=72 * 3600)
    _write(root / "var" / "revived-gates" / "revived-tree.tar.gz", age_s=72 * 3600)
    # An older non-terminal run superseded by a newer
    # terminal one: the declaration has lapsed.
    _job_manifest(root, "finished-job", {"name": "finished-job", "staging_dirs": ["var/finished-gates"]})
    _job_record(root, "finished-job-20260101T000000Z", "finished-job", "running", age_s=96 * 3600)
    _job_record(root, "finished-job-20260102T000000Z", "finished-job", "failed", age_s=72 * 3600)
    _write(root / "var" / "finished-gates" / "finished-tree.tar.gz", age_s=72 * 3600)
    chosen = _plan_paths(root)
    assert "var/revived-gates/revived-tree.tar.gz" not in chosen
    assert "var/finished-gates/finished-tree.tar.gz" in chosen


def test_undeclared_staging_keeps_the_existing_grace_rules(tmp_path):
    # A declaration elsewhere in the store changes
    # nothing for staging no live job declares: past
    # the floor it prunes, inside the floor it is kept.
    root = _sandbox(tmp_path)
    _job_manifest(root, "unrelated-job", {"name": "unrelated-job", "staging_dirs": ["var/other-gates"]})
    _write(root / "var" / "orphan-gates" / "old-tree.tar.gz", age_s=72 * 3600)
    _write(root / "var" / "orphan-gates" / "old.bundle", age_s=72 * 3600)
    _write(root / "var" / "orphan-gates" / "fresh-tree.tar.gz", age_s=3600)
    chosen = _plan_paths(root)
    assert "var/orphan-gates/old-tree.tar.gz" in chosen
    assert "var/orphan-gates/old.bundle" in chosen
    assert "var/orphan-gates/fresh-tree.tar.gz" not in chosen
