"""The served lease card: one lease's card shape,
assembled in the state build beside the record it
describes (the lease-card unification plan, Step 1).

Both frontends used to derive this card client-side
from the same records — the panel's projections and
the superapp's view model, two stacks over one
payload, disagreeing in places (countdown grammar,
time zone, state derivation). The card is the union
of what both computed, with the panel's derivation
canonical where they disagreed, computed here where
the record, the shape catalog, and the grant state
are all in hand. A frontend renders the card as
served; it derives nothing and branches on nothing.

The card's capability set states, per action verb,
whether the lease core would accept that action on
this lease — computed from the core's own refusal
rules, so a frontend disables the action before the
click instead of learning from a refusal:

- adopt applies only where a session listing exists
  (the home venue's CLI can show sessions); another
  venue's lease registers its session directly and
  has nothing to adopt (reason "venue").
- extend / shorten refuse while a grant manages the
  lease — the record's standing stamp under an
  active grant, the core's standing-managed refusal
  (reason "grant-managed").
- exec is in the frontend interface's verb set but
  no route serves it (reason "unserved").

Everything here is a pure function of the served
entry, the specs list, the grant verdict, and the
build's clock — no dials, no file reads.
"""

import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..core import foundation

# The panel's served-time zone (its format module's
# TZ): served labels are computed in it, so a card
# reads the same on every surface and in every
# viewer's own zone.
_DISPLAY_TZ = ZoneInfo("America/New_York")

_VENUE_LABELS = {"colab": "Colab", "local": "Local"}

_RENEWAL_SUFFIX = re.compile(r"-r\d+$")

REASON_VENUE = "venue"
REASON_GRANT_MANAGED = "grant-managed"
REASON_UNSERVED = "unserved"

# The card's action verbs, in the canonical
# interface's order for a lease: the lifecycle verbs,
# adoption, and the interface's unserved exec.
CARD_VERBS = ("extend", "shorten", "release", "adopt", "exec")


def _parse(iso):
    """A served timestamp as an aware datetime;
    served stamps carry their offset (a bare one
    reads as UTC)."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _js_num(value) -> str:
    """A number as the clients' template strings
    render it: integral values without a fraction,
    others in their shortest round-trip form."""
    value = float(value)
    if value == int(value):
        return str(int(value))
    return repr(value)


def fmt_time(iso) -> str:
    """The panel's fmtTime: hour (no leading zero),
    two-digit minute, AM/PM, in the served zone."""
    dt = _parse(iso).astimezone(_DISPLAY_TZ)
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{hour}:{dt.minute:02d} {ampm}"


def fmt_remaining(ms) -> str:
    """The panel's fmtRemaining: whole minutes,
    clamped at zero, as "H h MM min left" (hours
    are never folded into days)."""
    mins = max(0, math.floor(ms / 60000 + 0.5))
    return f"{mins // 60} h {mins % 60:02d} min left"


def display_name(session: str) -> str:
    """The panel's liveSessionName: the renewal
    suffix drops, the base name title-cases word by
    word; the nameless sentinel keeps its word."""
    if session == "?":
        return "Unnamed session"
    base = _RENEWAL_SUFFIX.sub("", session)
    return " ".join(
        w[:1].upper() + w[1:] if w else w
        for w in base.split("-"))


def venue_label(venue: str) -> str:
    """The panel's venueLabel: a labelled venue kind
    renders its label; an unlabelled one renders as
    its own served id, never dressed as another."""
    return _VENUE_LABELS.get(venue, venue)


def spec_index(specs_list) -> dict:
    """The panel's specMap over the served specs
    list: keyed by id (first entry wins) and by
    venue:id where the entry carries its venue."""
    index = {"by_id": {}, "by_venue_id": {}}
    for spec in specs_list or []:
        if spec.get("id") is None:
            continue
        if spec["id"] not in index["by_id"]:
            index["by_id"][spec["id"]] = spec
        if spec.get("venue"):
            index["by_venue_id"][
                f"{spec['venue']}:{spec['id']}"] = spec
    return index


def _spec_for(index, shape, venue):
    """The panel's shape lookup: the venue-scoped
    entry wins, then the bare id's."""
    if venue:
        spec = index["by_venue_id"].get(f"{venue}:{shape}")
        if spec is not None:
            return spec
    return index["by_id"].get(shape)


def _shape_descriptor(spec) -> str:
    """The panel's spec descriptor: "CPU" alone when
    a plain CPU shape's name is its label, otherwise
    kind and shape joined ("CPU · High-RAM",
    "GPU · T4")."""
    gpu = spec.get("gpu")
    tpu = spec.get("tpu")
    kind = "GPU" if gpu else "TPU" if tpu else "CPU"
    shape = gpu or tpu or (
        "High-RAM" if spec.get("high_mem") else "Standard")
    if not gpu and not tpu and shape == spec.get("label"):
        return kind
    return f"{kind} · {shape}"


def lease_capabilities(record, grant_active_now: bool) -> dict:
    """One lease's capability set: per verb,
    {"applicable": bool, "reason": str | None} —
    the core's refusal rules, stated ahead of the
    click (see the module docstring)."""
    venue = record.get("venue") or foundation.VENUE
    grant_managed = bool(record.get("standing")) \
        and grant_active_now

    def cap(applicable, reason=None):
        return {"applicable": applicable, "reason": reason}

    managed = cap(
        not grant_managed,
        REASON_GRANT_MANAGED if grant_managed else None)
    return {
        "extend": dict(managed),
        "shorten": dict(managed),
        "release": cap(True),
        "adopt": cap(
            venue == foundation.VENUE,
            None if venue == foundation.VENUE
            else REASON_VENUE),
        "exec": cap(False, REASON_UNSERVED),
    }


def lease_card(entry, index, grant_active_now: bool,
               now_dt: datetime) -> dict:
    """One record-carrying state entry's card: the
    identity the card shows, the panel's derived
    labels as served strings, the deadline's
    presentation values, and the capability set.
    `entry` is the state build's own entry (its
    served record copy — never mutated here);
    `index` is spec_index over the build's specs."""
    record = entry["record"]
    venue = record.get("venue") or foundation.VENUE
    shape = record.get("shape")
    spec = _spec_for(index, shape, record.get("venue"))
    shape_label = spec.get("label") if spec else None
    if not shape_label:
        shape_label = shape
    deadline = record.get("deadline")
    deadline_dt = _parse(deadline)
    expired = deadline_dt <= now_dt
    remaining_ms = int(round(
        (deadline_dt - now_dt).total_seconds() * 1000))
    # The burn rate: the record's own rate, else the
    # catalog's for the shape (the panel diagnostics'
    # fallback — the bare id's entry, not venue-scoped).
    rate = record.get("rate_cu_per_hour")
    if rate is None:
        bare = index["by_id"].get(shape)
        rate = bare.get("rate_cu_per_hour") if bare else None
    rate_label = f"{_js_num(rate)} CU/h" \
        if rate is not None else "Cost unconfirmed"
    at_acquire = record.get("budget_at_acquire") or {}
    reserved = at_acquire.get("projected")
    if reserved is None:
        reserved = at_acquire.get("reserved_cu")
    if reserved is None:
        reserved = 0
    return {
        "session": record.get("session"),
        "display_name": display_name(record.get("session")),
        "venue": venue,
        "venue_label": venue_label(venue),
        "target": record.get("target"),
        "shape": shape,
        "shape_label": shape_label,
        "shape_descriptor": _shape_descriptor(spec)
        if spec else shape,
        "caller": record.get("caller")
        or entry.get("caller"),
        "account": record.get("account"),
        "state": "renewal-due" if expired else "running",
        "state_label": "Renewal due" if expired
        else "Running",
        "state_tone": "warn" if expired else "ok",
        "action": entry.get("action"),
        "standing": bool(record.get("standing")),
        "acquired_at": record.get("acquired_at"),
        "deadline": deadline,
        "deadline_label": fmt_time(deadline),
        "ends_label": f"{'ended' if expired else 'ends'} "
        f"{fmt_time(deadline)}",
        "expired": expired,
        "remaining_ms": remaining_ms,
        "remaining_label": "deadline passed" if expired
        else f"{fmt_time(deadline)} · "
        f"{fmt_remaining(remaining_ms)}",
        "rate_cu_per_hour": record.get("rate_cu_per_hour"),
        "rate_label": rate_label,
        "reserved_cu": reserved,
        "envelope_id": record.get("envelope_id"),
        "diagnostics": _diagnostics(
            entry, record, rate_label, now_dt),
        "capabilities": lease_capabilities(
            record, grant_active_now),
    }


def _diagnostics(entry, record, rate_label, now_dt):
    """The card's diagnostics block (the panel's V7
    derivations that the records portion can serve):
    heartbeat and pulse labels, the burn label, and
    the sync claim. Serves None when nothing is
    known — no heartbeat age, no pulse result, no
    claim (honest absence, the panel's rule; its
    listener-census branch rides the listeners
    portion, which is not this build's input)."""
    heartbeat_age = entry.get("keepalive_heartbeat_age_s")
    pulse = record.get("last_pulse_result")
    claim = entry.get("sync_claim")
    if heartbeat_age is None and not pulse and not claim:
        return None
    claim_view = None
    if claim:
        until = claim.get("expires_at") \
            or claim.get("until") \
            or now_dt.isoformat()
        claim_view = {
            "caller": claim.get("caller"),
            "until_label": fmt_time(until),
        }
    return {
        "heartbeat_label": "unknown"
        if heartbeat_age is None
        else f"{math.floor(heartbeat_age + 0.5)}s ago",
        "pulse_label": pulse,
        "burn_label": rate_label,
        "sync_claim": claim_view,
    }
