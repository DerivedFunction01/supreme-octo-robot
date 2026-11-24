"""The capacity collector's pass and loop, extracted
from the serving shell (server.py) along its natural
seam: panel reads cost tens of seconds, so the
collection runs on its own slow cadence into the
cached snapshot the staffing measure reads. The shell
wires the loop as one of its supervised workers; the
pass itself — its collectors, its merge discipline,
and its failure recording — lives here whole.
"""

from datetime import datetime

from attention.infra.store import Store
from attention.services import contracts
from attention.services.measure import (
    lanes,
    plans,
    records,
    staffing,
    stamps,
    venue,
    worktrees,
)
from attention.services.reads import digest
from attention.settings import Settings


def _capacity_pass(store: Store, settings: Settings, lock) -> None:
    """One capacity collection (the pinned loop's body):
    panel reads cost tens of seconds, so they run on their
    own slow cadence into the cached snapshot the staffing
    measure reads. A failed collection never kills the
    serve — and never goes silent either: the failure is
    recorded in the served state (capacity_pass_error,
    with the pass's instant and the exception's identity)
    so a frozen snapshot names its own cause, and the
    next clean pass clears the record in its merge."""
    try:
        now = datetime.now().astimezone()
        fresh = store.load_state()
        before = (fresh.get("capacity_snapshot"), fresh.get("capacity_error"))
        staffing.collect_capacity(fresh, settings, now)
        trees_changed = worktrees.collect(fresh, now)
        records_changed = records.collect(fresh, now)
        lanes_changed = lanes.collect(fresh, now)
        consumption_changed = records.collect_consumption(fresh, settings, now)
        unlanded_changed = records.collect_unlanded(fresh, settings, now)
        goals_changed = records.collect_goals(fresh, now)
        stamps_changed = stamps.collect(fresh, settings, now)
        venue_changed = venue.collect(fresh, settings, now)
        frontier_changed = venue.collect_frontier(fresh, settings, now)
        plans_changed = plans.collect(fresh, now)
        contracts_changed = contracts.sync(fresh)
        digest_changed = digest.collect_wb_facts(fresh, settings, now)
        after = (fresh.get("capacity_snapshot"), fresh.get("capacity_error"))
        if (
            after != before
            or fresh.get("capacity_pass_error")
            or trees_changed
            or records_changed
            or lanes_changed
            or consumption_changed
            or unlanded_changed
            or goals_changed
            or contracts_changed
            or stamps_changed
            or venue_changed
            or frontier_changed
            or plans_changed
            or digest_changed
        ):
            with lock:
                state = store.load_state()
                state["capacity_snapshot"] = after[0]
                state["capacity_error"] = after[1]
                state["capacity_pass_error"] = None
                if trees_changed:
                    state["worktree_snapshot"] = fresh["worktree_snapshot"]
                if records_changed:
                    state["record_snapshot"] = fresh["record_snapshot"]
                if lanes_changed:
                    state["lane_snapshot"] = fresh["lane_snapshot"]
                if consumption_changed:
                    state["consumption_snapshot"] = fresh["consumption_snapshot"]
                if unlanded_changed:
                    state["unlanded_snapshot"] = fresh["unlanded_snapshot"]
                if goals_changed:
                    state["goal_snapshot"] = fresh["goal_snapshot"]
                if stamps_changed:
                    state["stamp_snapshot"] = fresh["stamp_snapshot"]
                    state["blocked_snapshot"] = fresh["blocked_snapshot"]
                if venue_changed:
                    state["venue_snapshot"] = fresh["venue_snapshot"]
                if frontier_changed:
                    state["frontier_snapshot"] = fresh["frontier_snapshot"]
                if plans_changed:
                    state["plan_snapshot"] = fresh["plan_snapshot"]
                if contracts_changed:
                    state["programmes"] = fresh["programmes"]
                if digest_changed:
                    state["digest_wb_snapshot"] = fresh["digest_wb_snapshot"]
                store.save_state(state)
    except Exception as err:
        # The merge above never ran, so nothing in this
        # pass landed; record why, under the same lock
        # and load-merge discipline, against the current
        # state — never over another loop's fresher keys.
        # A failure to record is itself contained: it
        # must not kill the serve either.
        try:
            with lock:
                state = store.load_state()
                state["capacity_pass_error"] = {
                    "at": datetime.now().astimezone(),
                    "error": f"{type(err).__name__}: {err}",
                }
                store.save_state(state)
        except Exception:
            pass


def _capacity_loop(stop, store: Store, settings: Settings, lock) -> None:
    while not stop.is_set():
        _capacity_pass(store, settings, lock)
        stop.wait(max(60.0, settings.capacity_collect_minutes * 60))
