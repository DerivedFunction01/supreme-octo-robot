#!/usr/bin/env python3
"""The load monitor's bounded snapshot store.

Builds one snapshot from two /proc samples (the sampler
is proc_sample.py, the one homed module) and writes the
store the Task Manager section reads: {"current": the
latest snapshot, "recent": a ring of up to 12 snapshots
taken while an episode was open}. The page never samples
/proc; it reads this store, so its cost is constant
while the box is overloaded.

Snapshot shape (fixed; consumers take it as served):
{"stamp", "load": [l1, l5, l15], "cpus", "mem",
 "processes": top 25 by cpu_pct desc, each {pid, ppid,
 cpu_pct, mem_pct, elapsed_s, argv, cwd, repo, thread},
 "venues": [{kind, name, live, in_flight}],
 "episode": {open, opened_at, last_spoke_at}}

`repo` is the first path segment under the workspace
root and `thread` the routes-file label for that repo —
the same derivation local_test_watch.route_for performs,
reused from that module, never copied.

Stdlib only; paths derive from ops/paths.py. The store
path is overridable by env LOAD_MONITOR_SNAPSHOT.
"""
import json
import os

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = _importlib_util.spec_from_file_location(
        name, os.path.join(_here, filename))
    module = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


proc_sample = _load("proc_sample", "proc_sample.py")
local_test_watch = _load("local_test_watch", "local_test_watch.py")

_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    os.path.join(os.path.dirname(_here), "paths.py"))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

STORE_PATH = os.environ.get(
    "LOAD_MONITOR_SNAPSHOT",
    os.path.join(paths.STATE_DIR, "load-monitor-snapshot.json"))
TOP_N = 25
RECENT_MAX = 12


def repo_for(cwd, workspace):
    """The first path segment under the workspace root,
    or None when the process does not live under it."""
    if not cwd or not workspace:
        return None
    rel = os.path.relpath(cwd, workspace)
    if rel.startswith(".." + os.sep) or rel == "..":
        return None
    return rel.split(os.sep)[0]


def build_snapshot(proc_root, table_a, table_b, elapsed_s,
                   venues, episode, workspace=None, routes=None,
                   at=None, ticks=None):
    """One snapshot dict from the two sampled tables.
    Load, CPU count, and memory are read from proc_root;
    per-process CPU percent is the two-sample delta."""
    workspace = workspace or paths.WORKSPACE_ROOT
    if routes is None:
        routes = local_test_watch.load_routes()
    if ticks is None:
        ticks = proc_sample.ticks_per_second()
    load = proc_sample.read_loadavg(proc_root)
    cpus = proc_sample.cpu_count(proc_root)
    mem = proc_sample.read_meminfo(proc_root)
    percents = proc_sample.cpu_percents(
        table_a, table_b, elapsed_s, ticks)
    uptime = proc_sample.read_uptime(proc_root)
    total_kb = mem["total_kb"] or 1
    rows = []
    for row in table_b:
        cwd, _derived = local_test_watch.locate(
            row["argv"], row["cwd"], workspace)
        route = None
        if cwd:
            route = local_test_watch.route_for(
                cwd, workspace, routes)
        elapsed = 0.0
        if uptime is not None and ticks:
            elapsed = max(
                0.0, uptime - row["starttime"] / ticks)
        rows.append({
            "pid": row["pid"], "ppid": row["ppid"],
            "cpu_pct": percents.get(row["pid"], 0.0),
            "mem_pct": round(
                100.0 * row["rss_kb"] / total_kb, 1),
            "elapsed_s": round(elapsed, 1),
            "argv": list(row["argv"]), "cwd": cwd,
            "repo": repo_for(cwd, workspace),
            "thread": (route or {}).get("label"),
        })
    rows.sort(key=lambda r: r["cpu_pct"], reverse=True)
    return {
        "stamp": at,
        "load": [load[0], load[1], load[2]],
        "cpus": cpus,
        "mem": mem,
        "processes": rows[:TOP_N],
        "venues": venues,
        "episode": episode,
    }


def load_store(path=None):
    """The standing store, or an empty one when the file
    is absent or unreadable."""
    try:
        with open(path or STORE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {"current": data.get("current"),
                    "recent": data.get("recent") or []}
    except (OSError, ValueError):
        pass
    return {"current": None, "recent": []}


def write_store(snapshot, path=None, store=None):
    """Write {"current": snapshot, "recent": ring}: an
    episode-open snapshot joins the ring (newest last,
    capped at RECENT_MAX); a calm snapshot leaves the
    ring standing. Returns the store written."""
    if store is None:
        store = load_store(path)
    recent = list(store.get("recent") or [])
    if (snapshot.get("episode") or {}).get("open"):
        recent = (recent + [snapshot])[-RECENT_MAX:]
    out = {"current": snapshot, "recent": recent}
    paths.save_json(path or STORE_PATH, out)
    return out
