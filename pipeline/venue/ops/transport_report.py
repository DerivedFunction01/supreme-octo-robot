#!/usr/bin/env python3
"""The branch-transport adoption measure (branch-transport
plan, Step 4): per-programme transport counts read from the
run records, so a bundle fallback is a visible, countable
event rather than a silent habit.

Every run record (results/runs/<run_id>.json) carries its
fire stamp (started_at), its launch stamp (launch_at), its
caller attribution, and — since the branch-transport build
landed — the transport the runner used (transport.kind,
with the claim→launch span the launch measured). This
report reads records only; it launches nothing and writes
nothing.

Counting, over the window (records whose started_at falls
inside it):

- fired: a record exists — the run was claimed.
- launched: launch_at is stamped.
- never-launched: fired with no launch stamp.
- branch / bundle: a launched run counts as branch when
  its transport stamp names kind "branch"; every other
  launched run counts as bundle — the explicit "bundle"
  stamp, or no stamp at all (the pre-stamp era, when the
  snapshot bundle was the only transport that existed).
- programme: the programme the caller registry declares
  for the caller (config/callers.json's "programmes"
  object, read through the lease core's callers module):
  the caller string ahead of any ":" sub-attribution is
  the registry key, so a lane suffix reports under its
  base's programme. A caller with no declared programme
  keeps its own name as its row, and a record with no
  caller reads "unknown".

The median claim→launch span is reported per programme
and kind from the stamps that carry one (transport.
claim_to_launch_s); unstamped runs contribute counts,
never a fabricated span.

Windows: --day YYYY-MM-DD reads that UTC calendar day;
--end ISO with --hours N (default 24) reads the rolling
window ending at that instant; no arguments read the last
24 hours. --runs-dir reads a records directory other than
the store's own (a mirror, an archive, a test sandbox).
Output is one JSON object on stdout.
"""

from __future__ import annotations

import argparse
import importlib.util as _ilu
import json
import os
import statistics
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form. The
# COLAB_RUNNER_HOME override stays here: it re-roots the
# whole store, mirror-side, by design (as in store_prune).
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

_env_home = os.environ.get("COLAB_RUNNER_HOME")
REPO = Path(_env_home) if _env_home else _paths.REPO_RESOLVED
RUNS = REPO / "results" / "runs"

# Timestamp parsing and formatting ride the venue subtree's
# shared date home (the lease core foundation), never a
# local copy.
_foundation_spec = _ilu.spec_from_file_location(
    "venue_lease_foundation",
    REPO / "sync" / "lease" / "core" / "foundation.py")
foundation = _ilu.module_from_spec(_foundation_spec)
_foundation_spec.loader.exec_module(foundation)

# The lease core's callers module carries the registry's
# programme declarations; it imports its foundation as a
# package sibling, so it is bound under a synthetic package
# whose foundation is the instance above.
_core_pkg = types.ModuleType("venue_lease_core")
_core_pkg.__path__ = [str(REPO / "sync" / "lease" / "core")]
_core_pkg.foundation = foundation
sys.modules.setdefault("venue_lease_core", _core_pkg)
sys.modules.setdefault("venue_lease_core.foundation", foundation)
_callers_spec = _ilu.spec_from_file_location(
    "venue_lease_core.callers",
    REPO / "sync" / "lease" / "core" / "callers.py")
callers = _ilu.module_from_spec(_callers_spec)
sys.modules["venue_lease_core.callers"] = callers
_callers_spec.loader.exec_module(callers)


def programme(caller, programmes=None) -> str:
    """The report row for one record's caller: the registry's
    declared programme for the caller's base (the string ahead
    of any ":" sub-attribution), else the base itself; a record
    with no caller reads "unknown". `programmes` is the
    declaration map (callers.caller_programmes); None resolves
    it from this store's registry."""
    if not caller or not isinstance(caller, str):
        return "unknown"
    head = caller.split(":")[0]
    if programmes is None:
        programmes = callers.caller_programmes(REPO)
    return programmes.get(head) or head


def _epoch(ts):
    if not isinstance(ts, str):
        return None
    return foundation.epoch(ts)


def summarize(records, start_epoch: float, end_epoch: float,
              programmes=None) -> dict:
    """The pure count: an iterable of record dicts and the
    window [start_epoch, end_epoch) over started_at.
    `programmes` is the registry's declaration map
    (callers.caller_programmes); None resolves it from this
    store's registry, once, before counting."""
    if programmes is None:
        programmes = callers.caller_programmes(REPO)
    programmes_out: dict[str, dict] = {}
    spans: dict[str, dict[str, list]] = {}
    seen = skipped_no_start = 0

    def row(name):
        return programmes_out.setdefault(name, {
            "fired": 0, "launched": 0, "branch": 0,
            "bundle": 0, "never_launched": 0})

    for rec in records:
        seen += 1
        fired_at = _epoch(rec.get("started_at"))
        if fired_at is None:
            skipped_no_start += 1
            continue
        if not (start_epoch <= fired_at < end_epoch):
            continue
        name = programme(rec.get("caller"), programmes)
        r = row(name)
        r["fired"] += 1
        if not rec.get("launch_at"):
            r["never_launched"] += 1
            continue
        r["launched"] += 1
        transport = rec.get("transport")
        kind = transport.get("kind") if isinstance(transport, dict) else None
        kind = "branch" if kind == "branch" else "bundle"
        r[kind] += 1
        span = transport.get("claim_to_launch_s") if isinstance(transport, dict) else None
        if isinstance(span, (int, float)):
            spans.setdefault(name, {"branch": [], "bundle": []})[kind].append(span)

    totals = {"fired": 0, "launched": 0, "branch": 0,
              "bundle": 0, "never_launched": 0}
    for name, r in programmes_out.items():
        for key in totals:
            totals[key] += r[key]
        med = spans.get(name, {"branch": [], "bundle": []})
        r["median_claim_to_launch_s"] = {
            k: (round(statistics.median(v), 1) if v else None)
            for k, v in med.items()}
    return {
        "programmes": dict(sorted(programmes_out.items())),
        "totals": totals,
        "records_seen": seen,
        "records_skipped_no_start": skipped_no_start,
    }


def load_records(runs_dir: Path):
    """Every parseable record in the directory; unparseable
    files are counted, never silently read as runs."""
    records, unparseable = [], 0
    for path in sorted(runs_dir.glob("*.json")):
        try:
            rec = json.loads(path.read_text())
        except (OSError, ValueError):
            unparseable += 1
            continue
        if isinstance(rec, dict):
            records.append(rec)
        else:
            unparseable += 1
    return records, unparseable


def _iso(epoch_s: float) -> str:
    return foundation.iso_utc(datetime.fromtimestamp(epoch_s, timezone.utc))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None,
                    help="a UTC calendar day, YYYY-MM-DD")
    ap.add_argument("--end", default=None,
                    help="rolling window end (ISO); default: now")
    ap.add_argument("--hours", type=float, default=24.0,
                    help="rolling window length in hours (default 24)")
    ap.add_argument("--runs-dir", default=None,
                    help="records directory other than the store's own")
    args = ap.parse_args()

    if args.day:
        start = _epoch(f"{args.day}T00:00:00+00:00")
        if start is None:
            print(f"transport_report: unparseable --day {args.day!r}",
                  file=sys.stderr)
            return 2
        end = start + 24 * 3600
        window = {"kind": "day", "day": args.day}
    else:
        end = _epoch(args.end) if args.end else time.time()
        if end is None:
            print(f"transport_report: unparseable --end {args.end!r}",
                  file=sys.stderr)
            return 2
        start = end - args.hours * 3600
        window = {"kind": "rolling", "hours": args.hours}
    window["start"] = _iso(start)
    window["end"] = _iso(end)

    runs_dir = Path(args.runs_dir) if args.runs_dir else RUNS
    records, unparseable = load_records(runs_dir)
    report = summarize(records, start, end)
    report["window"] = window
    report["runs_dir"] = str(runs_dir)
    report["records_unparseable"] = unparseable
    report["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
