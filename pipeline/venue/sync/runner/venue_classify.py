#!/usr/bin/env python3
"""Venue-state classification: two samples in, one verdict out.

The classifier half of the venue-state mechanism (plan:
venue-state classification + state surface). A venue's truth
is its process table, never a run record's face: the sampler
(sync/runner/venue_sample.py) reads, per venue, the pid
table's occupancy and every live job tree's summed CPU ticks;
this leaf turns two consecutive samples into the venue's
state and one verdict per job, and writes the state file the
measures read (var/venue-state-<venue>.json).

Pure over its inputs: the previous sample, the current
sample, and the run records by run id (caller and timeout
evidence only — presence and progress come from the samples).
A classification issues on two samples; a first sample ever
carries no deltas and verdicts no job wedged.

Per-job verdicts:

- advancing: the tree's CPU time grew between the samples.
- stalled: the tree is alive, its CPU time is frozen (or it
  was not in the previous sample, so no delta exists), and
  it is within its progression grace and its record's
  timeout.
- wedged: the tree is alive with frozen CPU time and its
  age — now minus first-seen (the record enrichment's
  first_seen_at, falling back through the record's own
  launch stamps) — exceeds the grace, or exceeds the
  record's timeout_s. A tree still advancing past its
  timeout verdicts advancing here; the timeout reap keys
  off the record, not this verdict.
- gone: the tree is not alive in the current sample.

A job present in the previous sample and absent now is
omitted: it left the table between samples and its record
settles elsewhere.

Venue states, in precedence order:

- saturated: pids_current is at or above the saturation
  threshold of capacity — the saturation ratio's line,
  floored by the system reserve, whichever comes first
  (the sample's declared pids when it carries one, else
  its pids_max). Saturation outranks the job-derived
  states: a table at its ceiling refuses new work
  whatever the tracked jobs are doing — including when
  no tracked job is live and the table is held by
  untracked processes.
- wedged: at least one live job is wedged and none is
  advancing.
- advancing: at least one job tree is live (and the venue
  is neither saturated nor wedged by the rule above).
- idle: no live job trees.

The unreachable state is NOT computed here: it is a
transport verdict the bin entry writes when a venue cannot
be sampled at all.
"""

import json
from pathlib import Path

from .envelope import SYSTEM_RESERVE_THREADS
from .foundation import epoch, staged_write

SATURATION_RATIO = 0.85
GRACE_S = 600


def _saturation_threshold(capacity, saturation_ratio):
    """The pids_current at or above which a venue reads
    saturated: the ratio's line, floored by the system
    reserve — programme work is refused while the table's
    free remainder is inside the reserve
    (envelope.SYSTEM_RESERVE_THREADS), whatever ratio a
    configuration carries. At today's scales the ratio
    binds first; the floor is the invariant that keeps
    the reserve true at any capacity or ratio."""
    return min(saturation_ratio * capacity, capacity - SYSTEM_RESERVE_THREADS)


def _capacity(sample: dict):
    """The venue's declared pid capacity: a declared value
    the sample carries (pids_declared / pids_capacity, from
    the shape's budget) wins; else the sample's own read of
    the table's ceiling (pids_max)."""
    for key in ("pids_declared", "pids_capacity"):
        value = sample.get(key)
        if value:
            return value
    return sample.get("pids_max")


def _first_seen_epoch(rec: dict):
    """A job's age anchor: the first-seen stamp the bin
    entry enriches the record with (the earliest sample
    that saw the run), falling back through the record's
    own launch stamps. None is an honest unknown — an
    unanchored job is within grace by construction."""
    for key in ("first_seen_at", "started_at", "launch_at", "launch_confirmed_at"):
        value = epoch(rec.get(key))
        if value is not None:
            return value
    return None


def _job_verdict(job, prev_job, rec, *, now_epoch, first_sample, hz, grace_s):
    """(verdict, cpu_delta_s) for one job in the current
    sample. cpu_delta_s is None whenever no honest delta
    exists: no previous sample, the job absent from it, the
    tree gone, or a tick counter that moved backwards (a
    re-rooted tree — progression unknowable, never read as
    frozen)."""
    if not job.get("tree_alive"):
        return "gone", None
    if first_sample or prev_job is None:
        return "stalled", None
    delta_ticks = job.get("cpu_ticks", 0) - prev_job.get("cpu_ticks", 0)
    if delta_ticks < 0:
        return "stalled", None
    delta_s = delta_ticks / hz
    if delta_ticks > 0:
        return "advancing", delta_s
    # Frozen across the two samples: wedged past the grace
    # or past the record's own timeout, stalled inside both.
    seen = _first_seen_epoch(rec)
    age = None if seen is None or now_epoch is None else now_epoch - seen
    if age is not None and age > grace_s:
        return "wedged", delta_s
    timeout_s = rec.get("timeout_s")
    if age is not None and timeout_s is not None and age > timeout_s:
        return "wedged", delta_s
    return "stalled", delta_s


def classify(
    prev_sample,
    sample,
    records_by_run_id,
    *,
    hz=100,
    saturation_ratio=SATURATION_RATIO,
    grace_s=GRACE_S,
):
    """Classify one venue from two consecutive samples.

    prev_sample is the prior SAMPLE dict (None on the first
    pass ever); sample is the current one; records_by_run_id
    maps run id -> run record (or an enrichment of it). The
    sample's own hz, when it carries one, overrides the
    caller's. Returns the state dict in the state file's
    exact schema."""
    eff_hz = sample.get("hz") or hz
    records = records_by_run_id or {}
    prev_jobs = {}
    if prev_sample:
        prev_jobs = {j.get("run_id"): j for j in prev_sample.get("jobs", [])}
    now_epoch = epoch(sample.get("at"))
    jobs = []
    for job in sample.get("jobs", []):
        run_id = job.get("run_id")
        rec = records.get(run_id) or {}
        verdict, delta_s = _job_verdict(
            job,
            prev_jobs.get(run_id),
            rec,
            now_epoch=now_epoch,
            first_sample=prev_sample is None,
            hz=eff_hz,
            grace_s=grace_s,
        )
        jobs.append(
            {
                "run_id": run_id,
                "caller": rec.get("caller"),
                "root_pid": job.get("root_pid"),
                "tree_alive": bool(job.get("tree_alive")),
                "cpu_s": job.get("cpu_ticks", 0) / eff_hz,
                "cpu_delta_s": delta_s,
                "verdict": verdict,
            }
        )
    capacity = _capacity(sample)
    pids_current = sample.get("pids_current")
    live = [j for j in jobs if j["tree_alive"]]
    if (
        capacity
        and pids_current is not None
        and pids_current >= _saturation_threshold(capacity, saturation_ratio)
    ):
        state = "saturated"
    elif (
        live
        and any(j["verdict"] == "wedged" for j in live)
        and not any(j["verdict"] == "advancing" for j in live)
    ):
        state = "wedged"
    elif live:
        state = "advancing"
    else:
        state = "idle"
    return {
        "venue": sample.get("venue"),
        "state": state,
        "sampled_at": sample.get("at"),
        "pids_current": pids_current,
        "pids_capacity": capacity,
        "jobs": jobs,
    }


def write_state(state: dict, var_dir) -> Path:
    """Write one venue's state file through the unified
    writer (the foundation's staged_write — the venue's one
    write seam): a denied or failed write leaves the
    standing file byte-identical, so a measure never reads
    a torn state. Returns the file's path."""
    var_dir = Path(var_dir)
    var_dir.mkdir(parents=True, exist_ok=True)
    target = var_dir / f"venue-state-{state['venue']}.json"
    staged_write(target, (json.dumps(state, indent=2) + "\n").encode())
    return target
