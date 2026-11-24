#!/usr/bin/env python3
"""Single-flight claims: one run id, one execution.

The twin-execution root (diagnosed 2026-11-21 from the Steam
battery record): a daemonized fire's claim landed AFTER the
parent's bounded wait had already declared it dead, and a lane
resuming the "dead" id relaunched it — two executions sharing
one run id and every piece of fixed per-mode session state the
payload keyed on it. The cure removes both faces:

- The daemonize PARENT claims the record itself, before it
  spawns the child, in a dedicated "claiming" state carrying a
  claim deadline. The record is pollable from the instant the
  parent prints the id — there is no window in which a launched
  run has no record, and no "unconfirmed" verdict to misread
  as dead. The child ADOPTS its pre-claimed record instead of
  claiming.
- A resume keys on state. A record whose execution may still
  be alive — a claiming record whose loss is not decidable, or
  any non-terminal record whose launch was confirmed — is
  ATTACHED (the resume reports the live state and exits),
  never relaunched. A takeover is permitted only when the
  claim is decidable as lost: the claim deadline has passed
  AND the claimed child pid is provably dead. The takeover
  stamps itself on the record, so the history shows both
  claims.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

from .foundation import REPO, RUNS, epoch, now
from .records import claim_first_save, load_run_record, save_record

CLAIM_DEADLINE_S = 180

# The manifest read (2026-11-24): a job manifest is written
# by tooling outside the runner, through channels whose
# landing a reader can race — a staged write's rename, a
# shell write still flushing under the flap — so the file
# observed at load can read empty or torn. The daemon child
# died on exactly that with a raw JSONDecodeError at the
# load and its record read launch-lost; several gate
# manifests were later found standing at 0 bytes, their
# creating writes lost before the fire. The read therefore
# retries on the sessions form (bounded attempts, a backoff
# ladder) and exhaustion raises ManifestUnreadable naming
# the path and the last face — honest and decidable, never
# a bare traceback. A durably empty manifest still refuses:
# no reader can resurrect content that never landed — but
# it refuses NAMED, at the daemonize parent before any
# claim is written (spawn_daemon validates through this
# same load) or at the child before any session work.
MANIFEST_READ_ATTEMPTS = 3
MANIFEST_READ_BACKOFF_S = (2, 5)


class ManifestUnreadable(Exception):
    """The job manifest could not be read within the bounded
    retries. `missing` is True when the file never appeared
    (the fire's usage refusal), False when it stood but
    stayed unreadable, empty, or unparseable."""

    def __init__(self, path, face, missing):
        super().__init__(f"job manifest {path}: {face} (after {MANIFEST_READ_ATTEMPTS} read attempts)")
        self.path = path
        self.face = face
        self.missing = missing


def load_manifest(manifest_path):
    """Read and parse the job manifest at manifest_path,
    retrying empty or torn reads on the bounded ladder;
    returns the manifest dict. Raises ManifestUnreadable
    on exhaustion."""
    face = "missing"
    missing = True
    for attempt in range(MANIFEST_READ_ATTEMPTS):
        if attempt:
            time.sleep(MANIFEST_READ_BACKOFF_S[min(attempt - 1, len(MANIFEST_READ_BACKOFF_S) - 1)])
        try:
            text = manifest_path.read_text()
        except OSError as exc:
            face = f"unreadable ({type(exc).__name__}: {exc})"[:160]
            missing = isinstance(exc, FileNotFoundError)
            continue
        if not text.strip():
            face, missing = "empty", False
            continue
        try:
            job = json.loads(text)
        except ValueError as exc:
            face, missing = f"unparseable ({exc})"[:160], False
            continue
        if not isinstance(job, dict):
            face, missing = f"not a JSON object ({type(job).__name__})", False
            continue
        return job
    raise ManifestUnreadable(manifest_path, face, missing)


def option_like_refusal(job_name, resume) -> "str | None":
    """The refusal message for an option-like job name or
    resume id, or None when both names are clean. A token
    beginning with "-" in a name position is a flag consumed
    as a value by a misparsed invocation — `--resume
    --detach` claimed a run record named --detach, and a
    --session record stood beside it (2026-11-23, both
    quarantined by hand after days in results/runs/) — so
    the refusal fires at parse, before any record is
    written: no launch may claim an id that parses as an
    option, at creation or at resume."""
    if isinstance(job_name, str) and job_name.startswith("-"):
        return f"refusing option-like job name {job_name!r}: a flag was consumed as the job name"
    if isinstance(resume, str) and resume.startswith("-"):
        return f"refusing option-like run id {resume!r} for --resume: a flag was consumed as the run id"
    return None


def pid_alive(pid) -> bool:
    """True when pid names a live process. A pid we cannot
    signal for permission still exists; a missing or malformed
    pid is not evidence of life."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def pre_claim(job_name: str, run_id: str, shape_id, caller) -> dict:
    """The daemonize parent's first save: claim the minted id
    in the claiming state and return the record as claimed
    (its run_id carries any collision suffix). Raises on a
    failed claim — the parent then spawns nothing."""
    born = now()
    deadline = datetime.now(timezone.utc) + timedelta(seconds=CLAIM_DEADLINE_S)
    rec = {
        "run_id": run_id,
        "job": job_name,
        "shape": shape_id,
        "state": "claiming",
        "started_at": born,
        "resumed": False,
        "claim_by": "daemonize-parent",
        "claim_deadline": deadline.isoformat(),
    }
    if caller:
        rec["caller"] = caller
    claim_first_save(rec)
    return rec


def claim_lost(rec: dict) -> bool:
    """A claiming record is decidable as lost only when its
    deadline has passed AND its child pid is provably dead.
    Either fact alone leaves the claim undecided — a slow
    claim is not a dead one."""
    if rec.get("state") != "claiming":
        return False
    deadline = epoch(rec.get("claim_deadline"))
    if deadline is None or time.time() <= deadline:
        return False
    return not pid_alive(rec.get("daemon_child_pid"))


def attach_verdict(rec: dict):
    """None when a resume may proceed (terminal record, a
    decidable-lost claim, or a non-terminal record whose launch
    was never confirmed — the re-drive case). Otherwise a dict
    describing the live execution the resume attaches to."""
    state = rec.get("state")
    if state == "claiming":
        if claim_lost(rec):
            return None
        return {"attached": True, "state": state, "reason": "claim-outstanding"}
    if state in ("starting", "running", "polling") and rec.get("launch_confirmed_at"):
        return {"attached": True, "state": state, "reason": "launch-confirmed", "collect_via": "--poll"}
    return None


def spawn_daemon(job_name: str, args: list, manifest_path) -> tuple[str, str]:
    """The daemonize parent's act: pre-claim the minted id,
    spawn the child in its own session with stdio on the run's
    daemon log, stamp the child's pid onto the claim, and
    return (claimed_id, log_path). A failed pre-claim raises —
    the parent then spawns nothing, so no execution ever
    exists without its record already on disk. The manifest
    is validated through load_manifest BEFORE the claim: a
    manifest that cannot be read dooms the child at its own
    load, so refusing here — named, with no record written —
    is the honest fire-time form of that death."""
    load_manifest(manifest_path)
    minted = f"{job_name}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    rec = pre_claim(job_name, minted, None, None)
    claimed = rec["run_id"]
    log_path = RUNS.parent / f"{claimed}.daemon.log"
    child_env = dict(os.environ)
    child_env["COLAB_RUN_ID"] = claimed
    child_env["COLAB_RUN_DAEMON_CHILD"] = "1"
    child_args = [a for a in args if a != "--daemonize"]
    with open(log_path, "w") as log_fh:
        proc = subprocess.Popen(
            [sys.executable, str(REPO / "bin" / "colab-run"), *child_args],
            stdout=log_fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True, cwd=str(REPO), env=child_env)
    rec["daemon_child_pid"] = proc.pid
    save_record(rec)
    return claimed, str(log_path)


def adopt(run_id: str, shape_id):
    """A daemonized child adopts its parent's pre-claim:
    returns the record moved to "starting", or None when no
    pre-claim stands (the caller falls back to claiming for
    itself, exactly as a self-minted launch does)."""
    prior = load_run_record(run_id)
    if prior is None or prior.get("state") != "claiming" or prior.get("claim_by") != "daemonize-parent":
        return None
    prior.update(state="starting", claim_adopted_at=now())
    prior.setdefault("shape", shape_id)
    return prior


def stamp_takeover(rec: dict) -> None:
    """Mark a resume's takeover of a decidable-lost claim, so
    the record carries both claims' facts. The driver stamp
    moves to the taking-over process: daemon_child_pid names
    the run's current driver wherever a reader (the sweep's
    daemon-orphan test) asks whether that driver still lives,
    and a dead predecessor's pid would read as a dead driver
    for a run a live process is now driving."""
    rec.update(claim_takeover_at=now(), claim_takeover_from=rec.get("daemon_child_pid"))
    rec["daemon_child_pid"] = os.getpid()
