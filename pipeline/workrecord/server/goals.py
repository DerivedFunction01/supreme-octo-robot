"""The goal-records feed (contract 11): the feeds
document's goals block, read from the goal-record store
(lib/goals — the work-record service's own store, at the
configured state dir).

The store is the truth; this feed is its projection in
the shape the app's adapter consumes (lib/goals'
serve_record). A deployment with no store yet serves an
empty array and says so on the document's face — honest
absence, never invented records. A store that does not
parse is a feed failure, not an empty feed: lib/goals
raises and the assembly's caller sees it (a torn store
must never read as "no goals").
"""

from lib.writes import goals as goals_mod

from . import config as cfgmod
from .common import CFG, ApiError


def goals_feed() -> dict:
    """{goals, goalsSource} for the assembly document:
    every record in the store, slug-ordered, served."""
    path = cfgmod.goals_path(CFG)
    store = goals_mod.GoalStore(path)
    records = store.records()
    goals = [goals_mod.serve_record(r) for r in
             sorted(records, key=lambda r: r["slug"])]
    if goals:
        source = ("pipeline goal-record store "
                  "(contract 11): "
                  f"{len(goals)} record(s) served from "
                  f"{path.name}")
    else:
        source = ("pipeline goal-record store "
                  "(contract 11): no records in the "
                  "store yet — the array is the shape "
                  "the adapter consumes as records land")
    return {"goals": goals, "goalsSource": source}


def _store() -> goals_mod.GoalStore:
    return goals_mod.GoalStore(cfgmod.goals_path(CFG))


def goal_ping(slug, body) -> dict:
    """POST /api/goals/{slug}/ping {armed, cadence_minutes?}:
    arm or disarm the record's ping through the store's
    one writer (GoalStore.set_ping — a closed goal's
    retired ping refuses re-arm there, and the entry sync
    rides the outcome). The response carries the record
    in its served form, so the caller adopts served state,
    never a local projection of it."""
    if not isinstance(body.get("armed"), bool):
        raise ApiError(400, "ping needs a boolean "
                            "\"armed\"")
    store = _store()
    if store.get(slug) is None:
        raise ApiError(404, f"unknown goal {slug}")
    try:
        outcome = store.set_ping(
            slug, body["armed"],
            cadence_minutes=body.get("cadence_minutes"))
    except goals_mod.GoalError as e:
        raise ApiError(400, str(e))
    return {"goal": goals_mod.serve_record(
                outcome["record"]),
            "ping_sync": outcome.get("ping_sync")}


def goal_status(slug, body) -> dict:
    """POST /api/goals/{slug}/status {post}: append a
    status post through the store's one writer
    (GoalStore.post_status — the writer rules apply
    there: contract 06's closed code set, a blocked post
    carries its basis citation or is refused, the writer
    stamps posted_at and the verification, a terminal
    post retires the ping in the same call)."""
    post = body.get("post")
    if not isinstance(post, dict):
        raise ApiError(400, "status needs a \"post\" "
                            "object")
    store = _store()
    if store.get(slug) is None:
        raise ApiError(404, f"unknown goal {slug}")
    try:
        outcome = store.post_status(slug, post)
    except goals_mod.GoalError as e:
        raise ApiError(400, str(e))
    return {"goal": goals_mod.serve_record(
                outcome["record"]),
            "ping_sync": outcome.get("ping_sync")}
