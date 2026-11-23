import importlib.util as _ilu
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from . import foundation, accounts as _accounts

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths",
    Path(__file__).resolve().parent.parent.parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

_naming_spec = _ilu.spec_from_file_location("colab_naming", _paths.NAMING)
naming = _ilu.module_from_spec(_naming_spec)
_naming_spec.loader.exec_module(naming)

_liveness_spec = _ilu.spec_from_file_location("colab_liveness_entry", _paths.LIVENESS_ENTRY)
liveness_entry = _ilu.module_from_spec(_liveness_spec)
_liveness_spec.loader.exec_module(liveness_entry)


def session_record_path(repo: Path, session: str) -> Path:
    return foundation.var_dir(repo) / f"lease-{session}.json"


def session_evidence_path(repo: Path, session: str) -> Path:
    return foundation.var_dir(repo) / f"session-evidence-{session}.json"


def write_session_evidence(repo: Path, rec: dict) -> None:
    """Project the record's deadline-bearing fields into the
    session-evidence file (E2): {deadline, acquired_at, shape,
    spec, caller} — a verbatim copy of the same record, written
    with the record's own staged-sibling discipline. The
    projection exists so orphan derivation keeps an evidenced
    deadline when the record itself is lost; save_record
    refreshes it on every save, so no lifecycle path that
    creates or moves a deadline — acquire, extend, shorten,
    renewal, adoption — can miss it, and it never depends on
    the renewal kit having installed."""
    session = rec.get("session")
    if not session:
        return
    evidence = {
        "deadline": rec.get("deadline"),
        "acquired_at": rec.get("acquired_at"),
        "shape": rec.get("shape"),
        "spec": rec.get("shape_spec"),
        "caller": rec.get("caller"),
        # Venue key (S5, plan §7 V1): the projection carries the
        # record's venue — save_record stamps the record before
        # this refresh runs, so the two never disagree. The
        # session-evidence schema is amended to match (contract
        # 12, finding 1 disposition).
        "venue": rec.get("venue"),
    }
    p = session_evidence_path(repo, session)
    foundation.staged_write(p, json.dumps(evidence, indent=2).encode())


def _valid_record(data) -> dict | None:
    return data if isinstance(data, dict) and data.get("session") else None


def _record_files(repo: Path) -> list[Path]:
    """Every file that may hold a lease record: the per-session
    files under var/ (the name a file carries says nothing; its
    record's session is the key)."""
    var = foundation.var_dir(repo)
    files = []
    if var.exists():
        for path in sorted(var.glob("lease-*.json")):
            if path.name in ("lease-spend.json", "lease-request.json"):
                continue
            files.append(path)
    return files


def _filename_session(name: str) -> str:
    """The session a record file's NAME claims
    (lease-<session>.json): the only attribution a file whose
    contents cannot be read still carries."""
    stem = name[len("lease-"):] if name.startswith("lease-") else name
    return stem[: -len(".json")] if stem.endswith(".json") else stem


def _record_from_bytes(path: Path) -> dict | None:
    """The record a file holds, or None when the file cannot
    yield one — unreadable, unparseable, or not a record."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return _valid_record(data)


def torn_records(repo: Path) -> list[dict]:
    """Every lease-record file whose contents cannot yield a
    record (E1): served as a finding instead of vanishing from
    every reader the way an unparseable file does today. A
    torn file is attributed by the only thing it still
    carries — its filename. The handover file is a different
    class living under the same prefix (a live handover
    marker, never a record) and is excluded by name. This is
    a pure read: nothing here renames anything — quarantine
    is a writer's act, below."""
    out = []
    for path in _record_files(repo):
        if path.name == "lease-handover.json":
            continue
        if _record_from_bytes(path) is not None:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        out.append({"session": _filename_session(path.name), "file": path.name, "bytes": size})
    return out


def quarantine_torn(repo: Path, session: str | None = None, now_dt: datetime | None = None) -> list[dict]:
    """Rename torn record files out of the record namespace —
    <name>.torn-<ts>, bytes preserved — so the writers that
    need the path (save_record's target, the adoption path)
    never reason about a torn file in place. With a session,
    only that session's file moves. The rename is the whole
    remedy: the torn bytes are evidence and are never deleted
    here. Returns the quarantined entries, each with its new
    name under "quarantined_as"."""
    now_dt = now_dt or datetime.now(timezone.utc)
    stamp = now_dt.strftime("%Y%m%dT%H%M%SZ")
    out = []
    for entry in torn_records(repo):
        if session is not None and entry["session"] != session:
            continue
        src = foundation.var_dir(repo) / entry["file"]
        dst = src.with_name(f"{entry['file']}.torn-{stamp}")
        if dst.exists():
            dst = src.with_name(f"{entry['file']}.torn-{stamp}-{os.getpid()}")
        os.replace(src, dst)
        out.append({**entry, "quarantined_as": dst.name})
    return out


def all_records(repo: Path) -> list[dict]:
    """Every lease record on disk, exactly as written. One record
    per session: when two files hold the same session, the
    session-keyed file wins. Order: acquisition order."""
    by_session: dict[str, dict] = {}
    canonical: set[str] = set()
    for path in _record_files(repo):
        rec = _valid_record(foundation.load_json(path, None))
        if rec is None:
            continue
        session = rec["session"]
        if path.name == f"lease-{session}.json":
            by_session[session] = rec
            canonical.add(session)
        elif session not in canonical:
            by_session.setdefault(session, rec)
    recs = list(by_session.values())
    recs.sort(key=lambda r: (r.get("acquired_at") or "", r.get("session") or ""))
    return recs


def load_record(repo: Path, session: str | None = None) -> dict | None:
    """With a session: that session's record. Without: the most
    recently used record (the lease a job call most plausibly
    belongs to), or None when no lease is on disk."""
    recs = all_records(repo)
    if session is not None:
        return next((r for r in recs if r.get("session") == session), None)
    if not recs:
        return None
    return max(recs, key=lambda r: (r.get("last_used_at") or "", r.get("acquired_at") or ""))


# --- Pruned-jobs projection ----------------------------------------------------
# Local why: job registrations were append-only — touch_job adds,
# finish_job removes, and a registration whose backing record
# ended without a finish (a killed runner, a detached call nobody
# polled to its end) stayed on the record forever: one live
# record carried 63 registrations, 23 of them backed by terminal
# or missing records, and every consumer that read the raw list
# (the state document, the reap's idle test, the sync-claim
# evidence) inherited the lie. The projection is the one truth:
# a registration counts only while its backing run record
# (results/runs/<id>.json) or detached record
# (results/detached/<id>.json) exists and is non-terminal.
# The state vocabularies are the consumers' own: the runner's
# terminal states for runs, and a detached record is live only
# in its running state with no finish stamp.

RUN_NONTERMINAL_STATES = ("starting", "running", "polling")
DETACHED_LIVE_STATES = ("running",)


def run_backing(repo: Path, run_id: str) -> tuple[dict | None, bool]:
    """One run record by id: (record, file_exists). The record
    is None when the file cannot yield one — missing, or torn
    mid-write; the flag separates the two, because a torn
    record is unknown, never dead."""
    path = repo / "results" / "runs" / f"{run_id}.json"
    rec = foundation.load_json(path, None)
    return (rec if isinstance(rec, dict) else None), path.exists()


def detached_backing(repo: Path, det_id: str) -> tuple[dict | None, bool]:
    """One detached record by id (the part after `detached:`),
    under the same contract as run_backing."""
    path = repo / "results" / "detached" / f"{det_id}.json"
    rec = foundation.load_json(path, None)
    return (rec if isinstance(rec, dict) else None), path.exists()


def detached_activity(repo: Path, session: str) -> str | None:
    """The newest activity stamp among the session's detached
    records (results/detached/): a record's activity is its
    finished_at when it has one, else its started_at. None
    when the session has no detached records. This is the
    evidence the served last-use line folds in (state.status):
    detached shell work is session use even though no lease
    path stamps the lease record for it — the panel read cozy
    as unused since 15:55Z while a detached probe ran there
    from 15:58Z (2026-11-11)."""
    latest = None
    detached = repo / "results" / "detached"
    if detached.is_dir():
        for path in sorted(detached.glob("*.json")):
            det = foundation.load_json(path, None)
            if not isinstance(det, dict) or det.get("session") != session:
                continue
            stamp = det.get("finished_at") or det.get("started_at")
            if isinstance(stamp, str) and (latest is None or stamp > latest):
                latest = stamp
    return latest


def job_entry(repo: Path, job_id: str) -> dict | None:
    """One registration resolved against its backing record:
    {id, kind, state, started_at} while the backing record
    exists and is non-terminal, else None (pruned). A backing
    file that exists but cannot be read is torn — unknown,
    never dead — and the registration stands with state
    "unknown". A registration with no backing-record kind (a
    bare name that is neither a run id nor `detached:<id>`)
    resolves against the runs directory like any run id."""
    if not isinstance(job_id, str):
        return None
    if job_id.startswith("detached:"):
        det_id = job_id.split(":", 1)[1]
        det, exists = detached_backing(repo, det_id)
        if det is None:
            return {"id": job_id, "kind": "detached", "state": "unknown", "started_at": None} if exists else None
        if det.get("finished_at"):
            return None
        state = det.get("state", "running")
        if state not in DETACHED_LIVE_STATES:
            return None
        return {"id": job_id, "kind": "detached", "state": state, "started_at": det.get("started_at")}
    run, exists = run_backing(repo, job_id)
    if run is None:
        return {"id": job_id, "kind": "run", "state": "unknown", "started_at": None} if exists else None
    state = run.get("state")
    if state not in RUN_NONTERMINAL_STATES:
        return None
    return {"id": job_id, "kind": "run", "state": state, "started_at": run.get("started_at")}


def live_jobs(repo: Path, rec: dict) -> list[dict]:
    """The record's pruned jobs projection: the kinded entries
    of the registrations that are still backed by a live
    record, in registration order. Every consumer of a record's
    jobs — the state document, the census, adoption seeding,
    the reap's idle test — reads this, never the raw list."""
    out = []
    for job_id in rec.get("jobs") or []:
        entry = job_entry(repo, job_id)
        if entry is not None:
            out.append(entry)
    return out


def _pulse_pair_newer(disk: dict, rec: dict) -> bool:
    """True when the on-disk record's pulse stamp is fresher
    than the saver's copy. An unparseable or absent stamp on
    either side is never newer — the saver's copy wins any
    doubt, so this test can only preserve, never invent."""
    try:
        disk_at = foundation.parse_dt(disk.get("last_pulse_at"))
        rec_at = foundation.parse_dt(rec.get("last_pulse_at"))
    except (TypeError, ValueError):
        return False
    if disk_at is None:
        return False
    return rec_at is None or disk_at > rec_at


def save_record(repo: Path, rec: dict) -> None:
    """Write one lease's record at its session path. Any other
    file holding a record for the same session is removed, so a
    stale copy can never resurrect the lease's old shape."""
    # The pulse stamp is the reap's field, written on its own
    # cadence into a fresh load (the 2026-11-21 reap cure);
    # every other writer saves a whole record from a copy it
    # loaded for its own mutation — jobs, deadline, lifecycle —
    # and a save whose load straddled the reap's stamp used to
    # overwrite the stamp with its stale values, every cycle
    # (the writer-side lost update: records read pulse-stale
    # for hours while the reap reported pulse ok). The stamp
    # pair therefore merges at this one funnel: when the
    # on-disk stamp is fresher, it is carried into the saver's
    # copy (and so into the caller's dict, like the jobs
    # pruning below) before the write. The saver's own fields
    # are never merged — this preserves the one field whose
    # writer is not the saver, nothing else.
    try:
        disk = load_record(repo, rec.get("session"))
    except Exception:
        disk = None
    if disk is not None and _pulse_pair_newer(disk, rec):
        rec["last_pulse_at"] = disk.get("last_pulse_at")
        rec["last_pulse_result"] = disk.get("last_pulse_result")
    # The jobs list persists pruned (the projection above):
    # registrations whose backing records are gone or terminal
    # are dropped at the write, so the store self-heals with no
    # migration. The caller's dict is pruned too — a save is the
    # moment the record's jobs become the projection everywhere,
    # including in the hands of the code that just saved it.
    if isinstance(rec.get("jobs"), list):
        rec["jobs"] = [entry["id"] for entry in live_jobs(repo, rec)]
    # Venue key (S5, plan §7 V1): stamped at write time from
    # the first extracted write. A record loaded from the
    # legacy stock gains the stamp the §10.3 migration would
    # give it the first time the extracted core saves it; no
    # reader ever defaults the key at read time.
    rec.setdefault("venue", foundation.VENUE)
    # Account key (venue rework): the account the session was
    # minted under, stamped at write the same way — the config's
    # default account for this venue. Pricing and spend
    # attribution address the record by it; no reader defaults
    # the key at read time.
    rec.setdefault("account", _accounts.default_account(foundation.load_config(repo), foundation.VENUE))
    session = rec["session"]
    p = session_record_path(repo, session)
    p.parent.mkdir(parents=True, exist_ok=True)
    # A torn file at this record's own path is quarantined
    # first (E1): the staged replace below would otherwise
    # destroy the torn bytes, which are the only evidence the
    # damage happened. A failed quarantine never fails the
    # save — landing the record is the critical act.
    try:
        quarantine_torn(repo, session=session)
    except OSError:
        pass
    # Through the unified writer (S5, plan §4.15): the
    # stage → fsync → read-back → rename protocol the record
    # writers used to hand-roll here is the platform writer's
    # one implementation — a denied or torn write leaves the
    # standing record byte-identical, and the failure surfaces
    # to the caller instead.
    foundation.staged_write(p, json.dumps(rec, indent=2).encode())
    for other in _record_files(repo):
        if other == p:
            continue
        held = _valid_record(foundation.load_json(other, None))
        if held is not None and held.get("session") == session:
            other.unlink(missing_ok=True)
    # Session liveness: a saved live record carries its derived
    # scheduler entry (sync/liveness_entry.py). The sync never
    # fails the save — drift is repaired by the reaper janitor.
    try:
        liveness_entry.sync_for_record(repo, rec)
    except Exception:
        pass
    # Session evidence (E2): the record's deadline projection,
    # refreshed on every save so every lifecycle write that
    # creates or moves a deadline leaves it current. Also
    # best-effort, for the same reason as the liveness sync:
    # the record itself is the primary copy.
    try:
        write_session_evidence(repo, rec)
    except Exception:
        pass


def retire_superseded(repo: Path, old_session: str, new_session: str, now_dt: datetime | None = None) -> str | None:
    """Retire a superseded generation's record at a renewal
    swap (2026-11-23): the old session's record leaves the live
    namespace in the swap's own act, preserved as a tombstone
    beside it — <file>.superseded-<ts>, the quarantine_torn
    rename-out form — carrying the record as it stood plus
    retired / superseded_by / superseded_at stamps. The bare
    delete this replaces left a reader of the old name nothing
    to reason from, and the failure it answers is the standing
    copy: a resume priced its run against a generation whose
    record still read as the lease's current pin while the
    server no longer held that session ("not found
    server-side", sunny-ridge-19 r1795368082). Out of the
    namespace, no pool, census, pin, or reap pass can mistake
    the tombstone for a live lease; on disk, the pointer names
    the generation that replaced it. The old session's
    evidence projection and liveness entry die with the live
    record, exactly as delete_record's. Returns the
    tombstone's file name, or None when no live record stood
    for the old session (the delete still runs)."""
    now_dt = now_dt or datetime.now(timezone.utc)
    stamp = now_dt.strftime("%Y%m%dT%H%M%SZ")
    held_path: Path | None = None
    held: dict | None = None
    for path in _record_files(repo):
        rec = _valid_record(foundation.load_json(path, None))
        if rec is not None and rec.get("session") == old_session:
            held_path, held = path, rec
            if path.name == f"lease-{old_session}.json":
                break
    tomb_name = None
    if held is not None and held_path is not None:
        tomb = dict(held)
        tomb.update(retired=True, superseded_by=new_session, superseded_at=now_dt.isoformat())
        dst = held_path.with_name(f"{held_path.name}.superseded-{stamp}")
        if dst.exists():
            dst = held_path.with_name(f"{held_path.name}.superseded-{stamp}-{os.getpid()}")
        foundation.staged_write(dst, json.dumps(tomb, indent=2).encode())
        tomb_name = dst.name
    delete_record(repo, old_session)
    return tomb_name


def delete_record(repo: Path, session: str) -> None:
    """Remove a lease's record, wherever it lives — for the same
    reason save cleans up: no stale copy may resurrect a released
    lease."""
    for path in _record_files(repo):
        held = _valid_record(foundation.load_json(path, None))
        if held is not None and held.get("session") == session:
            path.unlink(missing_ok=True)
    # The session-evidence projection (E2) dies with the
    # record it projects: a released lease leaves no deadline
    # evidence behind for a session that no longer exists.
    session_evidence_path(repo, session).unlink(missing_ok=True)
    # Session liveness: the derived scheduler entry dies with
    # the record, in the same call.
    try:
        liveness_entry.remove_for_session(repo, session)
    except Exception:
        pass
