"""Venue staffing measure pins (the superapp supervision plan,
Step 2): the family-concurrency measure and the plan-frontier
comparison, proven on recorded specimens.

The specimen records are a synthesized set of venue run records
in the live store's shape, standing in for one working day of a
multi-family fleet (fixtures/venue-results/runs — synthetic,
immutable: read, never written). The windows are the plan's, as
measured: 10:00–12:25Z reads staffed (several families across
sessions); from 12:30Z the fleet narrows to one carrying session
and the measure reads a serial defect — one family on one session
from 13:10Z, so the plan's 13:30Z defect-window start reads defect
as claimed. The 13:30Z instant was first probed staffed only
because four launch-lost records (their terminal events standing
in for a finish) manufactured the second family and the second
session; with the derivation cured it reads defect. The measure
is evaluated at instants inside each window from the records alone.
"""

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import wb_client  # noqa: E402
from attention.services.measure import (  # noqa: E402
    continuation,
    records,
    registry,
    staffing,
    staffing_venue,
    venue,
)
from attention.services.measure import staffing_rows  # noqa: E402
from attention.settings import Settings  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "venue-results"
CALM = "quiet-ridge-11"
SCARLET = "amber-cliff-23"


def at(hour, minute=0):
    return datetime(2026, 8, 6, hour, minute, tzinfo=UTC)


def edgar_records(now):
    records = venue.read_run_store(FIXTURES / "runs", now)
    declarations = registry.active_declarations()
    return [
        r
        for r in records
        if venue.attribute_slug(r["caller"], declarations) == "edgar-specimen"
    ]


def specimen_state(now, idle_minutes=52):
    """The served-view state at a specimen instant:
    capacity from the era's two live sessions, family
    facts computed from the recorded runs alone, and
    the programme's open work armed — including a
    research-delegate-only todo, which fires no venue
    runs and so must not count toward concurrency."""
    facts = venue.families_at(edgar_records(now), now, 30)
    armed = [
        {
            "project": "specimen-repo",
            "todo": todo,
            "row": {
                "project": "specimen-repo",
                "programme": "specimen-repo",
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
    return {
        "handlers": [],
        "handler_status": {},
        "items": [],
        "sends": [],
        "dispatch_failures": [],
        "verifications": [],
        "programmes": [],
        "armed_rows": armed,
        "capacity_error": None,
        "capacity_snapshot": {
            "at": now,
            "sessions": [{"session": CALM}, {"session": SCARLET}],
            "session_runs": {CALM: 1, SCARLET: 0},
            "idle_since": {SCARLET: now - timedelta(minutes=idle_minutes)},
            "specs": [],
        },
        "venue_snapshot": {
            "edgar-specimen": {"at": now, "jobs": len(edgar_records(now)), **facts}
        },
    }


def settings():
    return Settings(run_records_dir=FIXTURES / "detached")


def serial_rows(view):
    return [r for r in view["rows"] if r["kind"] == "serial_staffing"]


class SpecimenWindows(unittest.TestCase):
    def test_staffed_window_reads_below_the_cured_floor(self):
        from unittest import mock

        # Inside 10:00–12:25Z the records show several
        # families across both live sessions — five in
        # flight at 11:00. Under the first-seeded floor
        # (2) the bands read staffed; under the cured
        # floor (8 distinct register families in active
        # work at all times, owner order)
        # the same window reads as a defect on the
        # floor condition alone. The queue stands
        # nothing here either: its one remaining work
        # item was gated on the packet marker, which
        # stood unlanded at these instants. The 13:30Z
        # instant is probed as defect below.
        with mock.patch.object(registry, "staffing_contract_for", packet_unlanded):
            for now in (at(11), at(12), at(12, 15)):
                view = staffing.build_staffing(specimen_state(now), settings(), now)
                rows = serial_rows(view)
                self.assertEqual(len(rows), 1, f"at {now}")
                self.assertEqual(
                    rows[0]["conditions"],
                    ["fewer_than_min_families_in_flight"],
                    f"at {now}")
                facts = venue.families_at(edgar_records(now), now, 30)
                self.assertGreaterEqual(len(facts["families"]), 2, f"at {now}")
                carrying = {
                    s for e in facts["families"].values() for s in e["sessions"]
                }
                self.assertGreaterEqual(len(carrying), 2, f"at {now}")

    def test_serial_window_reads_as_defect(self):
        # Inside 13:30–15:22Z the records narrow to one
        # family on one session: a serial staffing defect.
        for now in (at(13, 30), at(14), at(15), at(15, 22)):
            view = staffing.build_staffing(specimen_state(now), settings(), now)
            rows = serial_rows(view)
            self.assertEqual(len(rows), 1, f"at {now}")
            row = rows[0]
            self.assertEqual(
                [f["name"] for f in row["families"]], ["cobalt"], f"at {now}"
            )
            self.assertEqual(row["sessions_used"], 1, f"at {now}")
            self.assertEqual(row["sessions_live"], 2, f"at {now}")
            self.assertIn(
                "fewer_than_min_families_in_flight", row["conditions"]
            )
        row = serial_rows(
            staffing.build_staffing(specimen_state(at(15, 22)), settings(), at(15, 22))
        )[0]
        self.assertIn(
            "one_deep_per_session_while_staffable_families_wait",
            row["conditions"],
        )
        self.assertEqual(
            row["idle_sessions"], [{"name": SCARLET, "idle_minutes": 52}]
        )
        self.assertEqual(row["idle_minutes"], 52)

    def test_research_delegate_todo_does_not_count(self):
        # The specimen state arms a second doing todo
        # staffed only by the research delegate; the
        # contract says a delegate does not count
        # toward family concurrency, and the delegate
        # fires no venue runs — the defect stands on
        # the one measured family.
        contract = registry.staffing_contract_for("edgar-specimen")
        self.assertFalse(contract["delegate_counts_toward_concurrency"])
        now = at(15, 22)
        facts = venue.families_at(edgar_records(now), now, 30)
        self.assertEqual(list(facts["families"]), ["cobalt"])
        view = staffing.build_staffing(specimen_state(now), settings(), now)
        self.assertEqual(len(serial_rows(view)), 1)


class FamilyDerivation(unittest.TestCase):
    def test_job_stems(self):
        prefix = venue.job_prefix(
            ["specimen-ci-fable-gate", "specimen-ci-cobalt-price"]
        )
        self.assertEqual(prefix, "specimen-ci-")
        cases = {
            "specimen-ci-cobalt-gate": "cobalt",
            "specimen-ci-cobalt-price": "cobalt",
            "specimen-ci-ledger-cobalt-extract-b": "ledger-cobalt",
            "specimen-ci-ledger-cobalt-price": "ledger-cobalt",
            "specimen-ci-formtest-build-gateC": "formtest",
            "specimen-ci-tier-level-price": "tier-level",
        }
        for job, family in cases.items():
            self.assertEqual(venue.family_of(job, prefix), family, job)

    def test_caller_attribution(self):
        declarations = registry.active_declarations()
        self.assertEqual(
            venue.attribute_slug(
                "edgar-specimen:specimen-lane", declarations
            ),
            "edgar-specimen",
        )
        self.assertEqual(
            venue.attribute_slug("edgar-specimen", declarations),
            "edgar-specimen",
        )
        # Declared caller stems: a programme whose
        # runs ride a caller that is not its slug stem
        # attributes by its registry declaration.
        self.assertEqual(
            venue.attribute_slug("specimenwork", declarations),
            "specimen-platform",
        )
        self.assertEqual(
            venue.attribute_slug("speciment-cust", declarations),
            "specimen-tenant",
        )
        self.assertEqual(
            venue.attribute_slug("speciment-cust:emp", declarations),
            "specimen-tenant",
        )
        self.assertIsNone(venue.attribute_slug("panel", declarations))


def queue_state(families):
    """A synthetic venue snapshot for the edgar
    programme, in the served shape: the named
    families in flight on the named sessions, the
    programme's open work armed."""
    now = at(15, 22)
    state = {
        "armed_rows": [
            {
                "project": "specimen-repo",
                "todo": "ci-corefin-coci-build",
                "row": {"project": "specimen-repo", "programme": "specimen-repo"},
            }
        ],
        "venue_snapshot": {
            "edgar-specimen": {
                "at": now,
                "jobs": 4,
                "families": {
                    name: {"sessions": sessions, "runs": 1, "child_runs": 0}
                    for name, sessions in families.items()
                },
                "workers": len(families),
                "child_workers": 0,
                "coordinator_caller": "edgar-specimen",
            }
        },
    }
    idle = {SCARLET: now - timedelta(minutes=52)}
    return now, state, [CALM, SCARLET], idle


_REAL_CONTRACT_FOR = registry.staffing_contract_for


# The specimen contract is the configured one: its
# queue carries the gated instrument build, so the
# queue pins exercise the gated-item form by flipping
# the packet marker's landed flag alone.
def _specimen_contract(slug, landed):
    contract = _REAL_CONTRACT_FOR(slug)
    if contract:
        for entry in contract["staffable_queue"]:
            if entry["key"] == "specimen-packet-landing":
                entry["landed"] = landed
    return contract


def _discharged_contract(slug):
    """The configured contract with its work item
    discharged — the queue form after the build stands
    delivered and pruned: markers only, nothing due."""
    contract = _REAL_CONTRACT_FOR(slug)
    if contract:
        contract["staffable_queue"] = [
            entry
            for entry in contract["staffable_queue"]
            if entry.get("marker")
        ]
    return contract


# The specimen contract with the packet marker landed /
# unlanded, respectively.
def packet_landed(slug):
    return _specimen_contract(slug, True)


def packet_unlanded(slug):
    return _specimen_contract(slug, False)


class QueueMeasure(unittest.TestCase):
    """The queue condition (staffing-commission
    amendment): due items named on the serial row,
    gated items never due before their gate
    resolves, an in-flight family never due."""

    def test_due_item_named_gated_items_not_due(self):
        from unittest import mock

        now, state, live, idle = queue_state({"cobalt": [CALM]})
        # Under the specimen contract with the marker
        # unlanded, the queue's only work item (the
        # instrument build) is gated: nothing reads due.
        with mock.patch.object(registry, "staffing_contract_for", packet_unlanded):
            rows = staffing_rows._family_rows(state, now, live, idle)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("prerequisite_due_family_unstaffed", row["conditions"])
        self.assertEqual(row["queue_unstaffed"], [])
        # The discharged contract form carries the same
        # discharge: the build stands pruned from the
        # queue, so nothing reads due on it either.
        with mock.patch.object(
            registry, "staffing_contract_for", _discharged_contract
        ):
            rows = staffing_rows._family_rows(state, now, live, idle)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("prerequisite_due_family_unstaffed", row["conditions"])
        self.assertEqual(row["queue_unstaffed"], [])

    def test_bands_met_but_queue_due_still_raises(self):
        from unittest import mock

        # Bands met under the cured floor: eight
        # families in flight, stacked on the two
        # sessions so the one-deep condition does not
        # fire — the queue condition stands alone.
        fillers = {f"fam-{c}": [CALM] if i < 3 else [SCARLET]
                   for i, c in enumerate("abcdef")}
        now, state, live, idle = queue_state(
            {"cobalt": [CALM], "ledger-cobalt": [SCARLET], **fillers}
        )
        with mock.patch.object(registry, "staffing_contract_for", packet_landed):
            rows = staffing_rows._family_rows(state, now, live, idle)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["conditions"], ["prerequisite_due_family_unstaffed"])

    def test_in_flight_family_is_never_due(self):
        from unittest import mock

        fillers = {f"fam-{c}": [CALM] if i < 2 else [SCARLET]
                   for i, c in enumerate("abcde")}
        now, state, live, idle = queue_state(
            {
                "cobalt": [CALM],
                "ledger-cobalt": [SCARLET],
                "specimenbuild": [CALM],
                **fillers,
            }
        )
        # The specimen's instrument build is due-eligible
        # under the landed marker; its family in flight
        # still keeps it from reading due.
        with mock.patch.object(registry, "staffing_contract_for", packet_landed):
            self.assertEqual(staffing_rows._family_rows(state, now, live, idle), [])

    def test_marker_flip_makes_the_gated_item_due(self):
        from unittest import mock

        now, state, live, idle = queue_state(
            {
                "cobalt": [CALM],
                "ledger-cobalt": [SCARLET],
                "otherfam": [CALM],
            }
        )
        with mock.patch.object(registry, "staffing_contract_for", packet_landed):
            rows = staffing_rows._family_rows(state, now, live, idle)
        self.assertEqual(len(rows), 1)
        # The specimen's instrument item reads due once
        # its gate resolves — the queue's only work item.
        self.assertEqual(
            [e["key"] for e in rows[0]["queue_unstaffed"]],
            ["specimen-instrument-build"],
        )

    def test_queue_due_gate_semantics(self):
        queue = [
            {"key": "a", "label": "A", "family": "fa", "staffable_when": None},
            {"key": "gate", "label": "G", "marker": True, "landed": False},
            {"key": "b", "label": "B", "family": "fb", "staffable_when": "gate"},
            {"key": "c", "label": "C", "family": "fc", "staffable_when": "a"},
        ]
        due = staffing_venue._queue_due(queue, set())
        self.assertEqual([e["key"] for e in due], ["a"])
        # A landed marker resolves its gate; a work
        # item still standing in the queue does not
        # resolve its own.
        queue[1]["landed"] = True
        due = staffing_venue._queue_due(queue, set())
        self.assertEqual([e["key"] for e in due], ["a", "b"])
        # Landed work is pruned by amendment: with
        # the gating item gone, its dependent is due.
        pruned = [e for e in queue if e["key"] != "a"]
        due = staffing_venue._queue_due(pruned, set())
        self.assertEqual([e["key"] for e in due], ["b", "c"])


PLAN_TEXT = """# Fixture plan

## Steps

### Step 1 — Foundation

<!-- wb-step
step=1
todos=foundation
requires=
fanout=single lane — the contract the rest read
-->

### Step 2 — Parallel lanes

<!-- wb-step
step=2
todos=lane-a|lane-b
requires=foundation
est=45m
fanout=two lanes over the landed contract
-->

### Step 3 — Shared-state step

<!-- wb-step
step=3
todos=shared-step
requires=foundation
serial=the shared registry file — one editor
-->

### Step 4 — Later step

<!-- wb-step
step=4
todos=later-step
requires=lane-a
fanout=single lane
-->
"""


class FrontierComparison(unittest.TestCase):
    def test_step_blocks_parse(self):
        steps = venue.parse_step_blocks(PLAN_TEXT)
        self.assertEqual([s["step"] for s in steps], [1, 2, 3, 4])
        self.assertEqual(steps[1]["todos"], ["lane-a", "lane-b"])
        self.assertEqual(steps[1]["requires"], ["foundation"])
        self.assertIsNotNone(steps[1]["fanout"])
        self.assertIsNotNone(steps[2]["serial"])
        # The est field rides the block: declared where
        # the block declares one, None where it
        # declares none.
        self.assertEqual(steps[1]["est"], "45m")
        self.assertIsNone(steps[0]["est"])

    def test_shortfall_and_serial_exception(self):
        steps = venue.parse_step_blocks(PLAN_TEXT)
        statuses = {
            "foundation": "done",
            "lane-a": "doing",
            "lane-b": "todo",
            "shared-step": "todo",
            "later-step": "todo",
        }
        result = venue.frontier_for(steps, statuses, set(statuses))
        # lane-b is prerequisite-due fanout work, unstaffed.
        self.assertEqual(result["expected"], ["lane-a", "lane-b"])
        self.assertEqual(result["actual"], ["lane-a"])
        self.assertEqual(result["missing"], ["lane-b"])
        # The serial-declared step is a named exception,
        # never part of the expected set; the later step
        # is not yet prerequisite-due.
        self.assertEqual(result["serial_excluded"], ["shared-step"])
        self.assertNotIn("later-step", result["expected"])

    def test_staffed_frontier_has_no_shortfall(self):
        steps = venue.parse_step_blocks(PLAN_TEXT)
        statuses = {
            "foundation": "done",
            "lane-a": "doing",
            "lane-b": "doing",
            "shared-step": "todo",
            "later-step": "todo",
        }
        result = venue.frontier_for(steps, statuses, set(statuses))
        self.assertEqual(result["missing"], [])

    def test_served_shortfall_row(self):
        now = at(15, 22)
        state = specimen_state(now)
        state["frontier_snapshot"] = {
            "fixture-bundle": {
                "bundle": "fixture-bundle",
                "project": "specimen-repo",
                "slug": "edgar-specimen",
                "at": now,
                "expected": ["lane-a", "lane-b"],
                "actual": ["lane-a"],
                "missing": ["lane-b"],
                "serial_excluded": ["shared-step"],
            }
        }
        view = staffing.build_staffing(state, settings(), now)
        rows = [r for r in view["rows"] if r["kind"] == "frontier_shortfall"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bundle"], "fixture-bundle")
        self.assertEqual(rows[0]["missing"], ["lane-b"])
        self.assertEqual(rows[0]["handle"], "@specimen-field")

    def test_collect_frontier_from_surface_and_plan(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plans").mkdir()
            (root / "plans" / "fixture-plan.md").write_text(
                PLAN_TEXT, encoding="utf-8"
            )
            todos = [
                {
                    "id": t,
                    "status": s,
                    "bundle": "fixture-bundle",
                    "plan": "plans/fixture-plan.md",
                }
                for t, s in (
                    ("foundation", "done"),
                    ("lane-a", "doing"),
                    ("lane-b", "todo"),
                    ("shared-step", "todo"),
                    ("later-step", "todo"),
                )
            ]
            real_projects, real_todos = wb_client.fetch_projects, wb_client.fetch_todos
            wb_client.fetch_projects = lambda url, timeout: ["specimen-repo"]
            wb_client.fetch_todos = lambda url, project, timeout: {
                "available": True,
                "todos": todos,
            }
            try:
                state = {
                    "programmes": [
                        {"slug": "edgar-specimen", "worktree_roots": [tmp]}
                    ],
                    "armed_rows": [
                        {
                            "project": "specimen-repo",
                            "todo": "lane-a",
                            "row": {"bundle": "fixture-bundle"},
                        }
                    ],
                }
                changed = venue.collect_frontier(state, settings(), at(15, 22))
            finally:
                wb_client.fetch_projects, wb_client.fetch_todos = (
                    real_projects,
                    real_todos,
                )
            self.assertTrue(changed)
            entry = state["frontier_snapshot"]["fixture-bundle"]
            self.assertEqual(entry["slug"], "edgar-specimen")
            self.assertEqual(entry["missing"], ["lane-b"])
            self.assertEqual(entry["serial_excluded"], ["shared-step"])

    def test_collect_frontier_attributes_the_supervision_bundle(self):
        # The wb naming seam, reconciled in the registry
        # seed: the supervision bundle is served under
        # "specimen-viewer" while its armed rows key
        # "specimen-record" — both names declared for the
        # programme, so the collector attributes the
        # bundle to specimen-platform instead of
        # leaving the row slug-null.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plans").mkdir()
            (root / "plans" / "fixture-plan.md").write_text(
                PLAN_TEXT, encoding="utf-8"
            )
            todos = [
                {
                    "id": t,
                    "status": s,
                    "bundle": "2026-11-19-superapp-supervision-reminders",
                    "plan": "plans/fixture-plan.md",
                }
                for t, s in (
                    ("foundation", "done"),
                    ("lane-a", "doing"),
                    ("lane-b", "todo"),
                    ("shared-step", "todo"),
                    ("later-step", "todo"),
                )
            ]
            real_projects, real_todos = wb_client.fetch_projects, wb_client.fetch_todos
            wb_client.fetch_projects = lambda url, timeout: ["specimen-viewer"]
            wb_client.fetch_todos = lambda url, project, timeout: {
                "available": True,
                "todos": todos,
            }
            try:
                state = {
                    "programmes": [
                        {"slug": "specimen-platform", "worktree_roots": [tmp]}
                    ],
                    "armed_rows": [
                        {
                            "project": "specimen-record",
                            "todo": "lane-a",
                            "row": {
                                "bundle": "2026-11-19-superapp-supervision-reminders"
                            },
                        }
                    ],
                }
                changed = venue.collect_frontier(state, settings(), at(15, 22))
            finally:
                wb_client.fetch_projects, wb_client.fetch_todos = (
                    real_projects,
                    real_todos,
                )
            self.assertTrue(changed)
            entry = state["frontier_snapshot"][
                "2026-11-19-superapp-supervision-reminders"
            ]
            self.assertEqual(entry["slug"], "specimen-platform")
            self.assertEqual(entry["missing"], ["lane-b"])


def _record(run_id, state, started, finished, caller="speciment-cust"):
    return {
        "id": run_id,
        "job": "specimen-reformed-gate",
        "caller": caller,
        "session": "storm-mosaic-17",
        "state": state,
        "started_at": started,
        "finished_at": finished,
        "evidence_at": finished or started,
    }


class TerminalUnconsumed(unittest.TestCase):
    """The terminal-unconsumed class: a terminal failed
    run the owning programme's own records never cite
    in that state.
    The specimen shape is steampower-reformed-gate-
    20261121T005537Z — terminal FAILED, recorded by
    the collector within seconds, unconsumed for
    90+ minutes while its seat reported it in flight."""

    def test_terminal_selection_covers_the_three_specimen_shapes(self):
        now = at(2, 0)
        orphaned = _record(
            "job-scenes-20261119T010000Z", "orphaned", at(0, 30), None
        )
        orphaned["terminal_event_at"] = at(1, 20)
        orphaned["missing_outputs"] = []
        unpulled = _record(
            "job-collect-20261119T011000Z", "complete", at(1, 10), at(1, 15)
        )
        unpulled["missing_outputs"] = ["frames.tar", "base-scenes.json"]
        clean = _record(
            "job-gate-20261119T013000Z", "complete", at(1, 30), at(1, 40)
        )
        clean["missing_outputs"] = []
        records_in = [
            _record("job-gate-20261119T010000Z", "failed", at(1, 0), at(1, 10)),
            clean,
            _record("job-gate-20261119T015000Z", "failed", at(1, 50), None),
            _record("job-gate-20261119T015500Z", "polling", at(1, 55), None),
            orphaned,
            unpulled,
        ]
        for record in records_in:
            record.setdefault("terminal_event_at", None)
            record.setdefault("missing_outputs", [])
        out = venue.terminal_unconsumed_at(records_in, now)
        by_id = {r["id"]: r for r in out}
        self.assertEqual(
            set(by_id),
            {
                "job-gate-20261119T010000Z",
                "job-scenes-20261119T010000Z",
                "job-collect-20261119T011000Z",
            },
        )
        self.assertEqual(by_id["job-gate-20261119T010000Z"]["shape"], "failed")
        self.assertEqual(
            by_id["job-gate-20261119T010000Z"]["finished_at"], at(1, 10).isoformat()
        )
        # The orphaned shape's terminal instant is its
        # terminal event, not a payload finish.
        self.assertEqual(by_id["job-scenes-20261119T010000Z"]["shape"], "orphaned")
        self.assertEqual(
            by_id["job-scenes-20261119T010000Z"]["finished_at"], at(1, 20).isoformat()
        )
        self.assertEqual(by_id["job-collect-20261119T011000Z"]["shape"], "unpulled")
        self.assertEqual(
            by_id["job-collect-20261119T011000Z"]["missing_outputs"],
            ["frames.tar", "base-scenes.json"],
        )

    def test_consumption_citation_needs_a_terminal_token(self):
        run = "specimen-reformed-gate-20261121T005537Z"
        self.assertEqual(
            records.cited_terminal_runs(f"gate {run} FAILED at 01:09Z; re-forming"),
            {run},
        )
        self.assertEqual(
            records.cited_terminal_runs(f"collected {run}: exit 1, evidence missing"),
            {run},
        )
        # A launch citation is not consumption.
        self.assertEqual(records.cited_terminal_runs(f"fired {run} on storm"), set())
        self.assertEqual(records.cited_terminal_runs(f"{run} in flight"), set())
        # A terminal word with no run id cites nothing.
        self.assertEqual(records.cited_terminal_runs("the gate failed"), set())

    def _state(self, now, finished, consumed=()):
        return {
            "venue_snapshot": {
                "specimen-tenant": {
                    "at": now,
                    "jobs": 1,
                    "terminal_unconsumed": [
                        {
                            "id": "specimen-reformed-gate-20261121T005537Z",
                            "job": "specimen-reformed-gate",
                            "caller": "speciment-cust",
                            "session": "storm-mosaic-17",
                            "state": "failed",
                            "shape": "failed",
                            "started_at": (finished - timedelta(minutes=14)).isoformat(),
                            "finished_at": finished.isoformat(),
                            "missing_outputs": [],
                        }
                    ],
                }
            },
            "consumption_snapshot": {
                "specimen-tenant": {"at": now, "consumed": sorted(consumed)}
            },
        }

    def test_row_raises_after_one_interval_and_clears_on_consumption(self):
        now = at(2, 0)
        finished = now - timedelta(minutes=90)
        rows = staffing_rows._terminal_rows(self._state(now, finished), now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "terminal_unconsumed")
        self.assertEqual(rows[0]["idle_minutes"], 90)
        self.assertEqual(
            rows[0]["run_id"], "specimen-reformed-gate-20261121T005537Z"
        )
        consumed = self._state(
            now, finished, consumed=["specimen-reformed-gate-20261121T005537Z"]
        )
        self.assertEqual(staffing_rows._terminal_rows(consumed, now), [])

    def test_actuation_maps_to_the_terminal_class(self):
        self.assertEqual(
            continuation.SWEEP_CLASSES["terminal_unconsumed"], ("terminal",)
        )
        self.assertIn(
            "collect the record", continuation._SWEEP_NEXT_ACT["terminal_unconsumed"]
        )

    def test_row_waits_one_cadence_interval(self):
        now = at(2, 0)
        finished = now - timedelta(minutes=10)
        self.assertEqual(
            staffing_rows._terminal_rows(self._state(now, finished), now), []
        )


if __name__ == "__main__":
    unittest.main()
