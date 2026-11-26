"""Venue-state actuators: the decisions and payloads that act
on the classification (venue-state mechanism, step 4).

The classifier (sync/runner/venue_classify.py) verdicts; this
leaf turns verdicts into the mechanism's three acts:

- Reap: a wedged job — and any live tree past its record's
  timeout, the classifier's advancing-past-timeout case
  included, since the timeout reap keys off the record —
  is killed venue-side by the reap payload and its record
  settles failed with the two CPU samples as evidence. The
  payload sweeps by run-dir match across the whole process
  table, not only the root's process group: a tree can
  outlive its root (descendants reparented to init keep the
  run dir in their command line or cwd while the root-pid
  read sees nothing), so the kill set is the union of the
  root's descendants, the root's process-group members, and
  every process naming the run dir — and the settle is
  licensed only by a verified-empty table: a reap that
  leaves a survivor never writes the exit file and never
  settles the record.
- Saturation refusal: a fresh state file reading
  "saturated" refuses a new dispatch to that venue, naming
  the state; a stale or absent file refuses nothing — a
  measure's silence is not a verdict.
- Share sizing: a dispatch stamps the job's parallelism
  share — the shape's declared cores scaled by the venue's
  free pid fraction from the state file — into the run
  environment and onto the record.

The decision functions are pure over their inputs (state
dicts, record dicts, process-table dicts); the one shared
helper they need is the foundation's epoch, bound at import
like the classifier's. The venue-side reap script is an
embedded payload whose matching logic mirrors the pure
functions here — the venue cannot import this module, so
the walk is spelled out there and pinned here by fixtures.
"""

import json

from .foundation import epoch

# The exit code a reap writes venue-side: 128 + SIGTERM, the
# code the tree would have reported had the TERM landed on
# the job itself.
REAP_EXIT_CODE = 143

# A state file older than this is not evidence: the sampler
# writes every 120 s, so three missed cycles mean the
# surface is dark, and a dark surface refuses nothing and
# sizes no share.
STATE_FRESH_S = 360

# The TERM grace inside the reap payload before the KILL:
# the reconciliation charter's ~8 s.
TERM_GRACE_S = 8


def load_state(var_dir, venue):
    """One venue's state dict from its state file, or None
    when the file is absent, unreadable, or not a state
    dict. A measure never fails on the surface's absence."""
    from pathlib import Path

    try:
        data = json.loads((Path(var_dir) / f"venue-state-{venue}.json").read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _fresh(state, now_epoch, max_age_s):
    """Whether a state dict is fresh enough to act on: it
    carries a parseable sampled_at no older than the bound
    (and not ahead of the reader's clock beyond slack)."""
    if not isinstance(state, dict) or now_epoch is None:
        return False
    sampled = epoch(state.get("sampled_at"))
    if sampled is None:
        return False
    return -60 <= now_epoch - sampled <= max_age_s


def saturation_refusal(state, *, now_epoch, max_age_s=STATE_FRESH_S):
    """The preflight refusal for a dispatch to a saturated
    venue, or None. Only a fresh "saturated" verdict
    refuses, and the refusal names the state and the table
    that produced it."""
    if not _fresh(state, now_epoch, max_age_s):
        return None
    if state.get("state") != "saturated":
        return None
    return (
        f"venue {state.get('venue')} is saturated "
        f"(venue-state: pids {state.get('pids_current')}/{state.get('pids_capacity')} "
        f"at {state.get('sampled_at')}) — new fires refuse until the table drains "
        "below the watermark"
    )


def share_for(state, cores, *, now_epoch, max_age_s=STATE_FRESH_S):
    """The parallelism share a dispatch stamps for one job.

    With a fresh state file carrying the table's occupancy,
    the share is the declared cores scaled by the free pid
    fraction, floored at one worker: a contended venue
    divides its cores, an empty one lends them all. Without
    a fresh reading the share is the declared cores
    unscaled and the basis names why — the dispatch still
    records the share it used, never a silent default.
    Returns {"workers", "free_fraction", "basis"}; workers
    is None when no core count is declared (nothing to
    stamp — the job form's own default stands).
    """
    if not cores:
        return {"workers": None, "free_fraction": None, "basis": "no-cores-declared"}
    cores = int(cores)
    if state is None:
        return {"workers": cores, "free_fraction": None, "basis": "no-state"}
    if not _fresh(state, now_epoch, max_age_s):
        return {"workers": cores, "free_fraction": None, "basis": "stale-state"}
    current = state.get("pids_current")
    capacity = state.get("pids_capacity")
    if current is None or not capacity:
        return {"workers": cores, "free_fraction": None, "basis": "no-occupancy"}
    free = max(0.0, min(1.0, 1.0 - current / capacity))
    workers = max(1, int(cores * free)) if free > 0 else 1
    return {"workers": workers, "free_fraction": round(free, 4), "basis": "state"}


# --- the process-table match (mirrored in the reap payload) ---


def _names_run_dir(proc, run_dir):
    """Whether a process names the run dir: its command line
    carries the dir, or its cwd is the dir or under it. This
    leg is what catches a descendant reparented to init —
    invisible to both the root's tree walk and its process
    group, still holding the run's files and ports."""
    cmdline = proc.get("cmdline") or ""
    if run_dir in cmdline:
        return True
    cwd = proc.get("cwd") or ""
    return cwd == run_dir or cwd.startswith(run_dir + "/")


def matching_pids(procs, root_pid, run_dir, *, pgid=None, exclude=frozenset()):
    """The pids a reap acts on, from a process table of
    pid -> {"ppid", "pgid", "cmdline", "cwd"}.

    The union of three legs: the root's descendant tree
    (the root included), the root's process-group members,
    and every process naming the run dir. The exclusions
    are absolute: pid 1 and below are never subjects, the
    caller's own chain (the payload's pid and its
    ancestors, passed as exclude) never is, and a process
    naming a DIFFERENT run dir is another job's — it enters
    only through this tree's own structural legs, never
    through the name match.
    """
    excluded = set(exclude) | {0, 1}
    matched = set()
    if root_pid is not None and root_pid in procs:
        children = {}
        for pid, proc in procs.items():
            children.setdefault(proc.get("ppid"), []).append(pid)
        stack = [root_pid]
        while stack:
            pid = stack.pop()
            if pid in matched:
                continue
            matched.add(pid)
            stack.extend(children.get(pid, []))
        group = procs[root_pid].get("pgid") if pgid is None else pgid
        if group is not None:
            for pid, proc in procs.items():
                if proc.get("pgid") == group:
                    matched.add(pid)
    elif pgid is not None:
        for pid, proc in procs.items():
            if proc.get("pgid") == pgid:
                matched.add(pid)
    for pid, proc in procs.items():
        if _names_run_dir(proc, run_dir):
            matched.add(pid)
    return sorted(matched - excluded)


def survivors(procs, root_pid, run_dir, *, pgid=None, exclude=frozenset()):
    """The pids still matching after a reap: the same match
    over the post-kill table. The root's pgid is passed from
    the pre-kill read — once the root is gone its group can
    still hold survivors, and they are found by the group
    leg or the name leg, never by a root that no longer
    exists. An empty list is the only licence to settle."""
    return matching_pids(procs, root_pid, run_dir, pgid=pgid, exclude=exclude)


# --- reap decisions ---


def _age_anchor(rec):
    for key in ("first_seen_at", "started_at", "launch_at", "launch_confirmed_at"):
        value = epoch(rec.get(key))
        if value is not None:
            return value
    return None


def reap_decisions(state, records_by_run_id, *, now_epoch):
    """The reap decisions one venue's state file licenses.

    A decision per live tree the actuator must kill: every
    job the classifier verdicts wedged, and every live tree
    past its record's timeout (the classifier verdicts a
    still-advancing tree past its timeout "advancing" by
    design — the timeout reap keys off the record, here).
    Terminal records and gone trees decide nothing. Each
    decision carries its evidence: the verdict and the two
    CPU samples the record settles with.
    """
    decisions = []
    if not isinstance(state, dict):
        return decisions
    records = records_by_run_id or {}
    for job in state.get("jobs", []):
        run_id = job.get("run_id")
        if run_id is None or not job.get("tree_alive"):
            continue
        root_pid = job.get("root_pid")
        if root_pid is None:
            continue
        rec = records.get(run_id) or {}
        if rec.get("state") in ("complete", "failed", "orphaned"):
            continue
        anchor = _age_anchor(rec)
        age = None if anchor is None or now_epoch is None else now_epoch - anchor
        timeout_s = rec.get("timeout_s")
        reason = None
        if job.get("verdict") == "wedged":
            reason = "wedged"
        elif age is not None and timeout_s is not None and age > timeout_s:
            reason = "timeout"
        if reason is None:
            continue
        decisions.append(
            {
                "run_id": run_id,
                "root_pid": root_pid,
                "caller": rec.get("caller") or job.get("caller"),
                "reason": reason,
                "evidence": {
                    "verdict": job.get("verdict"),
                    "cpu_s": job.get("cpu_s"),
                    "cpu_delta_s": job.get("cpu_delta_s"),
                    "age_s": None if age is None else round(age, 1),
                    "timeout_s": timeout_s,
                },
            }
        )
    return decisions


def settle_action(parsed):
    """What a reap outcome licenses: ("settle", exit_code)
    only when the payload verified the table empty and an
    exit code stands (written by the reap, or already
    standing from the job's own finish); ("hold", survivors)
    otherwise — a reap that leaves a survivor, or whose
    reading never arrived, settles nothing."""
    if not parsed:
        return "hold", []
    left = parsed.get("survivors") or []
    if parsed.get("verified_gone") and not left and parsed.get("exit_code") is not None:
        return "settle", parsed["exit_code"]
    return "hold", left


# --- the reap payload (venue side) ---

_REAP_SCRIPT = """\
import json
import os
import signal
import sys
import time
from pathlib import Path

RUN_ID = __RUN_ID__
ROOT_PID = __ROOT_PID__
TERM_GRACE_S = __TERM_GRACE_S__
REAP_EXIT = __REAP_EXIT__


def read_table():
    procs = {}
    proc_root = Path("/proc")
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return procs
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            text = (entry / "stat").read_text()
        except OSError:
            continue
        rparen = text.rfind(")")
        if rparen < 0:
            continue
        fields = text[rparen + 2:].split()
        if len(fields) < 3:
            continue
        try:
            ppid = int(fields[1])
            pgid = int(fields[2])
        except ValueError:
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\\x00", b" ").decode(errors="replace")
        except OSError:
            cmdline = ""
        try:
            cwd = os.readlink(entry / "cwd")
        except OSError:
            cwd = ""
        procs[pid] = {"ppid": ppid, "pgid": pgid, "cmdline": cmdline, "cwd": cwd}
    return procs


def self_chain(procs):
    chain = set()
    pid = os.getpid()
    while pid and pid > 1 and pid not in chain:
        chain.add(pid)
        entry = procs.get(pid)
        pid = entry["ppid"] if entry else None
    return chain


def names_run_dir(proc, run_dir):
    if run_dir in (proc.get("cmdline") or ""):
        return True
    cwd = proc.get("cwd") or ""
    return cwd == run_dir or cwd.startswith(run_dir + "/")


def matching(procs, root_pid, run_dir, pgid, exclude):
    excluded = set(exclude) | {0, 1}
    matched = set()
    if root_pid is not None and root_pid in procs:
        children = {}
        for pid, proc in procs.items():
            children.setdefault(proc.get("ppid"), []).append(pid)
        stack = [root_pid]
        while stack:
            pid = stack.pop()
            if pid in matched:
                continue
            matched.add(pid)
            stack.extend(children.get(pid, []))
    group = pgid
    if group is None and root_pid is not None and root_pid in procs:
        group = procs[root_pid].get("pgid")
    if group is not None:
        for pid, proc in procs.items():
            if proc.get("pgid") == group:
                matched.add(pid)
    for pid, proc in procs.items():
        if names_run_dir(proc, run_dir):
            matched.add(pid)
    return sorted(matched - excluded)


def signal_all(pids, sig):
    sent = []
    for pid in pids:
        try:
            os.kill(pid, sig)
            sent.append(pid)
        except (ProcessLookupError, PermissionError):
            continue
    return sent


def main():
    run_dir = str(Path.home() / "runs" / RUN_ID)
    procs = read_table()
    exclude = self_chain(procs)
    root_entry = procs.get(ROOT_PID) if ROOT_PID is not None else None
    root_pgid = root_entry.get("pgid") if root_entry else None
    matched = matching(procs, ROOT_PID, run_dir, root_pgid, exclude)
    termed = signal_all(matched, signal.SIGTERM)
    deadline = time.time() + TERM_GRACE_S
    left = matching(read_table(), ROOT_PID, run_dir, root_pgid, exclude)
    while left and time.time() < deadline:
        time.sleep(0.5)
        left = matching(read_table(), ROOT_PID, run_dir, root_pgid, exclude)
    killed = []
    if left:
        killed = signal_all(left, signal.SIGKILL)
        time.sleep(1)
    final = matching(read_table(), ROOT_PID, run_dir, root_pgid, exclude)
    verified = not final
    exit_path = Path(run_dir) / "exit"
    exit_code = None
    exit_written = False
    if exit_path.exists():
        try:
            exit_code = int(exit_path.read_text().strip())
        except (OSError, ValueError):
            exit_code = None
    if verified and exit_code is None:
        try:
            exit_path.write_text(str(REAP_EXIT) + "\\n")
            exit_code = REAP_EXIT
            exit_written = True
        except OSError:
            pass
    print("REAPJ " + json.dumps({
        "run_id": RUN_ID,
        "root_pid": ROOT_PID,
        "matched": matched,
        "termed": termed,
        "killed": killed,
        "survivors": final,
        "verified_gone": verified,
        "exit_code": exit_code,
        "exit_written": exit_written,
    }))


main()
"""


def build_reap_command(run_id: str, root_pid) -> str:
    """The single SSH exec payload for one reap: sweep the
    run's whole match (tree, process group, run-dir name)
    with TERM, wait the grace, KILL the survivors, verify
    the table empty, and only then write the exit file.
    The run id and root pid are embedded as literals (the
    sampler payload's form); the run id is a dispatcher-
    minted name, never free text."""
    script = (
        _REAP_SCRIPT.replace("__RUN_ID__", json.dumps(str(run_id)))
        .replace("__ROOT_PID__", json.dumps(root_pid))
        .replace("__TERM_GRACE_S__", str(TERM_GRACE_S))
        .replace("__REAP_EXIT__", str(REAP_EXIT_CODE))
    )
    return "python3 - <<'VENUE_REAP_EOF'\n" + script + "VENUE_REAP_EOF\n"


def parse_reap_output(text: str):
    """Reap payload output -> its verdict dict, or None when
    no REAPJ line arrived (the exec failed, timed out, or
    the venue answered something else — an unread reap is a
    hold, never a settle)."""
    for line in (text or "").splitlines():
        if line.startswith("REAPJ "):
            try:
                data = json.loads(line[6:])
            except ValueError:
                return None
            return data if isinstance(data, dict) else None
    return None
