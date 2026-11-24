"""Durable serve boot record: one appended record per
serve startup, in the scheduler's state home
(`<home>/state/serve-boots.json`, the stateio JSON form
every scheduler store uses — no second store).

Why this exists (the 2026-11-24 outage class):
workhorse.service was found down with ExecMainStatus=0
three times in a day, and nothing the serve itself wrote
could say when it had started, from what code, how long
startup took, or that it had ever become ready — the
serve's log carries startup banners only and the journal
keeps only the current boot. Each boot now leaves its own
record, and a new boot appends: the previous boot's
record is left intact, so a death is diagnosable from the
record set the serve itself left behind (the next boot's
record proves the return; the gap between one boot's
record and the next is the outage).

A record carries: `instance` (a per-process id, minted
at open), `boot_id` (the kernel boot id, the
restart-reconcile machinery's own source — several serve
instances share one kernel boot across restarts),
`entry` (which serve entry opened it), `pid`,
`started_at`, the code stamp (`head` / `tree` of the
checkout the serve booted from, None when git cannot say
— the stamp never blocks startup), and the ready stamp:
`ready_at` with `startup_latency_s`, the seconds from
process start to health-ready. Health-ready is defined
at the wiring point: the listeners are bound (a
Listener's socket binds at construction) and the serve
loop is about to start, so a client answer is a thread
start away.

Writes ride dispatch.stateio (the platform staged
writer), so a crash mid-write leaves the previous good
file. A record file that exists but cannot be parsed is
moved aside (`.corrupt-<instance>`), never silently
discarded and never a startup refusal: the boot record
is observability, and observability must not be able to
down the serve it observes. Callers still wrap the call
and continue without a record on any other failure.
"""
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone

from dispatch.stateio import StateError, read_json, write_json

RECORD_NAME = "serve-boots.json"
BOOT_ID_FILE = os.environ.get(
    "SCHEDULER_VM_BOOT_ID_FILE") or "/proc/sys/kernel/random/boot_id"


def record_path(home):
    """The boot record's path under a scheduler home."""
    return os.path.join(home, "state", RECORD_NAME)


def kernel_boot_id(path=None):
    """The kernel boot id from the boot-id file (the
    restart-reconcile machinery's source), or None when
    it cannot be read."""
    try:
        with open(path or BOOT_ID_FILE, "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def code_stamp(repo_root):
    """(head, tree) of the checkout at repo_root, from
    git; (None, None) when git cannot say. Bounded and
    never raising: the stamp is evidence, not a gate."""
    def rev_parse(rev):
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", rev],
            capture_output=True, text=True, timeout=5)
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None
    try:
        return rev_parse("HEAD"), rev_parse("HEAD^{tree}")
    except (OSError, subprocess.SubprocessError):
        return None, None


def _read_boots(path, aside_stamp):
    try:
        data = read_json(path, {"boots": []})
    except StateError:
        # An unreadable record is moved aside intact and
        # the record starts fresh (see module docstring).
        try:
            os.replace(path, f"{path}.corrupt-{aside_stamp}")
        except OSError:
            pass
        return []
    if not isinstance(data, dict):
        return []
    boots = data.get("boots")
    return list(boots) if isinstance(boots, list) else []


def open_boot(path, *, entry, repo_root, now=None, boot_id=None,
              instance=None, pid=None, stamp=None):
    """Append this process's boot record and return it.
    `now`, `boot_id`, `instance`, `pid` and `stamp` (the
    (head, tree) code stamp) are injectable for tests;
    the defaults read the live machine."""
    now = now or datetime.now(timezone.utc)
    instance = instance or uuid.uuid4().hex
    head, tree = stamp if stamp is not None else code_stamp(repo_root)
    record = {
        "instance": instance,
        "boot_id": kernel_boot_id() if boot_id is None else boot_id,
        "entry": entry,
        "pid": os.getpid() if pid is None else pid,
        "started_at": now.isoformat(),
        "head": head,
        "tree": tree,
        "ready_at": None,
        "startup_latency_s": None,
    }
    boots = _read_boots(path, instance)
    boots.append(record)
    write_json(path, {"boots": boots})
    return record


def stamp_ready(path, instance, *, started_monotonic, now=None,
                monotonic=None):
    """Stamp the boot record `instance` health-ready:
    ready_at plus startup_latency_s measured from
    `started_monotonic` (the wiring point's process-start
    monotonic stamp). Returns False — and writes nothing
    — when no such record stands."""
    now = now or datetime.now(timezone.utc)
    monotonic = time.monotonic() if monotonic is None else monotonic
    boots = _read_boots(path, instance)
    for record in boots:
        if record.get("instance") == instance:
            record["ready_at"] = now.isoformat()
            record["startup_latency_s"] = round(
                monotonic - started_monotonic, 3)
            write_json(path, {"boots": boots})
            return True
    return False
