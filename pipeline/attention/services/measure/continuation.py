"""Continuation dispatch: a measured stall in a declared
programme dispatches its own continue ping to the owning
thread, repeating on the programme's cadence until the
measure itself clears — never an acknowledgement.

The implementation is split along its seams —
continuation_triggers (the stall triggers),
continuation_drain (the Step 4 drain hand-over), and
continuation_actuation (the staffing and sweep
actuation passes) — and this module keeps run_pass,
the one pass that composes them, and re-exports the
whole surface, so existing imports of
attention.services.measure.continuation are unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from attention.domain import attention as dom  # noqa: F401
from attention.infra import wb_client  # noqa: F401
from attention.services import programmes  # noqa: F401
from attention.services.dispatch import dispatch
from attention.services.measure import registry, staffing, stamps  # noqa: F401
from attention.services.waits import engine, fulfillment  # noqa: F401
from attention.services.writes import ingest  # noqa: F401

from .continuation_actuation import (  # noqa: F401
    _STAFFING_CLEARING,
    _SWEEP_CLEARING,
    _SWEEP_NEXT_ACT,
    STAFFING_KINDS,
    STAFFING_LEDGER,
    STAFFING_RULE_ID,
    SWEEP_CLASSES,
    SWEEP_LEDGER,
    SWEEP_RULE_ID,
    _actuate_rows,
    _frontier_steer,
    _serial_steer,
    _staffing_bound_hours,
    _staffing_cadence,
    _staffing_key,
    _staffing_route,
    _staffing_slug,
    _staffing_steer,
    _sweep_steer,
    run_staffing_pass,
    run_sweep_pass,
)
from .continuation_drain import (  # noqa: F401
    DRAIN_TIMEOUT_S,
    _drain_declaration,
    run_drain_pass,
)
from .continuation_triggers import (  # noqa: F401
    _ACTS,
    _CLEARING,
    DEFAULT_IDLE_CLASSES,
    TRIGGER_KINDS,
    _cadence,
    _idle_triggers,
    _is_complete,
    _raise_void_item,
    _signature,
    _triggers,
)


def run_pass(state: dict, settings, now: datetime) -> bool:
    """One continuation pass: a trigger with no ping inside
    its cadence window writes a continuation send; a trigger
    the measure no longer raises leaves the ledger."""
    view = staffing.build_staffing(state, settings, now)
    triggers, watch_changed = _triggers(state, settings, now, view)
    ledger = state.setdefault("continuation", {})
    changed = watch_changed
    if run_drain_pass(state, settings, now):
        changed = True
    if run_staffing_pass(state, settings, now, view):
        changed = True
    if run_sweep_pass(state, settings, now, view):
        changed = True
    for key in list(ledger):
        if key not in triggers:
            del ledger[key]
            changed = True
    for key, (handle, summary, detail, cadence) in triggers.items():
        entry = ledger.get(key)
        if entry and now - entry["last_ping_at"] < timedelta(minutes=cadence):
            continue
        handler = next(
            (h for h in state.get("handlers", []) if h["handle"] == handle),
            None,
        )
        if handler is not None and handler.get("retired"):
            continue
        if entry and entry.get("send_id"):
            prior = next(
                (x for x in state.get("sends", []) if x["id"] == entry["send_id"]),
                None,
            )
            if prior is not None and dispatch.state_of(prior, now) in (
                "undispatched",
                "claimed",
            ):
                # The last ping still stands undelivered in
                # the queue; a twin mint helps no one.
                continue
        send = engine.record_send(
            state,
            "continuation",
            handle,
            {"summary": summary, "detail": detail},
            now,
            rule_id="attention:continuation",
        )
        ledger[key] = {
            "last_ping_at": now,
            "pings": (entry or {}).get("pings", 0) + 1,
            "send_id": send["id"],
        }
        changed = True
    return changed
