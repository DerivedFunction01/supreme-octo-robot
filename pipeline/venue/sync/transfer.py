#!/usr/bin/env python3
"""Chunked file transfer over the colab CLI's file channel.

Measured constraints (live):
- `colab upload` lands files at the VM root unless the remote path is
  absolute — always use /content-absolute remote paths.
- Single-file uploads succeed at 50 MB and fail immediately at 75 MB
  (SSLEOFError from the runtime proxy, proxy-independent): the contents
  API has a size ceiling between those values. Transfers chunk at 32 MB
  and reassemble on the far side; integrity is by SHA-256 end to end.
- Tunnel throughput is ~1.6 MB/s each way.

Reliability: the P2 1 GB upload died at part 12 of 32 on a
contents-API drop and the whole transfer was lost. Parts are now
retried individually (PART_ATTEMPTS attempts, linear backoff) and both
directions resume: before moving a part, the far side's copy is
verified by per-part SHA-256 and skipped when it already matches, so
re-running a failed transfer moves only the missing or corrupt parts.
The end-to-end SHA-256 still gates the assembled file.

bin/colab-xfer is the verb over this library: it drives the two
functions with a progress callback and keeps a pollable transfer
record per move.
"""

# Portability exceptions (gate component directives):
# portability-exception: ~/.local/bin/colab — the removed per-user CLI shim location, named in the resolution note to forbid it
# portability-exception: f:\ — scanner artifact in the embedded remote-program payload text below (an `as f:` binding colon followed by a string-escape backslash), not a path
# portability-exception: d:\ — scanner artifact in the embedded remote-program payload text below (an `if d:` binding colon followed by a string-escape backslash), not a path

import hashlib
import importlib.util as _ilu
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CHUNK = 32 * 1024 * 1024
PART_ATTEMPTS = 3
PART_BACKOFF_S = 5
# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

REPO = _paths.REPO_RESOLVED

# The CLI funnel — resolution ($COLAB_BIN, else the uv tool venv,
# else PATH, else ~/.local/bin/colab), the NO_PROXY environment,
# and the guarded invocation — is sync/cli.py's, the one
# implementation every consumer loads (consolidation Lane B
# step 5; this module used to carry its own unguarded copies).
# The names stay bound on this module because its callers and
# tests address them here — and because this module's internals
# call the bare name, so a test's fake binds exactly here.
_cli_spec = _ilu.spec_from_file_location("cli", Path(__file__).resolve().parent / "cli.py")
cli = _ilu.module_from_spec(_cli_spec)
_cli_spec.loader.exec_module(cli)

colab = cli.colab
colab_bin = cli.colab_bin
colab_env = cli.colab_env
json_object_from_output = cli.json_object_from_output

# Launch-health journal (written by the runner's launch path,
# sync/lease/sessions/health.py owns the shape): the trailing window and
# failure cluster that mark a session degraded.
HEALTH_WINDOW_MINUTES = 30
HEALTH_FAILURE_CLUSTER = 2


def _session_degraded(session: str) -> bool:
    """Whether the launch-health journal marks this session
    degraded right now, under the lease health module's rule
    (most recent outcome in the trailing window a failure, or a
    failure cluster since the last success). The journal is
    evidence, not state: a missing or unreadable journal reads
    as not degraded. Mirrored here rather than imported — the
    transfer layer sits below the lease package."""
    import json as _json
    from datetime import datetime, timedelta, timezone

    try:
        lines = (REPO / "var" / "launch-health.jsonl").read_text().splitlines()
    except OSError:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=HEALTH_WINDOW_MINUTES)
    last_ok = None
    last_fail = None
    fails_since_ok = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = _json.loads(line)
            if entry.get("session") != session:
                continue
            at = datetime.fromisoformat(entry["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        if at < cutoff:
            continue
        if entry.get("ok"):
            last_ok = entry["ts"]
            fails_since_ok = 0
        else:
            last_fail = entry["ts"]
            fails_since_ok += 1
    return bool(
        (last_fail and (last_ok is None or last_fail > last_ok))
        or fails_since_ok >= HEALTH_FAILURE_CLUSTER
    )


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _exec_file(session: str, code: str, timeout: int = 600) -> subprocess.CompletedProcess:
    # Unique staging name per call: a fixed name made concurrent
    # transfers clobber each other's scripts (and made the fake
    # CLI serve the first script staged under that name for every
    # later call — the chunked-upload proof failure).
    f = REPO / "var" / f"transfer-exec-{os.getpid()}-{time.time_ns()}.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(code)
    return colab("exec", "-s", session, "--timeout", str(timeout), "-f", str(f), timeout=timeout + 120)


def _attempt(fn) -> tuple:
    """Run fn (returning a CompletedProcess) up to PART_ATTEMPTS times.

    A non-zero return code or a subprocess timeout counts as a failed
    attempt. Returns (process, attempts_used); process is None when
    every attempt timed out.
    """
    proc = None
    for i in range(1, PART_ATTEMPTS + 1):
        try:
            proc = fn()
        except subprocess.TimeoutExpired:
            proc = None
        if proc is not None and proc.returncode == 0:
            return proc, i
        if i < PART_ATTEMPTS and PART_BACKOFF_S:
            time.sleep(PART_BACKOFF_S * i)
    return proc, PART_ATTEMPTS


def _xfer_dir(digest: str, remote_name: str = "") -> str:
    """The per-transfer staging directory for one payload,
    derived from its whole-file SHA-256: .xfer-<digest[:12]>.
    Parts live under it, never flat beside the target — residue
    from a completed transfer must be unable to poison a
    consumer globbing the target's directory (xfer
    .part-000 chunks beside a bundle were swallowed by a job's
    part-* reassembly glob and doubled it). The derivation is
    content-keyed so both directions and any re-run agree on
    the directory, which keeps resume working.

    When the target carries a directory (a per-run target —
    the runner's Step 5 form), the staging directory sits
    inside that directory, not at the session root: a
    root-level content-keyed directory is one slot per
    payload for the whole session, and a packet family that
    stages the identical payload for several runs (the
    segfin base/packet/check jobs and their one tree tar)
    shared it — the first run to finish deleted the whole
    directory under its siblings' in-flight parts, and a
    sibling's reassemble could complete out of parts another
    transfer staged. Inside the target's own directory the
    staging is as per-run as the target itself; a bare
    target (the colab-xfer contract) keeps the root form."""
    parent = os.path.dirname(remote_name)
    return f"{parent}/.xfer-{digest[:12]}" if parent else f".xfer-{digest[:12]}"


def _cleanup_parts(session: str, target: str, staging_dir: str) -> None:
    """Remove a completed transfer's staging directory and any
    legacy flat parts for the same target. Best-effort: the
    transfer has already verified end to end when this runs,
    and a cleanup failure must not fail it — the residue it
    leaves is inert under the staging directory (a failed
    transfer keeps its parts: they are its resume state)."""
    try:
        _exec_file(session, (
            "# transfer:cleanup\n"
            "import glob, os, shutil\n"
            "BASE = '/content' if os.getcwd() == '/content' else os.getcwd()\n"
            f"TARGET = {json.dumps(target)}\n"
            f"DIR = {json.dumps(staging_dir)}\n"
            "shutil.rmtree(os.path.join(BASE, DIR), ignore_errors=True)\n"
            "for pat in (TARGET + '.part-*', TARGET + '.dl-*'):\n"
            "    for p in glob.glob(os.path.join(BASE, pat)):\n"
            "        os.unlink(p)\n"
            "print('{}')\n"
        ), timeout=240)
    except Exception:
        pass


def _remote_part_hashes(session: str, names: list, mkdir_dir: str = "") -> dict:
    """SHA-256 of each named part already in /content ({} on any failure).

    A failed probe is not fatal: the caller just uploads everything,
    and the end-to-end hash still gates the result. When
    mkdir_dir is given, the script creates that staging
    directory first — uploads into a directory that does not
    exist fail on the far side.
    """
    names_json = json.dumps(names)
    # The generated scripts address session files through BASE:
    # /content on a real VM (where the exec's cwd is /content),
    # the working dir under the fake CLI (whose session root is
    # the cwd) — the same dual-world seam the runner and shell_job
    # use. The upload/download commands keep their /content-
    # absolute remote paths; that is the CLI's own contract.
    # The probe is bounded tighter than the phase execs below
    # and its timeout is caught: it is a resume optimization,
    # and a stall here must read as "no resume information"
    # (upload everything), never as twelve silent minutes in
    # front of a transfer that has not started (xfer
    # verify-phase stalls on a saturated kernel).
    try:
        r = _exec_file(session, (
            "# transfer:part-hashes\n"
            "import hashlib, json, os\n"
            "BASE = '/content' if os.getcwd() == '/content' else os.getcwd()\n"
            f"MKDIR = {json.dumps(mkdir_dir)}\n"
            "if MKDIR:\n"
            "    os.makedirs(os.path.join(BASE, MKDIR), exist_ok=True)\n"
            f"NAMES = {names_json}\n"
            # A part name can carry a directory (a target
            # inside a per-run directory — the runner's
            # Step 5 form): its staging parent must exist
            # before the part uploads, or they fail on the
            # far side exactly as a top-level upload into a
            # missing directory does.
            "for name in NAMES:\n"
            "    d = os.path.dirname(name)\n"
            "    if d:\n"
            "        os.makedirs(os.path.join(BASE, d), exist_ok=True)\n"
            "out = {}\n"
            "for name in NAMES:\n"
            "    p = os.path.join(BASE, name)\n"
            "    if os.path.exists(p):\n"
            "        h = hashlib.sha256()\n"
            "        with open(p, 'rb') as f:\n"
            "            while c := f.read(1024*1024):\n"
            "                h.update(c)\n"
            "        out[name] = h.hexdigest()\n"
            "print(json.dumps(out))\n"
        ), timeout=240)
    except subprocess.TimeoutExpired:
        return {}
    try:
        return json_object_from_output(r.stdout)
    except (ValueError, json.JSONDecodeError):
        return {}


def chunked_upload(session: str, local: Path, remote_name: str, progress=None, staging_token: str | None = None) -> dict:
    """Upload local to /content/<remote_name> in 32 MB parts; verify hash.

    Parts already on the VM with a matching SHA-256 are skipped
    (resume); each remaining part is retried up to PART_ATTEMPTS times.
    When progress is given it is called with {"parts", "parts_done",
    "resumed_parts", "moved_parts"} once the part count is known and
    again after every part lands or is skipped — the transfer
    record bin/colab-xfer keeps is written from these calls.

    The local part files live under a per-transfer staging
    token (var/chunks/<token>/): parts named by remote_name
    alone were one flat slot per name, and two concurrent
    transfers of different files under one remote name
    overwrote each other's parts between split and upload —
    the bytes that landed were the other transfer's, caught
    only by the end-to-end hash as a failed run
    (the B3-S3b tree-tar specimen). The token defaults to a
    per-process unique value; a caller that knows its run
    passes it (the runner passes the run id). The remote
    staging dir is content-addressed by the file's hash
    within the target's directory (_xfer_dir): identical
    bytes headed for the same target share it safely, and
    two runs' copies of one payload — different targets —
    never meet there. Local parts are scratch (resume is
    remote-side) and are removed when the transfer closes.

    Part-0 retry (launch-path plan, Step 5): a pass that
    fails at part 0 with zero parts landed — the
    steampower-df-union-gate T161748Z specimen, 3 attempts,
    0 parts, nothing resumed — retries the whole transfer
    once inside this call. Nothing exists on the far side
    to poison, and the failure's class is a saturated
    channel at the transfer's first burst, which a fresh
    pass (probe included) re-tests honestly; the retry's
    result carries "whole_transfer_retry": True. A failure
    at any later part — or at part 0 with parts already
    landed — keeps the per-part resume exactly as it was:
    the pass's own result stands and a re-run moves only
    the missing parts.
    """
    result = _chunked_upload_pass(session, local, remote_name, progress=progress, staging_token=staging_token)
    if result.get("ok") or result.get("stage") != "upload part 0" or result.get("resumed_parts") or result.get("uploaded_parts"):
        return result
    retry = _chunked_upload_pass(session, local, remote_name, progress=progress, staging_token=staging_token)
    retry["whole_transfer_retry"] = True
    return retry


def _chunked_upload_pass(session: str, local: Path, remote_name: str, progress=None, staging_token: str | None = None) -> dict:
    """One pass of chunked_upload (which see): split, probe
    the far side's parts, move the missing ones, reassemble,
    verify end to end."""
    local = Path(local)
    digest = sha256_file(local)
    staging_dir = _xfer_dir(digest, remote_name)
    token = staging_token or f"{os.getpid()}-{time.time_ns()}"
    part_dir = REPO / "var" / "chunks" / token
    metas = []
    with open(local, "rb") as fh:
        i = 0
        while chunk := fh.read(CHUNK):
            part = part_dir / f"{remote_name}.part-{i:03d}"
            part.parent.mkdir(parents=True, exist_ok=True)
            part.write_bytes(chunk)
            metas.append({"name": f"{staging_dir}/{part.name}", "path": part, "sha256": sha256_bytes(chunk)})
            i += 1

    def emit(resumed: int, moved: int) -> None:
        if progress is not None:
            progress({"parts": len(metas), "parts_done": resumed + moved,
                      "resumed_parts": resumed, "moved_parts": moved})

    # The part-hash probe is resume detection only — an
    # optimization. On a session the launch journal already
    # reads degraded, the probe contends with the part uploads
    # for the same worst channel and its bounded stall is paid
    # serially before any byte moves (the file-cap
    # specimen: the verify leg timed out twice against
    # byte-identical parts). Skip it there; every part uploads
    # and the end-to-end hash still verifies.
    probe_skipped = _session_degraded(session)
    remote_hashes = {} if probe_skipped else _remote_part_hashes(session, [m["name"] for m in metas], mkdir_dir=staging_dir)
    resumed = uploaded = retried = 0
    emit(0, 0)
    for i, m in enumerate(metas):
        if remote_hashes.get(m["name"]) == m["sha256"]:
            resumed += 1
            emit(resumed, uploaded)
            continue
        r, used = _attempt(lambda m=m: colab("upload", "-s", session, str(m["path"]), f"/content/{m['name']}", timeout=3600))
        if r is None or r.returncode != 0:
            stderr = "" if r is None else (r.stdout + r.stderr)[-300:]
            shutil.rmtree(part_dir, ignore_errors=True)
            return {"ok": False, "stage": f"upload part {i}", "attempts": used,
                    "resumed_parts": resumed, "uploaded_parts": uploaded, "stderr": stderr}
        uploaded += 1
        if used > 1:
            retried += 1
        emit(resumed, uploaded)
    names = json.dumps([m["name"] for m in metas])
    # The verify phase (reassemble + end-to-end hash) rides the
    # same attempt discipline as the parts: it is idempotent,
    # and until it did, a stall here was one silent 720 s bound
    # ending in an uncaught timeout or a stage-less failure —
    # the caller could not tell a wedged verify from a slow
    # transfer.
    r, _used = _attempt(lambda: _exec_file(session, (
        "# transfer:reassemble\n"
        "import hashlib, json, os\n"
        "BASE = '/content' if os.getcwd() == '/content' else os.getcwd()\n"
        f"parts = {names}\n"
        # A target inside a directory (the per-run form)
        # needs its parent created before the write, like
        # the part staging above; a bare name's dirname is
        # empty and the makedirs is a no-op.
        f"os.makedirs(os.path.join(BASE, {json.dumps(os.path.dirname(remote_name))}), exist_ok=True)\n"
        f"out = open(os.path.join(BASE, '{remote_name}'), 'wb')\n"
        "h = hashlib.sha256()\n"
        "for name in parts:\n"
        "    with open(os.path.join(BASE, name), 'rb') as f:\n"
        "        while c := f.read(1024*1024):\n"
        "            out.write(c); h.update(c)\n"
        "out.close()\n"
        "print(json.dumps({'sha256': h.hexdigest()}))\n"
    )))
    got = None
    if r is not None:
        try:
            got = json_object_from_output(r.stdout)["sha256"]
        except (ValueError, json.JSONDecodeError, KeyError):
            pass
    if got != digest:
        shutil.rmtree(part_dir, ignore_errors=True)
        return {"ok": False, "stage": "verify (reassemble)", "sha256": digest, "remote_sha256": got,
                "parts": len(metas), "resumed_parts": resumed,
                "uploaded_parts": uploaded, "retried_parts": retried,
                "stderr": "" if r is None else (r.stderr or "")[-300:]}
    # Verified end to end: the parts have done their work.
    # Remove them (and any legacy flat residue for this target)
    # so the target's directory holds only the target.
    _cleanup_parts(session, remote_name, staging_dir)
    shutil.rmtree(part_dir, ignore_errors=True)
    return {"ok": True, "sha256": digest, "remote_sha256": got,
            "parts": len(metas), "resumed_parts": resumed,
            "uploaded_parts": uploaded, "retried_parts": retried,
            "probe_skipped": probe_skipped}


def chunked_download(session: str, remote_name: str, dest: Path, progress=None) -> dict:
    """Download /content/<remote_name> in 32 MB parts; verify hash locally.

    The remote split reports a SHA-256 per part and for the whole file.
    A local part copy whose hash already matches is skipped (resume);
    each remaining part is retried up to PART_ATTEMPTS times, and a
    downloaded part whose hash mismatches counts as a failed attempt.
    When progress is given it is called with {"parts", "parts_done",
    "resumed_parts", "moved_parts"} once the remote split reports and
    again after every part lands or is skipped.
    """
    # The split rides the attempt discipline too (idempotent:
    # it rewrites the same part files): a stall names its phase
    # instead of raising through the caller.
    r, _used = _attempt(lambda: _exec_file(session, (
        "# transfer:split\n"
        "import hashlib, json, os\n"
        "BASE = '/content' if os.getcwd() == '/content' else os.getcwd()\n"
        f"REMOTE = {json.dumps(remote_name)}\n"
        "path = os.path.join(BASE, REMOTE)\n"
        "size = os.path.getsize(path)\n"
        f"CH = {CHUNK}\n"
        "whole = hashlib.sha256()\n"
        "with open(path, 'rb') as f:\n"
        "    while c := f.read(1024*1024):\n"
        "        whole.update(c)\n"
        "digest = whole.hexdigest()\n"
        # The split's staging follows the remote file's
        # directory, the upload side's derivation (_xfer_dir):
        # a per-run remote (a run's out dir) stages its parts
        # inside that directory, never in the session-root
        # slot every run moving the same payload would share.
        "_parent = os.path.dirname(REMOTE)\n"
        "DIR = (_parent + '/.xfer-' + digest[:12]) if _parent else ('.xfer-' + digest[:12])\n"
        "os.makedirs(os.path.join(BASE, DIR), exist_ok=True)\n"
        "parts = []\n"
        "with open(path, 'rb') as f:\n"
        "    i = 0\n"
        "    while c := f.read(CH):\n"
        "        name = DIR + '/' + REMOTE + '.dl-' + format(i, '03d')\n"
        "        dest = os.path.join(BASE, name)\n"
        "        os.makedirs(os.path.dirname(dest), exist_ok=True)\n"
        "        open(dest, 'wb').write(c)\n"
        "        parts.append({'name': name, 'size': len(c), 'sha256': hashlib.sha256(c).hexdigest()})\n"
        "        i += 1\n"
        "print(json.dumps({'size': size, 'sha256': digest, 'dir': DIR, 'parts': parts}))\n"
    )))
    if r is None:
        return {"ok": False, "stage": "remote split", "stdout": "", "stderr": "remote split exec timed out on every attempt"}
    try:
        info = json_object_from_output(r.stdout)
        parts = info["parts"]
    except (ValueError, json.JSONDecodeError, KeyError, TypeError):
        return {"ok": False, "stage": "remote split", "stdout": r.stdout[-300:], "stderr": r.stderr[-300:]}
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    resumed = downloaded = retried = 0

    def emit() -> None:
        if progress is not None:
            progress({"parts": len(parts), "parts_done": resumed + downloaded,
                      "resumed_parts": resumed, "moved_parts": downloaded})

    emit()
    staging_prefix = (info.get("dir") or "") + "/"
    local_parts = []
    for meta in parts:
        name, want_sha = meta["name"], meta["sha256"]
        # The local part file keeps the part's source-relative
        # path (its remote path minus the split's staging
        # directory), not the bare part basename: a flat slot
        # per basename made two concurrent downloads of
        # different files whose parts share a basename — every
        # run's outputs carry the same names — stage onto the
        # same local files, the shape the upload side's local
        # staging was cured of by its per-transfer token. Keyed by the source path, a re-run of
        # the same download still finds its parts (resume),
        # and another source's parts never share the file. A
        # part name outside the staging directory (a split
        # staged by an older form) falls back to the basename,
        # the layout before this cure.
        rel = name[len(staging_prefix):] if staging_prefix and name.startswith(staging_prefix) else Path(name).name
        tmp = REPO / "var" / "chunks" / rel
        tmp.parent.mkdir(parents=True, exist_ok=True)
        if tmp.exists() and tmp.stat().st_size == meta["size"] and sha256_file(tmp) == want_sha:
            resumed += 1
            local_parts.append(tmp)
            emit()
            continue

        def fetch(tmp=tmp, name=name, want_sha=want_sha):
            d = colab("download", "-s", session, f"/content/{name}", str(tmp), timeout=3600)
            if d.returncode == 0 and not (tmp.exists() and sha256_file(tmp) == want_sha):
                # Channel reported success but the bytes are wrong:
                # count it as a failed attempt so it is retried.
                return subprocess.CompletedProcess(d.args, 1, d.stdout, d.stderr)
            return d

        d, used = _attempt(fetch)
        if d is None or d.returncode != 0:
            stderr = "" if d is None else (d.stdout + d.stderr)[-300:]
            return {"ok": False, "stage": f"download {name}", "attempts": used,
                    "resumed_parts": resumed, "downloaded_parts": downloaded, "stderr": stderr}
        downloaded += 1
        if used > 1:
            retried += 1
        local_parts.append(tmp)
        emit()
    h = hashlib.sha256()
    with open(dest, "wb") as out:
        for tmp in local_parts:
            data = tmp.read_bytes()
            out.write(data)
            h.update(data)
    ok = h.hexdigest() == info["sha256"]
    if ok:
        # Verified end to end: remove the split's staging
        # directory (and any legacy flat residue for this
        # target). A failed assembly keeps its remote parts —
        # they are the resume state for the next attempt.
        _cleanup_parts(session, remote_name, info.get("dir") or _xfer_dir(info["sha256"], remote_name))
    return {"ok": ok, "bytes": dest.stat().st_size,
            "sha256": h.hexdigest(), "remote_sha256": info["sha256"],
            "parts": len(parts), "resumed_parts": resumed,
            "downloaded_parts": downloaded, "retried_parts": retried}


if __name__ == "__main__":
    print("library module; import chunked_upload / chunked_download", file=sys.stderr)
    raise SystemExit(2)
