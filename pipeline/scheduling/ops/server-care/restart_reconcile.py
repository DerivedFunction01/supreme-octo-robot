#!/usr/bin/env python3
"""Restart reconciliation: orphaned runs become a pushed event.

Owner-escalated commission: VM restarts
silently orphan in-flight work — a detached
Colab run survives session-side, but the lane that would collect
it died with the old VM, its run record sits at a non-terminal
state forever, and nothing notices. Restart DETECTION already
exists (vm-restart-detector reports each new boot to the main
chat); this job is the reconciliation leg that names the damage.

Each pass:

- reads the Colab runner's run records (plain JSON; the read
  needs no credential) — state, caller, session, and the
  collector heartbeat: collector_at once the runner stamps
  it, last_evidence_at before that. Evidence freshness is
  attendance: a non-terminal record whose heartbeat has
  frozen has no live collector (the run itself may be fine
  session-side — the event says unattended, never dead).
- restart leg: when the kernel boot id differs from the last
  boot reconciled, every non-terminal record whose evidence
  predates the boot time was orphaned by this restart.
- stuck leg: every pass, a non-terminal record whose evidence
  is older than the staleness bound (default 30m) is orphaned
  in fact, restart or not.
- episodes, not spam: this job's state records each reported
  run under its episode key (the boot id for the restart leg,
  "stuck" otherwise). A record reports once per episode; a
  later pass finding it terminal closes it silently; still
  non-terminal at the next boot, it reports again under the
  new boot.

The second population is the scheduler's own fired jobs.
The firing layer ledgers a run_started event at fire time,
carrying the entry's timeout budget, and a run event at
completion; a started fire with neither a completion nor a
mark is a record in a non-terminal state — the shape a serve
death mid-run leaves behind (the specimen shape: a
fired daily job frozen at running across a VM replacement,
unreconciled for hours). The same two legs judge it: its
start predates a changed boot (restart leg), or it stands
past its budget plus the staleness bound with no completion
(budget leg). A judged fire is MARKED, not just reported:
the sweep appends the fire's terminal event to the ledger —
kind interrupted, the cause on the record — so the pair
closes for every later pass and the mark, once written, can
never be written twice. The sweep marks and surfaces only;
the owed work is the owning thread's to re-drive or write
off, never this job's.

Delivery: one addressed ping per affected owning thread is
planted in the scheduler outbox (body
bodies/restart-reconcile.md; detail carries the restart facts
and that owner's items — run ids, jobs, sessions, evidence
ages, never payloads). Owners resolve from the live config
bodies/restart-reconcile-owners.yaml by exact caller, else by
the caller's namespace — the segment before its first colon,
the caller registry's own lane grammar (programme:lane). A
caller with no resolved owner is never guessed: its items
print on UNRESOLVED
lines, which the entry's report rule carries to the main chat,
and the printed RECONCILE summary is the main chat's copy of
every event regardless.

Exit codes: 0 = pass complete (silent when nothing is new);
3 = the boot-id source, the run-record store, or the fired
ledger is unreadable, so the check cannot run — a distinct
outcome the entry declares, loud rather than silently never
firing.

Stdlib only; paths derived from this file's location, with env
overrides (SCHEDULER_RECONCILE_RUNS_DIR,
SCHEDULER_RECONCILE_STALE_SECS, SCHEDULER_VM_BOOT_ID_FILE,
SCHEDULER_RECONCILE_LEDGER_DB) for tests and proof runs.
"""
import argparse
import json
import os
import sqlite3
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

REPO = paths.REPO_ROOT
sys.path.insert(0, REPO)
sys.path.insert(0, paths.script_dir(__file__))

from server import registry  # noqa: E402
from dispatch.ledger import Ledger  # noqa: E402
from dispatch.outbox import Outbox  # noqa: E402

# The tolerant ISO parse home is the workrecord lib's
# (one owner per helper); its root joins the path the same
# derived way paths.py reaches the platform writer.
sys.path.insert(0, os.path.join(os.path.dirname(REPO), "workrecord"))
from lib.util import parse_instant as parse_ts  # noqa: E402

UTC = timezone.utc
WORKSPACE = paths.WORKSPACE_ROOT

RUNS_DIR = os.environ.get(
    "SCHEDULER_RECONCILE_RUNS_DIR") or os.path.join(
        WORKSPACE, "colab-runner", "results", "runs")
BOOT_ID_FILE = os.environ.get(
    "SCHEDULER_VM_BOOT_ID_FILE") or "/proc/sys/kernel/random/boot_id"
STATE_PATH = os.environ.get(
    "SCHEDULER_RECONCILE_STATE") or os.path.join(
        paths.STATE_DIR, "restart-reconcile.json")
STATE_DIR = paths.STATE_DIR
OWNERS_PATH = os.environ.get(
    "SCHEDULER_RECONCILE_OWNERS") or os.path.join(
        paths.BODIES_DIR, "restart-reconcile-owners.yaml")
BODY_REF = "bodies/restart-reconcile.md"
JOB_PREFIX = "restart-reconcile-"
LEDGER_DB = os.environ.get(
    "SCHEDULER_RECONCILE_LEDGER_DB") or os.path.join(
        paths.STATE_DIR, "scheduler.db")
FIRED_PREFIX = "fired:"
NONTERMINAL = {"polling", "starting", "running", "launched"}
DEFAULT_STALE_SECS = int(
    os.environ.get("SCHEDULER_RECONCILE_STALE_SECS") or 1800)
MAX_DETAIL_ITEMS = 25


def read_boot_id(path=BOOT_ID_FILE):
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def read_boot_time():
    """Kernel boot time (epoch -> datetime) from /proc/stat btime."""
    with open("/proc/stat", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("btime "):
                return datetime.fromtimestamp(
                    int(line.split()[1]), tz=UTC)
    raise OSError("btime not found in /proc/stat")


def load_owners(path):
    """(exact, namespaces, prefixes) caller routing from the
    live owners config in the registry YAML subset: `owners`
    maps a full caller name to {chat}; `namespaces` maps a
    caller's namespace — the segment before its first colon,
    the caller registry's own lane grammar (programme:lane) —
    to {chat}; `prefixes` maps a caller-name prefix (the dash
    families) to {chat}. A missing or malformed config
    resolves nobody."""
    empty = ({}, {}, {})
    try:
        with open(path, encoding="utf-8") as fh:
            config = registry.parse_yaml(fh.read(), path)
    except (OSError, registry.EntryError):
        return empty
    if not isinstance(config, dict):
        return empty

    def chats(section):
        mapping = config.get(section)
        if not isinstance(mapping, dict):
            return {}
        resolved = {}
        for caller, spec in mapping.items():
            if isinstance(spec, dict) \
                    and isinstance(spec.get("chat"), str) \
                    and spec["chat"]:
                resolved[str(caller)] = spec["chat"]
        return resolved

    return chats("owners"), chats("namespaces"), chats("prefixes")


def resolve_owner(caller, owners):
    """Exact caller first, else the caller's namespace (the
    segment before its first colon), else the longest dash-
    family prefix, else None."""
    exact, namespaces, prefixes = owners
    if caller in exact:
        return exact[caller]
    # The namespace is the segment before the first colon; a
    # caller with no colon is its own namespace (a bare caller
    # named for its namespace — e.g. edgar-specimen — resolves
    # by its full name).
    chat = namespaces.get(caller.split(":", 1)[0])
    if chat:
        return chat
    best = None
    for prefix, chat in prefixes.items():
        if caller.startswith(prefix):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, chat)
    return best[1] if best else None


def scan_records(runs_dir):
    """(records, unreadable_count). Each record keeps only the
    fields the sweep keys on, plus its evidence stamp."""
    records = []
    unreadable = 0
    for name in sorted(os.listdir(runs_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(runs_dir, name),
                      encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            unreadable += 1
            continue
        if not isinstance(raw, dict) or not raw.get("run_id"):
            unreadable += 1
            continue
        # The collector heartbeat: collector_at once the
        # runner's cure lands it (stamped at launch, every
        # evidence save, every poll reconcile, finalize);
        # last_evidence_at on pre-cure records — they advance
        # together on collected runs.
        evidence = parse_ts(raw.get("collector_at")) \
            or parse_ts(raw.get("last_evidence_at")) \
            or parse_ts(raw.get("started_at"))
        records.append({
            "run_id": raw["run_id"],
            "job": raw.get("job") or "",
            "caller": raw.get("caller") or "",
            "session": raw.get("session") or "",
            "state": raw.get("state") or "",
            "started_at": raw.get("started_at") or "",
            "evidence": evidence,
        })
    return records, unreadable


def scan_fired(db_path):
    """(open, closed) fired-job records from the scheduler's
    own ledger. A fire is the (job_id, due) pair of a
    run_started event; the pair closes when a run event (the
    engine's completion record) or an interrupted event (a
    prior sweep's mark) lands for it. Open records keep the
    fire's start and its timeout budget. A missing ledger is
    an empty population — the serve has never run here; a
    present one that cannot be read raises OSError, and the
    entry exits 3: the check does not run blind."""
    if not os.path.exists(db_path):
        return [], set()
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT record FROM events WHERE kind IN"
                " ('run_started', 'run', 'interrupted')"
                " ORDER BY id").fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise OSError(f"fired ledger unreadable: {exc}") from exc
    started, closed = {}, set()
    for (raw,) in rows:
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        key = (rec.get("job_id"), rec.get("due"))
        if None in key:
            continue
        if rec.get("kind") == "run_started":
            started[key] = {
                "job_id": rec["job_id"], "due": rec["due"],
                "started": parse_ts(rec.get("ts")),
                "timeout_secs": rec.get("timeout_secs"),
            }
        else:
            closed.add(key)
    return [rec for key, rec in started.items()
            if key not in closed], closed


def mark_interrupted(ledger, rec, cause, leg, boot_id):
    """Append the fire's terminal event: kind interrupted,
    the cause on the record. The ledger is append-only, so
    the mark is a new event for the fire's (job_id, due)
    pair — after it, scan_fired reads the pair closed, and
    no later pass can mark it again."""
    try:
        ledger.record(
            "interrupted", job_id=rec["job_id"], due=rec["due"],
            cause=cause, leg=leg, boot_id=boot_id)
    except sqlite3.Error as exc:
        raise OSError(f"fired ledger unwritable: {exc}") from exc


def load_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return {"boot_id": None, "reported": {}}
    if not isinstance(state, dict):
        return {"boot_id": None, "reported": {}}
    state.setdefault("boot_id", None)
    if not isinstance(state.get("reported"), dict):
        state["reported"] = {}
    return state


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    paths.save_json(path, state)


def run(runs_dir=RUNS_DIR, state_path=STATE_PATH,
        owners_path=OWNERS_PATH, state_dir=STATE_DIR,
        boot_id=None, boot_time=None, now=None,
        stale_secs=DEFAULT_STALE_SECS, outbox=None,
        ledger_db=LEDGER_DB, ledger=None):
    """One reconciliation pass. Returns the output lines."""
    now = now or datetime.now(UTC)
    if boot_id is None:
        boot_id = read_boot_id()
    if boot_time is None:
        boot_time = read_boot_time()
    records, unreadable = scan_records(runs_dir)
    by_id = {r["run_id"]: r for r in records}
    fired, fired_closed = scan_fired(ledger_db)
    state = load_state(state_path)
    reported = state["reported"]

    # Closures: a reported run that reached a terminal state
    # (or whose record is gone) leaves the episode silently.
    # A reported fire closes when its pair reaches a terminal
    # event in the ledger — its completion, or a prior mark.
    for run_id in list(reported):
        if run_id.startswith(FIRED_PREFIX):
            entry = reported[run_id]
            if (entry.get("job_id"), entry.get("due")) \
                    in fired_closed:
                del reported[run_id]
            continue
        record = by_id.get(run_id)
        if record is None or record["state"] not in NONTERMINAL:
            del reported[run_id]

    restarted = state["boot_id"] is not None \
        and boot_id != state["boot_id"]
    fresh = []
    for record in records:
        if record["state"] not in NONTERMINAL:
            continue
        evidence = record["evidence"]
        leg = None
        key = None
        if restarted and evidence is not None \
                and evidence < boot_time:
            leg, key = "restart", boot_id
        elif evidence is not None \
                and (now - evidence).total_seconds() > stale_secs:
            leg, key = "stuck", "stuck"
        if leg is None:
            continue
        # One report per episode: a report under the current
        # boot's key covers both legs for the whole boot (a
        # restart-reported run must not re-report as stuck on
        # the next pass); a "stuck" report does not cover a
        # later restart leg, which is a new episode.
        prev = reported.get(record["run_id"], {}).get("key")
        if prev is not None and (prev == key or prev == boot_id):
            continue
        item = dict(record)
        item["leg"] = leg
        item["episode"] = key
        item["evidence_age_min"] = int(
            (now - evidence).total_seconds() // 60) if evidence else None
        fresh.append(item)
        reported[record["run_id"]] = {
            "key": key, "at": now.isoformat(),
            "caller": record["caller"]}

    # The fired population, under the same two legs. A judged
    # fire is marked first and unconditionally — the pair is
    # open and judged, so its terminal event lands now, and
    # scan_fired closes it for every later pass: marked
    # exactly once, however the episodes fall. The episode
    # dedup below it governs only the ping.
    fired_ledger = ledger
    for rec in fired:
        started = rec["started"]
        if started is None:
            continue
        leg = key = cause = None
        if restarted and started < boot_time:
            leg, key = "restart", boot_id
            cause = (
                f"boot {boot_id} at {boot_time.isoformat()}: "
                "the serve owning this run died with the prior "
                "boot; no completion record landed")
        elif rec["timeout_secs"] is not None and \
                (now - started).total_seconds() \
                > rec["timeout_secs"] + stale_secs:
            leg, key = "budget", "budget"
            cause = (
                f"past budget: fired {started.isoformat()} with "
                f"timeout {rec['timeout_secs']}s and no "
                "completion record")
        if leg is None:
            continue
        if fired_ledger is None:
            fired_ledger = Ledger(os.path.dirname(ledger_db))
        mark_interrupted(fired_ledger, rec, cause, leg, boot_id)
        rid = FIRED_PREFIX + rec["job_id"] + ":" + rec["due"]
        prev = reported.get(rid, {}).get("key")
        if prev is not None and (prev == key or prev == boot_id):
            continue
        item = {
            "run_id": rid, "job": rec["job_id"],
            "caller": rec["job_id"], "session": "",
            "state": "interrupted", "leg": leg, "episode": key,
            "evidence_age_min": int(
                (now - started).total_seconds() // 60),
            "due": rec["due"], "cause": cause,
        }
        fresh.append(item)
        reported[rid] = {
            "key": key, "at": now.isoformat(),
            "caller": rec["job_id"], "job_id": rec["job_id"],
            "due": rec["due"]}

    state["boot_id"] = boot_id
    save_state(state_path, state)
    if not fresh:
        return []

    owners = load_owners(owners_path)
    groups = {}
    for item in fresh:
        chat = resolve_owner(item["caller"], owners)
        groups.setdefault(chat, []).append(item)

    if outbox is None:
        outbox = Outbox(state_dir, Ledger(state_dir))
    fired_new = sum(1 for i in fresh
                    if i["run_id"].startswith(FIRED_PREFIX))
    lines = [
        f"RECONCILE boot={boot_id[:8]} "
        f"booted={boot_time.isoformat()} new={len(fresh)} "
        f"owners={sum(1 for c in groups if c)}"
        + (f" fired={fired_new}" if fired_new else "")
        + (f" unreadable={unreadable}" if unreadable else "")]
    for chat, items in sorted(
            groups.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        callers = sorted({i["caller"] for i in items})
        if chat is None:
            for item in items:
                lines.append(
                    f"UNRESOLVED caller={item['caller']} "
                    f"run={item['run_id']} job={item['job']} "
                    f"session={item['session']} "
                    f"evidence_age_min={item['evidence_age_min']}")
            continue
        detail = {
            "target_chat": chat,
            "boot_id": boot_id,
            "booted_at": boot_time.isoformat(),
            "items": [{
                "run_id": i["run_id"], "job": i["job"],
                "caller": i["caller"], "session": i["session"],
                "state": i["state"], "leg": i["leg"],
                "evidence_age_min": i["evidence_age_min"],
                **({"due": i["due"], "cause": i["cause"]}
                   if "cause" in i else {}),
            } for i in items[:MAX_DETAIL_ITEMS]],
            "more": max(0, len(items) - MAX_DETAIL_ITEMS),
        }
        _ping, created = outbox.add_or_coalesce(
            JOB_PREFIX + boot_id[:8] + "-" + chat[:8], now,
            "agent-due", body_ref=BODY_REF, detail=detail, now=now)
        lines.append(
            f"ORPHANS owner={chat} callers={','.join(callers)} "
            f"runs={len(items)} ping={'planted' if created else 'standing'}")
    return lines


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        lines = run()
    except OSError as exc:
        sys.stderr.write(f"restart-reconcile: cannot run: {exc}\n")
        return 3
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
