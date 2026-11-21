#!/usr/bin/env python3
"""Storage watch: free-space tripwire for the home filesystem
and /tmp.

Reads available space on both filesystems on a short cadence
and stays silent while space is healthy. When free space crosses
below a threshold it emits exactly one report for that crossing:
one at the low threshold, and one more if the episode deepens to
the critical threshold. Crossing state lives in this job's state
file (the vm-restart-detector's episode discipline): a continuing
low episode does not re-report, de-escalation is silent, and a
recovery back above the low threshold re-arms the episode so a
later drop reports again. The first run adopts the current levels
as the baseline, silently.

Warnings carry the diagnosis: on a crossing run only, a shallow
du over the known stores (the repo tree and the home caches by
default; a deployment names its own stores through the env
seam below) lists the top consumers, bounded by a hard
timeout; when the du cannot complete, the warning says so
instead of guessing.

Thresholds are byte counts on free space. The home filesystem
uses the owner's figures (low 50 GB, critical 45 GB — retuned
2026-11-11: the app locked the owner out at ~42 GB free twice,
2026-11-08 and 2026-11-11, so both tiers now precede that
cutoff; the earlier 25/10 GB tiers sat below it and could
never warn in time). Those figures are the compiled defaults:
the entry's config block (contract 09) carries the same tiers
as its live-tunable knobs, and at fire time the engine sets
STORAGE_WATCH_HOME_LOW_GB / STORAGE_WATCH_HOME_CRIT_GB to the
saved values — when either variable is present it governs
(that tier, in GB), and when it is absent the compiled
constant governs, byte-for-byte the behavior this script has
always had. /tmp is a
small tmpfs where gigabyte thresholds are meaningless, so it
carries megabyte thresholds of the same shape (low 128 MB,
critical 32 MB — a full /tmp fails fleet test runs outright).

Exit codes: 0 = checked (silent, or one crossing report);
3 = a filesystem could not be read at all — a distinct outcome
the entry declares, so a platform change is loud rather than
silently never firing.

Seams (env): STORAGE_WATCH_STATE_DIR, STORAGE_WATCH_HOME_PATH,
STORAGE_WATCH_TMP_PATH, STORAGE_WATCH_STORES (pathsep-separated,
replaces the derived store list), STORAGE_WATCH_DU_TIMEOUT_SECS,
STORAGE_WATCH_HOME_LOW_GB / STORAGE_WATCH_HOME_CRIT_GB (the home
tiers in GB, set by the engine from the entry's config block at
fire time; absent or unparseable → the compiled constants).
Paths derive from this script's own location; nothing is
hardcoded to this machine.
"""

import importlib.util as _importlib_util
import json
import os
import shutil
import subprocess
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

GB = 1024 ** 3
MB = 1024 ** 2

HOME_LOW = 50 * GB
HOME_CRIT = 45 * GB
TMP_LOW = 128 * MB
TMP_CRIT = 32 * MB

HOME_LOW_ENV = "STORAGE_WATCH_HOME_LOW_GB"
HOME_CRIT_ENV = "STORAGE_WATCH_HOME_CRIT_GB"

LEVEL_NAMES = {1: "LOW", 2: "CRITICAL"}


def home_tier_bytes(env_name: str, default: int) -> int:
    """One home tier: the environment's GB figure when the
    variable is present and parseable, else the compiled
    constant — an absent variable changes nothing."""
    raw = os.environ.get(env_name)
    if raw is None or raw.strip() == "":
        return default
    try:
        gb = float(raw)
    except ValueError:
        return default
    if gb <= 0:
        return default
    return int(gb * GB)


def gb_label(nbytes: int) -> str:
    """The threshold label for a home tier: whole GB renders
    as the compiled labels always have (``50 GB``), a
    fractional tier with one decimal."""
    if nbytes % GB == 0:
        return f"{nbytes // GB} GB"
    return f"{nbytes / GB:.1f} GB"


def level_for(free: int, low: int, crit: int) -> int:
    """0 healthy, 1 below low, 2 below critical."""
    if free < crit:
        return 2
    if free < low:
        return 1
    return 0


def fmt_bytes(n: int) -> str:
    if n >= GB:
        return f"{n / GB:.1f} GB"
    if n >= MB:
        return f"{n / MB:.0f} MB"
    return f"{n / 1024:.0f} KB"


def default_stores(repo_root: str) -> list[str]:
    """The generic defaults: this repo's own tree and the home
    caches. A deployment's other stores are its own layout —
    they arrive through the STORAGE_WATCH_STORES seam, never
    as literals here."""
    home = os.path.expanduser("~")
    return [
        repo_root,
        os.path.join(home, ".cache"),
        os.path.join(home, ".local", "share", "uv"),
    ]


def top_stores(stores: list[str], timeout: int, limit: int = 8) -> list[str]:
    existing = [s for s in stores if os.path.isdir(s)]
    if not existing:
        return ["  top stores: none of the known stores exist"]
    try:
        out = subprocess.run(
            ["du", "-s", "-B1", *existing],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ["  top stores: unavailable (du did not complete)"]
    rows = []
    for line in out.stdout.splitlines():
        size, _, path = line.partition("\t")
        if size.strip().isdigit():
            rows.append((int(size), path))
    rows.sort(reverse=True)
    if not rows:
        return ["  top stores: unavailable (du reported nothing)"]
    return [
        f"  {path} — {fmt_bytes(size)}" for size, path in rows[:limit]
    ]


def main() -> int:
    repo_root = paths.REPO_ROOT
    state_dir = os.environ.get(
        "STORAGE_WATCH_STATE_DIR",
        os.path.join(repo_root, "state", "storage-watch"),
    )
    state_file = os.path.join(state_dir, "levels.json")
    home_path = os.environ.get("STORAGE_WATCH_HOME_PATH", os.path.expanduser("~"))
    tmp_path = os.environ.get("STORAGE_WATCH_TMP_PATH", "/tmp")

    home_low = home_tier_bytes(HOME_LOW_ENV, HOME_LOW)
    home_crit = home_tier_bytes(HOME_CRIT_ENV, HOME_CRIT)
    filesystems = [
        ("home", home_path, home_low, home_crit,
         gb_label(home_low), gb_label(home_crit)),
        ("/tmp", tmp_path, TMP_LOW, TMP_CRIT, "128 MB", "32 MB"),
    ]
    current: dict[str, int] = {}
    frees: dict[str, int] = {}
    for name, path, low, crit, _low_label, _crit_label in filesystems:
        try:
            frees[name] = shutil.disk_usage(path).free
        except OSError as exc:
            print(f"storage-watch: cannot read free space for {name} ({path}): {exc}")
            return 3
        current[name] = level_for(frees[name], low, crit)

    recorded: dict[str, int] | None = None
    try:
        with open(state_file) as fh:
            data = json.load(fh)
        recorded = {name: int(data.get(name, 0)) for name, *_ in filesystems}
    except (OSError, ValueError):
        recorded = None

    os.makedirs(state_dir, exist_ok=True)
    paths.staged_write(
        state_file, (json.dumps(current) + "\n").encode("utf-8"))

    if recorded is None:
        return 0  # baseline adoption is silent (detector discipline)

    crossed = [
        (name, low_label, crit_label)
        for name, _path, _low, _crit, low_label, crit_label in filesystems
        if current[name] > recorded[name]
    ]
    if not crossed:
        return 0

    stores_env = os.environ.get("STORAGE_WATCH_STORES")
    if stores_env is not None:
        stores = [s for s in stores_env.split(os.pathsep) if s]
    else:
        stores = default_stores(repo_root)
    du_timeout = int(os.environ.get("STORAGE_WATCH_DU_TIMEOUT_SECS", "90"))

    for name, low_label, crit_label in crossed:
        level = current[name]
        threshold = crit_label if level == 2 else low_label
        print(
            f"STORAGE {LEVEL_NAMES[level]}: {name} filesystem free "
            f"{fmt_bytes(frees[name])} — below the {threshold} "
            f"{LEVEL_NAMES[level].lower()} threshold"
        )
    print("top consuming stores (du, shallow):")
    for line in top_stores(stores, du_timeout):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
