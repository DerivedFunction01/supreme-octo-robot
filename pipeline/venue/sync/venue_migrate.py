#!/usr/bin/env python3
"""The §10.3 one-time migration: stamp the legacy record stock
with its venue, and disposition the hygiene remainder.

Ruled 2026-11-13 (plan §10.3): legacy lease/run records are
STAMPED `venue: colab` in a one-time migration at S5 — records
rewritten once, and no read-time default exists in any reader
to outlive its truth. This module is that migration. It is
deliberately re-runnable: at S11's cutover it runs once more
against the then-live store, and a record already stamped is
counted, never rewritten.

Hygiene (S1 finding 4, as updated by the 2026-11-13
reconciliation): run-record files that cannot be parsed, and
the record whose state (`completed`) is outside the contract's
three terminal states, are NOT repaired and NOT rewritten into
a guessed shape. They are quarantined — renamed out of the
runs namespace with their bytes preserved, the torn-record
precedent of the lease core (records.quarantine_torn) — and
named in the report this returns. A state is never invented
for a record whose own state is not in the vocabulary.

All writes ride the unified writer's staged protocol through
the lease core's foundation seam (plan §4.15).
"""

import importlib.util as _ilu
import json
import os
from datetime import datetime, timezone
from pathlib import Path


# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)


def _load_foundation():
    spec = _ilu.spec_from_file_location(
        "colab_lease_foundation", _paths.LEASE_FOUNDATION)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


foundation = _load_foundation()

TERMINAL_STATES = ("complete", "failed", "orphaned")
NONTERMINAL_STATES = ("starting", "running", "polling")
LEASE_EXCLUDES = ("lease-spend.json", "lease-request.json", "lease-handover.json")


def _stamp(path: Path, rec: dict, venue: str) -> bool:
    """Stamp one record in place (via the writer protocol).
    Returns True when a write happened."""
    if rec.get("venue") == venue:
        return False
    rec["venue"] = venue
    foundation.staged_write(path, json.dumps(rec, indent=2).encode())
    return True


def _quarantine(path: Path, tag: str, stamp: str) -> str:
    dst = path.with_name(f"{path.name}.{tag}-{stamp}")
    if dst.exists():
        dst = path.with_name(f"{path.name}.{tag}-{stamp}-{os.getpid()}")
    os.replace(path, dst)
    return dst.name


def migrate_store(var_dir: Path, runs_dir: Path, venue: str = "colab",
                  now_dt: datetime | None = None, dry_run: bool = False) -> dict:
    """Stamp one store (a var dir + a runs dir). Returns the
    census: what was stamped, what already carried the key,
    and every quarantine with its reason."""
    now_dt = now_dt or datetime.now(timezone.utc)
    stamp = now_dt.strftime("%Y%m%dT%H%M%SZ")
    out = {
        "venue": venue,
        "lease_stamped": 0, "lease_already": 0, "lease_unreadable": [],
        "evidence_stamped": 0, "evidence_already": 0,
        "runs_stamped": 0, "runs_already": 0,
        "quarantined": [],
    }
    var_dir = Path(var_dir)
    runs_dir = Path(runs_dir)
    if var_dir.is_dir():
        for path in sorted(var_dir.glob("lease-*.json")):
            if path.name in LEASE_EXCLUDES:
                continue
            try:
                rec = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                rec = None
            if not isinstance(rec, dict) or not rec.get("session"):
                # A lease file that cannot yield a record is the
                # torn-record class: the lease core serves it as
                # a finding and quarantines at its own writers —
                # the migration names it and leaves it to them.
                out["lease_unreadable"].append(path.name)
                continue
            if dry_run:
                out["lease_already" if rec.get("venue") == venue else "lease_stamped"] += 1
            elif _stamp(path, rec, venue):
                out["lease_stamped"] += 1
            else:
                out["lease_already"] += 1
        for path in sorted(var_dir.glob("session-evidence-*.json")):
            try:
                rec = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(rec, dict):
                continue
            if dry_run:
                out["evidence_already" if rec.get("venue") == venue else "evidence_stamped"] += 1
            elif _stamp(path, rec, venue):
                out["evidence_stamped"] += 1
            else:
                out["evidence_already"] += 1
    if runs_dir.is_dir():
        for path in sorted(runs_dir.glob("*.json")):
            try:
                rec = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                rec = None
            if not isinstance(rec, dict):
                if not dry_run:
                    as_name = _quarantine(path, "unparseable", stamp)
                else:
                    as_name = f"{path.name}.unparseable-{stamp}"
                out["quarantined"].append(
                    {"file": path.name, "as": as_name, "reason": "unparseable"})
                continue
            state = rec.get("state")
            if state is not None and state not in TERMINAL_STATES + NONTERMINAL_STATES:
                if not dry_run:
                    as_name = _quarantine(path, "invalid-state", stamp)
                else:
                    as_name = f"{path.name}.invalid-state-{stamp}"
                out["quarantined"].append(
                    {"file": path.name, "as": as_name,
                     "reason": f"state {state!r} outside the contract vocabulary"})
                continue
            if dry_run:
                out["runs_already" if rec.get("venue") == venue else "runs_stamped"] += 1
            elif _stamp(path, rec, venue):
                out["runs_stamped"] += 1
            else:
                out["runs_already"] += 1
    return out


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="colab-venue-migrate")
    ap.add_argument("--var", required=True, help="the store's var dir")
    ap.add_argument("--runs", required=True, help="the store's results/runs dir")
    ap.add_argument("--venue", default="colab")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    report = migrate_store(Path(args.var), Path(args.runs), venue=args.venue,
                           dry_run=args.dry_run)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
