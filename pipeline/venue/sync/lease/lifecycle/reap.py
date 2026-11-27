import contextlib
import dataclasses
import fcntl
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ..core import foundation, records, spend
from ..access import access, grants
from ..sessions import sessions, keepalive, renewal, identity
from ..state import listeners, orphans
from . import lifecycle, local_venue

# --- Cycle budget ---------------------------------------------------------------
# Local why: the hook bounds a reap pass at 420 s and kills the
# wait; the pass itself carried no budget, so at peak channel load
# its sequential furniture (identity exec, freshness download,
# keepalive launch, kernel pulse, listener census — per record)
# summed past the bound and the cycle died mid-flight
# (three exit-124s). Lifecycle legs always survived
# only because they happen to run first inside each record. The
# budget makes that ordering structural: lifecycle for every
# record completes before any furniture starts, furniture runs
# under a remaining-budget check that skips-and-reports instead
# of being killed, and keepalive launches execute as their own
# deferred phase. The default is sized against the reap
# COMMAND's budget (bin/colab-lease composes pass + collector
# against VENUE_LEASE_REAP_COMMAND_BUDGET_S, default 390): the
# pass takes at most 300 of it, the collector's subprocess ride
# takes the remainder, and the hook's 420 keeps ~30 for process
# startup, the result print, and the mirror capture.

_REAP_BUDGET_DEFAULT_S = 300.0


def _budget_s() -> float:
    raw = os.environ.get("VENUE_LEASE_REAP_BUDGET_S", os.environ.get("COLAB_LEASE_REAP_BUDGET_S"))  # step6-retire: COLAB_ dual-read fallback
    try:
        return float(raw) if raw else _REAP_BUDGET_DEFAULT_S
    except ValueError:
        return _REAP_BUDGET_DEFAULT_S


# --- Approval-gate scope -------------------------------------------------------
# The reaper hook's approval gate (initiation-time approval plan,
# Step 4) tracks tunnel hosts with no proven contact as pending:
# dialing one mints a fresh approval card, so the gate's default
# for a pending host is CLOSED — at most one probe dial per hour.
# Before this scope existed, the hook expressed the gate by
# skipping the whole reap whenever any host was pending, which
# froze every proven host's pulse, keepalive, and deadline
# enforcement between probes (one renewed host's
# unproven tunnel stalled three sessions' liveness for an hour
# at a time and read as three session stalls). The scope moves
# the boundary inside the pass: the hook now supplies the
# pending/probe host sets on the reap command line, and the pass
# scopes only the records on those hosts — a pending record gets
# no network contact except, on a probe pass, its one kernel
# pulse; every other record gets full duties. The gate supplies
# hosts, never sessions: the pass resolves them against its own
# records, so a named host with no record is inert. Validation
# lives on the value itself — a malformed token or a probe host
# that is not pending raises, and the CLI refuses before any
# lease work runs; an absent scope is exactly the pre-gate
# behaviour every other reap caller still gets.

_HOST_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclasses.dataclass(frozen=True)
class GateScope:
    """One pass's approval-gate scope: the tunnel hosts with no
    proven contact (pending) and the subset whose hourly probe
    is due on this pass (probe)."""

    pending_hosts: frozenset = frozenset()
    probe_hosts: frozenset = frozenset()

    def __post_init__(self):
        for host in (*self.pending_hosts, *self.probe_hosts):
            if not isinstance(host, str) or not _HOST_TOKEN.match(host):
                raise ValueError(f"malformed gate host token: {host!r}")
        extra = self.probe_hosts - self.pending_hosts
        if extra:
            raise ValueError(f"gate probe hosts not pending: {sorted(extra)}")


def parse_gate_scope(pending_csv: str | None, probe_csv: str | None) -> GateScope:
    """Parse the reap command line's comma-separated gate host
    lists. None (flag absent) and an empty value both parse to
    the empty set; a malformed token raises ValueError."""

    def tokens(csv: str | None) -> frozenset:
        if csv is None:
            return frozenset()
        return frozenset(tok.strip() for tok in csv.split(",") if tok.strip())

    return GateScope(pending_hosts=tokens(pending_csv), probe_hosts=tokens(probe_csv))


class _CycleBudget:
    """One pass's monotonic budget. `check` is the furniture
    gate: True while time remains; on exhaustion it records the
    skipped item's name and returns False, so a skip is always
    reported, never silent."""

    def __init__(self, budget_s: float):
        self.budget_s = budget_s
        self._started = time.monotonic()
        self.skipped: list[str] = []

    def remaining(self) -> float:
        return self.budget_s - (time.monotonic() - self._started)

    def check(self, what: str) -> bool:
        if self.remaining() > 0:
            return True
        self.skipped.append(what)
        return False

    def report(self) -> dict:
        return {"budget_s": self.budget_s, "spent_s": round(time.monotonic() - self._started, 1), "skipped": self.skipped}


def _reap_lifecycle(colab, repo: Path, cfg: dict, rec: dict, grant: dict | None, now_dt: datetime, state: str, diag: dict, scoped: bool = False) -> tuple[dict, bool]:
    """One record's lifecycle legs, given its state verdict:
    the pre-two-tier reap logic (hard deadline, idle shutdown,
    death-clearing, renewal) plus grant-expiry enforcement for
    standing leases — a standing lease whose grant has lapsed
    (or vanished) is released even before its own deadline.
    Returns (result, kept): kept is True when the lease survives
    and its liveness furniture is still owed.

    A scoped record (its tunnel host is approval-pending) gets
    no leg that dials the session: renewal and every release
    wait for proven contact, and the record reports kept with
    the gate marker naming why. The absent path still runs —
    it is local bookkeeping over the pass's shared snapshot
    (stamp, confirm, clear), not a dial — except its renewal
    attempt, which creates a session and is therefore gated."""
    if state == "unknown":
        return {"action": "kept-unknown", "session": rec["session"], "read_error": diag.get("read_error"), "attempts": diag.get("attempts")}, False
    if state == "absent":
        if not scoped and rec.get("renew") and not rec.get("standing") and now_dt < foundation.parse_dt(rec["deadline"]):
            # Window lease whose session died mid-window: renew it
            # instead of clearing (lease-extension plan). A failed
            # renewal keeps the record — the next cycle retries, and
            # the window's end still releases normally below once it
            # passes. Standing records never take this branch.
            renewed = renewal._attempt_renewal(colab, repo, cfg, rec, state, now_dt)
            if renewed is not None:
                foundation.clear_absent_stamp(repo, rec["session"])
                return {"action": "renewed", "session": rec["session"], **renewed}, False
            return {"action": "renewal-failed", "session": rec["session"]}, False
        # Deletion needs the absence confirmed across passes: a
        # single absent read is as often the session list's
        # flicker as the runtime's death (adopted
        # records were cleared within one cycle of a false
        # absent while their sessions lived and worked). The
        # first absent read stamps and keeps; a later pass still
        # absent past the confirmation window clears; any live
        # read resets the clock (below).
        since = foundation.absent_since(repo, rec["session"])
        if since is None or (now_dt - since).total_seconds() < foundation.ABSENT_CONFIRM_S:
            foundation.stamp_absent(repo, rec["session"], since or now_dt, now_dt)
            return {"action": "kept-absent-unconfirmed", "session": rec["session"], "absent_since": (since or now_dt).isoformat()}, False
        foundation.clear_absent_stamp(repo, rec["session"])
        spend.append_spend_segment(repo, rec, now_dt)
        grants._note_envelope_lease_released(repo, rec, "cleared-dead")
        records.delete_record(repo, rec["session"])
        return {"action": "cleared-dead", "session": rec["session"]}, False
    foundation.clear_absent_stamp(repo, rec["session"])
    if scoped:
        live = records.live_jobs(repo, rec)
        return {"action": "kept", "session": rec["session"], "deadline": rec["deadline"], "jobs": [entry["id"] for entry in live], "gate": "pending"}, True
    if rec.get("standing") and not grants.grant_active(grant, now_dt):
        rel = lifecycle.release(colab, repo, reason="grant-expired", session=rec["session"], now_dt=now_dt)
        return {"action": "released-standing-expired", "stop": rel.get("stop"), "was": rel.get("was")}, False
    if now_dt >= foundation.parse_dt(rec["deadline"]):
        rel = lifecycle.release(colab, repo, reason="deadline", session=rec["session"], now_dt=now_dt)
        return {"action": "released-deadline", "stop": rel.get("stop"), "was": rel.get("was")}, False
    idle = cfg.get("idle_shutdown_minutes")
    # The idle test reads the pruned projection, not the raw
    # registrations: a record whose jobs all ended without a
    # finish_job is idle-eligible, not pinned forever by ghosts.
    live = records.live_jobs(repo, rec)
    if idle is not None and not live:
        if now_dt - foundation.parse_dt(rec["last_used_at"]) > timedelta(minutes=float(idle)):
            rel = lifecycle.release(colab, repo, reason="idle", session=rec["session"], now_dt=now_dt)
            return {"action": "released-idle", "stop": rel.get("stop"), "was": rel.get("was")}, False
    renewal_failed = False
    if rec.get("renew") and not rec.get("standing"):
        # Renewal threshold: the session's age passes the platform cap
        # minus the overlap margin while the window is still open.
        if now_dt - foundation.parse_dt(rec["acquired_at"]) >= timedelta(hours=renewal.SESSION_CAP_HOURS) - renewal.RENEWAL_MARGIN:
            renewed = renewal._attempt_renewal(colab, repo, cfg, rec, state, now_dt)
            if renewed is not None:
                return {"action": "renewed", "session": rec["session"], **renewed}, False
            renewal_failed = True  # the session still lives; the kept path below maintains it
    out = {"action": "kept", "session": rec["session"], "deadline": rec["deadline"], "jobs": [entry["id"] for entry in live]}
    if renewal_failed:
        out["renewal"] = "failed"
    return out, True


def _reap_furniture(colab, repo: Path, cfg: dict, rec: dict, out: dict, now_dt: datetime, scoped: bool = False, probe: bool = False) -> bool:
    """One kept record's liveness furniture: the kernel
    pulse, the keepalive freshness read, and the runtime
    identity check. Returns True when the keepalive read found
    the loop stale and a launch is owed — the launch itself is
    the caller's act (the pass defers it to its own phase; a
    stalled launch then starves nothing).

    A scoped record (approval-pending host) gets none of it:
    the freshness read, the keepalive launch, and the identity
    probe are all tunnel contact the gate reserves. On a probe
    pass the record gets exactly one dial — the kernel pulse,
    the gate's own contact test — stamped on a fresh load
    exactly as the cadenced pulse stamps it, because the stamp
    is the contact evidence both gate latches read. A scoped
    record never owes a keepalive launch.

    The pulse runs FIRST (the pulse-first cure): it is the
    liveness heartbeat the whole layer reads, and under a
    sick CLI every dial in this function burns tens of
    seconds — queued behind the identity exec and the
    heartbeat read, the pulse starved for hours while the
    sessions executed fine (no reap pass completed between
    07:23Z and the cure; both live records read pulse-stale /
    pulse-failing to the liveness checker the whole time).
    The stamp lands on a FRESH load of the record, not the
    pass's copy: the pass loaded its copy minutes earlier
    under slow dials, and a save from a stale copy is a
    lost update waiting for the next concurrent writer —
    the 07:23Z pass reported a pulse ok for one record
    whose stamp never persisted."""
    if scoped:
        if probe:
            result = keepalive.kernel_pulse(colab, repo, rec["session"])
            fresh_rec = records.load_record(repo, rec["session"]) or rec
            fresh_rec["last_pulse_at"] = now_dt.isoformat()
            fresh_rec["last_pulse_result"] = result
            records.save_record(repo, fresh_rec)
            rec["last_pulse_at"] = fresh_rec["last_pulse_at"]
            rec["last_pulse_result"] = result
            out["pulse"] = result
            out["gate"] = "probe"
        else:
            out["pulse"] = "gated"
            out["gate"] = "pending"
        return False
    launch_owed = False
    if cfg.get("keepalive", {}).get("enabled"):
        pulse_every = float(cfg["keepalive"].get("pulse_seconds", 600))
        last_pulse = rec.get("last_pulse_at")
        due = last_pulse is None or (now_dt - foundation.parse_dt(last_pulse)).total_seconds() >= pulse_every
        if due:
            result = keepalive.kernel_pulse(colab, repo, rec["session"])
            fresh_rec = records.load_record(repo, rec["session"]) or rec
            fresh_rec["last_pulse_at"] = now_dt.isoformat()
            fresh_rec["last_pulse_result"] = result
            records.save_record(repo, fresh_rec)
            rec["last_pulse_at"] = fresh_rec["last_pulse_at"]
            rec["last_pulse_result"] = result
            out["pulse"] = result
        else:
            out["pulse"] = "not-due"
        fresh, age = keepalive.keepalive_fresh(colab, repo, rec["session"])
        if fresh:
            out["keepalive"] = "ok"
            out["heartbeat_age_s"] = round(age, 1)
        else:
            launch_owed = True
    # Runtime identity, on this pass's cadence: a runtime
    # replaced under this lease's name surfaces here (the
    # check spools the event and re-stamps; an unreadable
    # probe is unknown, never a verdict). Only a confirmed
    # replacement rides the result — the notable-outcome
    # precedent of the renewal flag above.
    ident = identity.check_identity(colab, repo, rec, now_dt)
    if ident.get("identity") == "replaced":
        out["runtime_identity"] = "replaced"
        out["runtime_jobs"] = ident.get("jobs", [])
        out["runtime_runs"] = ident.get("runs", [])
    return launch_owed


def _reap_record(colab, repo: Path, cfg: dict, rec: dict, grant: dict | None, now_dt: datetime, gate: GateScope | None = None) -> dict:
    """One record's whole reap — lifecycle, furniture, and an
    inline keepalive launch — over its own state read. The
    pass composes the same legs in phases under the cycle
    budget; this composition remains for callers that reap a
    single record directly."""
    diag: dict = {}
    state = sessions.session_state(colab, rec["session"], diag, attempts=sessions._REAP_READ_ATTEMPTS, timeout=sessions._REAP_READ_TIMEOUT_S)
    scoped = gate is not None and rec.get("host") in gate.pending_hosts
    out, kept = _reap_lifecycle(colab, repo, cfg, rec, grant, now_dt, state, diag, scoped=scoped)
    if kept:
        probe = scoped and rec.get("host") in gate.probe_hosts
        if _reap_furniture(colab, repo, cfg, rec, out, now_dt, scoped=scoped, probe=probe):
            out["keepalive"] = keepalive.ensure_keepalive(colab, repo, rec["session"]).get("keepalive")
    return out


_REAP_PRIORITY = ("released-deadline", "cleared-dead", "released-standing-expired", "released-idle", "renewed", "renewal-failed", "kept-absent-unconfirmed", "kept-unknown", "kept")


@contextlib.contextmanager
def _reap_lock(repo: Path):
    """One reap pass at a time. The hook fires reap on a fixed
    poll and kills its wait at a timeout, but the reap process
    itself used to run on — the next poll then started a second
    pass over the same records, and two passes renewing the same
    lease in parallel minted duplicate successor leases.
    The lock is an flock on a var/ file: held only
    while a pass runs, released by the OS when the holder dies
    (a kill included), so it can never go stale."""
    path = foundation.var_dir(repo) / "reap.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def reap(colab, repo: Path, now_dt: datetime | None = None, gate: GateScope | None = None) -> dict:
    with _reap_lock(repo) as held:
        if not held:
            return {"action": "already-running", "records": []}
        return _reap_pass(colab, repo, now_dt, gate=gate)


def _reap_pass(colab, repo: Path, now_dt: datetime | None = None, gate: GateScope | None = None) -> dict:
    """Hook duty: reap every lease record. The top-level
    action/fields are the most consequential per-record result —
    or the sole record's, in a one-lease world — so the hook's
    parsing (kept/none/released-deadline/cleared-dead) keeps its
    meaning; every record's outcome is also listed under
    "records".

    The pass runs in phases under the cycle budget: one shared
    listing (the snapshot) classifies every record and feeds
    unattributed detection — which therefore still runs before
    any release, against the records as the pass found them,
    and costs no second read; then every record's lifecycle
    legs complete, unconditionally; then the furniture phases
    (per-record identity/keepalive/pulse, the deferred
    keepalive launches, the listener census) run under the
    budget's remaining time, skipping-and-reporting what does
    not fit.

    A gate scope (the reaper hook's approval gate) narrows the
    per-record legs for records on pending hosts only — see
    GateScope; the shared listing and the global detections
    are control-plane reads, not per-host tunnel contact, and
    are never scoped."""
    now_dt = now_dt or datetime.now(timezone.utc)
    cfg = foundation.load_config(repo)
    recs = records.all_records(repo)
    budget = _CycleBudget(_budget_s())
    diag: dict = {}
    snapshot = sessions.list_snapshot(colab, diag, attempts=sessions._REAP_READ_ATTEMPTS, timeout=sessions._REAP_READ_TIMEOUT_S)
    live = sessions.live_sessions(colab, repo, text=snapshot) if snapshot is not None else None
    # Unattributed detection runs even with no records at all —
    # that is precisely the world where a stray matters.
    unattributed = access.detect_unattributed(colab, repo, now_dt, live=live)
    # Nameless detection rides the same pass: an assignment
    # with no usable name is invisible to every name-keyed
    # verdict above, so it is censused by endpoint here, the
    # moment the pass sees it (orphans.detect_nameless).
    nameless = orphans.detect_nameless(repo, live, now_dt)
    if not recs:
        out = {"action": "none", "records": [], "unattributed": unattributed, "nameless": nameless, "budget": budget.report()}
        if gate is not None:
            out["gate"] = {"pending_sessions": [], "probe_sessions": []}
        return out
    grant = grants.load_grant(repo)
    for rec in recs:
        # Host reconcile (initiation-time approval follow-up):
        # a birth capture is not the last word — the
        # record's first saves and the capture save are seconds
        # apart (keepalive + pulse run between them), and a
        # concurrent writer holding a pre-capture copy (a keepwarm
        # pulse, a reap save) restores a hostless record; an
        # adopted lease ran exactly that race and the reaper's
        # approval gate stayed blind to its host for hours while
        # the acquire output reported the capture fine.
        # Re-derive the host from the local binding every pass: a
        # fill is silent (the birth event already spooled), a real
        # change spools as origin "reconcile". The binding is the
        # home venue's; another venue's record has no host here.
        if (rec.get("venue") or foundation.VENUE) != foundation.VENUE:
            continue
        if keepalive._capture_session_host(repo, rec, "reconcile", spool_on_first=False):
            records.save_record(repo, rec)
    # Approval-gate scope, resolved after the host reconcile so
    # it reads the freshest host per record: the sessions whose
    # record sits on a pending host, and the subset whose host's
    # probe is due on this pass.
    pending_sessions: set[str] = set()
    probe_sessions: set[str] = set()
    if gate is not None:
        for rec in recs:
            host = rec.get("host")
            if host in gate.pending_hosts:
                pending_sessions.add(rec["session"])
                if host in gate.probe_hosts:
                    probe_sessions.add(rec["session"])
    results = []
    kept_pairs = []
    for rec in recs:
        # Liveness is per-venue: the shared snapshot is the home
        # venue's session list and classifies only its own
        # records. Another venue's record reads unknown here —
        # kept, never absent, never reaped by this pass — until
        # that venue's own liveness source classifies it.
        state = sessions.state_in_snapshot(snapshot, rec["session"]) if (rec.get("venue") or foundation.VENUE) == foundation.VENUE else "unknown"
        out, kept = _reap_lifecycle(colab, repo, cfg, rec, grant, now_dt, state, diag, scoped=rec["session"] in pending_sessions)
        entry = {"session": rec.get("session"), **out}
        results.append(entry)
        if kept:
            kept_pairs.append((rec, entry))
    launch_requests = []
    for rec, entry in kept_pairs:
        if not budget.check(f"furniture:{rec['session']}"):
            entry["furniture"] = "skipped-budget"
            continue
        scoped = rec["session"] in pending_sessions
        if _reap_furniture(colab, repo, cfg, rec, entry, now_dt, scoped=scoped, probe=rec["session"] in probe_sessions):
            launch_requests.append((rec, entry))
    for rec, entry in launch_requests:
        if not budget.check(f"keepalive-launch:{rec['session']}"):
            # The next cycle's freshness read finds the loop
            # still stale and asks again — a deferral costs one
            # cycle, never the lease.
            entry["keepalive"] = "launch-deferred"
            continue
        entry["keepalive"] = keepalive.ensure_keepalive(colab, repo, rec["session"]).get("keepalive")
    # Listener census (standing hygiene): throttled
    # per session inside maybe_collect; the collector stamps its
    # own failures and never raises, and this guard keeps even a
    # collector defect out of the reap's path.
    for rec in recs:
        if (rec.get("venue") or foundation.VENUE) != foundation.VENUE:
            # The census reads through the home venue's session
            # tunnel; another venue's record is not its subject.
            continue
        if rec["session"] in pending_sessions:
            # The listener census reads through the session's
            # tunnel — contact the gate reserves like any other.
            continue
        if not budget.check(f"listeners:{rec['session']}"):
            continue
        try:
            listeners.maybe_collect(colab, repo, rec, now_dt)
        except Exception:  # noqa: BLE001
            pass
    # Local-venue pulse: the local venue's pulse verdict is its
    # SSH probe, and this pass is the one periodic writer that
    # visits local records — stamp the verdict here, on a fresh
    # load (the pulse discipline above), at the keepalive pulse
    # cadence. The stamp is the venue's own liveness evidence
    # for the checker; the pass still never classifies or reaps
    # the record. A stamp failure leaves the record unstamped —
    # the checker's pulse-stale reading stays the report.
    for rec in recs:
        if (rec.get("venue") or foundation.VENUE) != "local":
            continue
        if not budget.check(f"local-pulse:{rec['session']}"):
            continue
        try:
            pulse_every = float(cfg.get("keepalive", {}).get("pulse_seconds", 600))
            last_pulse = rec.get("last_pulse_at")
            due = last_pulse is None or (now_dt - foundation.parse_dt(last_pulse)).total_seconds() >= pulse_every
            if not due:
                continue
            probed = local_venue.probe_for_record(repo, rec, now_dt=now_dt)
            if probed is None:
                continue
            fresh_rec = records.load_record(repo, rec["session"]) or rec
            fresh_rec["last_pulse_at"] = now_dt.isoformat()
            fresh_rec["last_pulse_result"] = "ok" if probed else "unreachable"
            records.save_record(repo, fresh_rec)
        except Exception:  # noqa: BLE001
            pass
    # Colab venue-state parity (venue-state mechanism,
    # step 6): classify the home sessions and the fleet
    # aggregate from this pass's own reads — the shared
    # snapshot's liveness per session and the records'
    # live-jobs projections — into the same state-file
    # shape the local sampler writes, through the same
    # classifier. Guarded like the listener census: a
    # parity failure never breaks the reap.
    if budget.check("venue-state:colab"):
        try:
            from . import venue_state

            live_by_session = {
                rec["session"]: sessions.state_in_snapshot(snapshot, rec["session"]) == "alive"
                for rec in recs
                if (rec.get("venue") or foundation.VENUE) == foundation.VENUE
            }
            venue_state.pass_colab(repo, recs, live_by_session, now_dt.isoformat())
        except Exception:  # noqa: BLE001
            pass
    top = results[0] if len(results) == 1 else None
    if top is None:
        for action in _REAP_PRIORITY:
            top = next((r for r in results if r["action"] == action), None)
            if top is not None:
                break
    out = dict(top)
    out["records"] = results
    out["unattributed"] = unattributed
    out["nameless"] = nameless
    out["budget"] = budget.report()
    if gate is not None:
        out["gate"] = {"pending_sessions": sorted(pending_sessions), "probe_sessions": sorted(probe_sessions)}
    return out
