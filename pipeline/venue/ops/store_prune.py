#!/usr/bin/env python3
"""The runner store prune (owner ruling: "Auto
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
     archives beside it (by precedent);
  7. launch-staging tree tarballs in named var/ subdirs
     (var/*/*-tree*.tar.gz — the plain and suffixed forms,
     e.g. lane01-tree-<hash>.tar.gz) and snapshot bundles in
     the same staging subdirs (var/*/*.bundle), past the
     same 48 h floor — formation staging a lane dropped
     in the store's own namespace (a programme's
     gate-staging pattern); class 2's rationale (every launch rebuilds
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
     live record, and the job dirs the store's
     untracked config names as excluded
     (var/store-prune-excluded-dirs.json — shared
     input stores for in-flight lanes) are never
     entered. This class does not run at all when
     that config is not provisioned, and the report
     says so: without the operator's own exclusion
     list the class cannot prove a payload dir is
     not a shared store.

Protected staging: a var/ subdir a live job declares as
its gate staging is never a candidate, whatever the
staged files' age — staging dropped for a gate not yet
fired carries no run record, so age alone cannot tell
it from dead staging. A job declares a staging dir in
its own manifest (adapters/*/jobs/<job>/job.json)
three ways: the "staging_dirs" field (a "var/<dir>"
path or a bare "<dir>" name), an "uploads" entry under
var/<dir>/ (the form existing manifests already use),
and its own home var/<job-name>/ (the job's directory
name or its manifest "name"). A job is live while it
has no run records at all (declared, not yet fired)
or its latest run record is not terminal; once the
latest run is terminal the declaration lapses and
the dir prunes under the ordinary class rules.
Undeclared staging is unchanged.

Never touched: run and transfer RECORDS (results/runs,
results/xfers — metadata and verdicts are the evidence the
programmes cite), lease records, anything a non-terminal
run or a fresh non-terminal transfer references, declared
staging of a live job, anything younger than the class
floors, and anything outside the classes above. The prune
stops as soon as the free-space target is met. --dry-run
reports the plan without deleting. Every execution appends
its report to var/prune-log.jsonl.

The argument surface parses through the unified argv
contract (pipeline/platform/argv.py): --dry-run is a
safety flag (a boolean given a value refuses), the
numeric flags convert after the parse (a non-number is
a usage refusal, exit 2), and an unknown or malformed
token is a usage refusal, never a live prune.
"""

from __future__ import annotations

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

# The unified argv contract home, loaded by location
# through the paths spine.
_argv_spec = _ilu.spec_from_file_location(
    "pipeline_platform_argv", _paths.PLATFORM_ARGV)
platform_argv = _ilu.module_from_spec(_argv_spec)
_argv_spec.loader.exec_module(platform_argv)

DECLARATION = {
    "name": "store_prune",
    "summary": "prune the runner store to a free-space target",
    "flags": {
        "target-free-gb": {"takes_value": True, "default": 60.0,
                           "help": "free-space target in GB"},
        "if-below-gb": {"takes_value": True,
                        "help": "standing mode: exit 0 doing nothing "
                                "unless free space is below this"},
        "dry-run": {"safety": True,
                    "help": "report the plan without deleting"},
    },
}

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
# collector assembles the verdict from them (a
# prune pass swept an M1 gate's outputs mid-collection).
# Terminal alone is not cold: a run's payload dir is a
# candidate only once its last activity — collector
# heartbeat first, the record's own stamps as fallback —
# is older than this grace. The grace is a day, not two
# hours: gate outputs are landing evidence, cited and
# re-read across the working day that lands them —
# the two-hour grace once swept a whole evening's
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
# shared input stores for in-flight lanes, named by the
# operator in the store's untracked config (the sealed
# register's form: a name list in the var store, never
# tracked). The live names are operational data; tracked
# code carries none of them.
EXCLUDED_DIRS_REL = ("var", "store-prune-excluded-dirs.json")


def _terminal_job_excluded_dirs() -> frozenset | None:
    """The excluded job dirs from the untracked config,
    or None when it is not provisioned (absent,
    unreadable, or not a JSON list of names). None is
    the honest degradation: without the operator's
    list the terminal-job payload class cannot prove
    a payload dir is not a shared input store, so the
    class does not run — never a baked-in fallback."""
    try:
        data = json.loads(REPO.joinpath(*EXCLUDED_DIRS_REL).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, list) or not all(isinstance(name, str) for name in data):
        return None
    return frozenset(data)


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


TERMINAL_STATES = frozenset({"complete", "failed", "orphaned"})


def _staging_dir(raw, min_parts: int) -> "Path | None":
    """One manifest staging reference -> the var/ subdir
    it names. References are store-relative ("var/<dir>"
    or a bare "<dir>"); the staging dir is the first
    component under var/. Absolute paths, ".." parts,
    and references too shallow for the caller's form
    name nothing."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or text.startswith("/"):
        return None
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        return None
    if parts[0] == "var":
        parts = parts[1:]
    if len(parts) < min_parts:
        return None
    return VAR / parts[0]


def _protected_staging_dirs(latest_by_job: dict) -> set:
    """The var/ staging dirs declared by live jobs.

    Declaration is read from the jobs' own manifests
    under adapters/*/jobs/<job>/job.json — no registry.
    A manifest's job keys are its directory name and its
    "name" field (run records are stamped with either).
    A job is live when no record is stamped with any of
    its keys (declared staging, not yet fired) or when
    the newest such record is not terminal; a job whose
    latest run is terminal declares nothing. A live job
    protects its home var/<job-name>/ for each key, the
    dirs its "staging_dirs" field names, and the var/
    subdir each of its "uploads" entries sits under."""
    protected_staging: set = set()
    adapters_root = REPO / "adapters"
    if not adapters_root.exists():
        return protected_staging
    for manifest_path in sorted(adapters_root.glob("*/jobs/*/job.json")):
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            manifest = {}
        if not isinstance(manifest, dict):
            manifest = {}
        keys = {manifest_path.parent.name}
        name = manifest.get("name")
        if isinstance(name, str) and name:
            keys.add(name)
        records = [latest_by_job[key] for key in keys if key in latest_by_job]
        if records:
            _activity, latest_state = max(records, key=lambda item: item[0])
            if latest_state in TERMINAL_STATES:
                continue
        for key in keys:
            protected_staging.add(VAR / key)
        declared = manifest.get("staging_dirs")
        if isinstance(declared, str):
            declared = [declared]
        if isinstance(declared, list):
            for raw in declared:
                staging_dir = _staging_dir(raw, min_parts=1)
                if staging_dir is not None:
                    protected_staging.add(staging_dir)
        staging_dir = _staging_dir(manifest.get("staging_dir"), min_parts=1)
        if staging_dir is not None:
            protected_staging.add(staging_dir)
        uploads = manifest.get("uploads")
        if isinstance(uploads, list):
            for raw in uploads:
                staging_dir = _staging_dir(raw, min_parts=2)
                if staging_dir is not None:
                    protected_staging.add(staging_dir)
    return protected_staging


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
    skipped_classes: list = []

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
    latest_by_job: dict = {}
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
            if job not in latest_by_job or activity > latest_by_job[job][0]:
                latest_by_job[job] = (activity, rec.get("state"))
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
        protected_staging = _protected_staging_dirs(latest_by_job)
        for staging in VAR.glob("*/*-tree*.tar.gz"):
            if staging.name in protected:
                continue
            if any(parent in protected_staging for parent in staging.parents):
                continue
            if now - staging.stat().st_mtime > ARCHIVE_AGE_FLOOR_S:
                add(7, staging, "launch-staging tree tarballs past the 48h floor")
        for staging_bundle in VAR.glob("*/*.bundle"):
            if staging_bundle.name in protected:
                continue
            if any(parent in protected_staging for parent in staging_bundle.parents):
                continue
            if now - staging_bundle.stat().st_mtime > ARCHIVE_AGE_FLOOR_S:
                add(7, staging_bundle, "staging-subdir snapshot bundles past the 48h floor")
    excluded_dirs = _terminal_job_excluded_dirs() if jobs_root.exists() else None
    if jobs_root.exists() and excluded_dirs is None:
        skipped_classes.append(
            "job payload files of terminal jobs "
            "(excluded-dirs config not provisioned)"
        )
    if jobs_root.exists() and excluded_dirs is not None:
        tracked = _tracked_job_paths(jobs_root)
        already = {p for _o, p, _s, _c in candidates}
        for job_dir in sorted(jobs_root.iterdir()):
            if not job_dir.is_dir():
                continue
            if job_dir.name in excluded_dirs:
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
    # sweeps invisible to their consumers.
    payload_dirs = sorted(
        p.name
        for _o, p, _s, cls in chosen
        if cls == "payload dirs of terminal runs"
    )
    return chosen, {
        "free_before": free_now,
        "projected_free": projected,
        "classes": summary,
        "skipped_classes": skipped_classes,
        "payload_dirs": payload_dirs[:100],
        "payload_dirs_total": len(payload_dirs),
    }


def main() -> int:
    try:
        parsed = platform_argv.parse(DECLARATION, sys.argv[1:])
    except platform_argv.UsageError as exc:
        print(str(exc), file=sys.stderr)
        print(platform_argv.help_text(DECLARATION),
              file=sys.stderr, end="")
        return platform_argv.USAGE_EXIT
    if "help" in parsed:
        print(parsed["help"], end="")
        return 0
    flags = parsed["flags"]
    try:
        target_free_gb = float(flags["target-free-gb"])
        if_below_gb = (float(flags["if-below-gb"])
                       if flags["if-below-gb"] is not None else None)
    except ValueError:
        print("store_prune: --target-free-gb and --if-below-gb "
              "take numbers", file=sys.stderr)
        return platform_argv.USAGE_EXIT
    dry_run = flags["dry-run"]

    free_now = shutil.disk_usage(REPO).free
    if if_below_gb is not None and free_now >= if_below_gb * GB:
        # Standing mode stays silent above the threshold:
        # the scheduler entry reports on output, so a pass
        # that prunes nothing must print nothing.
        return 0
    chosen, report = plan(target_free_gb)
    reclaimed = 0
    if not dry_run:
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
            "pruned": not dry_run and bool(chosen),
            "dry_run": dry_run,
            "files": len(chosen),
            "reclaimed_bytes": reclaimed if not dry_run else 0,
            "free_after": shutil.disk_usage(REPO).free,
            "target_free_gb": target_free_gb,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    print(json.dumps(report, indent=2))
    if not dry_run and chosen:
        with (VAR / "prune-log.jsonl").open("a") as fh:
            fh.write(json.dumps(report) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
