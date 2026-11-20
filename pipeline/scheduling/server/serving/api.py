"""The /api/v1 read API: every derivation the viewer shows is
computed here and served ready (backend does the work; the
viewer is a consumer). Read-only by design — ack, suspend and
admit stay in bin/sched and chat. Status semantics live here:
an accepted non-zero exit is a normal outcome, never dressed
up as a failure, and absent data is served as null, never
back-filled."""
import os
from datetime import datetime, timedelta, timezone

from dispatch.ledger import iso, parse_iso
from . import classification as classification_mod
from ..entries import configblocks
from ..registry import expected_wake_per_day

UTC = timezone.utc
FAILURE_STATUSES = ("failure", "timeout", "spawn_error")


def cadence_label(entry):
    cad = entry.cadence
    if cad["type"] == "interval":
        return f"every {cad['every']}"
    if cad["type"] == "daily":
        return f"daily {cad['at']}"
    return f"weekly {', '.join(cad['dow'])} {cad['at']}"


def outcome_label(rec):
    """The one outcome wording, used everywhere the API serves a run."""
    status = rec.get("status")
    code = rec.get("exit_code")
    if status == "ok":
        if code in (0, None):
            return "OK"
        return f"Exit {code} · normal"
    if status == "failure":
        return f"Failed · exit {code}"
    if status == "timeout":
        return "Timed out"
    if status == "spawn_error":
        return "Could not start"
    return status or "—"


def _run_view(rec):
    if rec is None:
        return None
    return {
        "ts": rec["ts"], "due": rec.get("due"), "status": rec.get("status"),
        "exit_code": rec.get("exit_code"), "label": outcome_label(rec),
        "matched_pattern": rec.get("matched_pattern"),
        "collapsed": rec.get("collapsed"), "error": rec.get("error"),
        "stdout_tail": rec.get("stdout_tail"), "stderr_tail": rec.get("stderr_tail"),
    }


def _agent_activity(engine, entry, now, batch=None):
    """The agent-kind counterpart of the run view. An agent job
    never produces `run` records: at each due the engine records
    `agent_due` and raises an outbox ping, and the ack closes
    the cycle. Serve that lifecycle ready — the latest due, its
    ack state, and the 24h counts — with activity labels, never
    run language. Returns (last_activity, activity_24h); both
    are None-shaped honestly when no due is on record.

    `batch` carries the list view's pre-fetched data for this
    job ({counts, dues, acks, pending}); without it the data is
    queried per job, as the detail view does."""
    ledger = engine.ledger
    epoch_24h = (now - timedelta(hours=24)).timestamp()
    if batch is not None:
        counts = {"dues": batch["counts"]["dues"],
                  "acked": batch["counts"]["acked"],
                  "overdue": False}
        dues = batch["dues"]
        pending_all = batch["pending"]
        acks = batch["acks"]
    else:
        counts = {"dues": ledger.count_since(epoch_24h, job_id=entry.id,
                                             kinds=["agent_due"]),
                  "acked": ledger.count_since(epoch_24h, job_id=entry.id,
                                              kinds=["ping_acked"]),
                  "overdue": False}
        dues = ledger.query(job_id=entry.id, kinds=["agent_due"], limit=50)
        pending_all = engine.outbox.pending() if engine.outbox else []
        acks = None
    if not dues:
        return None, counts
    last = dues[0]
    pending = [p for p in pending_all
               if p["job_id"] == entry.id]
    if pending:
        ping = pending[0]  # pending() is oldest first
        age = (now - parse_iso(ping["created"])).total_seconds()
        overdue = age > engine.values["outbox_ack_timeout_secs"]
        counts["overdue"] = overdue
        view = {"ts": last["ts"], "due": last.get("due"),
                "state": "overdue" if overdue else "pending",
                "label": "Past ack timeout" if overdue else "Ping pending",
                "tone": "fail" if overdue else "warn",
                "acked_at": None, "collapsed": last.get("collapsed")}
        return view, counts
    if acks is None:
        acks = ledger.query(job_id=entry.id, kinds=["ping_acked"], limit=1)
    ack = acks[0] if acks and acks[0]["ts"] >= last["ts"] else None
    view = {"ts": last["ts"], "due": last.get("due"),
            "state": "acked" if ack else "served",
            "label": "Served · acked" if ack else "Served",
            "tone": "ok",
            "acked_at": ack["ts"] if ack else None,
            "collapsed": last.get("collapsed")}
    return view, counts


def _failure_streak(runs_newest_first):
    streak = 0
    for rec in runs_newest_first:
        if rec.get("status") in FAILURE_STATUSES:
            streak += 1
        else:
            break
    return streak


def job_view(engine, entry, now, batch=None):
    ledger = engine.ledger
    if batch is not None:
        runs = batch["runs"]
        ok_24h, bad_24h = batch["run_counts"]
    else:
        runs = ledger.query(job_id=entry.id, kinds=["run"], limit=50)
        epoch_24h = (now - timedelta(hours=24)).timestamp()
        ok_24h = ledger.count_since(epoch_24h, job_id=entry.id,
                                     kinds=["run"], statuses=["ok"])
        bad_24h = sum(ledger.count_since(epoch_24h, job_id=entry.id,
                                         kinds=["run"], statuses=[s])
                      for s in FAILURE_STATUSES)
    last = runs[0] if runs else None
    due = engine.next_due_map().get(entry.id)
    if entry.kind == "agent":
        last_activity, activity_24h = _agent_activity(
            engine, entry, now,
            batch=batch["agent"] if batch is not None else None)
    else:
        last_activity, activity_24h = None, None
    return {
        "id": entry.id,
        "kind": entry.kind,
        "status": entry.status,
        "suspend_reason": entry.get("suspend_reason"),
        "owner": entry.get("owner"),
        "cadence": entry.cadence,
        "cadence_label": cadence_label(entry),
        "timezone": entry.timezone_name(engine.values["default_timezone"]),
        "next_due": iso(due) if due else None,
        "next_due_in_secs": int((due - now).total_seconds()) if due else None,
        "last_run": _run_view(last),
        "last_activity": last_activity,
        "activity_24h": activity_24h,
        "runs_24h": {"total": ok_24h + bad_24h, "ok": ok_24h, "failed": bad_24h},
        "failure_streak": _failure_streak(runs),
        "expected_wake_per_day": expected_wake_per_day(entry),
        "report_when": entry.report["when"],
        # The classification axis (contract 09, amendment
        # 2026-11-13): served, never derived client-side.
        **classification_mod.classify(entry.id),
    }


def overview(engine, now):
    values = engine.values
    health = engine.health_data()
    entries = list(engine.entries.values())
    by_kind, by_status = {}, {}
    for entry in entries:
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
        by_status[entry.status] = by_status.get(entry.status, 0) + 1
    pending = engine.outbox.pending() if engine.outbox else []
    pings_by_kind = {}
    for ping in pending:
        pings_by_kind[ping["kind"]] = pings_by_kind.get(ping["kind"], 0) + 1
    timeout = values["outbox_ack_timeout_secs"]
    aged = sum(1 for p in pending
               if (now - parse_iso(p["created"])).total_seconds() > timeout)
    epoch_24h = (now - timedelta(hours=24)).timestamp()
    ledger = engine.ledger
    # The 24h totals ride ONE grouped pass over the window
    # (the jobs_list shape): the per-counter count_since
    # fan-out re-walked the window once per counter — and
    # once per failure status — on every overview request.
    # The grouped sums are the same counts by construction:
    # same window predicate, partitioned by (job, kind,
    # status) and re-summed here.
    grouped = ledger.counts_since_grouped(
        epoch_24h, kinds=["run", "ping_woken", "ping_created"])
    runs_24h = sum(n for (_job, kind, _status), n in grouped.items()
                   if kind == "run")
    failures_24h = sum(n for (_job, kind, status), n in grouped.items()
                       if kind == "run" and status in FAILURE_STATUSES)
    wakeups_24h = sum(n for (_job, kind, _status), n in grouped.items()
                      if kind == "ping_woken")
    pings_created_24h = sum(n for (_job, kind, _status), n in grouped.items()
                            if kind == "ping_created")
    last_prune = ledger.query(kinds=["ledger_pruned"], limit=1)
    stats = ledger.stats()
    return {
        "served_at": iso(now),
        "server_now": iso(now),
        "status": health["status"],
        "state_error": health["state_error"],
        "registry_errors": health["registry_errors"],
        "pid": os.getpid(),
        "uptime_secs": int((now - engine.started_at).total_seconds()),
        "last_tick": health["last_tick"],
        "running": health["running"],
        "registry": {"total": len(entries), "by_kind": by_kind,
                     "by_status": by_status,
                     # The migrated count, in the pinned server's
                     # shape: it summed the entries carrying the
                     # flag. This format abolished the field
                     # family (contract 14, amendment 3) — an
                     # entry stands in the registry only by
                     # admission through the one writer path
                     # (contract 13), so every entry here is a
                     # migrated entry and the count is the total.
                     "migrated": len(entries)},
        "outbox": {"depth": len(pending), "by_kind": pings_by_kind,
                   "aged": aged},
        "totals_24h": {"runs": runs_24h, "failures": failures_24h,
                       "wakeups_served": wakeups_24h,
                       "pings_created": pings_created_24h},
        "expected_wake_per_day": round(
            sum(expected_wake_per_day(e) for e in entries
                if e.status == "active"), 1),
        "storage": {"kind": "sqlite", "events": stats["events"],
                    "db_bytes": stats["db_bytes"], "oldest": stats["oldest"],
                    "newest": stats["newest"],
                    "retention_days": values["ledger_retention_days"],
                    "last_prune": ({"ts": last_prune[0]["ts"],
                                    "dropped": last_prune[0].get("dropped")}
                                   if last_prune else None)},
        "config": {"tick_secs": values["tick_secs"], "port": values["port"],
                   "default_timezone": values["default_timezone"],
                   "outbox_ack_timeout_secs": timeout},
    }


def jobs_list(engine, now):
    """The list view reads its ledger data in bulk: one grouped
    count pass and one bucketed recent-records pass per kind,
    instead of ~15 per-job queries (the fan-out, multiplied by
    a fresh connection per query, was the 11–25s cost the D-6
    proof measured). The per-job views built from the batches
    are field-identical to the detail path's per-job queries."""
    entries = [engine.entries[job_id] for job_id in sorted(engine.entries)]
    epoch_24h = (now - timedelta(hours=24)).timestamp()
    grouped = engine.ledger.counts_since_grouped(
        epoch_24h, kinds=["run", "agent_due", "ping_acked"])
    slices = {}
    for (job_id, kind, status), n in grouped.items():
        slices.setdefault(job_id, {})[(kind, status)] = n
    job_ids = [entry.id for entry in entries]
    runs_by_job = engine.ledger.recent_by_job(["run"], 50, job_ids=job_ids)
    agent_ids = [entry.id for entry in entries if entry.kind == "agent"]
    dues_by_job = (engine.ledger.recent_by_job(
        ["agent_due"], 50, job_ids=agent_ids) if agent_ids else {})
    acks_by_job = (engine.ledger.recent_by_job(
        ["ping_acked"], 1, job_ids=agent_ids) if agent_ids else {})
    pending = engine.outbox.pending() if engine.outbox else []
    items = []
    for entry in entries:
        counts = slices.get(entry.id, {})
        ok_24h = counts.get(("run", "ok"), 0)
        bad_24h = sum(counts.get(("run", s), 0) for s in FAILURE_STATUSES)
        batch = {"runs": runs_by_job.get(entry.id, []),
                 "run_counts": (ok_24h, bad_24h)}
        if entry.kind == "agent":
            batch["agent"] = {
                "counts": {
                    "dues": sum(n for (k, _s), n in counts.items()
                                if k == "agent_due"),
                    "acked": sum(n for (k, _s), n in counts.items()
                                 if k == "ping_acked")},
                "dues": dues_by_job.get(entry.id, []),
                "acks": acks_by_job.get(entry.id, []),
                "pending": pending}
        items.append(job_view(engine, entry, now, batch=batch))
    return {"served_at": iso(now), "jobs": items}


def job_detail(engine, job_id, now):
    entry = engine.entries.get(job_id)
    if entry is None:
        return None
    view = job_view(engine, entry, now)
    catalog = entry.get("catalog")
    view["detail"] = {
        "title": entry.get("title"),
        "timeout_secs": entry.timeout_secs,
        "ok_exit_codes": entry.report["ok_exit_codes"],
        "run": entry.get("run"),
        "body": entry.get("body"),
        "escalate_body": entry.get("escalate_body"),
        "state_paths": entry.get("state_paths"),
        "report": entry.report,
        "classification": entry.get("classification"),
        "lifetime": entry.get("lifetime"),
        # The detail projections the S8 dispositions named
        # (contract 09): the entry record already carries
        # these fields; absent data serves as null, never
        # back-filled. `catalog` projects to the view axis
        # only — parameters and setup are adoption
        # machinery, not view data.
        "suspended_on": entry.get("suspended_on"),
        "self_removal": entry.get("self_removal"),
        "catalog": ({"origin": catalog.get("origin"),
                     "generality": catalog.get("generality"),
                     "use_case": catalog.get("use_case")}
                    if isinstance(catalog, dict) else None),
        # The entry's config block, projected to the served
        # configView (null when the entry carries none).
        "config": configblocks.view_of(entry),
    }
    runs = engine.ledger.query(job_id=job_id, kinds=["run"], limit=50)
    view["recent_runs"] = [_run_view(rec) for rec in runs]
    dues = engine.ledger.query(job_id=job_id, kinds=["agent_due"], limit=50)
    view["recent_dues"] = [
        {"ts": rec["ts"], "due": rec.get("due"),
         "collapsed": rec.get("collapsed")} for rec in dues]
    pings = engine.ledger.query(
        job_id=job_id,
        kinds=["ping_created", "ping_woken", "ping_acked", "ping_coalesced",
               "ping_voided"],
        limit=20)
    view["ping_history"] = [
        {"ts": rec["ts"], "kind": rec["kind"], "ping_id": rec.get("ping_id"),
         "ping_kind": rec.get("ping_kind"), "detail": _event_detail(rec)}
        for rec in pings]
    return view


def pings_list(engine, now):
    timeout = engine.values["outbox_ack_timeout_secs"]
    out = []
    for ping in (engine.outbox.pending() if engine.outbox else []):
        age = int((now - parse_iso(ping["created"])).total_seconds())
        item = dict(ping)
        item["age_secs"] = age
        item["overdue"] = age > timeout
        out.append(item)
    out.sort(key=lambda p: p["created"])  # oldest first, always
    return {"served_at": iso(now), "pings": out}


def pings_recent(engine, now, limit=20):
    """The acked-pings window (G5, contract 09): the most
    recently acked pings, newest ack first, served as their
    outbox records. The window is built from the ledger's
    ping_acked events joined to the outbox store — acked
    records leave `pending()` the moment they are acked, so
    the ledger is the only place their order survives."""
    out = []
    if engine.outbox is None:
        return {"served_at": iso(now), "pings": out}
    seen = set()
    acks = engine.ledger.query(kinds=["ping_acked"], limit=limit * 4)
    for event in acks:
        ping_id = event.get("ping_id")
        if not ping_id or ping_id in seen:
            continue
        seen.add(ping_id)
        rec = engine.outbox.get(ping_id)
        if rec is not None and rec.get("state") == "acked":
            out.append(dict(rec))
        if len(out) >= limit:
            break
    return {"served_at": iso(now), "pings": out}


def _event_detail(rec):
    kind = rec["kind"]
    if kind == "run":
        text = outcome_label(rec)
        if rec.get("matched_pattern"):
            text += f" · matched {rec['matched_pattern']}"
        return text
    if kind in ("ping_created", "ping_woken", "ping_acked", "ping_voided",
                "ping_coalesced"):
        return f"ping {rec.get('ping_kind') or ''} {rec.get('ping_id') or ''}".strip()
    if kind == "agent_due":
        return "agent due"
    if kind == "catchup":
        return f"caught up {rec.get('collapsed')} collapsed points"
    if kind == "skipped_overlap":
        return "skipped — previous run still running"
    if kind == "ledger_pruned":
        return f"pruned {rec.get('dropped')} events past retention"
    if kind == "registry_error":
        return "registry failed to parse — last-good registry kept"
    if kind == "state_error":
        return f"state error: {rec.get('error')}"
    if kind == "op":
        text = f"{rec.get('op') or '?'} {rec.get('target') or ''}".strip()
        text += f" by {rec.get('caller') or '?'} — {rec.get('status') or '?'}"
        if rec.get("error"):
            text += f" ({rec['error']})"
        if rec.get("exit_code") is not None:
            text += f" exit {rec['exit_code']}"
        return text
    return kind


def ledger_feed(engine, now, limit=50):
    records = engine.ledger.query(limit=limit)
    events = [{"ts": rec["ts"], "kind": rec["kind"],
               "job_id": rec.get("job_id"), "detail": _event_detail(rec)}
              for rec in records]
    return {"served_at": iso(now), "events": events}
