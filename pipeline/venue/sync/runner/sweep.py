#!/usr/bin/env python3
"""The sweep: reconcile non-terminal run records against the
live session list — orphaned sessions, launches whose launcher
died mid-launch (stale "running"), and launches that died
before landing (stale "starting").
"""

import contextlib
import io
import json
import os
import time
from datetime import datetime, timezone

from .foundation import REPO, RUNS, colab, lease, now
from .claims import claim_lost, pid_alive
from .records import TERMINAL_STATES, collector_stale, emit_terminal_event, mark_terminal, save_record
from .reader import read_reader, write_reader

# A record still in "running" (the pre-confirmation state) this
# long after its start, with no fresher evidence, had its
# launcher die mid-launch: live launchers pass through the state
# in minutes (launch exec + one confirmation read, both bounded).
STALE_RUNNING_S = 1200
# The stale-"starting" bound for the sweep: "starting" is a
# pre-launch state whose worst legitimate hold is one wedged
# upload call (subprocess bound 3600 s) plus the phases around
# it, so the bound sits at twice that call. Past it, with no
# fresher stamp or save, the launcher died before the launch.
STALE_STARTING_S = 7200


def _daemon_orphan(rec: dict) -> bool:
    """A daemonized launch whose driver is decidable as dead
    before its launch began: the record carries
    its daemon child's pid as the driver stamp, the launch
    never began (no launch_at — the stamp the launch exec's
    own save writes), and the pid is provably dead. A claiming
    record keys on the claim's own lost test (deadline passed
    AND pid dead — claims.claim_lost); a starting record on
    the dead pid alone, because the daemon child IS the
    launcher: dead, it launches nothing, at any record age.
    A live pid is never an orphan — a daemon queued behind
    the session launch lock sits in "starting" with its pid
    alive, healthy at any age — and the stamp follows the
    driver (a resume re-stamps it, by takeover or in place),
    so the test always names the process currently driving
    the run."""
    if rec.get("launch_at") or rec.get("launch_confirmed_at"):
        return False
    if rec.get("daemon_child_pid") is None:
        return False
    if rec.get("state") == "claiming":
        return claim_lost(rec)
    return not pid_alive(rec.get("daemon_child_pid"))


def _launch_reading(rec: dict) -> str:
    """One reader pass over the session the run's launch
    landed on, for the stale-"running" verdict: "footprint"
    (the launch landed — job pids, an exit stamp, a log tail,
    or a checkpoint, the launch confirmation's own test),
    "absent" (a readable pass with no footprint at all: the
    launch provably never landed), or "unknown" (the pass
    itself could not be read — a timeout is a lost response,
    never a proven negative)."""
    session = rec.get("launch_session") or rec.get("session")
    remote_out = rec.get("remote_out")
    if not session or not remote_out:
        return "unknown"
    reader = write_reader(str(rec.get("run_id")), remote_out, [])
    confirm_timeout = int(os.environ.get("COLAB_RUN_CONFIRM_TIMEOUT_S") or min(int(os.environ.get("COLAB_RUN_POLL_TIMEOUT_S", "300")), 120))
    state, _err = read_reader(session, reader, confirm_timeout)
    if state is None:
        return "unknown"
    if state.get("job_pids") or state.get("exit_stamp") is not None or state.get("job_log_tail") or state.get("checkpoint"):
        return "footprint"
    return "absent"


def orphan_sweep() -> tuple[list[dict], bool]:
    """Reconcile non-terminal run records against live sessions.

    Membership is exact-name, through the lease core's live-list
    parser (lease.live_sessions) — never substring on raw stdout:
    a name that textually collides with a live one must not read
    as alive, and a partial list must not read as a census. An
    unreadable list (None) reconciles nothing — the session_state
    rule, that no caller may act on a list it could not read. A
    torn record is skipped, never fatal: one damaged file must
    not block the reconcile of every other run (it blocked every
    runner entry in the write-denial flap). The sweep runs on the
    reconcile cadences (--poll, --sweep), never on the launch
    path. Returns (findings, live_list_readable)."""
    findings = []
    if not RUNS.exists():
        return findings, True
    live = lease.live_sessions(colab, REPO)
    if live is None:
        return findings, False
    live_names = {entry["session"] for entry in live}
    confirmed_absent: set[str] = set()
    for f in sorted(RUNS.glob("*.json")):
        try:
            rec = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        # A launched record reconciles against the session its
        # launch landed on (launch_session), not a later
        # resume's re-stamped binding — the poll's routing
        # (VENUE DEFECT 2, leg c). Pre-launch records carry no
        # launch_session; their binding is the record's
        # session, unchanged.
        eff_session = rec.get("launch_session") or rec.get("session")
        if rec.get("state") in ("running", "polling", "starting") and eff_session and eff_session in live_names:
            # A live sighting resets the absence clock, whatever
            # branch below then handles the record.
            lease.foundation.clear_absent_stamp(REPO, eff_session)
        if rec.get("state") in ("running", "polling", "starting") and eff_session and eff_session not in live_names:
            # Orphaning needs the absence confirmed across
            # observations: the live list comes back
            # partial under load, so a name missing from one list
            # is as often the list's flicker as the session's
            # death — one sweep's reading orphaned healthy,
            # evidence-carrying runs all evening. The lease
            # core's shared absence stamp carries the clock:
            # first absence stamps and spares the run; a later
            # sweep still absent past the window orphans.
            # Co-tenants share the session's stamp: once one
            # record's confirmation clears it, its siblings must
            # not read the cleared stamp as a first absence —
            # the pass remembers the confirmation itself.
            if eff_session not in confirmed_absent:
                since = lease.foundation.absent_since(REPO, eff_session)
                now_dt = datetime.now(timezone.utc)
                if since is None or (now_dt - since).total_seconds() < lease.foundation.ABSENT_CONFIRM_S:
                    lease.foundation.stamp_absent(REPO, eff_session, since or now_dt, now_dt)
                    continue
                confirmed_absent.add(eff_session)
                lease.foundation.clear_absent_stamp(REPO, eff_session)
            rec["state"] = "orphaned"
            rec["orphan_noted_at"] = now()
            save_record(rec)
            if emit_terminal_event(rec):
                save_record(rec)
            findings.append({"run_id": rec["run_id"], "job": rec["job"], "action": "marked orphaned; relaunch with --resume RUN_ID to continue from its remote run-id"})
        elif rec.get("state") == "running" and rec.get("remote_out") and not rec.get("launch_confirmed_at"):
            # Stale-running: the launcher died between stamping
            # "running" and confirming the launch (a killed
            # launcher — flap, signal — lands here even with the
            # launch path's timeout guards). "running" is a
            # minutes-long state for any live launcher, and an
            # actively reconciled run keeps last_evidence_at
            # fresh, so staleness on both clocks earns the
            # record one reader pass over its launch session —
            # the pass, not the clocks, decides (below). The remote_out gate is
            # the discriminator: a launched record always carries
            # it (stamped in the same save as "running"), while a
            # registration-style record without one is co-tenancy
            # evidence the sweep has never touched.
            try:
                started_age = (datetime.now(timezone.utc) - datetime.fromisoformat(rec["started_at"])).total_seconds()
                evidence_age = (datetime.now(timezone.utc) - datetime.fromisoformat(rec["last_evidence_at"])).total_seconds() if rec.get("last_evidence_at") else None
            except (KeyError, ValueError):
                started_age, evidence_age = 0, None
            if started_age > STALE_RUNNING_S and (evidence_age is None or evidence_age > STALE_RUNNING_S):
                # Time alone never writes the run off: one
                # reader pass over the launch session decides
                # (VENUE DEFECT 2, leg c — a launch that had
                # landed on a healthy session was written off
                # launch-lost because its confirmation window
                # outlived the client that waited on it). A
                # footprint rescues the record to polling for
                # collection; a readable total absence is the
                # proven no-launch and the write-off proceeds;
                # an unreadable pass is unknown and the record
                # stays collectable for a later pass.
                verdict = _launch_reading(rec)
                if verdict == "footprint":
                    rec["state"] = "polling"
                    rec["launch_confirmed_at"] = now()
                    rec["last_evidence_at"] = now()
                    save_record(rec)
                    findings.append({"run_id": rec["run_id"], "job": rec["job"], "action": "launch confirmed on a sweep reader pass over the launch session; record moved to polling for collection"})
                elif verdict == "absent":
                    mark_terminal(rec, "failed", launch_lost=True, error=f"record still 'running' {int(started_age // 60)} min after start with no launch confirmation and no fresher evidence, and a reader pass over the launch session read no job footprint: the launcher died mid-launch; relaunch with --resume {rec['run_id']} to continue from its remote run-id")
                    findings.append({"run_id": rec["run_id"], "job": rec["job"], "action": "marked failed (launch-lost): stale 'running' record whose launcher died mid-launch (reader pass read no footprint); relaunch with --resume RUN_ID"})
        elif rec.get("state") in ("claiming", "starting") and (eff_session in live_names or not eff_session) and _daemon_orphan(rec):
            # Daemon-orphaned: decidable NOW, by the driver
            # stamp, without the stale-starting branch's
            # two-hour wait — a dead daemon launches nothing,
            # and every hour the record reads as pre-launch it
            # holds its caller's claim evidence as in-flight
            # work (six daemonized fires whose
            # daemons died silently sat in "starting" until
            # their callers gave up on them). The resume is
            # the re-drive: it attaches or takes over under
            # the claims discipline and relaunches the id.
            mark_terminal(rec, "failed", launch_lost=True, error=f"record still '{rec['state']}' with its daemon driver (pid {rec.get('daemon_child_pid')}) dead and no launch begun: the daemonized launch died before the launch landed; relaunch with --resume {rec['run_id']} to retry")
            findings.append({"run_id": rec["run_id"], "job": rec["job"], "action": f"marked failed (launch-lost): daemon-orphaned '{rec['state']}' record whose daemon driver died pre-launch; relaunch with --resume RUN_ID"})
        elif rec.get("state") == "starting" and (eff_session in live_names or not eff_session):
            # Stale-"starting": the launcher died before its
            # launch landed (the upload-phase deaths on a wedged
            # session — six records sat in "starting"
            # for hours, reading as in-flight work and holding
            # their callers' claim evidence). Freshness is the
            # freshest of the record's stamps and its file mtime
            # (every pre-launch save — bundle seed, usage read —
            # rewrites the file), and the bound clears the worst
            # legitimate pre-launch hold. Co-tenancy is not at
            # risk here: registration-style records are planted
            # in "running", a state this branch never touches.
            stamps = []
            for key in ("last_evidence_at", "launch_at", "resumed_at", "started_at"):
                try:
                    if rec.get(key):
                        stamps.append(datetime.fromisoformat(rec[key]).timestamp())
                except ValueError:
                    pass
            try:
                stamps.append(f.stat().st_mtime)
            except OSError:
                pass
            age = datetime.now(timezone.utc).timestamp() - max(stamps) if stamps else 0
            # A live daemon driver defeats the time proxy: the
            # bound prices a wedged upload, but a daemon queued
            # behind the session launch lock is alive in this
            # state with no fresher stamp, healthy at any age
            # (pid_alive(None) is False, so an unstamped
            # foreground record is governed by time exactly as
            # before).
            if age > STALE_STARTING_S and not pid_alive(rec.get("daemon_child_pid")):
                mark_terminal(rec, "failed", launch_lost=True, error=f"record still 'starting' {int(age // 60)} min after its freshest stamp: the launcher died before the launch landed; relaunch with --resume {rec['run_id']} to retry")
                findings.append({"run_id": rec["run_id"], "job": rec["job"], "action": "marked failed (launch-lost): stale 'starting' record whose launcher died pre-launch; relaunch with --resume RUN_ID"})
    return findings, True


# The standing collector. A detached run collects only when
# someone polls it, and a consumer that waits on the record
# file instead wedges silently — the record reads "polling"
# forever over a finished run (formation-laneb-scoped:
# its gate completed session-side in a minute and
# the record sat uncollected for 36+ minutes until an
# unrelated boot reconcile noticed). The lease reap cycle is
# the runner's standing heartbeat, so this pass rides it (and
# the --collect-stale verb): stale detached records get the
# same poll the verb runs. Caps keep one pass bounded — a
# poll costs a reader exec plus any pull it lands.
COLLECT_PASS_MAX = 3
COLLECT_PASS_BUDGET_S = 240
COLLECTOR_CALLER = "collector-sweep"


def _evidence_epoch(rec: dict) -> float:
    stamp = rec.get("collector_at") or rec.get("last_evidence_at") or rec.get("started_at")
    try:
        return datetime.fromisoformat(str(stamp)).timestamp()
    except (TypeError, ValueError):
        return 0.0


def collect_stale_detached(budget_s: int = COLLECT_PASS_BUDGET_S, max_records: int = COLLECT_PASS_MAX) -> dict:
    """One bounded collection pass over stale detached records.

    Candidates: non-terminal, detached_launch, collector-stale
    at the standing 600 s bound — stalest first. Each is driven
    through poll_run under the collector-sweep attribution
    (stdout captured; the outcome is read back from the
    record: finalized = now terminal, attended = the collector
    stamp advanced). Per-record non-raising: one bad record
    never stops the pass, and a pass failure never breaks the
    reap duty that hosts it."""
    from .verbs import poll_run  # lazy: verbs imports this module

    summary: dict = {"checked": 0, "attended": [], "finalized": [], "errors": [], "capped": False}
    if not RUNS.exists():
        return summary
    candidates = []
    for f in sorted(RUNS.glob("*.json")):
        try:
            rec = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("detached_launch") is not True or rec.get("state") in TERMINAL_STATES:
            continue
        if collector_stale(rec):
            candidates.append(rec)
    candidates.sort(key=_evidence_epoch)
    summary["checked"] = len(candidates)
    started = time.monotonic()
    previous_caller = os.environ.get("COLAB_CALLER")
    os.environ["COLAB_CALLER"] = COLLECTOR_CALLER
    processed = 0
    try:
        for rec in candidates:
            if processed >= max_records or time.monotonic() - started > budget_s:
                summary["capped"] = True
                break
            processed += 1
            run_id = str(rec.get("run_id"))
            before = rec.get("collector_at")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    poll_run(run_id)
            except Exception as exc:  # noqa: BLE001 — isolation per record
                summary["errors"].append({"run_id": run_id, "error": type(exc).__name__})
                continue
            try:
                after = json.loads((RUNS / f"{run_id}.json").read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if after.get("state") in TERMINAL_STATES:
                summary["finalized"].append(run_id)
            elif after.get("collector_at") != before:
                summary["attended"].append(run_id)
    finally:
        if previous_caller is None:
            os.environ.pop("COLAB_CALLER", None)
        else:
            os.environ["COLAB_CALLER"] = previous_caller
    return summary
