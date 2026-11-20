"""Staffing actuation tests (supervision plan Step 3):
the tick actuates the Step 2 defect rows — a steer
to the owning coordinator through the dispatch path,
re-posted on the registry reminder cadence until a
later measure clears the row, escalating to main
past the registry escalation bound. Steers are
app-issued records in the attention store, visible
in the app. The hard-stop floor is structural: only
the two measure kinds actuate, and a row naming a
hard-stop class never does. The specimen state is
the Step 2 recorded window: 14:00Z reads a serial
defect (one family on calm, scarlet idle).
"""

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import store as store_mod  # noqa: E402
from attention.services.dispatch import dispatch  # noqa: E402
from attention.services.measure import (  # noqa: E402
    continuation,
    registry,
    staffing,
    venue,
)
from attention.settings import Settings  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "venue-results"
CALM = "calm-ledge-48"
SCARLET = "scarlet-ledge-52"
BUNDLE = "2026-11-19-superapp-supervision-reminders"


def at(hour, minute=0):
    return datetime(2026, 11, 19, hour, minute, tzinfo=UTC)


def settings():
    return Settings(run_records_dir=FIXTURES / "detached")


def edgar_records(now):
    records = venue.read_run_store(FIXTURES / "runs", now)
    declarations = registry.active_declarations()
    return [
        r
        for r in records
        if venue.attribute_slug(r["caller"], declarations) == "edgar-greenfield"
    ]


def defect_state(now, frontier=None):
    """The served-view state at a defect instant: the
    14:00Z specimen (one family on calm, scarlet
    idle) with the programme's open work armed."""
    facts = venue.families_at(edgar_records(now), now, 30)
    armed = [
        {
            "project": "edgar-sec",
            "todo": todo,
            "row": {
                "project": "edgar-sec",
                "programme": "edgar-sec",
                "todo": todo,
                "bundle": "2026-11-17-greenfield-continuous-improvement",
                "status": "doing",
                "armed_at": (now - timedelta(minutes=5)).isoformat(),
                "cadence_minutes": 15,
            },
            "ingested_at": now,
        }
        for todo in ("ci-corefin-coci-build", "ci-research-discovery-lane")
    ]
    state = store_mod.empty_state()
    state["programmes"] = []
    state["armed_rows"] = armed
    state["capacity_snapshot"] = {
        "at": now,
        "sessions": [{"session": CALM}, {"session": SCARLET}],
        "session_runs": {CALM: 1, SCARLET: 0},
        "idle_since": {SCARLET: now - timedelta(minutes=52)},
        "specs": [],
    }
    state["venue_snapshot"] = {
        "edgar-greenfield": {"at": now, "jobs": len(edgar_records(now)), **facts}
    }
    if frontier is not None:
        state["frontier_snapshot"] = {BUNDLE: frontier}
    return state


def frontier_entry(slug, project="workbench-viewer"):
    return {
        "bundle": BUNDLE,
        "project": project,
        "slug": slug,
        "at": at(14),
        "expected": ["lane-a", "lane-b"],
        "actual": ["lane-a"],
        "missing": ["lane-b"],
        "serial_excluded": ["shared-step"],
    }


def _refresh_capacity(state, now):
    """The live capacity loop re-collects on its own
    cadence, so a tick minutes later reads a fresh
    snapshot: advance the frozen fixture snapshot's
    stamp to the tick, keeping the specimen facts.
    Without this the 15-minute staleness bound
    drops the serial row from the view and the
    ledger clears — the measure's own semantics,
    not the actuation's."""
    state["capacity_snapshot"]["at"] = now
    for facts in (state.get("venue_snapshot") or {}).values():
        facts["at"] = now


def _deliver_send(state, settings_, now, send, ref="chat:test:1"):
    """Deliver one send by id: the dispatch consumer
    claims and acks it, so the next cadence window
    may re-post that row."""
    dispatch.claim(state, send["id"], {"consumer": "test"}, settings_, now)
    dispatch.ack(
        state, send["id"], {"consumer": "test", "delivery_ref": ref}, now
    )


def _deliver(state, settings_, now, ref="chat:test:1"):
    """The live loop's delivery leg: the dispatch
    consumer claims and acks the steer, so the next
    cadence window may re-post."""
    _deliver_send(state, settings_, now, state["sends"][-1], ref)


def staffing_sends(state):
    return [
        s for s in state.get("sends") or []
        if s.get("rule_id") == continuation.STAFFING_RULE_ID
    ]


class StaffingActuationTests(unittest.TestCase):
    def test_defect_posts_exactly_one_steer_per_tick(self):
        state = defect_state(at(14))
        self.assertTrue(continuation.run_staffing_pass(state, settings(), at(14)))
        sends = staffing_sends(state)
        self.assertEqual(len(sends), 1)
        send = sends[0]
        self.assertEqual(send["handle"], "@xbrl")
        self.assertEqual(send["target"], "@xbrl")
        self.assertIn("cocisep", send["text"])
        self.assertIn("scarlet-ledge-52", send["text"])
        # A second pass on the same tick mints no twin.
        self.assertFalse(continuation.run_staffing_pass(state, settings(), at(14)))
        self.assertEqual(len(staffing_sends(state)), 1)

    def test_repost_after_reminder_cadence_not_before(self):
        # The edgar contract's reminder cadence is 30m.
        state = defect_state(at(14))
        continuation.run_staffing_pass(state, settings(), at(14))
        _deliver(state, settings(), at(14))
        _refresh_capacity(state, at(14, 15))
        self.assertFalse(
            continuation.run_staffing_pass(state, settings(), at(14, 15))
        )
        self.assertEqual(len(staffing_sends(state)), 1)
        _refresh_capacity(state, at(14, 31))
        self.assertTrue(
            continuation.run_staffing_pass(state, settings(), at(14, 31))
        )
        self.assertEqual(len(staffing_sends(state)), 2)

    def test_cleared_measure_stops_reposts(self):
        state = defect_state(at(14))
        continuation.run_staffing_pass(state, settings(), at(14))
        self.assertEqual(len(staffing_sends(state)), 1)
        # The 11:00Z specimen reads staffed: the row is
        # gone, so the ledger entry leaves with it and
        # no further steer posts (the pass still reports
        # the ledger clear as a change).
        staffed = defect_state(at(11))
        state["venue_snapshot"] = staffed["venue_snapshot"]
        state["capacity_snapshot"] = staffed["capacity_snapshot"]
        self.assertTrue(continuation.run_staffing_pass(state, settings(), at(11)))
        self.assertEqual(len(staffing_sends(state)), 1)
        self.assertEqual(state.get(continuation.STAFFING_LEDGER), {})

    def test_escalation_at_the_bound_not_before(self):
        # The edgar registry bound is 1h past first sight.
        state = defect_state(at(14))
        continuation.run_staffing_pass(state, settings(), at(14))
        _deliver(state, settings(), at(14))
        _refresh_capacity(state, at(14, 31))
        continuation.run_staffing_pass(state, settings(), at(14, 31))
        _deliver(state, settings(), at(14, 31), ref="chat:test:2")
        sends = staffing_sends(state)
        self.assertEqual(len(sends), 2)
        self.assertEqual(sends[1]["target"], "@xbrl")
        self.assertNotIn("escalated", sends[1]["text"])
        _refresh_capacity(state, at(15, 1))
        continuation.run_staffing_pass(state, settings(), at(15, 1))
        sends = staffing_sends(state)
        self.assertEqual(len(sends), 3)
        escalated = sends[2]
        self.assertEqual(escalated["target"], "main")
        self.assertIn("escalated to main", escalated["text"])
        self.assertIn("@xbrl has not responded", escalated["text"])

    def test_frontier_shortfall_steers_naming_prerequisite_due(self):
        state = defect_state(at(14), frontier=frontier_entry("edgar-greenfield"))
        continuation.run_staffing_pass(state, settings(), at(14))
        sends = staffing_sends(state)
        # One steer per standing row: the serial row and
        # the frontier row.
        self.assertEqual(len(sends), 2)
        frontier = [s for s in sends if "frontier shortfall" in s["text"]]
        self.assertEqual(len(frontier), 1)
        self.assertEqual(frontier[0]["handle"], "@xbrl")
        self.assertIn(BUNDLE, frontier[0]["text"])
        self.assertIn("lane-b", frontier[0]["text"])

    def test_slug_null_frontier_steers_by_bundle_and_project(self):
        # The supervision bundle the frontier could not
        # attribute: the steer is addressed by the
        # bundle and project it carries — never dropped,
        # never an invented slug — and never escalates,
        # since no registry declaration names a
        # coordinator to hold to the bound.
        state = defect_state(at(14), frontier=frontier_entry(None))
        continuation.run_staffing_pass(state, settings(), at(14))
        sends = staffing_sends(state)
        frontier = [s for s in sends if "frontier shortfall" in s["text"]]
        self.assertEqual(len(frontier), 1)
        self.assertEqual(frontier[0]["handle"], "workbench-viewer")
        self.assertEqual(frontier[0]["target"], "workbench-viewer")
        self.assertIn(BUNDLE, frontier[0]["text"])
        self.assertNotIn("supreme-octo-robot", frontier[0]["text"])
        # Past any bound, the row still never escalates:
        # no registry declaration names a coordinator to
        # hold to it. Deliver its steer first, so the
        # re-post — not the twin guard — is what the
        # tick exercises.
        _deliver_send(state, settings(), at(14), frontier[0])
        _refresh_capacity(state, at(16, 1))
        continuation.run_staffing_pass(state, settings(), at(16, 1))
        sends = staffing_sends(state)
        frontier = [s for s in sends if "frontier shortfall" in s["text"]]
        self.assertEqual(len(frontier), 2)
        self.assertTrue(all(s["target"] != "main" for s in frontier))

    def test_hard_stop_class_never_actuates(self):
        state = defect_state(at(14))
        view = staffing.build_staffing(state, settings(), at(14))
        serial = [
            r for r in view["rows"] if r["kind"] == "serial_staffing"
        ][0]
        poisoned = dict(
            serial, kind="permission_card", _key="permission_card:edgar"
        )
        with mock.patch.object(
            staffing, "build_staffing",
            return_value={"rows": [serial, poisoned]},
        ):
            changed = continuation.run_staffing_pass(
                state, settings(), at(14)
            )
        self.assertTrue(changed)
        sends = staffing_sends(state)
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0]["handle"], "@xbrl")

    def test_todo_route_targets_the_bundle(self):
        row = {
            "kind": "serial_staffing",
            "topic": "edgar-greenfield",
            "handle": "@xbrl",
            "handler_label": "edgar — greenfield extractor",
        }
        route = {"sender": "wb", "kind": "todo", "bundle": "b-1"}
        with mock.patch.object(
            registry, "coordinator_route_for", return_value=route
        ):
            handle, target = continuation._staffing_route(row, "edgar-greenfield")
        self.assertEqual(handle, "@xbrl")
        self.assertEqual(target, "b-1")

    def test_retired_handler_gets_no_steer(self):
        state = defect_state(at(14))
        state["handlers"] = [{"handle": "@xbrl", "retired": True}]
        self.assertFalse(continuation.run_staffing_pass(state, settings(), at(14)))
        self.assertEqual(staffing_sends(state), [])

    def test_run_pass_actuates_the_staffing_leg(self):
        state = defect_state(at(14))
        self.assertTrue(continuation.run_pass(state, settings(), at(14)))
        self.assertEqual(len(staffing_sends(state)), 1)


if __name__ == "__main__":
    unittest.main()
