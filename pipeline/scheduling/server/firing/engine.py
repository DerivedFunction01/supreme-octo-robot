"""The engine: rescans the registry every tick, fires due entries,
and applies the report rules. Semantics per spec Steps 3–4 and
EC-1–EC-11:

- a fired grid point is consumed (next_due advanced and persisted)
  BEFORE the run starts, so a crash or a backward clock jump can
  delay but never duplicate a run (EC-4);
- missed points collapse to the latest, with the count ledgered
  (EC-1); a still-running entry skips its point (no self-overlap);
- entries due on the same tick are dispatched in entry-id order,
  each execution in its own thread so one long job cannot block
  the cadence of the others (isolation);
- a registry that fails to parse keeps the last-good registry
  running and escalates once per distinct error (EC-9);
- corrupt durable state is fail-safe: no firing at all (EC-10).
"""
import os
import threading
from datetime import datetime, timezone

from . import executor, schedule
from . import stackdump as stackdump_mod
from .. import config as config_mod
from .. import registry
from dispatch.ledger import Ledger, iso, parse_iso
from dispatch.outbox import Outbox
from dispatch.stateio import StateError, read_json, write_json

UTC = timezone.utc
REGISTRY_JOB_ID = "scheduler-registry"


class LockError(Exception):
    pass


class Engine:
    def __init__(self, values, jobs_dir=None, state_dir=None, now_fn=None, inline=False):
        self.values = values
        self.home = values["home"]
        self.jobs_dir = jobs_dir or os.path.join(self.home, "jobs")
        self.state_dir = state_dir or os.path.join(self.home, "state")
        self.now_fn = now_fn or (lambda: datetime.now(UTC))
        self.started_at = self.now_fn()
        self.inline = inline
        os.makedirs(self.state_dir, exist_ok=True)
        self.ledger = Ledger(self.state_dir)
        self.entries = {}
        self.registry_errors = []
        self.state_error = None
        self.last_tick = None
        self._registry_error_sig = None
        self._running = {}
        self._lock = threading.Lock()
        self._lock_path = os.path.join(self.state_dir, "server.lock")
        self._lock_held = False
        self._last_prune_day = None
        # Stack-dump watchdog (stackdump-contract: v1): the
        # checker thread exercises this engine's health_data —
        # the computation the HTTP health route serves — so a
        # dump names a stalled health path, not a stalled tick.
        # Constructed here, started by the serve entry point
        # (start_stackdump); test engines never start it.
        self.stackdump = stackdump_mod.StackDumpWatchdog(
            name="scheduler",
            health=self.health_data,
            dump_path=os.path.join(self.state_dir, "stackdumps.log"),
            cadence_s=values.get("stackdump_cadence_s", 5.0),
            threshold_s=values.get("stackdump_threshold_s", 15.0),
            repeat_s=values.get("stackdump_repeat_s", 60.0),
            max_bytes=values.get("stackdump_max_bytes",
                                 16 * 1024 * 1024),
        )
        try:
            self.outbox = Outbox(self.state_dir, self.ledger)
            self._next_due = self._load_next_due()
        except StateError as exc:
            self.outbox = None
            self._next_due = {}
            self.state_error = str(exc)
            self.ledger.record("state_error", error=str(exc))
        if self.state_error is None:
            self._rescan(self.now_fn())

    # ---------------------------------------------------------- lock (EC-11)

    def acquire_lock(self):
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pid = None
            try:
                with open(self._lock_path, "r", encoding="utf-8") as fh:
                    pid = int(fh.read().strip())
                os.kill(pid, 0)
            except (ValueError, OSError):
                pid = None  # stale or unreadable lock: take over
            if pid is not None:
                raise LockError(f"another scheduler instance holds the lock (pid {pid})")
            # O_TRUNC matters: a shorter pid written over a
            # longer stale one would otherwise leave trailing
            # digits, corrupting the pid for every later
            # reader of the lock file.
            fd = os.open(self._lock_path,
                         os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        self._lock_held = True

    def release_lock(self):
        if self._lock_held:
            try:
                os.unlink(self._lock_path)
            except OSError:
                pass
            self._lock_held = False

    # ---------------------------------------------------------- state

    def _load_next_due(self):
        raw = read_json(os.path.join(self.state_dir, "next_due.json"), {})
        if not isinstance(raw, dict):
            raise StateError("next_due.json has the wrong shape")
        out = {}
        for job_id, text in raw.items():
            try:
                out[job_id] = parse_iso(text)
            except Exception as exc:
                raise StateError(f"next_due for {job_id} is unparseable: {text!r}") from exc
        return out

    def _save_next_due(self):
        write_json(
            os.path.join(self.state_dir, "next_due.json"),
            {job_id: iso(inst) for job_id, inst in self._next_due.items()},
        )

    # ---------------------------------------------------------- registry

    def _initial_due(self, entry, now):
        cadence = entry.cadence
        if cadence["type"] == "interval":
            return now + schedule.parse_every(cadence["every"])
        return schedule.first_point_at_or_after(cadence, entry.timezone_name(self.values["default_timezone"]), now)

    def _rescan(self, now):
        # The server's load is the live context: a missing body
        # is a defect here and quarantines like any other error,
        # never the overlay-absent pass a clean checkout takes.
        entries, errors = registry.load_dir(
            self.jobs_dir, self.home, anchors=config_mod.anchors(self.values),
            require_bodies=True,
        )
        if errors:
            self.registry_errors = errors
            sig = "\n".join(errors)
            if sig != self._registry_error_sig:
                self._registry_error_sig = sig
                self.ledger.record("registry_error", errors=errors)
                if self.outbox is not None:
                    self.outbox.add_or_coalesce(
                        REGISTRY_JOB_ID, now, "escalation",
                        detail={"errors": errors}, now=now,
                    )
            return  # keep the last-good registry (EC-9)
        self.registry_errors = []
        self._registry_error_sig = None
        previous = set(self.entries)
        self.entries = entries
        changed = False
        for job_id in previous - set(entries):
            if self.outbox is not None:
                self.outbox.void_for_job(job_id)
            if job_id in self._next_due:
                del self._next_due[job_id]
                changed = True
            self.ledger.record("entry_removed", job_id=job_id)
        for job_id, entry in entries.items():
            # Presence in the registry is admission (contract
            # 13): an entry stands here only by being written
            # through the one writer path, so every entry in
            # the rescan seeds its due. The pinned engine's
            # migrated-only clause is deliberately not carried
            # (amendment 3) — the field does not exist here.
            if job_id not in self._next_due:
                self._next_due[job_id] = self._initial_due(entry, now)
                changed = True
        if changed:
            self._save_next_due()

    # ---------------------------------------------------------- firing

    def tick(self, now=None):
        now = now or self.now_fn()
        self.last_tick = now
        if self.state_error is not None:
            return
        self._rescan(now)
        self._maybe_prune(now)
        for job_id in sorted(self.entries):
            entry = self.entries[job_id]
            if entry.status != "active":
                continue
            due_at = self._next_due.get(job_id)
            if due_at is None or due_at > now:
                continue
            tz_name = entry.timezone_name(self.values["default_timezone"])
            latest, collapsed, new_due = schedule.advance(entry.cadence, tz_name, due_at, now)
            with self._lock:
                running = job_id in self._running
            self._next_due[job_id] = new_due
            self._save_next_due()  # consumed before the run starts (EC-4)
            if running:
                self.ledger.record("skipped_overlap", job_id=job_id, due=iso(latest),
                                   collapsed=collapsed)
                continue
            if collapsed > 1:
                self.ledger.record("catchup", job_id=job_id, due=iso(latest), collapsed=collapsed)
            if entry.kind == "agent":
                self.outbox.add_or_coalesce(job_id, latest, "agent-due",
                                            body_ref=entry.get("body"), now=now)
                self.ledger.record("agent_due", job_id=job_id, due=iso(latest), collapsed=collapsed)
            elif self.inline:
                self._execute(entry, latest, collapsed)
            else:
                thread = threading.Thread(target=self._execute, args=(entry, latest, collapsed),
                                          name=f"run-{job_id}", daemon=True)
                with self._lock:
                    self._running[job_id] = thread
                thread.start()

    def _execute(self, entry, due, collapsed):
        try:
            # The fired record: a run stands in the ledger
            # from the moment it starts, carrying its budget,
            # so a serve that dies mid-run leaves a
            # non-terminal record the restart-reconcile sweep
            # can mark interrupted — instead of a fire that
            # vanishes with the process, its only trace the
            # consumed next_due. The completion "run" record
            # below is the same fire's terminal event; the
            # sweep pairs the two on (job_id, due).
            self.ledger.record(
                "run_started", job_id=entry.id, due=iso(due),
                timeout_secs=entry.timeout_secs, collapsed=collapsed,
            )
            result = executor.run_entry(entry, due, self.values["capture_cap_bytes"])
            self.ledger.record(
                "run", job_id=entry.id, due=iso(due), status=result.status,
                exit_code=result.exit_code, matched_pattern=result.matched_pattern,
                error=result.error, collapsed=collapsed,
                stdout_tail=result.stdout_tail[-500:], stderr_tail=result.stderr_tail[-500:],
            )
            self._apply_report_rules(entry, due, result)
        finally:
            with self._lock:
                self._running.pop(entry.id, None)

    def _apply_report_rules(self, entry, due, result):
        report = entry.report
        if result.status != "ok":
            if report["when"] != "never":
                self.outbox.add_or_coalesce(
                    entry.id, due, "escalation",
                    body_ref=entry.get("escalate_body"), detail=result.detail(),
                )
            return
        fire = report["when"] == "always"
        if not fire and report["report_patterns"]:
            fire = any(p in result.output for p in report["report_patterns"])
        if not fire and report["when"] == "on_output":
            fire = _has_reportable_output(result, report["quiet_patterns"])
        if fire:
            self.outbox.add_or_coalesce(
                entry.id, due, "report",
                detail={"exit_code": result.exit_code,
                        "stdout_tail": result.stdout_tail[-2000:],
                        "stderr_tail": result.stderr_tail[-2000:]},
            )

    def _maybe_prune(self, now):
        day = now.date()
        if self._last_prune_day != day:
            self._last_prune_day = day
            dropped = self.ledger.prune(self.values["ledger_retention_days"], now=now)
            if dropped:
                self.ledger.record("ledger_pruned", dropped=dropped)

    def next_due_map(self):
        return dict(self._next_due)

    # ---------------------------------------------------------- status

    def wait_idle(self, timeout=None):
        with self._lock:
            threads = list(self._running.values())
        for thread in threads:
            thread.join(timeout=timeout)

    def start_stackdump(self):
        self.stackdump.start()

    def health_data(self):
        if self.state_error is not None:
            status = "state_error"
        elif self.registry_errors:
            status = "registry_error"
        else:
            status = "ok"
        return {
            "status": status,
            "state_error": self.state_error,
            "registry_errors": self.registry_errors,
            "registry_count": len(self.entries),
            "last_tick": iso(self.last_tick) if self.last_tick else None,
            "outbox_depth": self.outbox.depth() if self.outbox else 0,
            "running": sorted(self._running),
            "stackdump_last_dump_at": self.stackdump.last_dump_at,
        }


def _has_reportable_output(result, quiet_patterns):
    for line in result.output.splitlines():
        text = line.strip()
        if text and not any(q in text for q in quiet_patterns):
            return True
    return False
