"""The outbox: durable pings to the main thread (spec Step 4).

A ping is written to state/outbox.json (temp-file-plus-rename)
before any wake is attempted. One pending ping per job — a job
that falls due again coalesces into its pending ping. Reading or
listing never acknowledges; ack is explicit and separate. A
pending ping re-surfaces in the wake set once per ack-timeout
window, tracked by last_woken_at.

The file is a working set, not the history: the ledger holds
the ping event sequence at its own retention. Two mechanisms
keep the working set cheap to stand behind (the health-
wedge cure — at 4,119 pings the file cost 0.3–0.6s to
re-parse on every operation, every operation took the one
lock to do it, and the health surface's own depth() call
queued behind the convoy until supervision read a live,
dispatching server as dead):

- Reload is keyed on the file's own change stamp
  (mtime_ns + size): an operation re-reads only when the
  file actually changed since this process last loaded it.
  Writes are temp-file-plus-rename, so another process's
  write always moves the stamp — the freshness the
  reload-every-operation form bought is kept, at a stat's
  price instead of a full parse's.
- Terminal pings (acked, void) are pruned at save time
  once past TERMINAL_RETENTION_DAYS: the file stops
  growing with history, so the parse that a stamp change
  does trigger stays bounded by the working set.
"""
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from .ledger import iso, parse_iso
from .stateio import StateError, read_json, write_json

UTC = timezone.utc
PING_KINDS = ("agent-due", "escalation", "report")
# The working-set horizon for terminal pings: far past any
# live wake/ack flow (ack windows are minutes), far short of
# the ledger's 90-day event retention, which is where the
# history of a pruned ping remains readable.
TERMINAL_RETENTION_DAYS = 7


class Outbox:
    def __init__(self, state_dir, ledger=None):
        self.path = os.path.join(state_dir, "outbox.json")
        self.ledger = ledger
        self._lock = threading.RLock()
        self._pings = []
        self._stamp = None
        self._reload()

    def _file_stamp(self):
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _reload(self):
        # The file is the source of truth, shared across processes
        # (the server, bin/sched, a drill planting a ping). Writes
        # are temp-file-plus-rename, so a reload never tears, and
        # another process's write always moves the file's stamp.
        # Every public operation reloads first — but the reload
        # re-reads only when the stamp moved; an unstamped cache
        # would hide other processes' writes and let this
        # process's next save silently resurrect an acked ping,
        # which is what the stamp keying exists to prevent.
        stamp = self._file_stamp()
        if stamp is not None and stamp == self._stamp:
            return
        data = read_json(self.path, {"pings": []})
        if not isinstance(data, dict) or not isinstance(data.get("pings"), list):
            raise StateError(f"outbox state {self.path} has the wrong shape")
        self._pings = data["pings"]
        self._stamp = stamp

    def _prune_terminal(self, now):
        """Drop terminal pings past the retention horizon.
        A ping whose terminal stamp cannot be read is kept:
        the prune never drops what it cannot date."""
        horizon = timedelta(days=TERMINAL_RETENTION_DAYS)
        kept = []
        for ping in self._pings:
            if ping.get("state") == "pending":
                kept.append(ping)
                continue
            raw = ping.get("acked_at") or ping.get("created")
            try:
                stamp = parse_iso(raw) if raw else None
            except (TypeError, ValueError, AttributeError):
                stamp = None
            if stamp is None or now - stamp < horizon:
                kept.append(ping)
        self._pings = kept

    def _save(self):
        self._prune_terminal(datetime.now(UTC))
        write_json(self.path, {"pings": self._pings})
        self._stamp = self._file_stamp()

    def _log(self, kind, **fields):
        if self.ledger is not None:
            self.ledger.record(kind, **fields)

    def add_or_coalesce(self, job_id, due_instant, kind, body_ref=None, detail=None, now=None):
        if kind not in PING_KINDS:
            raise ValueError(f"bad ping kind {kind!r}")
        now = now or datetime.now(UTC)
        with self._lock:
            self._reload()
            for ping in self._pings:
                if ping["job_id"] == job_id and ping["state"] == "pending" and ping["kind"] == kind:
                    ping["due"] = iso(due_instant)
                    ping["coalesced_count"] += 1
                    if detail:
                        ping["detail"] = detail
                    self._save()
                    self._log("ping_coalesced", ping_id=ping["id"], job_id=job_id,
                              coalesced_count=ping["coalesced_count"])
                    return ping, False
            ping = {
                "id": uuid.uuid4().hex[:12],
                "job_id": job_id,
                "due": iso(due_instant),
                "kind": kind,
                "body_ref": body_ref,
                "detail": detail or {},
                "created": iso(now),
                "state": "pending",
                "coalesced_count": 1,
                "last_woken_at": None,
            }
            self._pings.append(ping)
            self._save()
            self._log("ping_created", ping_id=ping["id"], job_id=job_id, ping_kind=kind)
            return ping, True

    def pending(self):
        with self._lock:
            self._reload()
            return [p for p in self._pings if p["state"] == "pending"]

    def depth(self):
        return len(self.pending())

    def get(self, ping_id):
        with self._lock:
            self._reload()
            for ping in self._pings:
                if ping["id"] == ping_id:
                    return ping
            return None

    def wake_set(self, now, ack_timeout_secs):
        """Pending pings the keeper should wake for now: never woken
        yet, or last woken at least one ack-timeout window ago
        (spec Step 4 — once per window, not every poll)."""
        out = []
        for ping in self.pending():
            last = ping.get("last_woken_at")
            if last is None or (now - parse_iso(last)).total_seconds() >= ack_timeout_secs:
                out.append(ping)
        return out

    def mark_woken(self, ping_ids, now=None):
        now = now or datetime.now(UTC)
        with self._lock:
            self._reload()
            changed = False
            for ping in self._pings:
                if ping["id"] in ping_ids and ping["state"] == "pending":
                    ping["last_woken_at"] = iso(now)
                    changed = True
                    self._log("ping_woken", ping_id=ping["id"], job_id=ping["job_id"])
            if changed:
                self._save()

    def ack(self, ping_id):
        """Explicit acknowledgement after the work is done. Acking an
        already-acked or void ping is a no-op, ledgered (Step 4)."""
        with self._lock:
            ping = self.get(ping_id)
            if ping is None:
                return None
            if ping["state"] != "pending":
                self._log("ack_noop", ping_id=ping_id, job_id=ping["job_id"], state=ping["state"])
                return ping
            ping["state"] = "acked"
            ping["acked_at"] = iso(datetime.now(UTC))
            self._save()
            self._log("ping_acked", ping_id=ping_id, job_id=ping["job_id"])
            return ping

    def void_for_job(self, job_id, reason="entry_deleted"):
        """Void a job's pending pings (its entry was deleted, spec
        Step 3 / EC-16). Returns how many were voided."""
        with self._lock:
            self._reload()
            count = 0
            for ping in self._pings:
                if ping["job_id"] == job_id and ping["state"] == "pending":
                    ping["state"] = "void"
                    ping["void_reason"] = reason
                    count += 1
                    self._log("ping_voided", ping_id=ping["id"], job_id=job_id, reason=reason)
            if count:
                self._save()
            return count
