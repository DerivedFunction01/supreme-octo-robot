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

import copy
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
CALM = "quiet-ridge-11"
SCARLET = "amber-cliff-23"
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
    """Deliver one send by id: stamp the delivery on
    the record, so the next cadence window may re-post
    that row. (The claim+ack path this once drove is
    retired — attention fold: sends are
    born settled and nothing claims them. The stamp
    stands the record in the same delivered read state
    these pins measure the actuation ledger against.)"""
    record = send.setdefault("dispatch", {})
    record["delivered_at"] = now
    record["delivery_ref"] = ref


def _deliver(state, settings_, now, ref="chat:test:1"):
    """The delivery leg, as a record stamp: the steer
    stands delivered, so the next cadence window may
    re-post."""
    _deliver_send(state, settings_, now, state["sends"][-1], ref)


def staffing_sends(state):
    return [
        s for s in state.get("sends") or []
        if s.get("rule_id") == continuation.STAFFING_RULE_ID
    ]


def packet_unlanded(slug):
    """The registry contract with the segment
    packet marker unlanded: the contract as it
    stood in the recorded specimen window, before
    the packet landing flipped the marker by
    amendment. The window is measured under the
    contract as it stood in the window; the live
    seed now carries the flip."""
    contract = _REAL_CONTRACT_FOR(slug)
    if contract:
        for entry in contract.get("staffable_queue") or []:
            if entry["key"] == "segment-packet-landing":
                entry["landed"] = False
    return contract


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
        self.assertIn("amber-cliff-23", send["text"])
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
        # The 11:00Z specimen reads staffed on the
        # count bands as first seeded, and the queue
        # stands nothing due there either, under the
        # contract as it stood in the window — its
        # staffable-now work was staffed and pruned
        # by amendment, and the one remaining item
        # was gated on the packet marker, which stood
        # unlanded at that instant (the flip came
        # later, by amendment, when the packet
        # landed). Under the cured floor (8 distinct
        # register families in active work) the
        # specimen's five families no longer clear
        # the measure, so the clearing state tops the
        # snapshot up to the floor with three further
        # families in flight — the measure clears:
        # the row is gone, the ledger entry leaves
        # with it, and no further steer posts (the
        # pass still reports the ledger clear as a
        # change).
        staffed = defect_state(at(11))
        families = staffed["venue_snapshot"]["edgar-greenfield"]["families"]
        for name in ("fam-a", "fam-b", "fam-c"):
            families[name] = {"sessions": [CALM], "runs": 1, "child_runs": 1}
        state["venue_snapshot"] = staffed["venue_snapshot"]
        state["capacity_snapshot"] = staffed["capacity_snapshot"]
        with mock.patch.object(
            registry, "staffing_contract_for", packet_unlanded
        ):
            cleared = continuation.run_staffing_pass(state, settings(), at(11))
        self.assertTrue(cleared)
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


# A synthetic queue in the commission's form, for
# the steer specimens: the seeded queue's only
# remaining work is gated on an unlanded marker,
# so the seed itself never reads due and cannot
# raise a commission — the steer form is proven
# against this fixture instead.
SYNTHETIC_QUEUE = [
    {
        "key": "trace-pricing",
        "label": "Trace pricing",
        "family": "tracefam",
        "staffable_when": None,
    },
    {
        "key": "register-close",
        "label": "Register close",
        "marker": True,
        "landed": False,
    },
    {
        "key": "reader-pricing",
        "label": "Reader pricing",
        "family": "readerfam",
        "staffable_when": "register-close",
    },
    {
        "key": "packet-landing",
        "label": "Packet landing",
        "marker": True,
        "landed": False,
    },
    {
        "key": "round-build",
        "label": "Round build",
        "family": "roundfam",
        "staffable_when": "packet-landing",
    },
]

_REAL_CONTRACT_FOR = registry.staffing_contract_for


def synthetic_queue_contract(slug):
    """The registry contract with its staffable
    queue swapped for the synthetic fixture."""
    contract = _REAL_CONTRACT_FOR(slug)
    if contract is not None:
        contract["staffable_queue"] = copy.deepcopy(SYNTHETIC_QUEUE)
    return contract


class CommissionSteerTests(unittest.TestCase):
    """The commission form (staffing-commission
    amendment): where the serial row carries due
    queue work, the steer's next act names it in
    queue order, with the gate clause for each item
    still gated on an unlanded marker; the clearing
    stays later-measure-only. The queue behind the
    row is the synthetic fixture above."""

    def test_serial_steer_carries_the_commission(self):
        state = defect_state(at(14))
        with mock.patch.object(
            registry, "staffing_contract_for", synthetic_queue_contract
        ):
            continuation.run_staffing_pass(state, settings(), at(14))
        sends = staffing_sends(state)
        self.assertEqual(len(sends), 1)
        text = sends[0]["text"]
        self.assertIn(
            "Staffing commission — staff: "
            "Trace pricing.",
            text,
        )
        self.assertIn(
            "Reader pricing staffs on "
            "Register close.",
            text,
        )
        self.assertIn(
            "Round build staffs on "
            "Packet landing.",
            text,
        )
        # The commission replaces the generic next act.
        self.assertNotIn("staff a second family", text)

    def test_commission_clears_only_on_a_staffing_measure(self):
        state = defect_state(at(14))
        with mock.patch.object(
            registry, "staffing_contract_for", synthetic_queue_contract
        ):
            continuation.run_staffing_pass(state, settings(), at(14))
            _deliver(state, settings(), at(14))
            # A delivered steer — the closest thing to an
            # acknowledgement the ledger ever sees — does
            # not clear the row: at the next cadence the
            # commission re-posts while the queue work
            # still stands unstaffed.
            _refresh_capacity(state, at(14, 31))
            self.assertTrue(
                continuation.run_staffing_pass(state, settings(), at(14, 31))
            )
            sends = staffing_sends(state)
            self.assertEqual(len(sends), 2)
            self.assertIn("Staffing commission", sends[1]["text"])
            _deliver(state, settings(), at(14, 31), ref="chat:test:2")
            # The measure showing the due family in
            # flight, bands met, clears it: no third
            # steer, and the ledger entry leaves.
            staffed = defect_state(at(11))
            families = staffed["venue_snapshot"]["edgar-greenfield"]["families"]
            families["tracefam"] = {"sessions": [CALM], "runs": 1, "child_runs": 1}
            # Topped up to the cured floor of 8: the
            # specimen's five families plus tracefam
            # read below the floor on their own.
            for name in ("fam-a", "fam-b"):
                families[name] = {"sessions": [CALM], "runs": 1, "child_runs": 1}
            state["venue_snapshot"] = staffed["venue_snapshot"]
            state["capacity_snapshot"] = staffed["capacity_snapshot"]
            self.assertTrue(continuation.run_staffing_pass(state, settings(), at(11)))
        self.assertEqual(len(staffing_sends(state)), 2)
        self.assertEqual(state.get(continuation.STAFFING_LEDGER), {})

    def test_no_queue_keeps_the_generic_next_act(self):
        # A serial row with no queue behind it (the
        # frontier programme shape) keeps the generic
        # next act byte-identical.
        row = {
            "kind": "serial_staffing",
            "topic": None,
            "handle": "@xbrl",
            "handler_label": "edgar — greenfield extractor",
            "families": [{"name": "cocisep", "sessions": [CALM], "runs": 1}],
            "idle_sessions": [{"name": SCARLET, "idle_minutes": 52}],
            "conditions": ["fewer_than_min_families_in_flight"],
        }
        _summary, detail = continuation._serial_steer(row, None, False, None)
        self.assertIn(
            "Next act: staff distinct register families up to the "
            "contract's floor in active work, or verify family by "
            "family that no parallelizable work stands.",
            detail,
        )
        self.assertNotIn("Staffing commission", detail)


if __name__ == "__main__":
    unittest.main()
