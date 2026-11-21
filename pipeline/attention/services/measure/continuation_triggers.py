"""Continuation triggers: the stall triggers a measure
raises — staffing-row triggers, returned-fulfillment
triggers, and the scripted idle detector — split from
continuation.py; attention.services.measure.
continuation re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime

from attention.services import programmes
from attention.services.measure import staffing, stamps
from attention.services.waits import fulfillment
from attention.services.writes import ingest

TRIGGER_KINDS = (
    "record_gap",
    "unarmed_work",
    "no_successor",
    "blocked_uncited",
    "blocked_unverified",
)

_ACTS = {
    "record_gap": (
        "Write a conforming progress-checkpoint to the lane record "
        "naming the current state, or declare the blocker there."
    ),
    "unarmed_work": (
        "Staff the standing work and arm it, or declare it settled with its evidence."
    ),
    "no_successor": (
        "Staff the successor step now; a verdict is not a stopping condition."
    ),
    "blocked_uncited": (
        "The blocked claim is VOID — it cites no basis. Resume the "
        "work under its standing authorization, or cite the owner's "
        "actual message (thread + time) as the claim's basis."
    ),
    "blocked_unverified": (
        "The blocked claim is VOID — its cited basis carries no "
        "verification stamp. Resume the work under its standing "
        "authorization while verification is sought."
    ),
}

DEFAULT_IDLE_CLASSES = [
    "plan starts",
    "docs reconciliation",
    "performance improvements (result-preserving)",
    "consolidation and duplication",
    "doc updates",
]

_CLEARING = (
    "Sent by owner-attention's evaluator; this ping repeats on the "
    "programme's cadence and clears only when the measure moves — "
    "a reply alone does not clear it."
)


def _cadence(state: dict, handle: str, settings) -> float:
    programme = programmes.by_handle(state).get(handle)
    if programme and programme.get("cadence_minutes"):
        return programme["cadence_minutes"]
    return settings.checkpoint_cadence_minutes


def _raise_void_item(state: dict, row: dict, now: datetime) -> None:
    """A void blocked claim stands as a defect item."""
    ingest.upsert_item(
        state,
        {
            "handle": row["handle"],
            "kind": "defect",
            "source_ref": f"void-block:{row['handle']}",
            "title": (
                f"Void blocked claim — {row['handler_label']}: {row['detail']} "
                "The claim is void; the programme is treated as resumable "
                "under its standing authorization."
            ),
            "provenance": "commission",
            "status": "WORKING",
        },
        now,
    )


def _signature(state: dict, programme: dict) -> str:
    slug = programme["slug"]
    records = (state.get("record_snapshot") or {}).get(slug, {}).get("records") or {}
    trees = (state.get("worktree_snapshot") or {}).get(slug, {}).get("trees") or []
    parts = [
        ("rec", path, str(entry.get("checkpoint_at")))
        for path, entry in sorted(records.items())
    ]
    parts += [
        ("tree", tree["name"], tree.get("tip"), tree.get("dirty"), tree.get("landed"))
        for tree in trees
    ]
    lane_stamps = (state.get("stamp_snapshot") or {}).get(slug, {}).get("stamps") or {}
    parts += [
        (
            "armed",
            entry["todo"],
            (entry.get("row") or {}).get("status"),
            stamps.normalize(lane_stamps.get(entry["todo"])),
        )
        for entry in programmes.armed_entries(state, programme)
    ]
    return repr(parts)


def _is_complete(state: dict, programme: dict) -> bool:
    """Complete reads from records alone: every armed
    todo terminal and no worktree standing unlanded.
    A standing tree is unfinished work whatever any
    earlier post claimed."""
    entries = programmes.armed_entries(state, programme)
    if entries and any(
        (entry.get("row") or {}).get("status") not in ("done",) for entry in entries
    ):
        return False
    trees = (state.get("worktree_snapshot") or {}).get(programme["slug"], {}).get(
        "trees"
    ) or []
    return not any(tree.get("landed") is False for tree in trees)


def _idle_triggers(state: dict, settings, now: datetime) -> tuple[dict, bool]:
    """The scripted idle detector: no signal moved for two
    cadence intervals fires by goal state — continuation
    when incomplete, the follow-on queue when complete."""
    watch = state.setdefault("idle_watch", {})
    triggers: dict = {}
    changed = False
    for programme in programmes.active_declarations(state):
        handles = programme.get("handles") or []
        if not handles:
            continue
        slug = programme["slug"]
        signature = _signature(state, programme)
        entry = watch.get(slug)
        if entry is None or entry.get("signature") != signature:
            watch[slug] = {"signature": signature, "since": now}
            changed = True
            continue
        cadence = programme.get("cadence_minutes") or (
            settings.checkpoint_cadence_minutes
        )
        idle_minutes = (now - entry["since"]).total_seconds() / 60
        if idle_minutes < 2 * cadence:
            continue
        complete = _is_complete(state, programme)
        classes = programme.get("idle_classes") or DEFAULT_IDLE_CLASSES
        state_word = (
            "goal complete — follow-on work"
            if complete
            else "goal incomplete — continuation"
        )
        summary = f"{programme['label']} — idle {int(idle_minutes)}m, {state_word}."
        detail = (
            "No signal has moved for two cadence intervals — no "
            "checkpoint, no worktree change, no run activity. "
            "Standing work, in order: "
            + "; ".join(classes)
            + ". Post the chosen work and staff it; agent-suggested "
            "follow-ups are built in a worktree for the owner's "
            f"review — triggered is not landed. {_CLEARING}"
        )
        triggers[f"idle:{slug}"] = (handles[0], summary, detail, cadence)
    return triggers, changed


def _triggers(
    state: dict, settings, now: datetime, view: dict | None = None
) -> tuple[dict, bool]:
    triggers: dict = {}
    if view is None:
        view = staffing.build_staffing(state, settings, now)
    for row in view["rows"]:
        if row["kind"] not in TRIGGER_KINDS or not row.get("handle"):
            continue
        if row["kind"] in ("blocked_uncited", "blocked_unverified"):
            _raise_void_item(state, row, now)
        sat = (
            row.get("checkpoint_gap_minutes")
            or row.get("stall_minutes")
            or row.get("idle_minutes")
        )
        sat_text = f" It has sat {int(sat)}m." if sat else ""
        summary = f"{row['handler_label']} — {row['kind_label']}."
        detail = f"{row['detail']}{sat_text} Next act: {_ACTS[row['kind']]} {_CLEARING}"
        key = (
            f"{row['kind']}:{row.get('topic') or row.get('handle') or ''}"
            f":{row.get('handler_label') or ''}"
        )
        triggers[key] = (
            row["handle"],
            summary,
            detail,
            _cadence(state, row["handle"], settings),
        )
    for item in fulfillment.returned_items(state, now, settings):
        derived = fulfillment.derive(item, state, now, settings)
        if not derived or derived["state"] != "stalled":
            continue
        summary = f"{item['title']} — decided, unfulfilled."
        detail = (
            "The owner's decision on this item was recorded but the "
            "act never landed, past the stall bound. Next act: "
            "fulfill the recorded decision, or declare the blocker "
            f"on the item. {_CLEARING}"
        )
        triggers[f"fulfillment:{item['id']}"] = (
            item["handle"],
            summary,
            detail,
            _cadence(state, item["handle"], settings),
        )
    idle, watch_changed = _idle_triggers(state, settings, now)
    triggers.update(idle)
    return triggers, watch_changed
