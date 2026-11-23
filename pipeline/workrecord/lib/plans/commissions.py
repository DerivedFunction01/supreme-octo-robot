"""Commissions of record: the checkable direction
(channel-indistinguishability cure).

From inside a lane, a genuine commission arriving on
its chat channel is indistinguishable from watch
traffic — repetition on the channel is not
verification. The durable record is the check: a
commission of record is a wb todo carrying commission
provenance (commissioned_by + commissioned_at
front-matter), planted only by the writers'
plant_commission (lib/writes/bundles.py) — the watch
machinery writes no todo files, so a watch-originated
claim can never mint the entry that would verify it.

verify_commission resolves a claimed todo id against
the record and rules, unambiguously:

- "commission" — the entry exists and carries
  well-formed provenance; the block states who
  commissioned it, when, and the entry's live status,
  so the lane acts on the record, not the channel.
- "not-a-commission" — no such entry, or the entry
  carries no (or malformed) provenance. A claim that
  does not resolve to an entry on the record is not a
  commission, however it arrived.

This module is pure read: same record → same verdict.
"""

from ..util import parse_iso
from . import bundles as bundle_parser

# The provenance keys, mirrored from the writers'
# COMMISSION_FIELDS (lib/writes/bundles.py) — the one
# mint. Kept as literals here so the read side never
# imports the write side.
_BY = "commissioned_by"
_AT = "commissioned_at"


def commission_entry(plans_dir, todo_id):
    """The record entry a claim cites: the parsed todo
    for todo_id, or None when the record holds no such
    entry. list_todos covers every bundle, the finished
    (archived) ones included."""
    for todo in bundle_parser.list_todos(plans_dir):
        if todo.get("id") == todo_id:
            return todo
    return None


def verify_commission(plans_dir, todo_id) -> dict:
    """Rule on a claimed commission: does todo_id
    resolve to a commission of record?

    Returns the verdict block: {verdict, todo_id,
    title, status, bundle, path, commissioned_by,
    commissioned_at, reason}. The verdict is about
    authenticity — a verified commission whose entry
    stands done or archived is still a commission of
    record, and the block's status says so, so the
    lane can tell live direction from history."""
    todo = commission_entry(plans_dir, todo_id)
    if todo is None:
        return {
            "verdict": "not-a-commission",
            "todo_id": todo_id,
            "title": None, "status": None,
            "bundle": None, "path": None,
            "archived": None,
            "commissioned_by": None,
            "commissioned_at": None,
            "reason": ("no entry on the record resolves "
                       "to this id — a claim carried only "
                       "by a chat channel is not a "
                       "commission"),
        }
    fields = todo.get("fields") or {}
    by = str(fields.get(_BY) or "").strip() or None
    at = str(fields.get(_AT) or "").strip() or None
    base = {
        "todo_id": todo_id,
        "title": todo.get("title"),
        "status": todo.get("status"),
        "bundle": todo.get("bundle"),
        "path": todo.get("path"),
        "archived": bool(todo.get("archived")),
        "commissioned_by": by,
        "commissioned_at": at,
    }
    if by is None or at is None:
        return {**base,
                "verdict": "not-a-commission",
                "reason": ("the record entry carries no "
                           "commission provenance — it "
                           "was never commissioned through "
                           "the record's write path")}
    try:
        parse_iso(at)
    except (TypeError, ValueError):
        return {**base,
                "verdict": "not-a-commission",
                "reason": (f"the entry's commissioned_at "
                           f"{at!r} is not an ISO-8601 "
                           f"instant — malformed provenance "
                           f"is not provenance")}
    return {**base,
            "verdict": "commission",
            "reason": (f"commission of record: planted by "
                       f"{by} at {at} through the record's "
                       f"write path")}
