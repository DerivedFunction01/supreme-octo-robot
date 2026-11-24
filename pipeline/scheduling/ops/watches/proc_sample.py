#!/usr/bin/env python3
"""The one homed /proc sampling module.

Every watch that needs machine or per-process numbers
reads them here: load averages, CPU count, memory, and
the process table (argv, cwd, CPU ticks, resident size).
Two reads of the process table a few seconds apart give
per-process CPU percent from the tick delta
(`cpu_percents`).

Stdlib only. Every function takes the proc root as an
input, so tests inject a fake proc root; production
passes "/proc".
"""
import os
import re


def ticks_per_second():
    return os.sysconf("SC_CLK_TCK")


def page_size():
    return os.sysconf("SC_PAGE_SIZE")


def read_loadavg(proc_root):
    """(load1, load5, load15) from <proc_root>/loadavg.
    Raises OSError when the proc root cannot be read."""
    os.listdir(proc_root)
    with open(os.path.join(proc_root, "loadavg"),
              encoding="utf-8") as fh:
        parts = fh.read().split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def cpu_count(proc_root):
    """CPU count from cpuinfo's processor lines, falling
    back to stat's per-CPU lines. Raises OSError when
    neither source yields a count."""
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
    return cpus


def read_meminfo(proc_root):
    """{"total_kb", "available_kb", "used_kb"} from
    <proc_root>/meminfo; used = total - available."""
    values = {}
    with open(os.path.join(proc_root, "meminfo"),
              encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 2 and parts[0] in (
                    "MemTotal:", "MemAvailable:"):
                values[parts[0]] = int(parts[1])
    total = values["MemTotal:"]
    available = values["MemAvailable:"]
    return {"total_kb": total, "available_kb": available,
            "used_kb": total - available}


def read_uptime(proc_root):
    """Seconds since boot from <proc_root>/uptime, or
    None when unreadable."""
    try:
        with open(os.path.join(proc_root, "uptime"),
                  encoding="utf-8") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _read_stat(proc_root, name):
    with open(os.path.join(proc_root, name, "stat"),
              "rb") as fh:
        raw = fh.read().decode("utf-8", "replace")
    # Fields after the parenthesised comm: rest[i] is
    # field i+3, so ppid=rest[1], utime=rest[11],
    # stime=rest[12], starttime=rest[19], rss=rest[21].
    rest = raw[raw.rindex(")") + 2:].split()
    return {
        "ppid": int(rest[1]),
        "utime": int(rest[11]),
        "stime": int(rest[12]),
        "starttime": int(rest[19]),
        "rss_pages": int(rest[21]),
    }


def read_process_table(proc_root):
    """One dict per readable process: {pid, ppid, argv,
    cwd, utime, stime, starttime, rss_kb}. utime/stime/
    starttime are clock ticks from /proc/<pid>/stat
    fields 14/15/22; rss_kb converts the field-24 page
    count. Processes that vanish mid-read are skipped."""
    out = []
    page_kb = page_size() // 1024
    for name in os.listdir(proc_root):
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, name, "cmdline"),
                      "rb") as fh:
                argv = [p.decode("utf-8", "replace")
                        for p in fh.read().split(b"\0") if p]
            try:
                cwd = os.readlink(
                    os.path.join(proc_root, name, "cwd"))
            except OSError:
                cwd = None
            stat = _read_stat(proc_root, name)
        except (OSError, ValueError, IndexError):
            continue
        if not argv:
            continue
        out.append({
            "pid": int(name), "ppid": stat["ppid"],
            "argv": argv, "cwd": cwd,
            "utime": stat["utime"], "stime": stat["stime"],
            "starttime": stat["starttime"],
            "rss_kb": stat["rss_pages"] * page_kb,
        })
    return out


def cpu_percents(table_a, table_b, elapsed_s, ticks):
    """{pid: cpu_pct} from two process tables sampled
    elapsed_s apart: the utime+stime tick delta over the
    window, as a percent of one CPU. A pid whose
    starttime changed between samples is a different
    process (pid reuse) and is skipped; a process only
    in table_b has no delta and is skipped."""
    if elapsed_s <= 0 or ticks <= 0:
        return {}
    before = {row["pid"]: row for row in table_a}
    out = {}
    for row in table_b:
        prev = before.get(row["pid"])
        if prev is None or prev["starttime"] != row["starttime"]:
            continue
        delta = (row["utime"] + row["stime"]) \
            - (prev["utime"] + prev["stime"])
        out[row["pid"]] = round(
            100.0 * (delta / ticks) / elapsed_s, 1)
    return out
