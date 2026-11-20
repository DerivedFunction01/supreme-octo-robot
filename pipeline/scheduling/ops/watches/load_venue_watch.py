#!/usr/bin/env python3
"""Load-venue watch: when this machine's CPU load rises
above its CPU count while High-RAM fleet sessions are live,
name the live sessions so work is pointed at the venue.

The pieces existed separately: the local-test watch samples
/proc/loadavg as context (never load-gated) and counts live
fleet sessions from the registry's colab-liveness entries
(count only, never names). This watch assembles them into
the one finding the owner ordered (2026-11-15): a script
that fires on CPU load and NAMES the active sessions.

Firing rule (mechanical, episode-based; state in
state/load-venue-watch.json): a run speaks only when the
1-minute load average exceeds the CPU count AND at least
one fleet session is live. An episode opens on the first
over-threshold sample and speaks ONCE, naming every live
session. While the episode continues it stays silent; it
closes when a sample falls to/below threshold or no
session is live, and a later rise is a new episode that
speaks again. No fleet live means always silent — there is
nothing to point at. A lost state file adopts the current
sample as a fresh episode (it must not swallow a live
overload).

Session names come from the liveness entries themselves:
the entry body's run.argv carries the session id as the
argument to bin/colab-liveness (e.g.
solar-falcon-70-r1794747856); the watch strips the lease-run
suffix (-r<digits>) to name the session (solar-falcon-70).
Filename parsing is the fallback only, for an entry whose
body cannot be read.

Exit codes: 0 = sampled (silent or the episode's one
finding printed); 3 = /proc could not be read at all
(loud, by design — the sibling watch's convention).
Stdlib only; paths derive from this file's location.
Tests inject a fake proc root, a fake jobs dir, or the
sampled values directly; production reads /proc and the
registry.
"""
import json
import os
import re
import sys
import time

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

_timestamps_spec = _importlib_util.spec_from_file_location(
    "ops_timestamps",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "timestamps.py"),
                       os.path.join(_here, "timestamps.py"))
         if os.path.isfile(_p)))
timestamps = _importlib_util.module_from_spec(_timestamps_spec)
_timestamps_spec.loader.exec_module(timestamps)

REPO = paths.REPO_ROOT
STATE = os.environ.get(
    "LOAD_VENUE_WATCH_STATE",
    os.path.join(paths.STATE_DIR, "load-venue-watch.json"))
JOBS_DIR = os.environ.get("LOAD_VENUE_WATCH_JOBS", paths.JOBS_DIR)
PROC_ROOT = os.environ.get("LOAD_VENUE_WATCH_PROC", "/proc")

_RUN_SUFFIX = re.compile(r"-r\d+$")


now = timestamps.zstamp_now


def fmt_load(load1):
    return "%g" % load1


def sample_load(proc_root):
    """(load1, cpus) from the proc root. Raises OSError when
    the proc root cannot be read — the caller maps that to
    exit 3. CPU count comes from cpuinfo's processor lines,
    falling back to stat's per-CPU lines."""
    os.listdir(proc_root)
    with open(os.path.join(proc_root, "loadavg"),
              encoding="utf-8") as fh:
        load1 = float(fh.read().split()[0])
    cpus = 0
    try:
        with open(os.path.join(proc_root, "cpuinfo"),
                  encoding="utf-8") as fh:
            cpus = sum(1 for line in fh
                       if line.startswith("processor"))
    except OSError:
        cpus = 0
    if not cpus:
        with open(os.path.join(proc_root, "stat"),
                  encoding="utf-8") as fh:
            cpus = sum(1 for line in fh
                       if re.match(r"cpu\d+\s", line))
    if not cpus:
        raise OSError("no CPU count in proc root")
    return load1, cpus


def session_name(entry_path, filename):
    """The session name for one liveness entry: the entry
    body's run.argv session argument (the token after the
    colab-liveness program token), with the lease-run suffix
    stripped. Filename parsing is the fallback."""
    try:
        with open(entry_path, encoding="utf-8") as fh:
            items = [line.strip()[2:].strip().strip("'\"")
                     for line in fh
                     if line.strip().startswith("- ")]
        for i, item in enumerate(items):
            if item.rsplit("/", 1)[-1] == "colab-liveness" \
                    and i + 1 < len(items):
                return _RUN_SUFFIX.sub("", items[i + 1])
    except OSError:
        pass
    stem = filename[len("colab-liveness-"):-len(".yaml")]
    return _RUN_SUFFIX.sub("", stem)


def live_sessions(jobs_dir):
    """The live fleet sessions' names, sorted: one per
    colab-liveness entry standing in the registry (the lease
    core renders one per live session and removes it at
    lease end)."""
    try:
        names = sorted(
            name for name in os.listdir(jobs_dir)
            if name.startswith("colab-liveness-")
            and name.endswith(".yaml"))
    except OSError:
        return []
    return [session_name(os.path.join(jobs_dir, name), name)
            for name in names]


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    os.replace(tmp, STATE)


def run(proc_root, jobs_dir=None, load1=None, cpus=None,
        sessions=None, at=None):
    """One cycle: returns (exit_code, report_lines). All
    inputs injectable — tests pass a fake proc root and jobs
    dir, or the sampled values outright."""
    if load1 is None or cpus is None:
        try:
            sampled_load, sampled_cpus = sample_load(proc_root)
        except (OSError, ValueError, IndexError):
            return 3, ["LOAD-VENUE WATCH: /proc could not be read"]
        if load1 is None:
            load1 = sampled_load
        if cpus is None:
            cpus = sampled_cpus
    if sessions is None:
        sessions = live_sessions(jobs_dir or JOBS_DIR)
    at = at or now()
    previous = load_state()
    open_now = bool(load1 > cpus and sessions)
    lines = []
    if open_now and not previous.get("episode_open"):
        lines.append(
            "LOAD-VENUE load1=%s cpus=%d — run compute on the "
            "live High-RAM session(s): %s. Local checks and "
            "code belong on the venue while the fleet is live."
            % (fmt_load(load1), cpus, ", ".join(sessions)))
    save_state({"episode_open": open_now,
                "opened_at": previous.get("opened_at")
                if open_now and previous.get("episode_open")
                else (at if open_now else None),
                "sessions": sessions if open_now else []})
    return 0, lines


def main():
    code, lines = run(PROC_ROOT)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
