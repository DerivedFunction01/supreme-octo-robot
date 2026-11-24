#!/usr/bin/env python3
"""Load monitor: sample this machine's load and
per-process CPU twice a few seconds apart, write the
bounded snapshot store every cycle (load_snapshot.py),
and speak on an overload episode — naming the heaviest
processes and every live venue, MSI and Colab alike.

Episode rule (mechanical; episode state rides in the
snapshot store's current.episode): the threshold is
LOAD_FACTOR × the CPU count on the 1-minute load. An
episode opens on the first over-threshold sample and
speaks, naming the top 5 processes (argv summary, repo,
owning thread) and every live venue. While it stays
open it re-speaks at most every RESPEAK_SECONDS; it
closes on a below-threshold sample. A stuck-open episode
in a stale store never suppresses a finding: its last
spoke is older than the re-speak interval, so the
re-speak is due.

Venues: Colab sessions come from the registry's
colab-liveness entries (session_name / live_sessions,
as before); the MSI local venue is live when its
transport answers — a TCP connect to 127.0.0.1:2222,
injectable in tests. in_flight counts are not known to
this watch and are served as null.

Exit codes: 0 = sampled (silent or a finding printed);
3 = /proc could not be read at all (loud, by design —
the sibling watches' convention).
Stdlib only; paths derive from ops/paths.py. Tests
inject fake proc roots, tables, venues, and probes;
production reads /proc and the registry.
"""
import calendar
import os
import re
import socket
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


def _load_sibling(name, filename):
    spec = _importlib_util.spec_from_file_location(
        name, os.path.join(_here, filename))
    module = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proc_sample = _load_sibling("proc_sample", "proc_sample.py")
load_snapshot = _load_sibling("load_snapshot", "load_snapshot.py")
local_test_watch = load_snapshot.local_test_watch

REPO = paths.REPO_ROOT
WORKSPACE = paths.WORKSPACE_ROOT
STATE = os.environ.get(
    "LOAD_VENUE_WATCH_STATE",
    os.path.join(paths.STATE_DIR, "load-venue-watch.json"))
SNAPSHOT = os.environ.get(
    "LOAD_MONITOR_SNAPSHOT", load_snapshot.STORE_PATH)
JOBS_DIR = os.environ.get("LOAD_VENUE_WATCH_JOBS", paths.JOBS_DIR)
PROC_ROOT = os.environ.get("LOAD_VENUE_WATCH_PROC", "/proc")
ROUTES = local_test_watch.ROUTES

LOAD_FACTOR = float(os.environ.get("LOAD_MONITOR_FACTOR", "2.0"))
RESPEAK_SECONDS = 15 * 60
SAMPLE_INTERVAL_S = 3.0
MSI_HOST = "127.0.0.1"
MSI_PORT = 2222

_RUN_SUFFIX = re.compile(r"-r\d+$")

now = timestamps.zstamp_now


def fmt_load(load1):
    return "%g" % load1


def sample_load(proc_root):
    """(load1, cpus) from the proc root, via proc_sample.
    Raises OSError when the proc root cannot be read —
    the caller maps that to exit 3."""
    load = proc_sample.read_loadavg(proc_root)
    return load[0], proc_sample.cpu_count(proc_root)


def session_name(entry_path, filename):
    """The session name for one liveness entry: the entry
    body's run.argv session argument (the token after the
    colab-liveness program token), with the lease-run
    suffix stripped. Filename parsing is the fallback."""
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
    colab-liveness entry standing in the registry (the
    lease core renders one per live session and removes
    it at lease end)."""
    try:
        names = sorted(
            name for name in os.listdir(jobs_dir)
            if name.startswith("colab-liveness-")
            and name.endswith(".yaml"))
    except OSError:
        return []
    return [session_name(os.path.join(jobs_dir, name), name)
            for name in names]


def probe_msi(host=MSI_HOST, port=MSI_PORT, timeout=1.0):
    """True when the local venue's transport answers a
    TCP connect (the forward listening on 127.0.0.1:2222)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def build_venues(sessions, msi_live):
    """The snapshot's venue list: the MSI local venue
    first, then one entry per live Colab session."""
    venues = [{"kind": "msi", "name": "local",
               "live": bool(msi_live), "in_flight": None}]
    venues.extend(
        {"kind": "colab", "name": name, "live": True,
         "in_flight": None}
        for name in sessions)
    return venues


def _stamp_epoch(stamp):
    """Epoch seconds for a Z-stamp, or None."""
    try:
        return calendar.timegm(time.strptime(
            stamp, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def _argv_summary(argv):
    """A runner-style one-line summary of an argv: the
    program plus its arguments, space-joined."""
    return " ".join(argv or [])


def _finding_line(snapshot):
    load = snapshot["load"]
    top = []
    for row in snapshot["processes"][:5]:
        top.append(
            "pid=%d cpu=%s%% repo=%s thread=%s argv=%s" % (
                row["pid"], "%g" % row["cpu_pct"],
                row["repo"] or "-", row["thread"] or "-",
                _argv_summary(row["argv"])))
    live = [v for v in snapshot["venues"] if v["live"]]
    venue_text = ", ".join(
        "%s:%s" % (v["kind"], v["name"]) for v in live) or "none"
    return (
        "LOAD-MONITOR load1=%s cpus=%d threshold=%s — "
        "heaviest: %s; live venues: %s. Run compute on a "
        "live venue while the fleet is live." % (
            fmt_load(load[0]), snapshot["cpus"],
            fmt_load(LOAD_FACTOR * snapshot["cpus"]),
            "; ".join(top) if top else "none", venue_text))


def run(proc_root, jobs_dir=None, load1=None, cpus=None,
        sessions=None, at=None, tables=None, elapsed_s=None,
        venues=None, msi_live=None, msi_probe=None,
        routes=None, workspace=None, snapshot_path=None,
        interval_s=None, sleep=None, at_epoch=None):
    """One cycle: returns (exit_code, report_lines). All
    inputs injectable — tests pass a fake proc root and
    jobs dir, sampled tables/values outright, or a fake
    MSI probe. Every successful cycle writes the
    snapshot store."""
    snapshot_path = snapshot_path or SNAPSHOT
    workspace = workspace or WORKSPACE
    if tables is None:
        table_a = table_b = None
        try:
            sampled_load, sampled_cpus = sample_load(proc_root)
            table_a = proc_sample.read_process_table(proc_root)
        except (OSError, ValueError, IndexError):
            return 3, ["LOAD-MONITOR: /proc could not be read"]
        if load1 is None:
            load1 = sampled_load
        if cpus is None:
            cpus = sampled_cpus
        wait = SAMPLE_INTERVAL_S if interval_s is None \
            else interval_s
        started = time.monotonic()
        (sleep or time.sleep)(wait)
        try:
            table_b = proc_sample.read_process_table(proc_root)
        except (OSError, ValueError, IndexError):
            return 3, ["LOAD-MONITOR: /proc could not be read"]
        if elapsed_s is None:
            elapsed_s = time.monotonic() - started
        tables = (table_a, table_b)
    if elapsed_s is None:
        elapsed_s = SAMPLE_INTERVAL_S
    if sessions is None:
        sessions = live_sessions(jobs_dir or JOBS_DIR)
    if msi_live is None:
        msi_live = (msi_probe or probe_msi)()
    if venues is None:
        venues = build_venues(sessions, msi_live)
    if routes is None:
        routes = local_test_watch.load_routes()
    at = at or now()
    if at_epoch is None:
        at_epoch = _stamp_epoch(at)
        if at_epoch is None:
            at_epoch = time.time()

    store = load_snapshot.load_store(snapshot_path)
    previous = ((store.get("current") or {}).get("episode")
                or {})
    over = load1 is not None and cpus \
        and load1 > LOAD_FACTOR * cpus
    speak = False
    if over:
        if not previous.get("open"):
            speak = True
            opened_at = at
            last_spoke = None
        else:
            opened_at = previous.get("opened_at") or at
            last_spoke = previous.get("last_spoke_at") \
                or opened_at
            spoke_epoch = _stamp_epoch(last_spoke)
            # A stale stuck-open episode's last spoke is
            # older than the re-speak interval (or
            # unparseable): the re-speak is due, never
            # suppressed.
            if spoke_epoch is None or \
                    at_epoch - spoke_epoch >= RESPEAK_SECONDS:
                speak = True
        episode = {"open": True, "opened_at": opened_at,
                   "last_spoke_at": at if speak else last_spoke}
    else:
        episode = {"open": False, "opened_at": None,
                   "last_spoke_at": None}

    try:
        snapshot = load_snapshot.build_snapshot(
            proc_root, tables[0], tables[1], elapsed_s,
            venues, episode, workspace=workspace,
            routes=routes, at=at)
    except (OSError, ValueError, IndexError, KeyError):
        # Injected sampled values with no readable proc
        # root (the deterministic seam): build the
        # snapshot from the injected values instead.
        snapshot = _injected_snapshot(
            load1, cpus, tables, elapsed_s, venues, episode,
            workspace, routes, at)
    if load1 is not None:
        snapshot["load"] = [load1] + list(snapshot["load"][1:])
    if cpus:
        snapshot["cpus"] = cpus
    load_snapshot.write_store(
        snapshot, path=snapshot_path, store=store)
    lines = [_finding_line(snapshot)] if speak else []
    return 0, lines


def _injected_snapshot(load1, cpus, tables, elapsed_s,
                       venues, episode, workspace, routes, at):
    """A snapshot built without a proc root, from the
    injected tables and values (tests' deterministic
    seam; production always has /proc)."""
    ticks = proc_sample.ticks_per_second()
    percents = proc_sample.cpu_percents(
        tables[0], tables[1], elapsed_s, ticks)
    rows = []
    for row in tables[1]:
        cwd, _derived = local_test_watch.locate(
            row["argv"], row["cwd"], workspace)
        route = local_test_watch.route_for(
            cwd, workspace, routes) if cwd else None
        rows.append({
            "pid": row["pid"], "ppid": row["ppid"],
            "cpu_pct": percents.get(row["pid"], 0.0),
            "mem_pct": 0.0, "elapsed_s": 0.0,
            "argv": list(row["argv"]), "cwd": cwd,
            "repo": load_snapshot.repo_for(cwd, workspace),
            "thread": (route or {}).get("label"),
        })
    rows.sort(key=lambda r: r["cpu_pct"], reverse=True)
    return {"stamp": at,
            "load": [load1 or 0.0, 0.0, 0.0],
            "cpus": cpus or 0,
            "mem": {"total_kb": 0, "available_kb": 0,
                    "used_kb": 0},
            "processes": rows[:load_snapshot.TOP_N],
            "venues": venues, "episode": episode}


def main():
    code, lines = run(PROC_ROOT)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
