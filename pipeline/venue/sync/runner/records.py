#!/usr/bin/env python3
"""Run records: persistence, terminal states, the outbox event.

A run's record (results/runs/<run_id>.json) is the runner's
state of record; this leaf owns writing it, reading it back,
and the exactly-one run-terminal event a terminal transition
appends to the UI outbox.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from .foundation import REPO, RUNS, VENUE, now, staged_write


def _prepare(rec: dict) -> None:
    # Shape uniformity (2026-11-12): last_evidence_at exists
    # on every record from its first save — initialized to
    # the record's birth, so a never-collected record's
    # evidence age reads as its whole life (the orphan
    # signal the restart-reconciliation sweep keys on)
    # instead of the field being absent and indistinguishable
    # from a reader's bug. Successful session reads are its
    # only later writers; a failed read never freshens it.
    if not rec.get("last_evidence_at") and rec.get("started_at"):
        rec["last_evidence_at"] = rec["started_at"]
    # Venue key (S5, plan §7 V1): stamped at write time, like
    # the lease records'; no reader defaults it (§10.3).
    rec.setdefault("venue", VENUE)


def save_record(rec: dict) -> None:
    _prepare(rec)
    RUNS.mkdir(parents=True, exist_ok=True)
    # Through the unified writer (S5, plan §4.15): the plain
    # in-place write this was is exactly the truncate-then-
    # denied class the writer's protocol makes impossible —
    # a denied save now leaves the standing record intact.
    staged_write(RUNS / f"{rec['run_id']}.json", json.dumps(rec, indent=2).encode())


# A fresh launch's id is minted from a second-resolution
# timestamp, so two launches of the same job inside one second
# mint the same id — and with unconditional saves, the second
# run silently absorbed the first's record and results dir
# (2026-11-14 specimen: parallel shards of one job launched in
# the same second; one record survived, the other shard's
# outputs were lost, no error at either launch). The first
# save therefore CLAIMS the id: an exclusive-create write that
# never overwrites an existing record file (live, terminal,
# or torn), suffixing -2, -3, … until a free id answers. The
# claim is the first save — no placeholder window — and the
# common case keeps the unsuffixed id byte-identical. The
# claim writes directly, not through the unified writer:
# exclusivity is the mechanism, a claim creates a new file
# (there is no standing record for a staged rename to
# protect), and a rename would silently overwrite the very
# occupant the claim exists to refuse.
CLAIM_ATTEMPTS = 100


def claim_first_save(rec: dict) -> str:
    """Write a fresh run's record for the first time, claiming
    its run_id atomically; returns the claimed id (rec updated
    to match). Raises RuntimeError when no suffix within
    CLAIM_ATTEMPTS is free — loud, never an overwrite."""
    _prepare(rec)
    RUNS.mkdir(parents=True, exist_ok=True)
    base = rec["run_id"]
    for n in range(1, CLAIM_ATTEMPTS + 1):
        candidate = base if n == 1 else f"{base}-{n}"
        rec["run_id"] = candidate
        try:
            fd = os.open(RUNS / f"{candidate}.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(rec, indent=2))
        return candidate
    rec["run_id"] = base
    raise RuntimeError(f"no free run id for {base} in {CLAIM_ATTEMPTS} attempts")


TERMINAL_STATES = ("complete", "failed", "orphaned")

# A non-terminal record whose collector has not touched it
# in this bound reads as unattended (collector_stale) —
# the display bound; the scheduler's restart sweep applies
# its own longer escalation bound to the same stamps.
COLLECTOR_STALE_S = 600


def stamp_collector(rec: dict, caller: "str | None" = None) -> None:
    """One collector touch: the launching poll loop, a --poll
    reconcile, a finalize — every process that works the
    record toward its terminal state stamps when it touched
    the record and, when it knows its name, who it is. A
    record frozen after its collector's death (the VM
    restart class) is then self-describing: who was
    collecting, and when they stopped."""
    rec["collector_at"] = now()
    if caller:
        rec["collector"] = caller


def collector_stale(rec: dict, at: "float | None" = None) -> bool:
    """Derived, never stored: a non-terminal record is
    collector-stale when its freshest collector stamp
    (collector_at, falling back through last_evidence_at
    to started_at for pre-cure records) is older than
    COLLECTOR_STALE_S. Staleness names ATTENDANCE only —
    the job's truth stays session-side, resolved by a poll."""
    if rec.get("state") in TERMINAL_STATES:
        return False
    stamp = rec.get("collector_at") or rec.get("last_evidence_at") or rec.get("started_at")
    if not stamp:
        return False
    try:
        epoch = datetime.fromisoformat(str(stamp)).timestamp()
    except ValueError:
        return False
    return (time.time() if at is None else at) - epoch > COLLECTOR_STALE_S


def load_run_record(run_id: str) -> dict | None:
    try:
        rec = json.loads((RUNS / f"{run_id}.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return rec if isinstance(rec, dict) else None


def outbox_path() -> Path:
    # The UI outbox lives in the runner var dir (the panel's own
    # var_dir() convention: $COLAB_RUNNER_VAR, else the repo's var).
    return Path(os.environ.get("COLAB_RUNNER_VAR", REPO / "var")) / "ui-outbox.jsonl"


def emit_terminal_event(rec: dict) -> bool:
    """Append the run's one run-terminal event to the UI outbox.

    The lease core already appends its own kinds there (the
    lease-extended chain the adoption census reads is the
    precedent); a run's terminal transition is the runner's kind.
    Guarded on the record: terminal_event_state stamps the state
    the event announced, so a second terminal observation of the
    same run (a --poll after the foreground poller finished, a
    sweep after a finalize) never double-announces — while a
    resumed run, whose resume clears the stamp, announces its new
    terminal state afresh. Best-effort: a failed append stamps
    nothing, so a later transition may retry it. Returns True
    when it appended."""
    if rec.get("terminal_event_state") == rec.get("state"):
        return False
    path = outbox_path()
    seq = 0
    try:
        lines = path.read_text().splitlines()
        for line in reversed(lines):
            if line.strip():
                try:
                    seq = int(json.loads(line).get("seq", 0))
                except (ValueError, json.JSONDecodeError):
                    seq = len(lines)
                break
    except OSError:
        seq = 0
    event = {
        "seq": seq + 1,
        "ts": now(),
        "kind": "run-terminal",
        "detail": {"run_id": rec["run_id"], "job": rec.get("job"), "caller": rec.get("caller"), "state": rec["state"], "session": rec.get("session")},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:
        return False
    rec["terminal_event_state"] = rec["state"]
    rec["terminal_event_at"] = event["ts"]
    return True


def mark_terminal(rec: dict, state: str, **fields) -> None:
    """Move a launched run to a terminal state: record update,
    save, and its exactly-one run-terminal outbox event."""
    rec.update(state=state, **fields)
    save_record(rec)
    if emit_terminal_event(rec):
        save_record(rec)
