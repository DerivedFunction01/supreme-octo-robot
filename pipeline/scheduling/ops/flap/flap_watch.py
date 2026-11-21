#!/usr/bin/env python3
"""Flap watcher: scripted origin-mimicry experiment for the
write-denial flap.

The flap denies writes by process class: agent-class
processes (spawned by the agent runtime's tool layer) are
denied during a wave; long-lived classes (this server) never
are. Class follows the spawning origin — agent-class
processes sit in /init.scope/hatch-tool-prepared-* cgroups —
so this watcher runs the flap canary (ops/flap/flap_canary.py)
from two origins every cycle:

- control: a plain child of the server tree (expected: never
  denied; if it ever denies, the class model is wrong);
- cgroup: a child moved, before it execs, into a dedicated
  /sys/fs/cgroup/init.scope/hatch-tool-prepared-flapwatch
  cgroup — the mimicked agent origin.

Each arm's verdict is appended to the experiment series
(state/flap-watch-series.jsonl) and compared with the arm's
last verdict in state/flap-watch.json. Silence while nothing
changes (baseline adoption included); one printed report on
any arm's transition — the entry's report block routes it.

The experiment's pre-stated success criteria and the
during-wave ground-truth protocol live in
state/flap-probe-study/read-signal-hunt.md. Until a live wave
tests it, a clear reading from the cgroup arm proves nothing:
both classes write fine between waves.

Exit codes: 0 = ran (any verdicts); 3 = the instrument
itself failed (the control arm could not run the canary).
Stdlib only; paths derive from this file's location.
"""
import json
import os
import subprocess
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

OPS_DIR = paths.script_dir(__file__)
REPO = paths.REPO_ROOT
sys.path.insert(0, OPS_DIR)

import flap_series  # noqa: E402

STATE = os.environ.get("FLAP_WATCH_STATE",
                       os.path.join(paths.STATE_DIR, "flap-watch.json"))
SERIES = os.environ.get("FLAP_WATCH_SERIES",
                        os.path.join(paths.STATE_DIR, "flap-watch-series.jsonl"))
ARMS_ROOT = os.environ.get("FLAP_WATCH_ARMS",
                           os.path.join(paths.STATE_DIR, "flap-watch-arms"))
CGROUP = os.environ.get(
    "FLAP_WATCH_CGROUP",
    "/sys/fs/cgroup/init.scope/hatch-tool-prepared-flapwatch")
CANARY = os.path.join(OPS_DIR, "flap_canary.py")

LAUNCHER = (
    "import sys, os\n"
    "sys.stdin.readline()\n"
    "os.execvpe(sys.argv[1], sys.argv[1:], os.environ)\n"
)


now = timestamps.zstamp_now


def parse_canary(out):
    try:
        return json.loads(out)
    except ValueError:
        return None


def run_canary(scratch):
    proc = subprocess.run([sys.executable, CANARY, scratch],
                          capture_output=True, text=True, timeout=120)
    return parse_canary(proc.stdout)


def run_control(scratch):
    sample = run_canary(scratch)
    if sample is None:
        return None
    return {"arm": "control", "placement": "server-tree",
            "verdict": sample["verdict"], "exit": sample["exit"],
            "core_denied": sample["core_denied"]}


def run_cgroup(scratch):
    try:
        os.makedirs(CGROUP, exist_ok=True)
    except OSError as e:
        return {"arm": "cgroup", "placement": "failed",
                "verdict": None, "detail": "mkdir: %s" % e}
    proc = subprocess.Popen(
        [sys.executable, "-c", LAUNCHER, sys.executable, CANARY, scratch],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    try:
        with open(os.path.join(CGROUP, "cgroup.procs"), "w") as fh:
            fh.write(str(proc.pid))
    except OSError as e:
        proc.kill()
        proc.wait()
        return {"arm": "cgroup", "placement": "failed",
                "verdict": None, "detail": "procs write: %s" % e}
    out, _ = proc.communicate("go\n", timeout=120)
    sample = parse_canary(out)
    if sample is None:
        return {"arm": "cgroup", "placement": "placed",
                "verdict": None, "detail": "canary output unparseable"}
    return {"arm": "cgroup", "placement": "placed",
            "verdict": sample["verdict"], "exit": sample["exit"],
            "core_denied": sample["core_denied"]}


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"arms": {}}


def save_state(state):
    paths.save_json(STATE, state)


def transitions(prev, current):
    """Arms whose verdict/placement state changed vs baseline."""
    changed = []
    for arm, sample in current.items():
        old = prev.get(arm)
        if old is None:
            continue  # baseline adoption is silent
        key = (sample.get("verdict"), sample.get("placement"))
        if key != (old.get("verdict"), old.get("placement")):
            changed.append((arm, old, sample))
    return changed


def render_report(changed, current, at):
    lines = ["FLAP WATCH transition %s" % at]
    for arm, old, sample in changed:
        if sample.get("verdict") is None:
            lines.append("%s arm: %s -> placement %s (%s)"
                         % (arm, old.get("verdict"),
                            sample.get("placement"),
                            sample.get("detail", "")))
        else:
            denied = sample.get("core_denied") or []
            lines.append("%s arm: %s -> %s%s"
                         % (arm, old.get("verdict"), sample["verdict"],
                            " (core denied: %s)" % ", ".join(denied)
                            if denied else ""))
    for arm, sample in current.items():
        if arm not in [c[0] for c in changed]:
            lines.append("%s arm: %s (unchanged)"
                         % (arm, sample.get("verdict")))
    lines.append("Ground truth needed: run "
                 "python3 ops/flap/flap_probe.py from an agent shell; "
                 "the protocol is in "
                 "state/flap-probe-study/read-signal-hunt.md.")
    return "\n".join(lines)


def main():
    at = now()
    current = {}
    for arm, runner in (("control", run_control), ("cgroup", run_cgroup)):
        scratch = os.path.join(ARMS_ROOT, arm)
        os.makedirs(scratch, exist_ok=True)
        current[arm] = runner(scratch)
    if current["control"] is None:
        print("FLAP WATCH instrument failure %s: control arm "
              "could not run the canary" % at)
        return 3
    for sample in current.values():
        if sample is None:
            continue
        record = dict(sample, at=at)
        flap_series.append_line(SERIES, json.dumps(record))
    state = load_state()
    changed = transitions(state.get("arms", {}), current)
    state["arms"] = {arm: {"verdict": s.get("verdict"),
                           "placement": s.get("placement"), "at": at}
                     for arm, s in current.items() if s is not None}
    save_state(state)
    if changed:
        print(render_report(changed, current, at))
    return 0


if __name__ == "__main__":
    sys.exit(main())
