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
import re
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


_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def transport_error(job) -> "str | None":
    """A loud-refusal verdict for the manifest's transport
    declaration (branch transport plan, 2026-11-23): the
    manifest declares the tree's form and the runner holds
    the preference — a committed, pushed tree names
    transport {kind: branch, repo, branch, sha}; an
    uncommitted tree names no transport and takes the
    snapshot-bundle path. Branch is the only declared kind:
    kind branch requires a repos-registry key, a branch
    name, and a full expected SHA, and a missing or
    malformed field refuses here, at load, naming the
    field — never mid-launch. Returns an error string, or
    None when the declaration is the contract's (or absent)."""
    declared = job.get("transport")
    if declared is None:
        return None
    if not isinstance(declared, dict):
        return f"manifest transport must be an object, got {type(declared).__name__}"
    kind = declared.get("kind")
    if kind is None:
        return "manifest transport is missing its kind field"
    if kind != "branch":
        return f"manifest transport kind {kind!r} is not a declared transport (only 'branch' is)"
    for field in ("repo", "branch", "sha"):
        value = declared.get(field)
        if value is None:
            return f"manifest transport (kind branch) is missing its {field} field"
        if not isinstance(value, str) or not value:
            return f"manifest transport {field} must be a non-empty string, got {value!r}"
    if not _FULL_SHA.match(declared["sha"]):
        return f"manifest transport sha must be a full 40-hex commit SHA, got {declared['sha']!r}"
    return None


def parse_transport(job) -> "dict | None":
    """The manifest's validated branch-transport declaration
    as a plain dict, or None when the job names no transport
    (the bundle path). Call only after transport_error has
    cleared the manifest."""
    declared = job.get("transport")
    if not isinstance(declared, dict) or declared.get("kind") != "branch":
        return None
    return {"kind": "branch", "repo": declared["repo"], "branch": declared["branch"], "sha": declared["sha"]}


def prepare_branch(session: str, transport: dict, clone_url: str, dest: str, run_id: str) -> "tuple[str | None, dict]":
    """Drive the session's base clone to the declared branch
    tip before launch (branch transport plan, Step 2): the
    snapshot build and the code-payload upload are skipped —
    the session fetches the branch from origin through the
    base-clone substrate (sync/base_clone.sh, extended to the
    named branch), which refuses a fetched tip that differs
    from the announced SHA; the echoed HEAD is asserted
    against the announcement here as well. A mismatch or an
    unreachable origin is an error HERE — the branch path
    never substitutes the bundle mid-launch; the fallback is
    the manifest's declaration (no transport named), made
    before the fire. Returns (error, info): on success error
    is None and info carries the dest and the asserted head.
    The fetch moves on the session's own channel, which
    reports no byte count, so no fetch size is claimed."""
    err = upload_one(session, REPO / "sync" / "base_clone.sh", "base_clone.sh", run_id)
    if err is not None:
        return f"branch transport: base_clone.sh upload: {err}", {}
    driver = REPO / "var" / f"branch-{run_id}.py"
    driver.parent.mkdir(parents=True, exist_ok=True)
    driver.write_text(
        "import subprocess\n"
        f"r = subprocess.run(['bash','base_clone.sh',{clone_url!r},{'/content/' + dest!r},{transport['branch']!r},{transport['sha']!r}], capture_output=True, text=True)\n"
        "print(r.stdout); print(r.stderr[-500:])\n"
    )
    try:
        r = colab("exec", "-s", session, "--timeout", "1800", "-f", str(driver), timeout=1900)
        out = r.stdout or ""
    except subprocess.TimeoutExpired:
        out = ""
    head = None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) > 3 and parts[:3] == ["base", "clone", "at"]:
            head = parts[3]
    if head is None:
        lease.append_launch_outcome(REPO, session, "branch", False, transport["branch"])
        return f"branch transport: fetch of {transport['branch']} ({transport['repo']}) did not land: {out.strip()[-300:]}", {}
    if head != transport["sha"]:
        lease.append_launch_outcome(REPO, session, "branch", False, transport["branch"])
        return f"branch transport: base clone HEAD {head} != announced sha {transport['sha']} for {transport['branch']} ({transport['repo']})", {}
    lease.append_launch_outcome(REPO, session, "branch", True, transport["branch"])
    return None, {"dest": dest, "head": head}


def stamp_transport(rec, job) -> "dict | None":
    """Stamp the record's transport at claim (branch
    transport plan, 2026-11-23): the manifest's declared
    branch form, or the bundle path a job takes by naming
    no transport, with the byte count the runner moves for
    it accumulated as the launch window advances. Returns
    the parsed branch declaration (or None) for the
    caller's own branch work. A resume re-stamps from its
    current manifest: the stamp describes this attempt's
    transport."""
    transport = parse_transport(job)
    if transport is not None:
        rec["transport"] = {**transport, "bytes_moved": 0, "fetch_bytes": None}
    else:
        rec["transport"] = {"kind": "bundle", "bytes_moved": 0}
    return transport


def resolve_branch_ctx(transport, seed_ctx) -> "tuple[str | None, dict | None]":
    """Resolve a branch declaration against the local repos
    registry before any session is held, so an unknown key
    fails the run holding nothing — the seed path's
    discipline. A run declaring both a bundle seed and
    branch transport names two transports for one tree and
    refuses here. Returns (error, ctx): ctx carries the
    registry entry's clone_url and dest for prepare_branch.
    (repo_registry is imported at call time: this module's
    load surface is the launch front end's original names,
    which the unit tests' stub foundations carry.)"""
    if transport is None:
        return None, None
    if seed_ctx is not None:
        return "branch transport: the run declares both a bundle seed (--seed) and branch transport; name one transport", None
    from .foundation import repo_registry

    try:
        registry = repo_registry.load_local_registry(REPO)
        _repo_id, entry = repo_registry.get_entry(registry, transport["repo"])
    except ValueError as exc:
        return f"branch transport: {exc}", None
    return None, {"clone_url": entry["clone_url"], "dest": entry["dest"]}


def transport_setup(rec, job, seed_ctx) -> "tuple[dict | None, str | None, dict | None]":
    """The claim-side transport sequence, in one call after
    the seed block: stamp the record's transport, fold a
    seed's bytes into the stamp, and resolve a branch
    declaration against the registry. Returns (transport,
    error, branch_ctx) — on error the caller fails the run
    with it; branch_ctx is prepare_branch's material."""
    transport = stamp_transport(rec, job)
    if seed_ctx is not None:
        rec["transport"]["bytes_moved"] = seed_ctx["manifest"]["bytes"]
    err, branch_ctx = resolve_branch_ctx(transport, seed_ctx)
    return transport, err, branch_ctx


def drive_branch_window(session, rec, transport, branch_ctx, run_id) -> "str | None":
    """The launch-window branch drive: prepare_branch, then
    stamp the asserted dest/head and the substrate upload's
    bytes on the record's transport. Returns prepare_branch's
    error, or None; the caller persists the record."""
    err, info = prepare_branch(session, transport, branch_ctx["clone_url"], branch_ctx["dest"], run_id)
    if err is not None:
        return err
    rec["transport"].update(dest=info["dest"], head=info["head"])
    rec["transport"]["bytes_moved"] = rec["transport"].get("bytes_moved", 0) + (REPO / "sync" / "base_clone.sh").stat().st_size
    return None


def build_seed_ctx(extra_args, rec) -> "tuple[str | None, dict | None]":
    """Build the bundle seed for a --seed run (the bundle
    transport's local half): resolve the named repo and
    variant against the local registry, build the snapshot
    bundle from the registry entry's local checkout (the
    same builder colab-check ships), and read the source
    repo's own git identity for the plant. Built before any
    session is held, so a local failure holds nothing.
    Returns (error, seed_ctx): seed_ctx carries the upload
    material for the launch window, and the bundle_seed
    record stamp is written to rec here.
    (repo_registry / git_identity are imported at call time,
    like resolve_branch_ctx's registry: the stub-foundation
    load surface.)"""
    from .foundation import git_identity, repo_registry

    def _extra(flag):
        return extra_args[extra_args.index(flag) + 1] if flag in extra_args and extra_args.index(flag) + 1 < len(extra_args) else None

    try:
        registry = repo_registry.load_local_registry(REPO)
        seed_repo_id, seed_entry = repo_registry.get_entry(registry, _extra("--repo"))
        seed_dest = repo_registry.variant_dest(seed_entry, _extra("--variant"))
    except ValueError as exc:
        return f"bundle seed: {exc}", None
    bundle_env = dict(os.environ)
    bundle_env["COLAB_REPO_SRC"] = str(Path(os.path.expanduser(seed_entry["local_path"])))
    bundle = subprocess.run(["bash", str(REPO / "sync" / "make_snapshot_bundle.sh")], capture_output=True, text=True, env=bundle_env)
    if bundle.returncode != 0:
        return f"bundle seed: snapshot build failed: {bundle.stderr[-300:]}", None
    seed_manifest = json.loads(bundle.stdout)
    # The git identity plant: the seeded tree carries the
    # source repo's own configured identity (its repo-local
    # user.name/user.email), never the forming shell's
    # inheritance. No complete pair at the source → no
    # plant, and the record says so.
    seed_identity = git_identity.repo_identity(seed_entry["local_path"])
    seed_ctx = {"repo": seed_repo_id, "dest": seed_dest, "clone_url": seed_entry["clone_url"], "bundle_path": Path(seed_manifest["bundle"]), "manifest": seed_manifest, "git_identity": seed_identity}
    rec["bundle_seed"] = {"repo": seed_repo_id, "dest": seed_dest, "sha256": seed_manifest["sha256"], "bytes": seed_manifest["bytes"], "snapshot_commit": seed_manifest["snapshot_commit"], "tree": seed_manifest["tree"], "git_identity": seed_identity}
    return None, seed_ctx


def stamp_transport_span(rec) -> None:
    """Stamp the claim→launch span as the launch window
    closes (branch transport plan): the claim is the
    record's birth (started_at — a resume never re-stamps
    it, so a resumed run's span prices all its attempts),
    the launch its confirmed stamp, falling back to the
    launch exec's own stamp on the unconfirmed branches.
    (epoch is imported at call time, like resolve_branch_ctx's
    registry: the stub-foundation load surface.)"""
    from .foundation import epoch

    claimed = epoch(rec.get("started_at"))
    launched = epoch(rec.get("launch_confirmed_at") or rec.get("launch_at"))
    if claimed is not None and launched is not None:
        rec["transport"]["claim_to_launch_s"] = round(launched - claimed, 1)


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
