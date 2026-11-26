"""Shadow parity (supervision plan Step 6): the app
measures in shadow beside the live cron fleet, over
the recorded specimen window. Every defect either
side raises is compared; a miss by the app side blocks cutover for
that surface. The bar (the plan's verify line): zero
app-side misses against cron-side defects on the
staffing and drain surfaces.

The cron-side rules are encoded independently in-test
from the cron bodies — they read
the same fixture run records and specimen facts, but
through their own derivations, never through the app
code under test. The app side is build_staffing,
run_pass's actuation legs, and the drain leg. The
specimens are the Step 2 recorded windows plus the
stall events and the launch-lost orphan the fleet
actually produced in the window.

What this harness does NOT cover (named, not hidden):
the greenfield watch's edgar-programme content
clauses (open-set coverage, imposter census,
elimination cascade, discoveries, combination
pricing, fresh-discovery delegate) are not generic
tick rules — they are coordinator-owned programme
rules, dispositioned in the parity report. The
orphan-B class (a terminal record never collected)
is a named residual: the run record carries no
outputs declaration, so the tick cannot tell
"nothing to pull" from "never pulled" — pinned by
test_terminal_uncollected_is_the_named_residual.
Utilization accounting (sweep A5) is computed at
report time from the todo files plus run records,
not served by the tick — the parity report carries
the fractions.
"""

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import store as store_mod  # noqa: E402
from attention.infra import wb_client  # noqa: E402
from attention.services.measure import (  # noqa: E402
    continuation,
    registry,
    staffing,
    venue,
)
from attention.settings import Settings  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                       / "workrecord"))

from lib import drain as drain_mod  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "venue-results"
CALM = "quiet-ridge-11"
SCARLET = "amber-cliff-23"
WINDOW_START = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 11, 20, 0, 30, tzinfo=UTC)
EVIDENCE_WINDOW_MINUTES = 30
CADENCE_MINUTES = 15

ZOMBIE = "specimen-ci-cobalt-price-20261119T115855Z"


def at19(hour, minute=0, second=0):
    return datetime(2026, 11, 19, hour, minute, second, tzinfo=UTC)


def at20(hour, minute=0, second=0):
    return datetime(2026, 11, 20, hour, minute, second, tzinfo=UTC)


def settings():
    return Settings(run_records_dir=FIXTURES / "detached")


# ----------------------------------------------------------------
# Cron side: independent encodings of the cron bodies, reading
# the raw fixture files directly (never the app's readers).
# ----------------------------------------------------------------

def raw_records():
    """The fixture run records as the cron bodies see
    them: raw JSON, keyed by the fields the crons
    name — no app normalization."""
    out = []
    for path in sorted((FIXTURES / "runs").glob("*.json")):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def _parse(raw):
    return datetime.fromisoformat(raw) if raw else None


# The fixture jobs' trailing action vocabulary: the
# segments a job name carries after its table family.
# A family is the job stem with those stripped from
# the right; it agrees with the Step 2 pinned cases
# (cocisep, corefin-coci, testform, is-setlevel).
_ONE_SEGMENT_ACTIONS = {
    "price", "price2", "gate", "probe", "diag", "diag2",
    "plain", "repro", "specimens", "trace", "fmt", "enum",
    "cascade", "g1", "g2", "g4", "g5", "b", "enumC",
    "reproC", "reproE", "build",
}
_TWO_SEGMENT_ACTIONS = {
    "gate-probe", "diag-d", "extract-d", "extract-b",
    "build-enumC-b", "build-gateC", "build-reproC-b",
    "build-reproE-b", "draw-b",
}


def cron_family(job):
    """The table family of a fixture job, by the
    action-vocabulary strip above."""
    stem = job[len("greenfield-ci-"):] \
        if job.startswith("greenfield-ci-") else job
    parts = stem.split("-")
    while len(parts) > 1:
        if "-".join(parts[-2:]) in _TWO_SEGMENT_ACTIONS:
            parts = parts[:-2]
        elif parts[-1] in _ONE_SEGMENT_ACTIONS:
            parts = parts[:-1]
        else:
            break
    return "-".join(parts) or stem


def cron_in_flight(records, now):
    """A run counts at `now` when its finish is still
    ahead, or its evidence advanced within the last 30
    minutes — the staffing reminder's measure, read
    from the raw fixture files. A terminal event is
    the runner's declaration, not a finish: it never
    stands in for one — and a record with no finish
    counts only while its evidence is fresh (the Step
    2 cure: a finishless record with frozen evidence
    is launch-lost, not in flight)."""
    out = []
    for rec in records:
        started = _parse(rec.get("started_at"))
        if started is None or started > now:
            continue
        finished = _parse(rec.get("finished_at"))
        evidence = _parse(rec.get("last_evidence_at")) or started
        finish_ahead = finished is not None and now < finished
        evidence_fresh = now - timedelta(
            minutes=EVIDENCE_WINDOW_MINUTES) <= evidence <= now
        if finish_ahead or evidence_fresh:
            out.append(rec)
    return out


def cron_serial(now):
    """The staffing measure's serial defect at `now`:
    (defect, families, carrying sessions), in the
    cured work-denominated form (owner order,
    cured form): open family work stands in every
    specimen (two edgar-sec todos armed), so the
    defect condition applies directly — fewer
    distinct register families in flight than the
    contract's floor of 8. Sessions are capacity,
    never the denominator: the carrying set is
    returned as evidence, not as a condition."""
    flying = cron_in_flight(raw_records(), now)
    live = {CALM, SCARLET}
    families = {}
    carrying = set()
    for rec in flying:
        families.setdefault(cron_family(rec["job"]), set()) \
            .add(rec.get("session") or "")
        if rec.get("session") in live:
            carrying.add(rec["session"])
    defect = len(families) < 8
    return defect, families, carrying


def cron_stall_gap(checkpoint_at, now):
    """Minutes since the lane's last conforming
    checkpoint. The sweep's IDLE bound (>30 minutes,
    no verified blocked basis) and the watch's stall
    bound (two missed 15-minute intervals) coincide
    at a 15-minute cadence."""
    return (now - checkpoint_at).total_seconds() / 60


def cron_orphans(now):
    """The sweep's orphan class at `now`, split by
    shape: (launch-lost, terminal-uncollected). A
    record with no payload finish and evidence stale
    past the 30-minute window is an orphan; one whose
    terminal event has landed is terminal-uncollected,
    one whose terminal event has not is launch-lost."""
    lost, uncollected = [], []
    for rec in raw_records():
        started = _parse(rec.get("started_at"))
        if started is None or started > now:
            continue
        if rec.get("finished_at"):
            continue
        evidence = _parse(rec.get("last_evidence_at")) or started
        if now - evidence <= timedelta(
                minutes=EVIDENCE_WINDOW_MINUTES):
            continue
        terminal = _parse(rec.get("terminal_event_at"))
        if terminal is not None and terminal <= now:
            uncollected.append(rec["run_id"])
        else:
            lost.append(rec["run_id"])
    return sorted(lost), sorted(uncollected)


# ----------------------------------------------------------------
# App side: the served view over the same specimens.
# ----------------------------------------------------------------

def edgar_records(now):
    records = venue.read_run_store(FIXTURES / "runs", now)
    declarations = registry.active_declarations()
    return [
        r
        for r in records
        if venue.attribute_slug(r["caller"], declarations)
        == "edgar-greenfield"
    ]


def specimen_state(now, idle_minutes=52):
    """The Step 2 served-view state at a specimen
    instant: capacity from the era's two live sessions,
    family facts from the recorded runs alone, the
    programme's open work armed. Built on the store's
    empty state, so the actuation legs find the sends
    ledger, templates, and presence they write."""
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
        for todo in ("ci-corefin-coci-build",
                     "ci-research-discovery-lane")
    ]
    state = store_mod.empty_state()
    state["programmes"] = []
    state["armed_rows"] = armed
    state["capacity_error"] = None
    state["capacity_snapshot"] = {
        "at": now,
        "sessions": [{"session": CALM}, {"session": SCARLET}],
        "session_runs": {CALM: 1, SCARLET: 0},
        "idle_since": {SCARLET: now - timedelta(minutes=idle_minutes)},
        "specs": [],
    }
    state["venue_snapshot"] = {
        "edgar-greenfield": {
            "at": now,
            "jobs": len(edgar_records(now)),
            **facts,
        }
    }
    return state


def orphan_state(now):
    """The specimen state with the venue collector's
    orphan facts attached, as venue.collect does."""
    state = specimen_state(now)
    state["venue_snapshot"]["edgar-greenfield"]["orphans"] = \
        venue.orphans_at(edgar_records(now), now, 30)
    return state


def stall_state(now, lane, checkpoint_at):
    """A lane-record specimen: the registry's
    edgar-greenfield declaration with one lane record
    whose latest conforming checkpoint is
    `checkpoint_at`."""
    declaration = next(
        d for d in registry.active_declarations()
        if d["slug"] == "edgar-greenfield")
    state = store_mod.empty_state()
    state["programmes"] = [declaration]
    state["record_snapshot"] = {
        "edgar-greenfield": {
            "at": now,
            "records": {
                lane: {
                    "lane": lane,
                    "checkpoint_at": checkpoint_at.isoformat(),
                },
            },
        },
    }
    state["capacity_snapshot"] = {
        "at": now,
        "sessions": [{"session": CALM}, {"session": SCARLET}],
        "session_runs": {CALM: 0, SCARLET: 0},
        "idle_since": {},
        "specs": [],
    }
    return state


def rows_of_kind(view, kind):
    return [r for r in view.get("rows") or [] if r["kind"] == kind]


_REAL_CONTRACT_FOR = registry.staffing_contract_for


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


def sweep_sends(state):
    return [
        s for s in state.get("sends") or []
        if s.get("rule_id") == continuation.SWEEP_RULE_ID
    ]


def staffing_sends(state):
    return [
        s for s in state.get("sends") or []
        if s.get("rule_id") == continuation.STAFFING_RULE_ID
    ]

class CronFamilyDerivation(unittest.TestCase):
    def test_family_strip_agrees_with_step2_pins(self):
        cases = {
            "specimen-ci-cobalt-gate": "cocisep",
            "specimen-ci-cobalt-price": "cocisep",
            "specimen-ci-ledger-cobalt-extract-b": "corefin-coci",
            "specimen-ci-ledger-cobalt-price": "corefin-coci",
            "specimen-ci-formtest-build-gateC": "testform",
            "specimen-ci-tier-level-price": "is-setlevel",
            "specimen-ci-rapids-g1-price": "cascade",
            "specimen-ci-group3-cascade": "rcg3",
            "specimen-ci-phase10-draw-b": "step10",
        }
        for job, family in cases.items():
            self.assertEqual(cron_family(job), family, job)


class StaffingParity(unittest.TestCase):
    def test_staffed_window_both_sides_agree(self):
        # Inside 10:00–12:25Z the records show several
        # families across both live sessions — five in
        # flight at 11:00. Under the contract as first
        # seeded (floor 2) neither side raised a
        # defect; under the cured floor (8 distinct
        # register families in active work at all
        # times, owner order) both sides
        # raise the same defect on the same count:
        # parity is agreement, and the specimen now
        # pins agreement at the cured band. The queue
        # side stands as it stood in the window: the
        # queue's one remaining work item was gated on
        # the packet marker, which stood unlanded at
        # these instants — so the row carries the
        # floor condition alone.
        for now in (at19(11), at19(12), at19(12, 15)):
            defect, families, carrying = cron_serial(now)
            self.assertTrue(defect, f"cron side at {now}")
            self.assertGreaterEqual(len(families), 2, f"at {now}")
            self.assertGreaterEqual(len(carrying), 2, f"at {now}")
            with mock.patch.object(
                registry, "staffing_contract_for", packet_unlanded
            ):
                view = staffing.build_staffing(
                    specimen_state(now), settings(), now)
            rows = rows_of_kind(view, "serial_staffing")
            self.assertEqual(len(rows), 1, f"app side at {now}")
            self.assertEqual(
                rows[0]["conditions"],
                ["fewer_than_min_families_in_flight"],
                f"app side at {now}")

    def test_defect_window_both_sides_agree(self):
        # Inside 13:30–15:22Z the records narrow to one
        # family on one session while the other live
        # session carries none: both sides raise the
        # same defect, with the same family and the
        # same session split.
        for now in (at19(13, 30), at19(14), at19(15),
                    at19(15, 22)):
            defect, families, carrying = cron_serial(now)
            self.assertTrue(defect, f"cron side at {now}")
            self.assertEqual(set(families), {"cocisep"},
                             f"at {now}")
            self.assertEqual(carrying, {CALM}, f"at {now}")
            view = staffing.build_staffing(
                specimen_state(now), settings(), now)
            rows = rows_of_kind(view, "serial_staffing")
            self.assertEqual(len(rows), 1, f"app side at {now}")
            row = rows[0]
            self.assertEqual(
                [f["name"] for f in row["families"]],
                ["cocisep"], f"at {now}")
            self.assertEqual(row["sessions_used"], 1, f"at {now}")
            self.assertEqual(row["sessions_live"], 2, f"at {now}")
            self.assertIn(
                "fewer_than_min_families_in_flight",
                row["conditions"])
            self.assertIn(
                "one_deep_per_session_while_staffable_families_wait",
                row["conditions"])


class StallParity(unittest.TestCase):
    def test_venue_staffing_measure_stall(self):
        # Last checkpoint 2026-11-19T16:40:03Z. At
        # 17:05Z (25 minutes — inside two intervals)
        # neither side flags; at 17:15Z (35 minutes —
        # past both the IDLE and the stall bound) both
        # do, and the app's row maps to both sweep
        # classes.
        checkpoint = datetime(2026, 11, 19, 16, 40, 3,
                              tzinfo=UTC)
        self.assertLess(
            cron_stall_gap(checkpoint, at19(17, 5)), 30)
        view = staffing.build_staffing(
            stall_state(at19(17, 5), "venue-staffing-measure",
                        checkpoint),
            settings(), at19(17, 5))
        self.assertEqual(
            rows_of_kind(view, "record_gap"), [])
        self.assertGreater(
            cron_stall_gap(checkpoint, at19(17, 15)), 30)
        view = staffing.build_staffing(
            stall_state(at19(17, 15), "venue-staffing-measure",
                        checkpoint),
            settings(), at19(17, 15))
        rows = rows_of_kind(view, "record_gap")
        self.assertEqual(len(rows), 1)
        self.assertIn(
            "venue-staffing-measure", rows[0]["handler_label"])
        self.assertEqual(
            set(continuation.SWEEP_CLASSES["record_gap"]),
            {"idle", "stall"})

    def test_retire_status_codes_stall(self):
        # Last checkpoint 2026-11-19T23:43:32Z. At
        # 00:05Z (about 21 minutes) neither side flags;
        # at 00:26Z — the instant the sweep's gap-closure
        # order was measured on the live fleet — both
        # do: the cron side reads a stall, the app side
        # a record gap for the lane.
        checkpoint = datetime(2026, 11, 19, 23, 43, 32,
                              tzinfo=UTC)
        self.assertLess(
            cron_stall_gap(checkpoint, at20(0, 5)), 30)
        view = staffing.build_staffing(
            stall_state(at20(0, 5), "retire-status-codes",
                        checkpoint),
            settings(), at20(0, 5))
        self.assertEqual(
            rows_of_kind(view, "record_gap"), [])
        self.assertGreater(
            cron_stall_gap(checkpoint, at20(0, 26)), 30)
        view = staffing.build_staffing(
            stall_state(at20(0, 26), "retire-status-codes",
                        checkpoint),
            settings(), at20(0, 26))
        rows = rows_of_kind(view, "record_gap")
        self.assertEqual(len(rows), 1)
        self.assertIn(
            "retire-status-codes", rows[0]["handler_label"])


class OrphanParity(unittest.TestCase):
    def test_launch_lost_orphan_both_sides_agree(self):
        # At 14:00Z the fleet holds four records with
        # no payload finish and evidence frozen since
        # their starts: the zombie (no terminal event
        # yet — launch-lost) and three whose terminal
        # events have landed (terminal-uncollected).
        # Both sides surface the same four records as
        # orphans — zero miss on the class.
        lost, uncollected = cron_orphans(at19(14))
        self.assertEqual(lost, [ZOMBIE])
        self.assertEqual(len(uncollected), 3)
        view = staffing.build_staffing(
            orphan_state(at19(14)), settings(), at19(14))
        rows = rows_of_kind(view, "orphan_record")
        self.assertEqual(
            sorted(r["run_id"] for r in rows),
            sorted(lost + uncollected))
        self.assertIn(
            ZOMBIE,
            [r["run_id"] for r in rows])

    def test_terminal_uncollected_is_the_named_residual(self):
        # At 15:00Z the zombie's terminal event has
        # landed (14:05:13Z): the cron side now reads
        # all four as terminal-uncollected, with the
        # self-collect act (A1). The app still raises
        # the orphan row for each — the record is
        # surfaced, not missed — but its next act is
        # the dispose-and-refire act, not self-collect:
        # the record carries no outputs declaration,
        # so the tick cannot tell "nothing to pull"
        # from "never pulled". Pinned here as the
        # orphan surface's residual, carried in the
        # parity report — not as a miss on the class.
        lost, uncollected = cron_orphans(at19(15))
        self.assertEqual(lost, [])
        self.assertEqual(len(uncollected), 4)
        self.assertIn(ZOMBIE, uncollected)
        view = staffing.build_staffing(
            orphan_state(at19(15)), settings(), at19(15))
        rows = rows_of_kind(view, "orphan_record")
        self.assertEqual(
            sorted(r["run_id"] for r in rows),
            sorted(uncollected))
        for row in rows:
            self.assertIn("dispose the record", row["detail"])
            self.assertNotIn("self-collect", row["detail"])


class SweepActuationParity(unittest.TestCase):
    def test_sweep_pass_actuates_stall_rows(self):
        # The sweep's stall actuation, homed in the
        # tick: the 17:15Z stall state steers the
        # owning coordinator once, sent by wb, naming
        # the lane and its next act; a second pass on
        # the same tick mints no twin.
        checkpoint = datetime(2026, 11, 19, 16, 40, 3,
                              tzinfo=UTC)
        state = stall_state(at19(17, 15),
                            "venue-staffing-measure", checkpoint)
        self.assertTrue(
            continuation.run_sweep_pass(
                state, settings(), at19(17, 15)))
        sends = sweep_sends(state)
        self.assertEqual(len(sends), 1)
        send = sends[0]
        self.assertEqual(send["handle"], "@xbrl")
        self.assertIn("venue-staffing-measure", send["text"])
        self.assertIn("checkpoint", send["text"])
        self.assertFalse(
            continuation.run_sweep_pass(
                state, settings(), at19(17, 15)))
        self.assertEqual(len(sweep_sends(state)), 1)

    def test_staffing_rows_never_double_actuate(self):
        # The serial defect at 14:00Z actuates through
        # the staffing pass only: the sweep pass raises
        # no second steer for it.
        state = specimen_state(at19(14))
        self.assertFalse(
            continuation.run_sweep_pass(
                state, settings(), at19(14)))
        self.assertEqual(sweep_sends(state), [])

    def test_staffing_pass_actuates_serial_rows(self):
        # The staffing reminder's enforcement, homed
        # in the tick: the 14:00Z defect steers the
        # coordinator once, naming the family in flight
        # and the idle session.
        state = specimen_state(at19(14))
        self.assertTrue(
            continuation.run_staffing_pass(
                state, settings(), at19(14)))
        sends = staffing_sends(state)
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0]["handle"], "@xbrl")
        self.assertIn("cocisep", sends[0]["text"])
        self.assertIn(SCARLET, sends[0]["text"])


class DrainParity(unittest.TestCase):
    def _todos(self, *specs):
        return [
            {"id": todo_id, "valid": valid, "status": status,
             "updated": "2026-11-19"}
            for todo_id, valid, status in specs
        ]

    def test_bundle_drained_matches_the_record(self):
        # The drain's record is the bundle's own todo
        # states: drained exactly when every todo is
        # valid and done — no cron covered drain, so
        # the parity is app-vs-record.
        drained = self._todos(("t-1", True, "done"),
                              ("t-2", True, "done"))
        self.assertTrue(drain_mod.bundle_drained(drained))
        open_tail = self._todos(("t-1", True, "done"),
                                ("t-2", True, "doing"))
        self.assertFalse(drain_mod.bundle_drained(open_tail))
        self.assertFalse(drain_mod.bundle_drained([]))
        invalid = self._todos(("t-1", True, "done"),
                              ("t-2", False, "done"))
        self.assertFalse(drain_mod.bundle_drained(invalid))

    def test_drain_leg_hands_the_registry_tail(self):
        # The drain leg hands the registry's own tail
        # set — supreme-octo-robot's three items — to
        # each of its workbench projects, per project.
        declaration = next(
            d for d in registry.active_declarations()
            if d["slug"] == "supreme-octo-robot")
        state = store_mod.empty_state()
        state["programmes"] = [declaration]
        seen = []

        def fake_run_drain(url, project, declarations, timeout):
            seen.append((project, declarations))
            return {"drain": [{
                "programme": "supreme-octo-robot",
                "raised": ["Consolidation"], "archived": []}]}

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(
                    wb_client, "run_drain", fake_run_drain):
            changed = continuation.run_drain_pass(
                state,
                Settings(data_path=None,
                         run_records_dir=Path(tmp) / "records"),
                at19(14))
        self.assertTrue(changed)
        self.assertEqual(
            [project for project, _ in seen],
            ["workbench-viewer", "workrecord"])
        for _, declarations in seen:
            self.assertEqual(len(declarations), 1)
            self.assertEqual(
                drain_mod.tail_titles(declarations[0]),
                ["Consolidation", "Doc updates",
                 "Performance pass"])
            self.assertEqual(
                declarations[0]["drain_tail"],
                declaration["drain_tail"])


class WatchGenericCoreParity(unittest.TestCase):
    def test_generic_core_maps_onto_tick_rows(self):
        # The greenfield watch's generic core — stall
        # with successor owed, prerequisite seams — is
        # the tick's rows: a record gap maps to the
        # sweep's stall class, and a frontier shortfall
        # (a prerequisite-due step with no lane) is one
        # of the staffing pass's two actuating kinds.
        self.assertEqual(
            set(continuation.SWEEP_CLASSES["record_gap"]),
            {"idle", "stall"})
        self.assertEqual(
            set(continuation.SWEEP_CLASSES["no_successor"]),
            {"stall"})
        self.assertIn(
            "frontier_shortfall", continuation.STAFFING_KINDS)
        self.assertIn(
            "serial_staffing", continuation.STAFFING_KINDS)


if __name__ == "__main__":
    unittest.main()
