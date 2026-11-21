"""Staffing rows, waits family: owner-waiting, armed,
worktree, and record-gap rows — split from
staffing_rows.py; attention.services.measure.
staffing_rows re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime

from attention.services import programmes

from .staffing_common import _as_dt, _row


def _latest_lane_stamp(state: dict, programme: dict) -> datetime | None:
    """The programme's newest lane record: the latest
    checkpoint stamp across its armed todos, or the
    latest checkpoint in its declared lane record files
    — whichever moved last. None when nothing moved."""
    latest = None
    stamps = (state.get("stamp_snapshot") or {}).get(programme["slug"]) or {}
    for value in (stamps.get("stamps") or {}).values():
        stamp = _as_dt(value)
        if stamp is not None and (latest is None or stamp > latest):
            latest = stamp
    records = (state.get("record_snapshot") or {}).get(programme["slug"]) or {}
    for record in (records.get("records") or {}).values():
        stamp = _as_dt(record.get("checkpoint_at"))
        if stamp is not None and (latest is None or stamp > latest):
            latest = stamp
    return latest


def _owner_waiting_rows(state, now, cadence_of, counts=None) -> list:
    """§1.11 (l): past one check cycle with no staffing
    measure and no record newer than the declaration, an
    owner-waiting declaration from the goal store is a row
    to main at once."""
    pings = state.get("pings") or {}
    rows = []
    for programme in programmes.active_declarations(state):
        entry = (state.get("goal_snapshot") or {}).get(programme["slug"]) or {}
        decls = entry.get("owner_waiting") or []
        if not decls:
            continue
        handles = programme.get("handles") or [programme["slug"]]
        handle = handles[0]
        label = programme["label"]
        topic = programme["slug"]
        latest = _latest_lane_stamp(state, programme)
        for decl in decls:
            commissioned = _as_dt(decl.get("commissioned_at"))
            declared_at = _as_dt(decl.get("declared_at")) or commissioned
            if commissioned is None:
                continue
            waiting = int((now - commissioned).total_seconds() // 60)
            staffed = False
            if counts is not None:
                entry_counts = counts.get(topic) or {}
                evidence = entry_counts.get("evidence")
                staffed = entry_counts.get("workers", 0) > 0 or (
                    evidence is not None and evidence > commissioned
                )
            if (
                (now - commissioned).total_seconds() > cadence_of(handle) * 60
                and (latest is None or latest <= declared_at)
                and not staffed
            ):
                row = _row(
                    topic,
                    handle,
                    label,
                    "owner_waiting",
                    f"The owner has waited {waiting} minutes on "
                    f"{decl['label']}: no workers measured for "
                    f"its topic and no lane record since the "
                    f"commission — past one check cycle. "
                    f"Owner-waiting outranks queue position.",
                    idle_minutes=waiting,
                    key=f"owner_waiting:{programme['slug']}:{decl.get('goal')}",
                )
                row["escalation"] = "main"
                rows.append(row)
            ping = pings.get(handle) or {}
            last_ask = _as_dt(ping.get("last_at"))
            if (
                last_ask is not None
                and (latest is None or latest <= last_ask)
                and (now - last_ask).total_seconds() > cadence_of(handle) * 60
            ):
                ask_age = int((now - last_ask).total_seconds() // 60)
                row = _row(
                    topic,
                    handle,
                    label,
                    "owner_waiting_unanswered",
                    f"An ask about {decl['label']} has "
                    f"gone unanswered for {ask_age} minutes — "
                    f"past one check cycle; the owner has "
                    f"waited {waiting} minutes since the "
                    f"commission. The answer precedes lane work.",
                    idle_minutes=waiting,
                    key=f"owner_waiting_unanswered:{programme['slug']}:{decl.get('goal')}",
                )
                row["escalation"] = "main"
                rows.append(row)
    return rows


def _armed_rows(state, now) -> list:
    """Armed work no checkpoint has picked up: a harness
    row older than two of its cadence intervals with no
    checkpoint stamp for its todo is unsupervised work —
    the lane has not started reporting, or has stopped."""
    stamps = state.get("stamp_snapshot") or {}
    stamped: set = set()
    for _slug, entry in stamps.items():
        for todo in entry.get("stamps") or {}:
            stamped.add(todo)
    rows = []
    for entry in state.get("armed_rows") or []:
        row = entry.get("row") or {}
        todo = entry.get("todo")
        if not todo or todo in stamped:
            continue
        armed_at = _as_dt(row.get("armed_at")) or _as_dt(entry.get("ingested_at"))
        if armed_at is None:
            continue
        cadence = row.get("cadence_minutes") or 15.0
        age = int((now - armed_at).total_seconds() // 60)
        if age <= 2 * cadence:
            continue
        rows.append(
            _row(
                entry.get("project"),
                todo,
                row.get("title") or todo,
                "armed_unreported",
                f"Armed {age} minutes ago; no checkpoint "
                f"names this todo after two cadence "
                f"intervals — the lane is unsupervised, "
                f"or the work has not started.",
                idle_minutes=age,
                key=f"armed_unreported:{entry.get('project')}:{todo}",
            )
        )
    return rows


def _worktree_rows(state, now, wb_topics=None) -> list:
    """The two derived checks on worktree presence: work
    that reads done in the workbench while trees stand
    unlanded, and a standing tree with no arm and no
    done work — unarmed. A standing tree is unfinished
    work whatever any earlier claim said."""
    snapshot = state.get("worktree_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for programme in programmes.active_declarations(state):
        entry = snapshot.get(programme["slug"])
        if not entry:
            continue
        trees = entry.get("trees") or []
        if not trees:
            continue
        handles = programme.get("handles") or []
        handle = handles[0] if handles else programme["slug"]
        armed = programmes.armed_entries(state, programme)
        info = (wb_topics or {}).get(programme["slug"]) or {}
        done = bool(
            info.get("todos_total") and info.get("todos_done", 0) >= info["todos_total"]
        )
        unlanded = [t for t in trees if t.get("landed") is False]
        if done and unlanded:
            names = ", ".join(t["name"] for t in unlanded[:3])
            rows.append(
                _row(
                    programme["slug"],
                    handle,
                    programme["label"],
                    "unlanded_claim",
                    f"The work reads done for this programme "
                    f"while {len(unlanded)} worktree(s) stand "
                    f"unlanded ({names}) — the claim is "
                    f"reported against the tree, not taken.",
                    key=f"unlanded_claim:{programme['slug']}",
                )
            )
        if not done and not armed:
            rows.append(
                _row(
                    programme["slug"],
                    handle,
                    programme["label"],
                    "unarmed_work",
                    f"{len(trees)} worktree(s) stand for this "
                    f"programme with no armed registry row and "
                    f"no done work — work standing "
                    f"unsupervised.",
                    key=f"unarmed_work:{programme['slug']}",
                )
            )
    return rows


def _record_rows(state, now, cadence_of) -> list:
    """A declared lane record whose latest conforming
    checkpoint is older than two cadence intervals is a
    record gap — the lane owes a checkpoint or a blocker."""
    snapshot = state.get("record_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for programme in programmes.declarations(state):
        entry = snapshot.get(programme["slug"])
        if not entry:
            continue
        cadence = programme.get("cadence_minutes") or cadence_of(
            (programme.get("handles") or [programme["slug"]])[0]
        )
        handles = programme.get("handles") or [programme["slug"]]
        for record in (entry.get("records") or {}).values():
            stamp = record.get("checkpoint_at")
            stamp = _as_dt(stamp) if stamp else None
            gap = None if stamp is None else (now - stamp).total_seconds() / 60
            if gap is not None and gap <= 2 * cadence:
                continue
            detail = (
                "No conforming progress-checkpoint in this "
                "lane's record yet — the lane owes its first "
                "checkpoint or its exact blocker."
                if gap is None
                else f"Latest conforming checkpoint in this "
                f"lane's record is {round(gap)}m old against a "
                f"{cadence:g}m cadence — a record gap: the lane "
                f"owes a checkpoint or its exact blocker."
            )
            rows.append(
                _row(
                    programme["slug"],
                    handles[0],
                    f"{programme['label']} — {record['lane']}",
                    "record_gap",
                    detail,
                    key=f"record_gap:{programme['slug']}:{record['lane']}",
                )
            )
    return rows
