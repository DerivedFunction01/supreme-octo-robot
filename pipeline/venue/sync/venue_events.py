#!/usr/bin/env python3
"""Venue events: the served event shape and its LogRow split.

Contract 12, finding 4 (S5 half): the venue event record
served one message string — {at, kind, tone, message, venue}
— while the kit's shared timeline row (LogRow, Variant B)
renders a split entry: a compact date token, a time, a
headline, a kind badge, a meta line, and a drawer behind it.
The runner frontend derived that split as a projection, per
consumer — the exact re-derivation the contracts exist to
prevent. The venue layer now serves the split natively: this
module is the one derivation, and the served event shape
carries the split fields as first-class fields (schema:
contracts/schemas/venue-event.schema.json).

The split is a pure function of the record: the date token
and time come from the record's own timestamp, the headline
is the message verbatim (the row wraps it; nothing is
truncated here), and the meta/entity fields carry only what
the record itself serves — a record with no actor or entity
serves none (honest absence, never an invented attribution).
The drawer's remaining facts (Time / Kind / Venue, and a
routing row resolved from the lease a message names) are the
consumer's composition over this shape and the lease records,
as frame B3 of the timeline study draws them.
"""

import calendar
import importlib.util as _ilu
from datetime import datetime
from pathlib import Path

# The lease core's date home, loaded by path: this module
# is itself loaded by path (no package context), so the
# home is bound the venue's by-path way.
_foundation_spec = _ilu.spec_from_file_location(
    "venue_lease_foundation",
    Path(__file__).resolve().parent / "lease" / "core"
    / "foundation.py")
foundation = _ilu.module_from_spec(_foundation_spec)
_foundation_spec.loader.exec_module(foundation)

VENUE = "colab"


def _parse(at):
    try:
        return foundation.parse_dt(str(at))
    except (TypeError, ValueError):
        return None


def split_event(entry: dict, venue: str = VENUE) -> dict:
    """One event record -> the served shape with its split.

    The record's own fields pass through exactly as written;
    the split fields are added. `venue` names the serving
    core's venue when the record itself carries none (a fact
    about the server, like the state portions' venue key —
    records the core writes carry their own)."""
    out = dict(entry)
    out.setdefault("venue", entry.get("venue") or venue)
    at = entry.get("at") or entry.get("ts")
    out.setdefault("at", at)
    dt = _parse(at)
    if dt is not None:
        out["date_token"] = f"{calendar.month_abbr[dt.month]} {dt.day}"
        hour = dt.hour % 12 or 12
        out["time"] = f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"
    else:
        out["date_token"] = None
        out["time"] = None
    out["headline"] = entry.get("message")
    detail = entry.get("detail") if isinstance(entry.get("detail"), dict) else {}
    out["entity"] = detail.get("session") or entry.get("session")
    out["meta"] = entry.get("meta") or detail.get("caller") or None
    return out
