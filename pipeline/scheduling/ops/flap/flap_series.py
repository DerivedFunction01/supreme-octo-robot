#!/usr/bin/env python3
"""Append-only sample series for the flap probe.

state/flap-state.json (maintained by ops/flap/flap_probe.py) is the
current-verdict file; this series is the timing record behind
it — one JSON sample per line, appended forever, so wave
starts, clears, and durations can be read back and measured.

Appends must survive the very denial being measured, so the
cadence job appends through the scheduler server's ops channel
(bin/sched exec), whose process class is never denied; this
script is the server-side end of that append as well as the
reader. A sample lost before it could be appended is not
hidden: the next appended sample carries gap_before_secs,
computed by the caller from the tail this script prints.

Verbs:
  append '<json>'   validate and append one sample line
  tail              print the last sample line (nothing when
                    the series does not exist yet)

Stdlib only; paths derive from this file's location.
"""
import json
import os
import sys

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

REPO = paths.REPO_ROOT
DEFAULT_PATH = os.path.join(paths.STATE_DIR, "flap-series.jsonl")


def append_line(path, line):
    """Append one validated sample line. Returns an error
    string, or None on success."""
    try:
        sample = json.loads(line)
    except ValueError as exc:
        return f"not JSON: {exc}"
    if not isinstance(sample, dict) or "at" not in sample \
            or "verdict" not in sample:
        return "a sample carries at and verdict"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(sample) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return None


def tail_line(path):
    """The last non-empty line, or None."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
    except OSError:
        return None
    return lines[-1] if lines else None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    path = DEFAULT_PATH
    if argv[:1] == ["--file"]:
        path = argv[1]
        argv = argv[2:]
    if not argv:
        print(__doc__)
        return 2
    verb = argv[0]
    if verb == "append" and len(argv) == 2:
        error = append_line(path, argv[1])
        if error:
            print(f"flap_series: {error}")
            return 2
        return 0
    if verb == "tail" and len(argv) == 1:
        line = tail_line(path)
        if line:
            print(line)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
