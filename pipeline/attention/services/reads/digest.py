"""Digest assembly (Step 4): a section per status kind
that has rows, a parked-plans band derived from the
workbench by reference, handlers collapsed by topic, and
stalls derived from stale non-terminal statuses.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from attention.domain import attention as dom
from attention.infra import wb_client
from attention.services import programmes
from attention.services.measure import staffing
from attention.services.reads import model
from attention.services.waits import facts as facts_mod
from attention.settings import Settings

SECTION_ORDER = (
    "push_needed",
    "defect",
    "followup",
    "improvement",
    "consolidation",
    "performance",
)
WORST_RANK = {
    "BLOCKED-HARD": 0,
    "BLOCKED-OWNER": 0,
    "REVIEW": 1,
    "WORKING": 2,
    "CONTINUE": 2,
    "PARKED": 3,
    "DONE": 4,
    "CLOSED": 5,
}


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def topic_of(handle: str) -> str:
    """The collapse key: the handle's prefix before its
    first dash, computed at assembly — a new lane under an
    existing topic joins it with no configuration."""
    bare = handle.lstrip("@")
    return bare.split("-", 1)[0] if "-" in bare else bare


def _kind_owner(state: dict, kind: str):
    for entry in state.get("item_kinds", []):
        if entry["kind"] == kind and entry.get("digest_owner"):
            return entry["digest_owner"]
    return dom.STATUS_KIND_OWNERS.get(kind, "owner")


def _row(
    state: dict, kind: str, title: str, handle: str, provenance, at, now: datetime
) -> dict:
    handlers = model.handler_map(state)
    return {
        "kind": kind,
        "title": title,
        "handle": handle,
        "handler_label": handlers.get(handle, {}).get("label", handle),
        "provenance": provenance,
        "provenance_label": model.PROVENANCE_LABELS.get(provenance, provenance),
        "at": _iso(at),
        "age_label": dom.waiting_label(at, now),
    }


def _sections(state: dict, now: datetime, facts: dict | None = None) -> list:
    rows: dict[str, list] = {}
    # One set, owner kinds only: Today's open items,
    # restricted to kinds the registry places with the owner.
    for item in model._live_items(state, now, facts):
        if item["kind"] not in dom.STATUS_KINDS:
            continue
        if _kind_owner(state, item["kind"]) != "owner":
            continue
        rows.setdefault(item["kind"], []).append(
            _row(
                state,
                item["kind"],
                facts_mod.served_title(item, (facts or {}).get(item["id"])),
                item["handle"],
                item.get("provenance", "offer"),
                item["waiting_since"],
                now,
            )
        )
    sections = []
    for kind in SECTION_ORDER:
        if not rows.get(kind):
            continue
        owner = _kind_owner(state, kind)
        sections.append(
            {
                "kind": kind,
                "kind_label": model._kind_label(state, kind),
                "owner": owner,
                "owner_label": model.DIGEST_OWNER_LABELS.get(owner, owner),
                "rows": sorted(rows[kind], key=lambda r: r["at"] or ""),
            }
        )
    return sections


def _expired_notes(state: dict, now: datetime, facts: dict | None = None) -> list:
    """The digest's expired section (the decision-
    staleness plan, Step 3): one note per expired item —
    the digest row shape plus the expiry record — so an
    expire-to-record lands on the owner's single
    surface as a one-line note, blocked-marked for the
    hard-stop form."""
    notes = []
    for item in state["items"]:
        expired = item.get("expired")
        if not expired:
            continue
        row = _row(
            state,
            item["kind"],
            facts_mod.served_title(item, (facts or {}).get(item["id"])),
            item["handle"],
            item.get("provenance", "offer"),
            item["waiting_since"],
            now,
        )
        notes.append(dom.expired_note(row, {**expired, "at": _iso(expired["at"])}))
    return sorted(notes, key=lambda note: note["expired_at"] or "")


def _stalls(state: dict, settings: Settings, now: datetime) -> list:
    # A stall reaches the owner's digest only when the lane
    # is blocked on the owner, with the act that clears it.
    terminal = {
        e["code"]: e.get("terminal", False)
        for e in state.get("status_codes") or dom.default_status_codes()
    }
    retired = model.retired_handles(state)
    out = []
    for handle, record in state.get("handler_status", {}).items():
        if handle in retired:
            continue
        code = record["status_code"]
        if terminal.get(code) or code == "PARKED":
            continue
        blockers = [
            b
            for b in record.get("blockers") or []
            if b.get("whose", "owner") == "owner"
        ]
        if not blockers:
            continue
        age_hours = (now - record["at"]).total_seconds() / 3600
        if age_hours > settings.stall_after_hours:
            out.append(
                {
                    "handle": handle,
                    "handler_label": model.handler_map(state)
                    .get(handle, {})
                    .get("label", handle),
                    "summary": blockers[0]["summary"],
                    "clearing_act": blockers[0].get("clearing_act"),
                    "status_code": code,
                    "status_label": model.status_label(state, code),
                    "age_hours": round(age_hours, 1),
                    "age_label": dom.waiting_label(record["at"], now),
                }
            )
    return sorted(out, key=lambda s: -s["age_hours"])


def _topics(state: dict, now: datetime, stalls: list) -> list:
    handlers = model.handler_map(state)
    statuses = state.get("handler_status", {})
    lanes: dict[str, dict] = {}
    for handle in set(statuses) | {i["handle"] for i in model.open_items(state, now)}:
        record = statuses.get(handle)
        lanes[handle] = {
            "handle": handle,
            "label": handlers.get(handle, {}).get("label", handle),
            "status_code": record["status_code"] if record else None,
            "status_label": (
                model.status_label(state, record["status_code"]) if record else None
            ),
            "need": (
                dom.classify_need(record["status_code"], state.get("status_codes"))
                if record
                else None
            ),
            "quick_verbs": (
                model.quick_verbs_for_status(state, handle, record) if record else []
            ),
        }
    counts: dict[str, dict] = {}
    for item in model.open_items(state, now):
        counts.setdefault(item["handle"], {})
        counts[item["handle"]][item["kind"]] = (
            counts[item["handle"]].get(item["kind"], 0) + 1
        )
    stall_handles = {s["handle"] for s in stalls}
    topics: dict[str, dict] = {}
    for handle, lane in lanes.items():
        topic = topics.setdefault(
            topic_of(handle),
            {"topic": topic_of(handle), "lanes": [], "open_counts": {}, "stalls": 0},
        )
        topic["lanes"].append({**lane, "stale": handle in stall_handles})
        for kind, n in counts.get(handle, {}).items():
            topic["open_counts"][kind] = topic["open_counts"].get(kind, 0) + n
        if handle in stall_handles:
            topic["stalls"] += 1
    out = []
    for topic in topics.values():
        topic["open_counts"] = [
            {
                "kind": kind,
                "kind_label": model._kind_label(state, kind),
                "count": n,
            }
            for kind, n in sorted(topic["open_counts"].items())
        ]
        topic["lanes"].sort(key=lambda lane: lane["handle"])
        ranked = [
            (WORST_RANK.get(lane["status_code"], 6), lane)
            for lane in topic["lanes"]
            if lane["status_code"]
        ]
        worst = min(ranked, key=lambda pair: pair[0])[1] if ranked else None
        topic["worst_code"] = worst["status_code"] if worst else None
        topic["worst_label"] = worst["status_label"] if worst else None
        out.append(topic)
    return sorted(out, key=lambda t: t["topic"])


def _plan_age_days(path: str, now: datetime):
    try:
        born = datetime.strptime(path[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (now.date() - born).days


def _parked_pull(state: dict, settings: Settings, now: datetime):
    """One workbench plans pull feeding three readers:
    the parked band, the per-project parked counts, and
    the per-project newest plan modification."""
    try:
        projects = wb_client.fetch_projects(settings.wb_url, settings.wb_timeout_s)
    except wb_client.WbUnavailable as err:
        return {"available": False, "reason": str(err), "plans": []}, {}, {}

    def pull(project):
        try:
            payload = wb_client.fetch_plans(
                settings.wb_url, project, settings.wb_timeout_s
            )
        except wb_client.WbUnavailable:
            return project, None
        return project, payload.get("plans") or []

    plans = []
    skipped = []
    counts: dict[str, int] = {}
    modified: dict[str, datetime] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for project, found in pool.map(pull, projects):
            if found is None:
                skipped.append(project)
                continue
            for plan in found:
                stamp = None
                raw_modified = plan.get("modified")
                if isinstance(raw_modified, str) and raw_modified:
                    try:
                        stamp = datetime.fromisoformat(raw_modified)
                    except ValueError:
                        stamp = None
                if stamp and (project not in modified or stamp > modified[project]):
                    modified[project] = stamp
                raw = (plan.get("status_raw") or "").lower()
                if plan.get("status_bucket") == "todo" and "approved" in raw:
                    counts[project] = counts.get(project, 0) + 1
                    plans.append(
                        {
                            "project": project,
                            "path": plan.get("path"),
                            "title": plan.get("title"),
                            "age_days": _plan_age_days(plan.get("path") or "", now),
                        }
                    )
    plans.sort(key=lambda p: (p["age_days"] is None, -(p["age_days"] or 0)))
    parked = {
        "available": True,
        "reason": None,
        "skipped_projects": skipped,
        "plans": plans,
    }
    return parked, counts, modified


def _wb_topics(state: dict, settings: Settings, modified: dict, now: datetime) -> dict:
    """Per-programme workbench evidence for the staffing
    measure, keyed by programme slug: todo counts summed
    across the programme's projects — restricted to its
    armed todos while work is live, whole-project once
    nothing is armed. A programme with no armed entries
    but every todo done still counts — its stage is
    complete and the no-successor row must see it.
    plan_modified is the newest plan change across its
    projects."""
    from attention.services.reads import derive

    out = {}
    for programme in programmes.active_declarations(state):
        projects = programmes.wb_projects(programme)
        entries = programmes.armed_entries(state, programme)
        total = done = 0
        served = False
        for project in projects:
            wanted = (
                {e.get("todo") for e in entries if e.get("project") == project}
                if entries
                else None
            )
            derived = derive.derive_counts(settings, project, wanted, now)
            if not derived.get("available") or not derived.get("todos"):
                continue
            served = True
            total += derived["todos"]["total"]
            done += derived["todos"]["done"]
        if not served or not total:
            continue
        stamps = [
            modified.get(project)
            for project in projects
            if modified.get(project) is not None
        ]
        out[programme["slug"]] = {
            "todos_total": total,
            "todos_done": done,
            "plan_modified": max(stamps) if stamps else None,
        }
    return out


def collect_wb_facts(state: dict, settings: Settings, now: datetime) -> bool:
    """Refresh the digest's workbench-facts snapshot (the
    AC-5 cure): the parked-plans pull and the per-topic
    workbench evidence are external reads costing seconds,
    so they collect on the capacity cadence — the same
    snapshot discipline as capacity/records/stamps — and
    the digest route reads the snapshot instead of pulling
    per request. Plan ages are NOT stored: age_days is
    recomputed at read from the plan path's date prefix,
    so a snapshot never serves a frozen age. True when the
    snapshot changed."""
    parked, counts, modified = _parked_pull(state, settings, now)
    topics = _wb_topics(state, settings, modified, now)
    snapshot = {
        "at": _iso(now),
        "parked": {
            "available": parked["available"],
            "reason": parked["reason"],
            "skipped_projects": parked.get("skipped_projects"),
            "plans": [
                {
                    "project": p["project"],
                    "path": p["path"],
                    "title": p["title"],
                }
                for p in parked["plans"]
            ],
        },
        "parked_counts": counts,
        "modified": {project: _iso(at) for project, at in modified.items()},
        "wb_topics": {
            topic: {
                "todos_total": entry["todos_total"],
                "todos_done": entry["todos_done"],
                "plan_modified": _iso(entry["plan_modified"]),
            }
            for topic, entry in topics.items()
        },
    }
    before = state.get("digest_wb_snapshot") or {}
    if {k: v for k, v in snapshot.items() if k != "at"} == {
        k: v for k, v in before.items() if k != "at"
    }:
        return False
    state["digest_wb_snapshot"] = snapshot
    return True


def _wb_facts_from_snapshot(state: dict, now: datetime):
    """The build_digest inputs from the collected
    snapshot, in the live pull's shapes: parked plans with
    ages recomputed at read, modified stamps parsed back
    to datetimes, per-topic evidence likewise. The stamps
    arrive as ISO strings in a freshly collected snapshot
    and as datetimes once the state has round-tripped the
    store (its load decodes T-form strings back to
    datetimes), so they normalize through _as_dt, which
    takes both. Deferred import: staffing_rows imports
    this module at its top level."""
    from attention.services.measure.staffing_rows import _as_dt

    snapshot = state["digest_wb_snapshot"]
    stored = snapshot["parked"]
    plans = [
        {**p, "age_days": _plan_age_days(p["path"] or "", now)} for p in stored["plans"]
    ]
    plans.sort(key=lambda p: (p["age_days"] is None, -(p["age_days"] or 0)))
    parked = {
        "available": stored["available"],
        "reason": stored["reason"],
        "plans": plans,
    }
    if stored.get("skipped_projects") is not None:
        parked["skipped_projects"] = stored["skipped_projects"]
    modified = {
        project: _as_dt(at) for project, at in (snapshot.get("modified") or {}).items()
    }
    topics = {
        topic: {
            "todos_total": entry["todos_total"],
            "todos_done": entry["todos_done"],
            "plan_modified": _as_dt(entry.get("plan_modified")),
        }
        for topic, entry in (snapshot.get("wb_topics") or {}).items()
    }
    return parked, snapshot.get("parked_counts") or {}, modified, topics


def build_digest(
    state: dict, settings: Settings, now: datetime, facts: dict | None = None
) -> dict:
    stalls = _stalls(state, settings, now)
    enabled_windows = model.digest_windows(state, settings)
    if state.get("digest_wb_snapshot"):
        parked, parked_counts, modified, wb_topics = _wb_facts_from_snapshot(state, now)
    else:
        # No collection has landed yet (first boot, or a
        # caller composing without the serve loops): pull
        # live, exactly as before the snapshot existed.
        parked, parked_counts, modified = _parked_pull(state, settings, now)
        wb_topics = _wb_topics(state, settings, modified, now)
    return {
        "contract": model.CONTRACT,
        "generated_at": _iso(now),
        "window": {
            "next_at": (
                _iso(
                    dom.next_window(
                        now,
                        tuple(enabled_windows),
                        model.digest_window_tz(state),
                    )
                )
                if enabled_windows
                else None
            ),
            "times": model.digest_window_times(state, settings),
            "tz": (state.get("digest_prefs") or {}).get("window_tz"),
            "enabled_times": enabled_windows,
        },
        "include": model.digest_include(state),
        "sections": _sections(state, now, facts),
        "expired": _expired_notes(state, now, facts),
        "programmes": [
            {
                "slug": p["slug"],
                "label": p["label"],
                "rule_text": p.get("rule_text", ""),
                "staffing_band": p.get("staffing_band"),
                "cadence_minutes": p.get("cadence_minutes"),
                "escalation_hours": p.get("escalation_hours"),
                "handles": p.get("handles", []),
            }
            for p in programmes.declarations(state)
        ],
        "stalls": stalls,
        "staffing": staffing.build_staffing(
            state,
            settings,
            now,
            wb_topics=wb_topics,
            parked_by_project=parked_counts,
        ),
        "topics": _topics(state, now, stalls),
        "parked_plans": parked,
    }
