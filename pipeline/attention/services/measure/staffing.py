"""Staffing supervision (spec §1.11): capacity collection
and the measured staffing defect, derived at assembly.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from attention.infra import panel_client, run_records
from attention.services import programmes
from attention.services.dispatch import dispatch as dispatch_mod
from attention.services.measure.staffing_rows import (
    _armed_rows,
    _as_dt,
    _blocked_rows,
    _family_rows,
    _frontier_rows,
    _lane_rows,
    lane_blocks,
    _orphan_rows,
    _overdue_rows,
    _owner_waiting_rows,
    _phantom_rows,
    _record_rows,
    _row,
    _terminal_rows,
    _unlanded_rows,
    _unrouted_rows,
    _worktree_rows,
)
from attention.services.reads import digest as digest_mod
from attention.services.reads import model
from attention.settings import Settings


def _spec_index(payload: dict) -> dict:
    specs = payload.get("specs") if isinstance(payload, dict) else None
    if not isinstance(specs, list):
        return {}
    return {s["id"]: s for s in specs if isinstance(s, dict) and s.get("id")}


def _session_view(entry: dict, specs: dict) -> dict | None:
    record = entry.get("record") if isinstance(entry.get("record"), dict) else {}
    session = entry.get("session") or record.get("session")
    if not session:
        return None
    action = entry.get("action") or entry.get("state") or entry.get("status")
    if action is not None and action != "active":
        return None
    if action is None and entry.get("live") is False:
        return None
    raw_shape = entry.get("shape") or record.get("shape")
    shape_id = raw_shape if isinstance(raw_shape, str) else None
    spec: dict = {}
    if isinstance(raw_shape, dict):
        spec.update(raw_shape)
        shape_id = raw_shape.get("id") or shape_id
    for extra in (record.get("shape_spec"), entry.get("spec")):
        if isinstance(extra, dict):
            spec.update(extra)
    if shape_id and shape_id in specs:
        spec = {**spec, **specs[shape_id]}
    high_mem = spec.get("high_mem", entry.get("high_mem", record.get("high_mem")))
    if high_mem is False:
        return None
    return {"session": session, "shape": shape_id, "high_mem": high_mem}


def collect_capacity(state: dict, settings: Settings, now: datetime) -> bool:
    """Refresh the cached capacity snapshot from the
    panel's portions; a failed read keeps the last good
    snapshot and records the reason."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        records_future = pool.submit(
            panel_client.fetch_records, settings.panel_url, settings.panel_timeout_s
        )
        specs_future = pool.submit(
            panel_client.fetch_specs, settings.panel_url, settings.panel_timeout_s
        )
        try:
            records_payload = records_future.result()
        except panel_client.PanelUnavailable as err:
            state["capacity_error"] = str(err)
            return False
        try:
            specs_payload = specs_future.result()
        except panel_client.PanelUnavailable:
            specs_payload = {}
    specs = _spec_index(specs_payload)
    entries = records_payload.get("records")
    if not isinstance(entries, list):
        state["capacity_error"] = "Lease panel sent an unreadable reply."
        return False
    sessions = []
    for entry in entries:
        if isinstance(entry, dict):
            view = _session_view(entry, specs)
            if view is not None:
                sessions.append(view)
    live_names = [s["session"] for s in sessions]
    try:
        running_now = run_records.read_running(settings.run_records_dir, now)
    except run_records.RunRecordsUnavailable:
        running_now = []
    session_runs = {name: 0 for name in live_names}
    for run in running_now:
        if run["session"] in session_runs:
            session_runs[run["session"]] += 1
    previous = state.get("capacity_snapshot") or {}
    previous_idle = previous.get("idle_since") or {}
    idle_since = {}
    for name in live_names:
        if session_runs[name] > 0:
            continue
        idle_since[name] = previous_idle.get(name) or now
    state["capacity_snapshot"] = {
        "at": now,
        "sessions": sessions,
        "session_runs": session_runs,
        "idle_since": idle_since,
        "specs": [
            {"id": s["id"], "label": s.get("label"), "high_mem": s.get("high_mem")}
            for s in specs.values()
        ],
    }
    state["capacity_error"] = None
    return True


def _unavailable(state: dict, snapshot, reason: str, rows: list | None = None) -> dict:
    return {
        "available": False,
        "reason": reason,
        "snapshot_at": model._iso(snapshot["at"]) if snapshot else None,
        "sessions_live": 0,
        "idle_minutes_total": 0,
        "sessions": [],
        "rows": rows or [],
    }


def _scope_topics(state: dict) -> dict:
    """Topics with live work, keyed by programme slug:
    armed entries grouped under their programme. A
    lane's record is its latest checkpoint stamp (or its
    arming time before its first stamp) and its
    workbench project — the post's refs, re-homed to the
    armed row. The lane handle is the programme's
    coordinator handle: an armed row names its todo,
    never a posting lane. A programme with no armed
    entries has no live work and is out of scope."""
    topics: dict[str, list] = {}
    stamps = state.get("stamp_snapshot") or {}
    for programme in programmes.active_declarations(state):
        handle = (programme.get("handles") or [programme["slug"]])[0]
        stamps_for = (stamps.get(programme["slug"]) or {}).get("stamps") or {}
        for entry in programmes.armed_entries(state, programme):
            row = entry.get("row") or {}
            at = (
                _as_dt(stamps_for.get(entry["todo"]))
                or _as_dt(row.get("armed_at"))
                or _as_dt(entry.get("ingested_at"))
            )
            record = {
                "at": at or datetime.min.replace(tzinfo=UTC),
                "refs": {"project": entry.get("project")},
            }
            topics.setdefault(programme["slug"], []).append((handle, record))
    return topics


def _attribute(caller: str, topics: dict, lanes_by_topic: dict) -> str | None:
    """The topic a run caller belongs to: the caller's
    base names the programme's slug outright, carries
    its slug stem, or names one of its lanes — the
    venue layer's rule, so the two measures attribute
    the same runs to the same topics. Longest wins."""
    bare = caller.lstrip("@").lower()
    if not bare:
        return None
    base = bare.split(":", 1)[0]
    best: tuple[int, str] | None = None
    for topic, lanes in lanes_by_topic.items():
        slug = topic.lower()
        stem = slug.split("-", 1)[0]
        names = {slug, stem}
        names.update(h.lstrip("@").lower() for h, _ in lanes)
        matched = 0
        for name in names:
            if base == name:
                matched = max(matched, len(name) + 1)
            elif base.startswith(name + "-"):
                matched = max(matched, len(name))
        if matched and (best is None or matched > best[0]):
            best = (matched, topic)
    return best[1] if best else None


def _done_topics(state: dict, wb_topics: dict) -> dict:
    """Topics whose referenced work reads done, keyed by
    programme slug: the workbench counts say every todo
    is done. The lane is synthesized from the programme
    declaration — a done topic has no armed entries left
    to name it."""
    topics: dict[str, list] = {}
    for programme in programmes.active_declarations(state):
        info = (wb_topics or {}).get(programme["slug"])
        if not info:
            continue
        if (
            not info.get("todos_total")
            or info.get("todos_done", 0) < info["todos_total"]
        ):
            continue
        handles = programme.get("handles") or []
        handle = handles[0] if handles else programme["slug"]
        projects = programmes.wb_projects(programme)
        record = {
            "at": _as_dt(info.get("plan_modified")) or datetime.min.replace(tzinfo=UTC),
            "refs": {"project": projects[0] if projects else None},
        }
        topics.setdefault(programme["slug"], []).append((handle, record))
    return topics


def build_staffing(
    state: dict,
    settings: Settings,
    now: datetime,
    wb_topics: dict | None = None,
    parked_by_project: dict | None = None,
) -> dict:
    """The staffing object the digest serves (§1.11 as
    amended): measured rows across the defect classes —
    never an acked state, never a silent all-staffed."""
    cadence_of = lambda handle: programmes.cadence_for(  # noqa: E731
        state, handle, settings.checkpoint_cadence_minutes
    )
    wb_topics = wb_topics or {}
    phantom = _phantom_rows(state, now)
    unrouted = _unrouted_rows(state)
    blocked = _blocked_rows(
        state,
        now,
        cadence_of,
        {r["_key"] for r in phantom},
    )
    prefix = (
        phantom
        + unrouted
        + blocked
        + _frontier_rows(state)
        + _overdue_rows(state, now)
        + _armed_rows(state, now)
        + _worktree_rows(state, now, wb_topics)
        + _record_rows(state, now, cadence_of)
        + _lane_rows(state, now)
        + _orphan_rows(state, now)
        + _terminal_rows(state, now)
        + _unlanded_rows(state, now)
    )
    owait = _owner_waiting_rows(state, now, cadence_of)
    snapshot = state.get("capacity_snapshot")
    if not snapshot or not snapshot.get("at"):
        return _unavailable(
            state,
            None,
            state.get("capacity_error") or "Capacity not collected yet.",
            rows=prefix + owait,
        )
    age_minutes = (now - snapshot["at"]).total_seconds() / 60
    if age_minutes > settings.capacity_stale_minutes:
        return _unavailable(
            state, snapshot, "Capacity snapshot is stale.", rows=prefix + owait
        )
    sessions = snapshot.get("sessions") or []
    live = [s["session"] for s in sessions]
    idle_since = snapshot.get("idle_since") or {}
    base = {
        "available": True,
        "reason": None,
        "snapshot_at": model._iso(snapshot["at"]),
        "sessions_live": len(live),
        "idle_minutes_total": 0,
        "sessions": [{"name": name, "running": 0} for name in live],
        "rows": [],
    }
    if len(live) < 2:
        base["rows"] = sorted(
            prefix + owait, key=lambda r: (r["topic"] or "", r["kind"])
        )
        return base
    try:
        recent = run_records.read_recent(settings.run_records_dir, now)
    except run_records.RunRecordsUnavailable as err:
        return _unavailable(state, snapshot, str(err), rows=prefix + owait)
    running = [r for r in recent if r["state"] == "running" and not r["finished_at"]]
    live_runs = {name: 0 for name in live}
    for run in running:
        if run["session"] in live_runs:
            live_runs[run["session"]] += 1
    base["sessions"] = [{"name": name, "running": live_runs[name]} for name in live]
    topics = _scope_topics(state)
    done_topics = _done_topics(state, wb_topics)
    all_topics = {**topics, **done_topics}
    counts: dict[str, dict] = {
        topic: {
            "workers": 0,
            "child": 0,
            "sessions": set(),
            "evidence": None,
            "jobs": 0,
        }
        for topic in all_topics
    }
    for run in recent:
        topic = _attribute(run["caller"], all_topics, all_topics)
        if topic is None:
            continue
        counts[topic]["jobs"] += 1
        stamp = run["finished_at"] or run["started_at"]
        if stamp and (
            counts[topic]["evidence"] is None or stamp > counts[topic]["evidence"]
        ):
            counts[topic]["evidence"] = stamp
    for run in running:
        if run["session"] not in live:
            continue
        topic = _attribute(run["caller"], all_topics, all_topics)
        if topic is None:
            continue
        counts[topic]["workers"] += 1
        counts[topic]["sessions"].add(run["session"])
        lanes = all_topics[topic]
        coordinators = {topic.lower()}
        coordinators.update(h.lstrip("@").lower() for h, _ in lanes)
        if run["caller"].lstrip("@").lower() not in coordinators:
            counts[topic]["child"] += 1
    handlers = model.handler_map(state)
    rows: list[dict] = (
        list(prefix)
        + _family_rows(state, now, live, idle_since)
        + _owner_waiting_rows(state, now, cadence_of, counts)
    )
    understaffed: set[str] = set()
    for topic, lanes in topics.items():
        workers = counts[topic]["workers"]
        child = counts[topic]["child"]
        sessions_used = len(counts[topic]["sessions"])
        if workers >= 2 and sessions_used >= 2:
            continue
        understaffed.add(topic)
        handle, _record = max(lanes, key=lambda pair: (pair[1]["at"], pair[0]))
        detail = (
            f"{workers} measured worker{'s' if workers != 1 else ''} "
            f"({child} child) on {sessions_used} of {len(live)} live sessions."
        )
        if workers == 0:
            detail += " No workers measured at all."
        elif child == 0:
            detail += " The coordinator is running without child workers."
        rows.append(
            _row(
                topic,
                handle,
                handlers.get(handle, {}).get("label", handle),
                "understaffed",
                detail,
                workers=workers,
                child_workers=child,
                sessions_used=sessions_used,
                sessions_live=len(live),
                jobs_run=counts[topic]["jobs"],
            )
        )
    cadence = settings.checkpoint_cadence_minutes
    for topic, lanes in topics.items():
        info = wb_topics.get(topic) or {}
        handle, _record = max(lanes, key=lambda pair: (pair[1]["at"], pair[0]))
        label = handlers.get(handle, {}).get("label", handle)
        status_at = max(r["at"] for _, r in lanes)
        evidence = counts[topic]["evidence"]
        plan_modified = _as_dt(info.get("plan_modified"))
        moved = (evidence and evidence > status_at) or (
            plan_modified and plan_modified > status_at
        )
        gap_minutes = int((now - status_at).total_seconds() // 60)
        if gap_minutes > settings.stall_after_hours * 60 and moved:
            rows.append(
                _row(
                    topic,
                    handle,
                    label,
                    "record_gap",
                    f"Work is moving, but the newest checkpoint is "
                    f"{gap_minutes} minutes old, against a "
                    f"{int(cadence)}-minute checkpoint cadence.",
                    workers=counts[topic]["workers"],
                    child_workers=counts[topic]["child"],
                    sessions_used=len(counts[topic]["sessions"]),
                    sessions_live=len(live),
                    checkpoint_gap_minutes=gap_minutes,
                    jobs_run=counts[topic]["jobs"],
                )
            )
        if (
            info.get("todos_total")
            and info.get("todos_done", 0) >= info["todos_total"]
            and counts[topic]["workers"] == 0
        ):
            last = max(
                [status_at] + [t for t in (evidence, plan_modified) if t is not None]
            )
            idle = int((now - last).total_seconds() // 60)
            if idle >= cadence:
                rows.append(
                    _row(
                        topic,
                        handle,
                        label,
                        "idle_unlanded",
                        f"The referenced work reads done, and nothing "
                        f"has been in flight for {idle} minutes; it is "
                        f"still unlanded.",
                        workers=0,
                        child_workers=0,
                        sessions_used=0,
                        sessions_live=len(live),
                        idle_minutes=idle,
                        jobs_run=counts[topic]["jobs"],
                    )
                )
    for topic, lanes in done_topics.items():
        if topic in topics or counts[topic]["workers"] > 0:
            continue
        project = next((r["refs"]["project"] for _, r in lanes if r.get("refs")), None)
        parked_count = (parked_by_project or {}).get(project or "", 0)
        if not project or not parked_count:
            continue
        handle, _record = max(lanes, key=lambda pair: (pair[1]["at"], pair[0]))
        rows.append(
            _row(
                topic,
                handle,
                handlers.get(handle, {}).get("label", handle),
                "no_successor",
                f"The stage is complete and {project} holds "
                f"{parked_count} approved unstarted plan"
                f"{'s' if parked_count != 1 else ''}, with no "
                f"workers fielded.",
                workers=0,
                child_workers=0,
                sessions_used=0,
                sessions_live=len(live),
                jobs_run=counts[topic]["jobs"],
            )
        )
    sends_by_id = {s.get("id"): s for s in state.get("sends") or []}
    for failure in state.get("dispatch_failures") or []:
        send = sends_by_id.get(failure.get("send_id"))
        if send is None:
            continue
        if dispatch_mod.state_of(send, now) == "delivered":
            continue
        topic = digest_mod.topic_of(send.get("handle") or "")
        if topic not in understaffed:
            continue
        handle = send.get("handle")
        reason = failure.get("reason") or "no reason recorded"
        rows.append(
            _row(
                topic,
                handle,
                handlers.get(handle, {}).get("label", handle),
                "steer_undeliverable",
                "A supervision send to this thread could not be "
                f"delivered ({reason}); it is addressed to main "
                "after one failed cycle.",
                workers=counts[topic]["workers"],
                child_workers=counts[topic]["child"],
                sessions_used=len(counts[topic]["sessions"]),
                sessions_live=len(live),
                key=f"steer_undeliverable:{failure.get('send_id')}",
            )
        )
    total_running = sum(live_runs.values())
    idle_total = 0
    for name in live:
        if live_runs[name] > 0:
            continue
        since = _as_dt(idle_since.get(name))
        idle_minutes = int((now - since).total_seconds() // 60) if since else 0
        idle_total += idle_minutes
        if total_running > 0 or understaffed:
            rows.append(
                _row(
                    None,
                    None,
                    name,
                    "fleet_idle",
                    f"{name} is live and has carried no runs for "
                    f"{idle_minutes} minutes while work queues on "
                    f"the fleet.",
                    sessions_live=len(live),
                    idle_minutes=idle_minutes,
                    key=f"fleet_idle:{name}",
                )
            )
    if total_running > 0 or rows:
        base["idle_minutes_total"] = idle_total
    memory = state.setdefault("staffing_rows", {})
    seen = set()
    for row in rows:
        key = row.pop("_key")
        seen.add(key)
        first = _as_dt(memory.get(key))
        if first is None:
            memory[key] = model._iso(now)
            first = now
        bound = programmes.escalation_for(
            state, row.get("handle"), settings.staffing_escalate_hours
        )
        if row["kind"] in ("steer_undeliverable", "phantom_stop") or (
            now - first
        ) >= timedelta(hours=bound):
            row["escalation"] = "main"
        directed = (state.get("owner_directed") or {}).get(row.get("topic") or "")
        row["owner_directed"] = bool(directed)
        if row["kind"] in (
            "understaffed",
            "record_gap",
            "idle_unlanded",
            "no_successor",
            "serial_staffing",
            "frontier_shortfall",
        ):
            stall = int((now - first).total_seconds() // 60)
            row["stall_minutes"] = stall
            if (
                stall >= 1
                and row.get("jobs_run") is not None
                and row["kind"]
                in ("understaffed", "record_gap", "idle_unlanded", "no_successor")
            ):
                workers = row.get("workers") or 0
                row["detail"] += (
                    f" The stall has run {stall} minutes; the work "
                    f"it interrupts measures {row['jobs_run']} jobs "
                    f"run, {workers} workers fielded."
                )
    for key in list(memory):
        if key not in seen:
            del memory[key]
    base["rows"] = sorted(
        rows, key=lambda r: (r["topic"] is None, r["topic"] or "", r["kind"])
    )
    return base
