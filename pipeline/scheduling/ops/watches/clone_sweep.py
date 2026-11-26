#!/usr/bin/env python3
"""Formation-clone sweeper: reaps gate-formation clones in
the workspace scratch roots once they pass the 1-hour
reconciliation window (the same window the worktree trim
gives archived worktrees).

Formation clones are created only under per-run directories
named <job>-<UTC yyyymmddThhmmssZ> inside the scratch roots
(tmp-gate, tmp-gate2, .tmp-parent-gate, tmp-s7 under the
workspace root). The timestamp in the name IS the stamp:
age is computed from the name, never from mtime (mtime lies
under copies). A directory whose name carries no valid run
timestamp is not a formation clone and is never touched —
provenance before deletion is the standing cleanup rule,
and an unmatched name means unproven provenance.

A candidate (matching name, older than the window) is
still kept while either live-process marker stands:

- an open fd into the directory (the /proc scan: every
  /proc/<pid>/fd symlink target is resolved and compared);
- a non-terminal runner run record naming it (a record
  under the venue results dir whose checkpoint carries no
  exit_code and whose own text names the path).

Bundles and run records are never candidates: they do not
match the naming pattern, and only directories directly
under a scratch root are ever considered. Session-side
clones under /content die with their session and are out
of scope.

Speech: silent when nothing qualifies; one CLONE-SWEEP
line per reap (name and age) and per failure, and in
dry-run mode one line per would-reap and per guard-keep
(a keep is not an act, so a real run stays silent about
it and simply re-examines it next cycle). Exit codes:
0 = swept (or nothing to do); 3 = a root could not be
listed or a removal failed (loud, the watches' convention).
--dry-run lists what a real run WOULD reap and removes
nothing; the job entry ships in that form until admission.

The argument surface parses through the unified argv
contract (pipeline/platform/argv.py): --dry-run is a
safety flag, honoured in either form (--dry-run,
--dry-run=<value> refuses — a boolean takes no value),
and an unknown or malformed token is a usage refusal
(exit 2), never a live sweep.

Stdlib only; paths derive from this file's location via
ops/paths.py. Tests inject fixture roots, a fixed now, and
fake probe results (or a fake proc root / results dir);
production reads the real roots, /proc, and the venue
results dir.
"""
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

# The unified argv contract home (pipeline/platform/argv.py),
# loaded by location under a private name — the tree's
# standing seam for platform modules (the stdlib owns the
# bare name `platform`). The path derives exactly as the
# paths spine derives PLATFORM_WRITER.
_argv_spec = _importlib_util.spec_from_file_location(
    "pipeline_platform_argv",
    os.path.join(os.path.dirname(paths.REPO_ROOT),
                 "platform", "argv.py"))
platform_argv = _importlib_util.module_from_spec(_argv_spec)
_argv_spec.loader.exec_module(platform_argv)

DECLARATION = {
    "name": "clone-sweep",
    "summary": "reap formation clones past the "
               "reconciliation window",
    "flags": {
        "dry-run": {"safety": True,
                    "help": "list what a real run would reap; "
                            "remove nothing"},
    },
    "verdict_codes": {"sweep-failed": 3},
}

WINDOW_SECS = int(os.environ.get("CLONE_SWEEP_WINDOW_SECS", "3600"))
PROC_ROOT = os.environ.get("CLONE_SWEEP_PROC", "/proc")
RESULTS_DIR = os.environ.get(
    "CLONE_SWEEP_RESULTS",
    os.path.join(os.path.dirname(paths.REPO_ROOT), "venue", "results"))
_ROOT_NAMES = ("tmp-gate", "tmp-gate2", ".tmp-parent-gate", "tmp-s7")


def default_roots():
    raw = os.environ.get("CLONE_SWEEP_ROOTS", "")
    if raw:
        return [p for p in raw.split(os.pathsep) if p]
    return [os.path.join(paths.WORKSPACE_ROOT, name)
            for name in _ROOT_NAMES]


_NAME_RE = re.compile(
    r"^(?P<prefix>[a-z0-9]+(?:[-_][a-z0-9]+)*)"
    r"-(?P<ts>\d{8}T\d{6}Z)$")


def formation_stamp(name):
    """The run timestamp a directory name carries as a
    timezone-aware datetime, or None when the name is not a
    formation-clone name. Strict: the stamp must sit at the
    very end of the name, parse as a real UTC calendar
    second (month 13, Feb 30, hour 25 all refuse), and
    round-trip byte-for-byte."""
    match = _NAME_RE.match(name)
    if not match:
        return None
    ts = match.group("ts")
    try:
        stamp = datetime.strptime(ts, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    if stamp.strftime("%Y%m%dT%H%M%SZ") != ts:
        return None
    return stamp.replace(tzinfo=timezone.utc)


def fd_held_paths(proc_root):
    """Absolute paths held open by any live process: the
    resolved targets of every /proc/<pid>/fd symlink.
    Unreadable entries are skipped — a process exiting
    mid-scan is the normal race, not a finding."""
    held = set()
    try:
        pids = os.listdir(proc_root)
    except OSError:
        return held
    for pid in pids:
        if not pid.isdigit():
            continue
        fd_dir = os.path.join(proc_root, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if target.endswith(" (deleted)"):
                target = target[:-len(" (deleted)")]
            held.add(target)
    return held


def nonterminal_record_texts(results_dir):
    """The text of every non-terminal runner run record
    under the results dir. A record is non-terminal while
    its checkpoint.json carries no exit_code; its own text
    files (checkpoint, logs) are what can name a clone
    directory. Terminal records protect nothing."""
    texts = []
    try:
        runs = os.listdir(results_dir)
    except OSError:
        return texts
    for run in sorted(runs):
        rdir = os.path.join(results_dir, run)
        checkpoint = os.path.join(rdir, "checkpoint.json")
        try:
            with open(checkpoint, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or "exit_code" in data:
            continue
        try:
            names = os.listdir(rdir)
        except OSError:
            continue
        for name in sorted(names):
            if not name.endswith((".json", ".log", ".txt", ".md")):
                continue
            try:
                with open(os.path.join(rdir, name),
                          encoding="utf-8",
                          errors="replace") as fh:
                    texts.append(fh.read())
            except OSError:
                continue
    return texts


def _is_held(path, held_paths):
    prefix = path + os.sep
    return any(p == path or p.startswith(prefix) for p in held_paths)


def fmt_age(age_secs):
    return "age=%.1fh" % (age_secs / 3600.0)


def run(roots, at, dry_run=False, window_secs=WINDOW_SECS,
        held_paths=None, record_texts=None, proc_root=PROC_ROOT,
        results_dir=RESULTS_DIR):
    """One sweep over the roots: returns (exit_code, lines).
    All inputs injectable — tests pass fixture roots, a
    fixed `at`, and fake probe results, or fake proc/results
    dirs for the probes themselves."""
    if held_paths is None:
        held_paths = fd_held_paths(proc_root)
    if record_texts is None:
        record_texts = nonterminal_record_texts(results_dir)
    lines = []
    failed = False
    for root in roots:
        try:
            entries = sorted(os.listdir(root))
        except OSError:
            lines.append("CLONE-SWEEP root unreadable: %s" % root)
            failed = True
            continue
        for name in entries:
            path = os.path.join(root, name)
            if os.path.islink(path) or not os.path.isdir(path):
                continue
            stamp = formation_stamp(name)
            if stamp is None:
                continue
            age = (at - stamp).total_seconds()
            if age <= window_secs:
                continue
            if _is_held(path, held_paths):
                if dry_run:
                    lines.append(
                        "CLONE-SWEEP kept (live fd): %s %s"
                        % (path, fmt_age(age)))
                continue
            if any(path in text for text in record_texts):
                if dry_run:
                    lines.append(
                        "CLONE-SWEEP kept (live run record): %s %s"
                        % (path, fmt_age(age)))
                continue
            if dry_run:
                lines.append("CLONE-SWEEP would reap %s %s"
                             % (path, fmt_age(age)))
                continue
            try:
                shutil.rmtree(path)
            except OSError as exc:
                lines.append("CLONE-SWEEP FAILED %s: %s" % (path, exc))
                failed = True
                continue
            lines.append("CLONE-SWEEP reaped %s %s"
                         % (path, fmt_age(age)))
    return (3 if failed else 0), lines


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = platform_argv.parse(DECLARATION, argv)
    except platform_argv.UsageError as exc:
        print(f"clone-sweep: {exc}", file=sys.stderr)
        print(platform_argv.help_text(DECLARATION),
              file=sys.stderr, end="")
        return platform_argv.USAGE_EXIT
    if "help" in parsed:
        print(parsed["help"], end="")
        return 0
    code, lines = run(default_roots(),
                      datetime.now(timezone.utc),
                      dry_run=bool(parsed["flags"]["dry-run"]))
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
