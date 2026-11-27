"""Venue-state sampler leaf: the probe payload, its parser, the store.

One SSH exec per local venue per cycle runs the probe payload
(build_probe_command) on the venue and prints line-based facts:
the container's pid occupancy, the disk occupancy of the root
store and the workspace mount, and, for every run dir carrying
a root.pid stamp, the root's liveness and the CPU ticks summed
over its whole process tree. parse_sample turns that text into
the sample dict the classification consumes; SampleStore keeps
the samples as JSON lines, one file per venue, so the last two
samples are always at hand for the two-sample rule. The disk
helpers here (disk_block, carried_disk_block,
load_disk_thresholds) turn a sample's disk reading into the
state surface's disk block: the host-side disk guard's WARN
was a line in a log nothing reads, so the warning lives on
this surface instead.

This leaf is stdlib-only at import time (the standalone module
loaders in the test suites load it by path); the venue paths
spine and the platform writer are loaded lazily, by path, only
when a SampleStore needs its default root or its write seam.
"""

import json
from pathlib import Path

# Declared pid budgets by venue shape id, used only when the
# venue's live pids.max cannot be read (the probe reports it
# whenever the cgroup files answer, and the live value always
# wins). lease.json is untracked operator config, so the
# declaration lives here rather than in a tracked config file.
DEFAULT_PIDS_BY_SHAPE = {
    "local": 1024,
    "local-hp": 1024,
}

# The probe payload's embedded interpreter script. It mirrors
# parse_stat / sum_tree_cpu below: the venue side cannot import
# this module (it runs as a lone exec payload), so the walk is
# spelled out there and the parser is pinned here by fixtures.
_PROBE_SCRIPT = """\
import os
import sys
from pathlib import Path


def read_first(paths):
    for candidate in paths:
        try:
            return Path(candidate).read_text().strip()
        except OSError:
            continue
    return None


def stat_fields(text):
    rparen = text.rfind(")")
    if rparen < 0:
        return None
    fields = text[rparen + 2:].split()
    if len(fields) < 13:
        return None
    try:
        return int(fields[1]), int(fields[11]) + int(fields[12])
    except ValueError:
        return None


def main():
    current = read_first(
        ["/sys/fs/cgroup/pids.current", "/sys/fs/cgroup/pids/pids.current"])
    limit = read_first(
        ["/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/pids/pids.max"])
    if current is None or limit is None:
        print("ERR pids cgroup files unreadable")
    print("PIDS {} {}".format(
        current if current is not None else "?",
        limit if limit is not None else "?"))

    stats = {}
    children = {}
    proc = Path("/proc")
    try:
        entries = list(proc.iterdir())
    except OSError:
        entries = []
        print("ERR proc unreadable")
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            parsed = stat_fields((entry / "stat").read_text())
        except OSError:
            continue
        if parsed is None:
            continue
        ppid, ticks = parsed
        pid = int(entry.name)
        stats[pid] = ticks
        children.setdefault(ppid, []).append(pid)

    def tree_ticks(root):
        total = 0
        stack = [root]
        seen = set()
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            total += stats.get(pid, 0)
            stack.extend(children.get(pid, []))
        return total

    def disk_used_kb(path):
        try:
            st = os.statvfs(path)
        except OSError:
            return None
        return (st.f_blocks - st.f_bfree) * st.f_frsize // 1024

    root_kb = disk_used_kb("/")
    if root_kb is not None:
        print("DISK root {}".format(root_kb))
    workspace_kb = disk_used_kb("/workspace")
    if workspace_kb is not None:
        print("DISK workspace {}".format(workspace_kb))

    runs = Path.home() / "runs"
    try:
        run_dirs = sorted(p for p in runs.iterdir() if p.is_dir())
    except OSError:
        run_dirs = []
    for run_dir in run_dirs:
        stamp = run_dir / "root.pid"
        if not stamp.exists():
            continue
        try:
            root = int(stamp.read_text().strip())
        except (OSError, ValueError):
            print("ERR {} root.pid unreadable".format(run_dir.name))
            continue
        alive = 1 if root in stats else 0
        ticks = tree_ticks(root) if alive else 0
        print("JOB {} {} {} {}".format(run_dir.name, root, alive, ticks))


main()
"""


def build_probe_command() -> str:
    """The single SSH exec payload: run the embedded reader on
    the venue and print the PIDS / JOB / ERR lines parse_sample
    consumes."""
    return "python3 - <<'VENUE_SAMPLE_EOF'\n" + _PROBE_SCRIPT + "VENUE_SAMPLE_EOF\n"


def parse_stat(text: str):
    """One /proc/<pid>/stat line -> (pid, (ppid, utime, stime)).

    The comm field may contain spaces and parentheses, so the
    fixed fields are read after the last ')': the remainder
    starts at field 3 (state), putting ppid at index 1, utime
    (field 14) at index 11 and stime (field 15) at index 12.
    Returns None for a malformed line.
    """
    rparen = text.rfind(")")
    head = text[: text.find(" ")] if " " in text else ""
    if rparen < 0 or not head.isdigit():
        return None
    fields = text[rparen + 2 :].split()
    if len(fields) < 13:
        return None
    try:
        ppid = int(fields[1])
        utime = int(fields[11])
        stime = int(fields[12])
    except ValueError:
        return None
    return int(head), (ppid, utime, stime)


def sum_tree_cpu(stat_by_pid: dict, roots=None) -> dict:
    """Sum utime+stime over each root's whole descendant tree.

    stat_by_pid maps pid -> (ppid, utime, stime). With roots
    given, returns {root: ticks} for exactly those roots (a root
    absent from the map sums to 0); without, the roots are the
    pids whose parent is absent from the map.
    """
    children = {}
    for pid, (ppid, _utime, _stime) in stat_by_pid.items():
        children.setdefault(ppid, []).append(pid)
    if roots is None:
        roots = [
            pid
            for pid, (ppid, _u, _s) in stat_by_pid.items()
            if ppid not in stat_by_pid
        ]
    sums = {}
    for root in roots:
        total = 0
        stack = [root]
        seen = set()
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            entry = stat_by_pid.get(pid)
            if entry is not None:
                total += entry[1] + entry[2]
            stack.extend(children.get(pid, []))
        sums[root] = total
    return sums


def declared_pids(shape_id):
    """The declared pid budget for a shape id, or None."""
    if shape_id is None:
        return None
    return DEFAULT_PIDS_BY_SHAPE.get(shape_id)


def effective_pids_capacity(sample: dict, shape_id=None):
    """The venue's pid capacity: the sample's live pids_max
    when it was readable, else the declared budget for the
    shape, else None."""
    live = sample.get("pids_max")
    if live is not None:
        return live
    return declared_pids(shape_id)


KB_PER_GB = 1048576


def _gb(kb):
    """Used KB -> GB at the surface's one decimal, or None
    for a missing reading."""
    if kb is None:
        return None
    return round(kb / KB_PER_GB, 1)


def load_disk_thresholds(var_dir) -> dict:
    """Per-target disk budgets from the untracked seed
    (var/disk-thresholds.json): {target: {"warn_gb": ...,
    "stop_gb": ...}} — each instance's DISK_WARN_GB /
    DISK_STOP_GB from its own environment record, seeded by
    the operator, never hardcoded here. An absent or
    unreadable seed, and any malformed entry, yields no
    budget for that target: unmeasured is the honest state,
    never a default."""
    try:
        data = json.loads((Path(var_dir) / "disk-thresholds.json").read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    budgets = {}
    for target, entry in data.items():
        if not isinstance(entry, dict):
            continue
        warn = entry.get("warn_gb")
        stop = entry.get("stop_gb")
        if isinstance(warn, (int, float)) and isinstance(stop, (int, float)):
            budgets[str(target)] = {"warn_gb": warn, "stop_gb": stop}
    return budgets


def disk_block(sample: dict, thresholds):
    """One sample's disk block for the state surface, or
    None when the venue carries no budget (thresholds
    missing) or the probe read no root store.

    The verdict rides the root store: it is the store that
    fills and kills the venue — the workspace image can sit
    near-empty while the root store rides to the cap. The
    evaluation reads the same one-decimal GB figure the
    block publishes, so the surface never contradicts
    itself: at the warn figure the state is "warn", at the
    stop figure "stop"."""
    if not thresholds:
        return None
    root_gb = _gb(sample.get("disk_root_used_kb"))
    if root_gb is None:
        return None
    warn = thresholds["warn_gb"]
    stop = thresholds["stop_gb"]
    if root_gb >= stop:
        state = "stop"
    elif root_gb >= warn:
        state = "warn"
    else:
        state = "ok"
    return {
        "root_used_gb": root_gb,
        "workspace_used_gb": _gb(sample.get("disk_workspace_used_kb")),
        "warn_gb": warn,
        "stop_gb": stop,
        "state": state,
    }


def carried_disk_block(prev_state):
    """The disk block an unreachable state carries: the
    previous state file's block, stamped with the last
    successful sample's time as disk_sampled_at — a venue
    dark reads with its last disk reading, never with none.
    A block already carried keeps its original stamp.
    None when the previous state carried no block."""
    if not isinstance(prev_state, dict):
        return None
    block = prev_state.get("disk")
    if not isinstance(block, dict):
        return None
    carried = dict(block)
    stamp = block.get("disk_sampled_at") or prev_state.get("sampled_at")
    if stamp is not None:
        carried["disk_sampled_at"] = stamp
    return carried


def _int_or_none(token):
    try:
        return int(token)
    except (TypeError, ValueError):
        return None


def parse_sample(text: str, venue: str, at) -> dict:
    """Probe output -> the sample dict.

    {venue, at, pids_current, pids_max, jobs: [{run_id,
    root_pid, tree_alive, cpu_ticks}], errors: [...]}.
    pids_max is None when the venue reports "max" (unlimited)
    or the value is unreadable; ERR lines collect into errors;
    malformed lines are ignored, never fatal. The DISK lines
    land as disk_root_used_kb / disk_workspace_used_kb (used
    KB of the root store and the workspace mount); a store
    the probe could not read is absent from its output and
    stays None here — honest absence, never 0-for-missing.
    """
    sample = {
        "venue": venue,
        "at": at,
        "pids_current": None,
        "pids_max": None,
        "disk_root_used_kb": None,
        "disk_workspace_used_kb": None,
        "jobs": [],
        "errors": [],
    }
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]
        if kind == "PIDS" and len(parts) == 3:
            sample["pids_current"] = _int_or_none(parts[1])
            if parts[2] != "max":
                sample["pids_max"] = _int_or_none(parts[2])
        elif kind == "DISK" and len(parts) == 3 and parts[1] in ("root", "workspace"):
            sample[f"disk_{parts[1]}_used_kb"] = _int_or_none(parts[2])
        elif kind == "JOB" and len(parts) == 5:
            root_pid = _int_or_none(parts[2])
            cpu_ticks = _int_or_none(parts[4])
            if root_pid is None or cpu_ticks is None or parts[3] not in ("0", "1"):
                continue
            sample["jobs"].append(
                {
                    "run_id": parts[1],
                    "root_pid": root_pid,
                    "tree_alive": parts[3] == "1",
                    "cpu_ticks": cpu_ticks,
                }
            )
        elif kind == "ERR":
            sample["errors"].append(line[4:].strip())
    return sample


class SampleStore:
    """JSON-lines sample store: var/venue-samples-<target>.jsonl
    under the venue root, one line per sample.

    Appends ride the foundation seam's staged_write (read the
    current bytes, stage the combined write) — the same writer
    the run records ride — so a reader never sees a partial
    line. A load context without the package (the by-path unit
    tests) passes its own writer= callable; there is no local
    write idiom in this module.
    """

    def __init__(self, root=None, writer=None):
        if root is not None:
            self._root = Path(root)
        else:
            self._root = self._default_root()
        self._writer = writer
        self._writer_tried = writer is not None

    @staticmethod
    def _foundation():
        from .foundation import REPO, staged_write

        return REPO, staged_write

    def _default_root(self):
        repo, _ = self._foundation()
        return repo / "var"

    def _platform_staged_write(self):
        if not self._writer_tried:
            self._writer_tried = True
            try:
                _, self._writer = self._foundation()
            except Exception:
                self._writer = None
        return self._writer

    def _staged_write(self, path, data: bytes):
        staged = self._platform_staged_write()
        if staged is None:
            raise RuntimeError(
                "SampleStore has no writer: the foundation seam is "
                "unavailable in this load context — pass writer= "
                "(the bin and the package context resolve it from "
                ".foundation)"
            )
        staged(path, data)

    def path_for(self, target: str) -> Path:
        return self._root / f"venue-samples-{target}.jsonl"

    def append(self, sample: dict) -> Path:
        path = self.path_for(str(sample["venue"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        line = (json.dumps(sample, sort_keys=True) + "\n").encode()
        existing = path.read_bytes() if path.exists() else b""
        self._staged_write(path, existing + line)
        return path

    def last_two(self, venue: str) -> list:
        """The venue's last two samples, oldest first; fewer
        when the store holds fewer, [] when it holds none.
        Malformed lines are skipped."""
        path = self.path_for(str(venue))
        if not path.exists():
            return []
        samples = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except ValueError:
                continue
        return samples[-2:]
