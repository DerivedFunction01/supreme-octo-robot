#!/usr/bin/env python3
"""Register-required component: a tracked surface's set
matches its tracked register exactly, and every write
surface carries ignore coverage.

Two checks, both over the tracked tree:

- Register match. The scheduler's tracked jobs surface
  (pipeline/scheduling/jobs) carries a tracked register
  (pipeline/scheduling/jobs-register.json) naming every
  tracked file there with its class. The tracked set and
  the register must agree exactly: a tracked file with no
  register entry fails, and a register entry with no
  tracked file fails the other way. This is the load-time
  admission rule's shape extended to the tracked tree —
  an instance entry re-entering the tracked set becomes
  a gate failure at the next gate, not a census finding
  months later. The register carries ids and classes in
  generic form only; instance entries live in the
  deployment's untracked overlay and never stand in it.

- Ignore coverage. Every directory the machinery writes
  run logs, run records, or generated instance files
  into carries ignore rules covering those writes. The
  probe set below names the known write surfaces; each
  probe is a representative written path checked with
  git check-ignore. An uncovered write surface is a
  finding in itself: auto-commit machinery and ordinary
  adds are how ignored-in-intent files become tracked
  in fact.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REGISTER_PATH = "pipeline/scheduling/jobs-register.json"
SURFACE_PREFIX = "pipeline/scheduling/jobs/"

# The known write surfaces: (directory, representative
# written file). A probe the ignore rules do not cover
# is a finding.
WRITE_SURFACES = (
    ("pipeline/scheduling/state", "probe-run-state.json"),
    ("pipeline/scheduling/bodies", "probe-body.md"),
    ("pipeline/scheduling/jobs-overlay", "probe-job.yaml"),
    ("pipeline/scheduling/staging", "probe-staging.tar.gz"),
    ("pipeline/venue/results/landings", "probe-landing.json"),
    ("pipeline/venue/var", "probe-state.json"),
    ("pipeline/platform/var", "probe-state.json"),
    ("pipeline/platform/state", "probe-layer.txt"),
    ("pipeline/attention/var", "probe-state.json"),
)


def compare(tracked_files, register_files):
    """(rows, failures): the exact-match verdict, both
    directions. tracked_files and register_files are file
    names within the surface."""
    tracked = set(tracked_files)
    registered = set(register_files)
    rows = [f"registered and tracked: {len(tracked & registered)}"]
    failures = []
    for name in sorted(tracked - registered):
        failures.append(
            f"tracked file with no register entry: {name}")
    for name in sorted(registered - tracked):
        failures.append(
            f"register entry with no tracked file: {name}")
    return rows, failures


def probe_coverage(check_ignore):
    """(rows, failures) over the write surfaces;
    check_ignore(relpath) answers True when the ignore
    rules cover the path."""
    rows = []
    failures = []
    for directory, probe in WRITE_SURFACES:
        relpath = f"{directory}/{probe}"
        if check_ignore(relpath):
            rows.append(f"write surface covered: {directory}")
        else:
            failures.append(
                f"write surface with no ignore coverage: {directory}")
    return rows, failures


def _tracked_surface_files(repo_root):
    proc = subprocess.run(
        ["git", "ls-files", "--", "pipeline/scheduling/jobs"],
        cwd=repo_root, capture_output=True, text=True, check=True)
    return [line[len(SURFACE_PREFIX):]
            for line in proc.stdout.splitlines()
            if line.startswith(SURFACE_PREFIX)]


def _check_ignore(repo_root):
    def check(relpath):
        proc = subprocess.run(
            ["git", "check-ignore", "-q", "--", relpath],
            cwd=repo_root, capture_output=True, text=True)
        return proc.returncode == 0
    return check


def scan(repo_root):
    """(rows, failures, scanned): the register match and
    the ignore-coverage probes over the tree at repo_root."""
    root = Path(repo_root)
    register = json.loads((root / REGISTER_PATH).read_text())
    register_files = [entry["file"] for entry in register["entries"]]
    tracked_files = _tracked_surface_files(root)
    rows, failures = compare(tracked_files, register_files)
    probe_rows, probe_failures = probe_coverage(_check_ignore(root))
    rows += probe_rows
    failures += probe_failures
    return rows, failures, len(tracked_files)


def render(rows, failures, scanned):
    lines = [f"register-required: {scanned} tracked files "
             f"on the registered surface"]
    lines += [f"  {row}" for row in rows]
    lines += [f"  FINDING: {failure}" for failure in failures]
    return lines
