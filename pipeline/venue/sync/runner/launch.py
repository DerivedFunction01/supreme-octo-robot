#!/usr/bin/env python3
"""The launch path's front end: verified pre-launch uploads,
and the orphan notes an acquire refusal prints (E1, runner
half) so a refusal names the state that may have caused it.
"""

import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from .foundation import REPO, colab, json_object_from_output, lease, transfer

# Pre-launch uploads above this size move through the chunked
# transfer (which verifies the whole-file hash) instead of the
# plain upload: the single-file ceiling the fs tools enforce.
UPLOAD_CHUNK_THRESHOLD_BYTES = 50 * 1024 * 1024

# The plain upload's timeout, size-scaled (improvement
# commissioned 2026-11-12 from a fleet datum: in a dead
# channel window, three launches each burned the flat 600 s
# before failing — a dead channel should confess at the pace
# the file's size prices, not at the largest payload's
# budget). The scale assumes a live channel moves at least
# ~8 KB/s (below the worst degraded-but-working rate measured
# that night, ~12 KB/s), floored so a small file still gets a
# real attempt, capped so the largest plain files keep the
# budget they have always had. Only the confession speed
# changes: the attempt stays single, the verify probe still
# gates execution, and the failure still names its stage.
UPLOAD_TIMEOUT_FLOOR_S = 120
UPLOAD_TIMEOUT_CAP_S = 600
UPLOAD_ASSUMED_MIN_BPS = 8192


def _upload_timeout_s(size_bytes: int) -> int:
    # The floor is env-tunable for the reason the probe's
    # timeout is (COLAB_RUN_PROBE_TIMEOUT_S precedent): tests
    # shrink it to watch a dead channel confess quickly.
    floor = int(os.environ.get("COLAB_RUN_UPLOAD_FLOOR_S", str(UPLOAD_TIMEOUT_FLOOR_S)))
    scaled = size_bytes // UPLOAD_ASSUMED_MIN_BPS
    return max(floor, min(UPLOAD_TIMEOUT_CAP_S, scaled))


def upload_one(session: str, src: Path, dest_name: str, tag: str) -> str | None:
    """One pre-launch upload, verified before the job starts.
    A failed or short transfer is an error HERE — never a
    missing file discovered inside the job later (2026-11-08:
    a ~100 MB snapshot bundle's plain upload failed with its
    return code unchecked and the run proceeded without it).
    Large files move chunked (hash-verified by the transfer);
    smaller files move plain and are verified by remote size
    AND SHA-256 through a probe exec in the session's working
    directory, the reader's own model. Returns an error
    string, or None on a verified landing."""
    # Every outcome is journaled as launch-channel health
    # (sync/lease/sessions/health.py): adoption ranks sessions by it.
    # Every call is timeout-guarded: colab() re-raises
    # TimeoutExpired by design, and an unguarded timeout here
    # killed the launcher by exception and stranded the run's
    # record (2026-11-11: five consecutive consol launches died
    # at this probe) — a timeout is an upload failure with an
    # error string, never a dead launcher.
    if src.stat().st_size > UPLOAD_CHUNK_THRESHOLD_BYTES:
        up = transfer.chunked_upload(session, src, dest_name, staging_token=tag)
        lease.append_launch_outcome(REPO, session, "upload", bool(up["ok"]), dest_name)
        if not up["ok"]:
            return f"chunked upload failed: {json.dumps(up)[:300]}"
        return None
    try:
        r = colab("upload", "-s", session, str(src), f"/content/{dest_name}", timeout=_upload_timeout_s(src.stat().st_size))
    except subprocess.TimeoutExpired:
        lease.append_launch_outcome(REPO, session, "upload", False, f"{dest_name}: upload timed out")
        return f"upload timed out for {dest_name}"
    if r.returncode != 0:
        lease.append_launch_outcome(REPO, session, "upload", False, dest_name)
        return f"upload failed (rc {r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}"
    probe = REPO / "var" / f"upload-probe-{tag}.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    # The probe reports size and SHA-256. Size alone was the
    # verify until 2026-11-21: a foreign file of the same size
    # in the shared /content/<basename> slot passed it, and an
    # overwrite landing between probe and launch was invisible
    # either way — the B3-S3b mislandings (a wrap copy carrying
    # another lane's bytes, a runner-script copy likewise).
    # The hash makes a wrong-bytes landing a launch failure
    # here; the per-session launch lock in main() closes the
    # overwrite window itself.
    expected_sha = hashlib.sha256(src.read_bytes()).hexdigest()
    probe.write_text(
        "import hashlib, json, os\n"
        f"p = {dest_name!r}\n"
        "if os.path.exists(p):\n"
        "    h = hashlib.sha256()\n"
        "    with open(p, 'rb') as fh:\n"
        "        while c := fh.read(1024 * 1024):\n"
        "            h.update(c)\n"
        "    print(json.dumps({'size': os.path.getsize(p), 'sha256': h.hexdigest()}))\n"
        "else:\n"
        "    print(json.dumps({'size': None, 'sha256': None}))\n"
    )
    # The timeout is env-tunable for the reason the poll loop's
    # is: tests shrink it (COLAB_RUN_POLL_TIMEOUT_S precedent).
    probe_timeout = int(os.environ.get("COLAB_RUN_PROBE_TIMEOUT_S", "300"))
    # The probe rides a bounded attempt discipline, like the
    # chunked transfer's parts: the exec channel stalls in
    # episodes of minutes (2026-11-17: probe-fail rates of
    # 9/60 and 10/79 on two sessions in one evening, successes
    # interleaved seconds apart), and a one-shot probe converted
    # each episode into a dead launch — including a solo launch
    # on a quiet session, where nothing was contending. A stall
    # signature (timeout, unreadable output) retries with
    # backoff; a size mismatch is information, not weather, and
    # returns at once. Both bounds are env-tunable so tests can
    # shrink them (the probe-timeout precedent above).
    probe_attempts = int(os.environ.get("COLAB_RUN_PROBE_ATTEMPTS", "3"))
    probe_backoff = float(os.environ.get("COLAB_RUN_PROBE_BACKOFF_S", "10"))
    stall_error = f"upload verify timed out for {dest_name}"
    stall_detail = f"{dest_name}: verify probe timed out"
    for attempt in range(1, max(1, probe_attempts) + 1):
        if attempt > 1 and probe_backoff:
            time.sleep(probe_backoff * (attempt - 1))
        try:
            pr = colab("exec", "-s", session, "--timeout", "120", "-f", str(probe), timeout=probe_timeout)
        except subprocess.TimeoutExpired:
            stall_error = f"upload verify timed out for {dest_name}"
            stall_detail = f"{dest_name}: verify probe timed out"
            continue
        try:
            landed = json_object_from_output(pr.stdout)
            size = landed["size"]
            landed_sha = landed["sha256"]
        except (ValueError, KeyError):
            stall_error = f"upload verify unreadable for {dest_name}: {pr.stdout.strip()[-200:]}"
            stall_detail = dest_name
            continue
        if size != src.stat().st_size:
            lease.append_launch_outcome(REPO, session, "probe", False, dest_name)
            return f"upload verify: {dest_name} landed at {size} bytes, expected {src.stat().st_size}"
        if landed_sha != expected_sha:
            lease.append_launch_outcome(REPO, session, "probe", False, dest_name)
            return f"upload verify: {dest_name} landed with sha256 {landed_sha}, expected {expected_sha} — the slot holds foreign bytes"
        lease.append_launch_outcome(REPO, session, "probe", True, dest_name)
        return None
    lease.append_launch_outcome(REPO, session, "probe", False, stall_detail)
    return stall_error


@contextlib.contextmanager
def session_launch_lock(session: str):
    """Serialize the upload→launch window per session.

    Manifest uploads land at /content/<basename> — one shared
    slot per session, kept because payloads name their uploads
    by contract (/content/gate.sh, /content/repos.json). Two
    launches uploading concurrently to one session therefore
    overwrote each other's same-named uploads between upload
    and launch, and a run executed a foreign payload (the
    class cured for the runner-script slot alone in
    2026-11-08; the B3-S3b re-price run hit it three times
    through manifest slots in 2026-11-21). Holding this lock
    from the first upload until the launch is confirmed makes
    the window atomic per session: a second launcher waits,
    then uploads over a job that has already started and read
    its payload. Running jobs are never locked. The lock is
    an flock on var/launch-<session>.lock — a launcher that
    dies inside the window releases it with its process, so a
    stranded lock cannot outlive its holder. Residual, named:
    a file a running job RE-READS mid-run under a contract
    name can still be overwritten by a later launch's
    same-named upload; closing that face needs per-run remote
    dirs, which breaks the args contract — out of scope here.
    """
    path = REPO / "var" / f"launch-{session}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def orphan_notes(shape_id: str, shape: dict) -> list[str]:
    """E1, runner half — failure path only: after an acquire
    refusal, name any live-but-unrecorded sessions at the
    requested shape and print the verb that restores them, the
    refusal-prints-the-alternative pattern. Costs one live-list
    read, so it never runs on a hot path; never fatal — a nicety
    must not mask the refusal it annotates."""
    try:
        live = lease.live_sessions(colab, REPO)
        if not live:
            return []
        recorded = {r.get("session") for r in lease.all_records(REPO)}
        want_class = "high_ram" if (shape or {}).get("high_mem") else "standard"
        notes = []
        for entry in live:
            name = entry["session"]
            if name in recorded or entry.get("shape_class") not in (None, want_class):
                continue
            notes.append(f"colab-run: note: session {name} is live but has no lease record (orphaned) — restore it with: bin/colab-lease adopt {name}")
        return notes
    except Exception:  # noqa: BLE001
        return []
