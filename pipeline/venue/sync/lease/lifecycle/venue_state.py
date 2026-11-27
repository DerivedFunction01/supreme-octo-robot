"""Colab venue-state parity (venue-state mechanism, step 6).

The local venues' classification comes from the sampler's
/proc reads; Colab has no process table to read, so the
reap pass computes the same classification from the reads
it already makes — the shared session snapshot and each
record's live-jobs projection — into the same state-file
shape, through the same classifier, so the four states
verdict identically on both venue kinds and every measure
reads one surface.

The progression signal a Colab run offers is its evidence
clock: the run record's last_evidence_at, which the
collector and the sweep advance while the run is attended.
A sample's per-job cpu_ticks is that clock's epoch (the
sample carries hz 1, so the state file's cpu_s is the
evidence epoch and cpu_delta_s is the seconds of evidence
advance between samples): evidence advancing is the
advancing verdict, evidence frozen across two reap passes
past the grace — or past the run's own timeout, when its
record carries one — is the wedged verdict. A session the
snapshot reads absent has no live trees. Pid occupancy is
the session's live-job count against no declared capacity:
saturation never verdicts for a Colab session until a
capacity is declared for it, which is the classifier's own
rule, not a special case here.

One state file per session (var/venue-state-<session>.json)
plus the fleet aggregate (var/venue-state-colab.json) the
Colab dispatch entry's saturation leg reads. No new Colab
traffic: every input is a local file or the pass's shared
snapshot.
"""

import importlib.util as _ilu
import json
from pathlib import Path

from ..core import foundation, records

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form, as
# the lease core binds it.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent.parent.parent / "paths.py"
)
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

_LEAVES = None


def _leaves():
    """The runner's sampler/classifier leaves, loaded by
    path behind a synthetic package whose foundation is a
    shim over this package's own foundation (the leaves'
    epoch and staged_write, single-sourced here). Loaded
    once; the reap pass calls this under its own guard, so
    a load failure disables the parity phase, never the
    reap."""
    global _LEAVES
    if _LEAVES is not None:
        return _LEAVES
    import sys
    import types

    runner_dir = _paths.RUNNER_DIR

    package = types.ModuleType("venue_state_runner")
    package.__path__ = [str(runner_dir)]
    shim = types.ModuleType("venue_state_runner.foundation")
    shim.epoch = foundation.epoch
    shim.staged_write = foundation.staged_write
    sys.modules["venue_state_runner"] = package
    sys.modules["venue_state_runner.foundation"] = shim
    leaves = {}
    for name in ("venue_sample", "venue_classify"):
        spec = _ilu.spec_from_file_location(
            f"venue_state_runner.{name}", runner_dir / f"{name}.py"
        )
        module = _ilu.module_from_spec(spec)
        sys.modules[f"venue_state_runner.{name}"] = module
        spec.loader.exec_module(module)
        leaves[name] = module
    _LEAVES = leaves
    return leaves


def run_record_for(repo: Path, run_id: str):
    """One runner run record by id, read plainly from the
    runs store, or None."""
    try:
        data = json.loads((repo / "results" / "runs" / f"{run_id}.json").read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _evidence_ticks(run_rec, entry):
    """A run's progression counter: the epoch of its latest
    evidence stamp, falling back through its start stamps.
    Zero is the honest floor — a run with no readable clock
    reads frozen, and the grace decides what that means."""
    for source in (run_rec, entry):
        if not isinstance(source, dict):
            continue
        for key in ("last_evidence_at", "started_at"):
            value = source.get(key)
            if value is None:
                continue
            try:
                return int(foundation.parse_dt(str(value)).timestamp())
            except (TypeError, ValueError):
                continue
    return 0


def session_sample(repo: Path, rec: dict, *, session_live: bool, at: str) -> dict:
    """One session's sample in the sampler leaf's shape,
    from the record's live-jobs projection and the run
    records behind it."""
    jobs = []
    for entry in records.live_jobs(repo, rec):
        if entry.get("kind") != "run":
            continue
        run_rec = run_record_for(repo, entry["id"]) or {}
        jobs.append(
            {
                "run_id": entry["id"],
                "root_pid": None,
                "tree_alive": bool(session_live),
                "cpu_ticks": _evidence_ticks(run_rec, entry),
            }
        )
    return {
        "venue": rec["session"],
        "at": at,
        "hz": 1,
        "pids_current": len(jobs),
        "pids_max": None,
        "jobs": jobs,
        "errors": [],
    }


def fleet_sample(repo: Path, recs: list, live_by_session: dict, at: str) -> dict:
    """The fleet aggregate sample (venue "colab"): every
    home record's live runs under one venue key — the file
    the Colab dispatch entry's saturation leg reads."""
    jobs = []
    for rec in recs:
        sample = session_sample(
            repo, rec, session_live=bool(live_by_session.get(rec["session"])), at=at
        )
        jobs.extend(sample["jobs"])
    return {
        "venue": "colab",
        "at": at,
        "hz": 1,
        "pids_current": len(jobs),
        "pids_max": None,
        "jobs": jobs,
        "errors": [],
    }


def _first_seen(store, sample) -> dict:
    """run id -> the earliest sample stamp that saw it,
    over the venue's whole store plus this sample (the
    sampler entry's enrichment, mirrored): the age anchor
    the classifier's grace and timeout verdicts measure
    from."""
    seen = {}
    path = store.path_for(str(sample["venue"]))
    lines = []
    if path.exists():
        lines = path.read_text().splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        for job in entry.get("jobs", []):
            run_id = job.get("run_id")
            if run_id is not None and run_id not in seen:
                seen[run_id] = entry.get("at")
    for job in sample.get("jobs", []):
        run_id = job.get("run_id")
        if run_id is not None and run_id not in seen:
            seen[run_id] = sample.get("at")
    return seen


def classify_and_write(repo: Path, sample: dict) -> dict:
    """Append one sample to the venue's store, classify it
    against the previous sample through the shared
    classifier, and write the state file. Returns the
    state dict written."""
    leaves = _leaves()
    var_dir = foundation.var_dir(repo)
    store = leaves["venue_sample"].SampleStore(
        root=var_dir, writer=foundation.staged_write
    )
    history = store.last_two(str(sample["venue"]))
    prev_sample = history[-1] if history else None
    first_seen = _first_seen(store, sample)
    store.append(sample)
    records_by_run_id = {}
    for job in sample.get("jobs", []):
        run_id = job.get("run_id")
        run_rec = run_record_for(repo, run_id) or {}
        enriched = {
            "caller": run_rec.get("caller"),
            "timeout_s": run_rec.get("timeout_s"),
            "started_at": run_rec.get("started_at"),
        }
        if first_seen.get(run_id) is not None:
            enriched["first_seen_at"] = first_seen[run_id]
        records_by_run_id[run_id] = enriched
    state = leaves["venue_classify"].classify(prev_sample, sample, records_by_run_id)
    leaves["venue_classify"].write_state(state, var_dir)
    return state


def pass_colab(repo: Path, recs: list, live_by_session: dict, at: str) -> dict:
    """The reap pass's parity phase: classify every home-
    venue record's session and the fleet aggregate, from
    the pass's own reads. Returns {venue: state name} for
    the pass's report. The caller guards the phase — a
    parity failure never breaks the reap."""
    written = {}
    home = [
        rec
        for rec in recs
        if (rec.get("venue") or foundation.VENUE) == foundation.VENUE
    ]
    for rec in home:
        sample = session_sample(
            repo,
            rec,
            session_live=bool(live_by_session.get(rec["session"])),
            at=at,
        )
        state = classify_and_write(repo, sample)
        written[rec["session"]] = state["state"]
    if home:
        state = classify_and_write(repo, fleet_sample(repo, home, live_by_session, at))
        written["colab"] = state["state"]
    return written
