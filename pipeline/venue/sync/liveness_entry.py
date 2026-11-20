"""Machine-written scheduler entries for live leases.

Session liveness plan (.plans/2026-11-06-session-liveness-
schedule.md): every live lease carries a derived schedule in
the scheduler server's registry — jobs/colab-liveness-
<session>.yaml, a scripted entry running bin/colab-liveness
every 15 minutes. The lease record is the record of truth and
the entry is its derived schedule, exactly the relationship
the workbench harness keeps between a todo and its
wb-progress entry.

The writer seams are the lease core's own record writers:
save_record arms (or refreshes) the entry, delete_record
removes it, so coverage holds by construction at every birth
(acquire, adoption, renewal swap, reconcile) and every death
(release, reap-terminal, clear). A sync failure never fails
the lease operation — reconcile (driven by the reaper hook's
janitor duty and by bin/colab-liveness --sync) repairs any
drift, and a leaked entry self-deletes on the checker's first
run that finds no live record.

Jobs-dir resolution: $COLAB_LIVENESS_JOBS_DIR when set (the
deliberate override — tests, tooling). Otherwise the real
registry is used only when the repo being operated on is
this module's own installed repo: the registry is the
pipeline's own scheduling registry (S5, plan §7 V5 — the
generator is a pipeline writer under contract 02, writing
into pipeline/scheduling/jobs beside this venue tree, no
longer a sibling repo under the process HOME). Test suites
operate on scratch repos, so the installed-repo guard keeps
a suite run from writing entries for fixture sessions into
the live registry (the test-isolation rule, learned from
the 2026-11-05 binding pollution). One more guard rides
here: under pytest (PYTEST_CURRENT_TEST set — in-process
tests, and the subprocesses they spawn from os.environ) the
default resolution always refuses, because in-process tests
drive the real repo against the fake CLI. No scheduler on
the machine means the sync is a silent no-op, as with the
workbench harness's seam.

Writes ride the unified writer's protocol (contract 15):
the entry stages to a fresh sibling and renames over, so a
denied write leaves the standing entry byte-identical.
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import os
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

ENTRY_PREFIX = "colab-liveness-"
_MODULE_REPO = _paths.REPO_RESOLVED


def jobs_dir(repo: Path) -> Path | None:
    env = os.environ.get("COLAB_LIVENESS_JOBS_DIR")
    if env:
        return Path(env)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    if Path(repo).resolve() != _MODULE_REPO:
        return None
    # Composed from _MODULE_REPO at call time, not bound
    # from the spine: the module root is a patchable seam
    # (the suite points it at a miniature pipeline tree),
    # and the scheduling dir is a function of that root.
    sibling = _MODULE_REPO.parent / "scheduling" / "jobs"
    return sibling if sibling.is_dir() else None


def _staged_write(path: Path, text: str) -> None:
    """The unified writer's protocol for one registry entry
    (contract 15): delegate to the platform writer where the
    pipeline tree provides it, else the same protocol inline
    (stage to a fresh sibling, fsync, read back, rename)."""
    import importlib.util as _ilu

    data = text.encode()
    cand = _paths.PLATFORM_WRITER
    if cand.exists():
        spec = _ilu.spec_from_file_location("pipeline_platform_writer", cand)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.staged_write(str(path), data)
        return
    tmp = path.with_name(f".{path.name}.sched-tmp-{os.getpid()}")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp, "rb") as fh:
            if fh.read() != data:
                raise OSError(f"read-back mismatch for {path}")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def entry_id(session: str) -> str:
    return ENTRY_PREFIX + session


def entry_path(repo: Path, session: str) -> Path | None:
    jd = jobs_dir(repo)
    return (jd / f"{entry_id(session)}.yaml") if jd else None


def render_entry(session: str) -> str:
    eid = entry_id(session)
    return f"""id: {eid}
title: 'Liveness check - Colab session {session}'
kind: scripted
status: active
cadence:
  type: interval
  every: 15m
owner: none
owner_reason: 'Machine-written by the venue lease core for one live lease; the lease record is the record of truth and this entry is its derived schedule.'
run:
  argv:
    - python3
    - ${{WS}}/supreme-octo-robot/pipeline/venue/bin/colab-liveness
    - {session}
timeout_secs: 120
report:
  when: on_failure
  ok_exit_codes:
    - 0
escalate_body: bodies/colab-liveness.md
state_paths:
  - ${{WS}}/supreme-octo-robot/pipeline/venue/var/liveness-{session}.json
classification: 'fixed command (bin/colab-liveness <session>); local file reads only, never dials the session; exit 0 healthy, cleared, or gone (self-disarmed), exit 3 with one LIVENESS line per finding it must speak; when it speaks is fully determined by its state file and the exit code, no content judgment'
lifetime: until_complete
self_removal: 'the lease core deletes this entry in the same call that deletes the lease record; the checker deletes it itself on the first run that finds no live record, and the reaper hook reconciliation retires any orphan'
"""


def sync_for_record(repo: Path, rec: dict) -> str:
    """Arm (or refresh) the entry for a live record. Returns a
    status word; never raises. Arming is refused while the
    entry's shared escalate body is absent from the scheduler
    repo (default resolution only): an entry pointing at a
    missing body fails registry validation, so the body lands
    first or nothing arms."""
    session = (rec or {}).get("session")
    if not session:
        return "no-session"
    try:
        path = entry_path(repo, session)
        if path is None:
            return "unavailable"
        if not os.environ.get("COLAB_LIVENESS_JOBS_DIR"):
            body = path.parent.parent / "bodies" / "colab-liveness.md"
            if not body.exists():
                return "unavailable"
        text = render_entry(session)
        if path.exists() and path.read_text() == text:
            return "present"
        _staged_write(path, text)
        return "written"
    except OSError as exc:
        return f"error: {exc}"


def write_state(path: Path, state: dict) -> None:
    """Write one checker's state file through the writer
    seam (register E5): the liveness-<session>.json file is
    shared with bin/colab-sh's cache writer, and both stage
    through the one platform-writer protocol — never a
    hand-rolled staging per component."""
    _staged_write(path, json.dumps(state, indent=1))


def remove_for_session(repo: Path, session: str) -> str:
    """Disarm: delete the entry and the checker's state file.
    Never raises."""
    try:
        path = entry_path(repo, session)
        if path is not None:
            path.unlink(missing_ok=True)
        state = var_dir(repo) / f"liveness-{session}.json"
        state.unlink(missing_ok=True)
        return "removed"
    except OSError as exc:
        return f"error: {exc}"


def live_sessions(records: list) -> set:
    return {r.get("session") for r in records if isinstance(r, dict) and r.get("session")}


def reconcile(repo: Path, records: list) -> dict:
    """Bring the registry in line with the live records: arm
    any live session missing an entry, retire any entry whose
    session holds no record. Returns what changed."""
    jd = jobs_dir(repo)
    if jd is None:
        return {"armed": [], "removed": [], "unavailable": True}
    live = live_sessions(records)
    by_session = {r["session"]: r for r in records if isinstance(r, dict) and r.get("session")}
    armed, removed = [], []
    for path in sorted(jd.glob(f"{ENTRY_PREFIX}*.yaml")):
        session = path.name[len(ENTRY_PREFIX):-len(".yaml")]
        if session not in live:
            remove_for_session(repo, session)
            removed.append(session)
    for session in sorted(live):
        if sync_for_record(repo, by_session[session]) == "written":
            armed.append(session)
    return {"armed": armed, "removed": removed}


def var_dir(repo: Path) -> Path:
    """The repo's var dir, honoring the same COLAB_RUNNER_VAR
    seam the lease core uses."""
    return Path(os.environ.get("COLAB_RUNNER_VAR", Path(repo) / "var"))


def load_records(repo: Path) -> list:
    """The repo's lease records, read plainly (this module is
    imported by the lease core, so it cannot import it back).
    Mirrors the core's record-file rules: lease-*.json plus
    the legacy lease.json, minus the spend/request ledgers,
    keeping only bodies that carry a session."""
    var = var_dir(repo)
    files = sorted(var.glob("lease-*.json"))
    legacy = var / "lease.json"
    if legacy.exists():
        files.append(legacy)
    records = []
    for f in files:
        if f.name in ("lease-spend.json", "lease-request.json", "lease-handover.json"):
            continue
        try:
            rec = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict) and rec.get("session"):
            records.append(rec)
    return records
