#!/usr/bin/env python3
"""The runner store prune (owner ruling, 2026-11-12: "Auto
prune, don't wait for me to state it — else it becomes too
late and I get locked out").

The store's growth driver is transfer staging: every seeded
launch uploads a ~109 MB snapshot bundle in 32 MB parts, and
the parts (plus the bundles themselves) accumulate in var/
long after their transfers complete. This prune reclaims,
in order:

  1. parts of COMPLETE transfers (var/*.part-*, var/chunks/*)
     — residue the moment the transfer lands;
  2. snapshot bundles at var/*.bundle (+ their manifests)
     older than the bundle age floor — every launch rebuilds
     its own from the source repo, which holds the truth;
  3. parts of failed / stale-running transfers and
     record-less parts past the resume window (24 h) — a
     failed transfer's parts are resume state, kept a day;
  4. results/<run-id>/ payload dirs of terminal runs;
  5. gate scratch bundles/patches in the workspace's
     tmp-gate directory;
  6. payload archives inside adapters job dirs
     (adapters/colab/jobs/*/*.tar.gz, *.bundle) past a
     48 h floor — the job's definition (job.json, wrap.py)
     is never a candidate, only the staged payload
     archives beside it (2026-11-18 precedent);
  7. launch-staging tree tarballs in named var/ subdirs
     (var/*/*-tree*.tar.gz — the plain and suffixed forms,
     e.g. hc01-tree-<hash>.tar.gz) and snapshot bundles in
     the same staging subdirs (var/*/*.bundle), past the
     same 48 h floor — formation staging a lane dropped
     in the store's own namespace (the steampower-gates
     pattern); class 2's rationale (every launch rebuilds
     its own from the source repo, which holds the truth)
     applies to the bundles, and the top-level class's
     shorter floor does not apply here, where formations
     stage beside their tarballs;
  8. job payload files of terminal jobs: the top-level
     files of adapters/colab/jobs/<job>/ when every run
     record stamped with that job is terminal (complete,
     failed, orphaned) and the job's newest record
     activity is past this class's evidence grace
     (6 h — terminality is the protection, so the
     archive classes' 48 h floor does not apply here).
     Never
     candidates even there: job.json, any *.json or
     *.jsonl file, files git tracks, and protected
     names. A job with no run records, a job with any
     live record, and the named excluded job dirs
     (shared input stores for in-flight lanes) are
     never entered.

Never touched: run and transfer RECORDS (results/runs,
results/xfers — metadata and verdicts are the evidence the
programmes cite), lease records, anything a non-terminal
run or a fresh non-terminal transfer references, anything
younger than the class floors, and anything outside the
classes above. The prune stops as soon as the free-space
target is met. --dry-run reports the plan without deleting.
Every execution appends its report to var/prune-log.jsonl.
"""

from __future__ import annotations

import argparse
import importlib.util as _ilu
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form. The
# COLAB_RUNNER_HOME override stays here: it re-roots the
# whole store, mirror-side, by design.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

_env_home = os.environ.get("COLAB_RUNNER_HOME")
REPO = Path(_env_home) if _env_home else _paths.REPO_RESOLVED
VAR = REPO / "var"
RESULTS = REPO / "results"
TMP_GATE = REPO.parent / "tmp-gate"
GB = 1024**3

BUNDLE_AGE_FLOOR_S = 2 * 3600
ARCHIVE_AGE_FLOOR_S = 48 * 3600
RESUME_WINDOW_S = 24 * 3600
FRESH_XFER_S = 3600
SCRATCH_AGE_FLOOR_S = 3600
# A completed run's outputs are at their hottest while its
# collector assembles the verdict from them (2026-11-12: a
# prune pass swept an M1 gate's outputs mid-collection).
# Terminal alone is not cold: a run's payload dir is a
# candidate only once its last activity — collector
# heartbeat first, the record's own stamps as fallback —
# is older than this grace. The grace is a day, not two
# hours: gate outputs are landing evidence, cited and
# re-read across the working day that lands them — on
# 2026-11-21/22 the two-hour grace swept a whole evening's
# gate pulls (gates A–U, the wd-diag verdict log) during
# the low-free window before their consumers re-read
# them, invisibly, because the prune log named no paths.
OUTPUT_GRACE_S = 24 * 3600

# The terminal-job payload class's evidence grace: a
# job's payload files are candidates once its newest
# record activity is older than this. Terminality is
# the protection — every record terminal means no run
# of the job is in flight — so this class does not
# ride the 48 h archive floor; the grace only leaves
# room for a terminal run's last evidence to land in
# its record before the job's payloads read as cold.
TERMINAL_JOB_EVIDENCE_GRACE_S = 6 * 3600

# Job dirs the terminal-job payload class never enters:
# shared input stores for in-flight lanes (the segment
# finish lane and the PPE recall build read them as live
# inputs). Named exactly; the set empties when those
# lanes hand back.
TERMINAL_JOB_EXCLUDED_DIRS = frozenset(
    {
        "specimen-ci-segform-payload",
        "specimen-ci-ppeform-payload",
        "specimen-ci-pperes-payload",
        "specimen-ci-pperes2-payload",
        "specimen-ci-ppesucc-payload",
        "specimen-ci-ppev1-payload",
    }
)


_foundation_spec = _ilu.spec_from_file_location(
    "venue_lease_foundation",
    REPO / "sync" / "lease" / "core" / "foundation.py")
foundation = _ilu.module_from_spec(_foundation_spec)
_foundation_spec.loader.exec_module(foundation)


def _epoch(iso) -> float:
    if iso is None:
        return 0.0
    parsed = foundation.epoch(str(iso))
    return parsed if parsed is not None else 0.0


def _load_records() -> tuple[set, list]:
    """Protected file names from in-flight work, and the
    transfer records indexed by the names their parts carry."""
    protected: set = set()
    now = time.time()
    for path in (RESULTS / "runs").glob("*.json"):
        try:
            rec = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("state") in ("starting", "running", "polling"):
            seed = rec.get("bundle_seed") or {}
            if seed.get("bundle"):
                protected.add(Path(seed["bundle"]).name)
    xfers = []
    for path in (RESULTS / "xfers").glob("*.json"):
        try:
            rec = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        rec["_stamp"] = max(_epoch(rec.get("finished_at")), _epoch(rec.get("started_at")), path.stat().st_mtime)
        xfers.append(rec)
        if rec.get("state") in ("starting", "running") and now - rec["_stamp"] < FRESH_XFER_S:
            for key in ("remote_name", "local_path"):
                if rec.get(key):
                    protected.add(Path(rec[key]).name)
    return protected, xfers


def _part_base(name: str) -> str:
    """sp-x.bundle.part-000 -> sp-x.bundle (also .part-0)."""
    stem, dot, tail = name.rpartition(".part-")
    return stem if dot and tail.isdigit() else name


def _tracked_job_paths(jobs_root: Path) -> set:
    """Absolute paths under the jobs root that git tracks
    — definitions (wrap scripts, manifests), never
    payloads. An unreadable or non-git store tracks
    nothing the prune can prove, so it yields the empty
    set rather than guessing."""
    try:
        rel = jobs_root.relative_to(REPO)
    except ValueError:
        return set()
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "--", str(rel)],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if out.returncode != 0:
        return set()
    return {REPO / line for line in out.stdout.splitlines() if line}


def plan(target_free_gb: float) -> tuple[list, dict]:
    now = time.time()
    protected, xfers = _load_records()
    by_base: dict = {}
    for rec in xfers:
        for key in ("remote_name", "local_path"):
            if rec.get(key):
                by_base.setdefault(Path(rec[key]).name, []).append(rec)

    def part_class(path: Path) -> "tuple[int, str] | None":
        base = _part_base(path.name)
        if base in protected or path.name in protected:
            return None
        recs = by_base.get(base, [])
        age = now - path.stat().st_mtime
        if recs:
            newest = max(recs, key=lambda r: r["_stamp"])
            if newest.get("state") == "complete":
                return (1, "parts of complete transfers")
            if now - newest["_stamp"] > RESUME_WINDOW_S and age > RESUME_WINDOW_S:
                return (3, "parts past the resume window")
            return None
        # No record: the runner's own internal transfers
        # (seed uploads) write no xfer record — their parts
        # are re-staged from the source file by any later
        # launch, so past the age floor they are pure residue.
        if age > BUNDLE_AGE_FLOOR_S:
            return (2, "unrecorded transfer staging past the age floor")
        return None

    candidates: list = []  # (order, path, bytes, class)

    def add(order: int, path: Path, cls: str):
        try:
            size = path.stat().st_size if path.is_file() else sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        except OSError:
            return
        candidates.append((order, path, size, cls))

    for part in list(VAR.glob("*.part-*")) + list((VAR / "chunks").glob("*")):
        if not part.is_file():
            continue
        verdict = part_class(part)
        if verdict:
            add(verdict[0], part, verdict[1])
    for bundle in VAR.glob("*.bundle"):
        if bundle.name in protected:
            continue
        if now - bundle.stat().st_mtime > BUNDLE_AGE_FLOOR_S:
            add(2, bundle, "snapshot bundles past the age floor")
            manifest = Path(str(bundle) + ".manifest.json")
            if manifest.exists():
                add(2, manifest, "snapshot bundles past the age floor")
    terminal_cold = set()
    job_activity: dict = {}
    job_live: set = set()
    all_record_stems = {p.stem for p in (RESULTS / "runs").glob("*.json")}
    for path in (RESULTS / "runs").glob("*.json"):
        try:
            rec = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        activity = path.stat().st_mtime
        for key in ("collector_at", "last_evidence_at", "finished_at"):
            activity = max(activity, _epoch(rec.get(key)))
        job = rec.get("job")
        if isinstance(job, str) and job:
            job_activity[job] = max(job_activity.get(job, 0.0), activity)
            if rec.get("state") not in ("complete", "failed", "orphaned"):
                job_live.add(job)
        if rec.get("state") not in ("complete", "failed", "orphaned"):
            continue
        if now - activity > OUTPUT_GRACE_S:
            terminal_cold.add(path.stem)
    for entry in RESULTS.iterdir():
        if entry.is_dir() and entry.name not in ("runs", "xfers"):
            if entry.name in terminal_cold or (entry.name not in all_record_stems and now - entry.stat().st_mtime > RESUME_WINDOW_S):
                add(4, entry, "payload dirs of terminal runs")
    if TMP_GATE.exists():
        for scratch in list(TMP_GATE.glob("*.bundle")) + list(TMP_GATE.glob("*.patch")):
            if now - scratch.stat().st_mtime > SCRATCH_AGE_FLOOR_S:
                add(5, scratch, "gate scratch")
    jobs_root = REPO / "adapters" / "colab" / "jobs"
    if jobs_root.exists():
        for archive in list(jobs_root.glob("*/*.tar.gz")) + list(jobs_root.glob("*/*.bundle")):
            if archive.name in protected:
                continue
            if now - archive.stat().st_mtime > ARCHIVE_AGE_FLOOR_S:
                add(6, archive, "job payload archives past the 48h floor")
    if VAR.exists():
        for staging in VAR.glob("*/*-tree*.tar.gz"):
            if staging.name in protected:
                continue
            if now - staging.stat().st_mtime > ARCHIVE_AGE_FLOOR_S:
                add(7, staging, "launch-staging tree tarballs past the 48h floor")
        for staging_bundle in VAR.glob("*/*.bundle"):
            if staging_bundle.name in protected:
                continue
            if now - staging_bundle.stat().st_mtime > ARCHIVE_AGE_FLOOR_S:
                add(7, staging_bundle, "staging-subdir snapshot bundles past the 48h floor")
    if jobs_root.exists():
        tracked = _tracked_job_paths(jobs_root)
        already = {p for _o, p, _s, _c in candidates}
        for job_dir in sorted(jobs_root.iterdir()):
            if not job_dir.is_dir():
                continue
            if job_dir.name in TERMINAL_JOB_EXCLUDED_DIRS:
                continue
            if job_dir.name not in job_activity or job_dir.name in job_live:
                continue
            if now - job_activity[job_dir.name] <= TERMINAL_JOB_EVIDENCE_GRACE_S:
                continue
            for entry in sorted(job_dir.iterdir()):
                if not entry.is_file():
                    continue
                if entry.name == "job.json" or entry.name.endswith((".json", ".jsonl")):
                    continue
                if entry.name in protected or entry in tracked or entry in already:
                    continue
                add(8, entry, "job payload files of terminal jobs")

    candidates.sort(key=lambda c: (c[0], -c[2]))
    free_now = shutil.disk_usage(REPO).free
    chosen, projected = [], free_now
    for order, path, size, cls in candidates:
        if projected >= target_free_gb * GB:
            break
        chosen.append((order, path, size, cls))
        projected += size
    summary: dict = {}
    for _o, _p, size, cls in chosen:
        summary[cls] = summary.get(cls, {"files": 0, "bytes": 0})
        summary[cls]["files"] += 1
        summary[cls]["bytes"] += size
    # The payload dirs a pass removes are named in the
    # report (bounded): an aggregate-only log made the
    # 2026-11-21/22 sweeps invisible to their consumers.
    payload_dirs = sorted(
        p.name
        for _o, p, _s, cls in chosen
        if cls == "payload dirs of terminal runs"
    )
    return chosen, {
        "free_before": free_now,
        "projected_free": projected,
        "classes": summary,
        "payload_dirs": payload_dirs[:100],
        "payload_dirs_total": len(payload_dirs),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-free-gb", type=float, default=60.0)
    ap.add_argument("--if-below-gb", type=float, default=None, help="standing mode: exit 0 doing nothing unless free space is below this")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    free_now = shutil.disk_usage(REPO).free
    if args.if_below_gb is not None and free_now >= args.if_below_gb * GB:
        # Standing mode stays silent above the threshold:
        # the scheduler entry reports on output, so a pass
        # that prunes nothing must print nothing.
        return 0
    chosen, report = plan(args.target_free_gb)
    reclaimed = 0
    if not args.dry_run:
        for _o, path, size, _cls in chosen:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                reclaimed += size
            except OSError:
                continue
    report.update(
        {
            "pruned": not args.dry_run and bool(chosen),
            "dry_run": args.dry_run,
            "files": len(chosen),
            "reclaimed_bytes": reclaimed if not args.dry_run else 0,
            "free_after": shutil.disk_usage(REPO).free,
            "target_free_gb": args.target_free_gb,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    print(json.dumps(report, indent=2))
    if not args.dry_run and chosen:
        with (VAR / "prune-log.jsonl").open("a") as fh:
            fh.write(json.dumps(report) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
