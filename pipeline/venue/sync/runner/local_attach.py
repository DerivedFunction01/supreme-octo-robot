"""The local entry's attach path: the container-state
readers a --poll/--wait serves from, the record resolution
an attach target names, and the attach route itself.

bin/local-run loads this leaf by path (its _load_runner_leaf
form) and binds the seams at call time from its own module
globals — the repo root, the venue module, the runner's
record machinery, the entry's fail verb — so the leaf
carries no import of the entry, and a test's monkeypatch
of an entry global is the binding the leaf calls. The
bodies are the entry's own, moved along this seam:
dispatch stays in the entry; everything that only reads a
run's state and serves an attach verdict lives here.
"""

import json
import time
from pathlib import Path

# Control-read warmup discipline (the read-side sibling of
# the launch discipline): a --poll fires right after
# ensure_transport, whose success is the transport's port
# answering — not SSH carrying over the tunnel, which can
# lag the port by longer than one read (the launch steps'
# recorded warmup). A single read in that window comes back
# "unknown" and the call would serve venue_unreachable over
# a healthy venue — the specimen was a hand-diagnosed
# kex-reset window during the strip staging, read as a
# venue failure. The poll therefore retries an "unknown"
# reading inside the call, on a bounded backoff; a resolved
# reading (exit / running / absent) is served at once and
# never re-read, and an "unknown" that survives every
# attempt is served as before — a lost read is still never
# a verdict.
READ_BACKOFF_S = (5, 15)
POLL_S = 5


def read_state(rec: dict, target: dict, seams: dict) -> dict:
    """The poll's container reading, through the warmup
    retry: the first non-"unknown" reading, or the last
    "unknown" when every attempt reads lost."""
    venue = seams["venue"]
    reading = venue.read_run_state(seams["repo"], rec, target=target)
    for backoff in READ_BACKOFF_S:
        if reading["reading"] != "unknown":
            break
        time.sleep(backoff)
        reading = venue.read_run_state(seams["repo"], rec, target=target)
    return reading


def confirmed_exit(rec: dict, target: dict, reading: dict, seams: dict) -> dict | None:
    """The confirmation read behind every terminal verdict
    this path serves: an "exit" reading is believed only
    when a second, independent read of the run's own exit
    file agrees on the code. A single anomalous read —
    whatever its source — cannot carry a verdict alone;
    a contested read is served as no verdict (the poll
    reports running, the reader pass leaves the face), and
    the next poll cycle reads the file again. Returns the
    reading when confirmed, else None."""
    confirm = seams["venue"].read_run_state(seams["repo"], rec, target=target)
    if confirm.get("reading") == "exit" and confirm.get("exit_code") == reading["exit_code"]:
        return reading
    return None


def poll(rec: dict, target: dict, seams: dict) -> dict:
    """One poll of the run's container state, through the
    lease core's tri-state reader (local_venue.read_run_state):
    a confirmed exit file finalizes the record through the
    runner's shared local finalize — terminal state from
    the code, completion time from the exit file's own
    mtime; no exit file yet is "running"; an unreadable
    container is "running" with the unreachable flag — a
    lost read is never a verdict, and neither is a single
    unconfirmed one."""
    reading = read_state(rec, target, seams)
    if reading["reading"] == "exit":
        if confirmed_exit(rec, target, reading, seams) is None:
            return {"state": "running", "exit_unconfirmed": True}
        state = seams["finalize_local_record"](rec, reading)
        return {"state": state, "exit_code": reading["exit_code"]}
    if reading["reading"] == "unknown":
        return {"state": "running", "venue_unreachable": True}
    return {"state": "running"}


def rederive(rec: dict, target: dict, seams: dict) -> dict | None:
    """The reader pass over a terminal record face: the
    container's exit file outranks the record, so a face it
    contradicts — an orphan flip over a finished run (the
    decxc shape: face "orphaned", run dir holding exit 0),
    a launch-time failure the detached run outlived — is
    re-derived from the container through the shared
    finalize. A face the exit file confirms, and any
    non-exit reading, stands as written. Returns the
    derived outcome, or None when the face stands."""
    reading = seams["venue"].read_run_state(seams["repo"], rec, target=target)
    if reading["reading"] != "exit":
        return None
    if confirmed_exit(rec, target, reading, seams) is None:
        return None
    code = reading["exit_code"]
    state = "complete" if code == 0 else "failed"
    if rec.get("state") == state and rec.get("exit_code") == code:
        return None
    seams["finalize_local_record"](rec, reading)
    return {"state": state, "exit_code": code, "rederived": True}


def wait(rec: dict, target: dict, max_s: int, timeout_s: int, seams: dict) -> int:
    deadline = time.monotonic() + min(max_s, timeout_s)
    while True:
        out = poll(rec, target, seams)
        if out["state"] != "running":
            print(json.dumps({"run_id": rec["run_id"], **out}, indent=2))
            return 0 if out["state"] == "complete" else 1
        if time.monotonic() > deadline:
            print(json.dumps({"run_id": rec["run_id"], "state": "running", "note": "wait bound reached; the run continues detached"}, indent=2))
            return 3
        time.sleep(POLL_S)


def record_target(rec: dict, seams: dict) -> dict | None:
    """The SSH target a run record belongs to: the target the
    record itself carries, else its shape's binding, else the
    venue's only target. A carried id that no longer resolves
    — a record written before its target was renamed — falls
    through to the same legs rather than ending the chain:
    the record's shape binding names the machine it ran on."""
    venue = seams["venue"]
    repo = seams["repo"]
    tid = rec.get("target")
    if isinstance(tid, str) and tid:
        target = venue.venue_target(repo, tid)
        if target is not None:
            return target
    _shape, _tid, target = venue.shape_target(repo, rec.get("shape") or "")
    return target or venue.venue_target(repo)


def newest_record_for_job(job_name: str, seams: dict) -> dict | None:
    """The newest local run record for a job name — the
    attach target when a --poll/--wait names the job rather
    than a run id. Run ids are <job>-<UTC timestamp>, so
    the job's records are the <job>-*.json files; the
    newest is the greatest started_at among them."""
    best = None
    try:
        files = sorted(seams["runs"].glob(f"{job_name}-*.json"))
    except OSError:
        return None
    for f in files:
        rec = seams["load_run_record"](f.stem)
        if rec is None or rec.get("job") != job_name or rec.get("venue") != "local":
            continue
        if best is None or str(rec.get("started_at") or "") >= str(best.get("started_at") or ""):
            best = rec
    return best


def attach(flags: dict, target_token, seams: dict) -> int:
    """The --poll/--wait route: resolve the attach target's
    record and serve its verdict. Attach, never dispatch:
    an invocation carrying an attach flag resolves to an
    existing run record or fails here — it can never fall
    through to the entry's job path, whose bare job name is
    the only dispatch spelling. (The defect this closes:
    `local-run <job> --wait` read as a dispatch and re-fired
    the job — a second execution of work believed to be a
    poll.)"""
    fail = seams["fail"]
    venue = seams["venue"]
    mode = "--wait" if flags["wait"] else "--poll"
    rec = seams["load_run_record"](target_token) if target_token else None
    if rec is None and target_token:
        rec = seams["newest_record_for_job"](target_token)
    if rec is None:
        return fail("--poll/--wait attach to an existing run: name a run id, or a job name that has at least one run")
    if rec.get("venue") != "local":
        return fail(f"run {rec['run_id']} is not a local-venue run")
    if rec.get("state") in seams["terminal_states"]:
        # A terminal face is accepted only after the
        # reader pass: the container's exit file outranks
        # the record (Step 2's poll half), so a face it
        # contradicts is re-derived before it is served.
        target = seams["record_target"](rec)
        if target is not None:
            venue.ensure_transport(target)
            derived = seams["rederive"](rec, target)
            if derived is not None:
                print(json.dumps({"run_id": rec["run_id"], **derived}, indent=2))
                return 0 if derived["state"] == "complete" else 1
        print(json.dumps({"run_id": rec["run_id"], "state": rec["state"]}, indent=2))
        return 0 if rec["state"] == "complete" else 1
    target = seams["record_target"](rec)
    if target is None:
        return fail("no local venue target resolves for this run (config/lease.json venue_targets.local)")
    venue.ensure_transport(target)
    if mode == "--poll":
        out = seams["poll"](rec, target)
        print(json.dumps({"run_id": rec["run_id"], **out}, indent=2))
        # The twins' shared still-running verdict (BT5):
        # 3 while the run is still running, as colab-run's
        # poll has always read; a poll that settles the run
        # keeps this tool's standing 0.
        return 3 if out["state"] == "running" else 0
    max_s = 3600
    if flags.get("max") is not None:
        try:
            max_s = int(flags["max"])
        except ValueError:
            return fail("--max must be an integer number of seconds")
    return seams["wait"](rec, target, max_s, int(rec.get("timeout_s") or 18000))
