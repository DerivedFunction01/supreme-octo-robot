"""Venue staffing measure pins (the superapp
supervision plan, Step 2): the family-concurrency
measure and the plan-frontier comparison, proven on
recorded specimens.

The specimen records are the venue runs store's own
records for the edgar fleet on 2026-11-19, copied
verbatim into fixtures/venue-results/runs (historical
and immutable — read, never written). The windows
are the plan's, as measured: 10:00–12:25Z reads
staffed (several families across sessions); from
12:30Z the fleet narrows to one carrying session and
the measure reads a serial defect — one family on
one session from 13:10Z, so the plan's 13:30Z
defect-window start reads defect as claimed. The
13:30Z instant was first probed staffed only
because four launch-lost records (their terminal
events standing in for a finish) manufactured the
second family and the second session; with the
derivation cured it reads defect. The measure is
evaluated at instants inside each window from the
records alone.
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
    venue,
)
from attention.services.measure import staffing_rows  # noqa: E402
from attention.settings import Settings  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "venue-results"
CALM = "calm-ledge-48"
SCARLET = "scarlet-ledge-52"


def at(hour, minute=0):
    return datetime(2026, 11, 19, hour, minute, tzinfo=UTC)


def edgar_records(now):
    records = venue.read_run_store(FIXTURES / "runs", now)
    declarations = registry.active_declarations()
    return [
        r
        for r in records
        if venue.attribute_slug(r["caller"], declarations) == "edgar-greenfield"
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
            "edgar-greenfield": {"at": now, "jobs": len(edgar_records(now)), **facts}
        },
    }


def settings():
    return Settings(run_records_dir=FIXTURES / "detached")


def serial_rows(view):
    return [r for r in view["rows"] if r["kind"] == "serial_staffing"]


class SpecimenWindows(unittest.TestCase):
    def test_staffed_window_reads_staffed(self):
        # Inside 10:00–12:25Z the records show several
        # families across both live sessions: no defect.
        # The 13:30Z instant is not probed here — under
        # the cured derivation it reads defect (the
        # launch-lost records that made it read staffed
        # are excluded), and it is probed as defect
        # below.
        for now in (at(11), at(12), at(12, 15)):
            view = staffing.build_staffing(specimen_state(now), settings(), now)
            self.assertEqual(serial_rows(view), [], f"at {now}")
            facts = venue.families_at(edgar_records(now), now, 30)
            self.assertGreaterEqual(len(facts["families"]), 2, f"at {now}")
            carrying = {
                s for e in facts["families"].values() for s in e["sessions"]
            }
            self.assertGreaterEqual(len(carrying), 2, f"at {now}")

    def test_serial_window_reads_as_defect(self):
        # Inside 13:30–15:22Z the records narrow to one
        # family on one session while the other live
        # session carries none: a serial staffing defect.
        # 13:30Z is the plan's defect-window start.
        for now in (at(13, 30), at(14), at(15), at(15, 22)):
            view = staffing.build_staffing(specimen_state(now), settings(), now)
            rows = serial_rows(view)
            self.assertEqual(len(rows), 1, f"at {now}")
            row = rows[0]
            self.assertEqual(
                [f["name"] for f in row["families"]], ["cocisep"], f"at {now}"
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
            "all_compute_on_one_session_while_another_live_session_carries_none",
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
        contract = registry.staffing_contract_for("edgar-greenfield")
        self.assertFalse(contract["delegate_counts_toward_concurrency"])
        now = at(15, 22)
        facts = venue.families_at(edgar_records(now), now, 30)
        self.assertEqual(list(facts["families"]), ["cocisep"])
        view = staffing.build_staffing(specimen_state(now), settings(), now)
        self.assertEqual(len(serial_rows(view)), 1)


class FamilyDerivation(unittest.TestCase):
    def test_job_stems(self):
        prefix = venue.job_prefix(
            ["greenfield-ci-cfsep-gate", "greenfield-ci-cocisep-price"]
        )
        self.assertEqual(prefix, "greenfield-ci-")
        cases = {
            "greenfield-ci-cocisep-gate": "cocisep",
            "greenfield-ci-cocisep-price": "cocisep",
            "greenfield-ci-corefin-coci-extract-b": "corefin-coci",
            "greenfield-ci-corefin-coci-price": "corefin-coci",
            "greenfield-ci-testform-build-gateC": "testform",
            "greenfield-ci-is-setlevel-price": "is-setlevel",
        }
        for job, family in cases.items():
            self.assertEqual(venue.family_of(job, prefix), family, job)

    def test_caller_attribution(self):
        declarations = registry.active_declarations()
        self.assertEqual(
            venue.attribute_slug(
                "edgar-successor:greenfield-followup", declarations
            ),
            "edgar-greenfield",
        )
        self.assertEqual(
            venue.attribute_slug("edgar-successor", declarations),
            "edgar-greenfield",
        )
        # Declared caller stems: a programme whose
        # runs ride a caller that is not its slug stem
        # attributes by its registry declaration.
        self.assertEqual(
            venue.attribute_slug("workhorse", declarations),
            "supreme-octo-robot",
        )
        self.assertEqual(
            venue.attribute_slug("steampower-cust", declarations),
            "steampowernj",
        )
        self.assertEqual(
            venue.attribute_slug("steampower-cust:emp", declarations),
            "steampowernj",
        )
        self.assertIsNone(venue.attribute_slug("panel", declarations))


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
                "project": "edgar-sec",
                "slug": "edgar-greenfield",
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
        self.assertEqual(rows[0]["handle"], "@xbrl")

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
            wb_client.fetch_projects = lambda url, timeout: ["edgar-sec"]
            wb_client.fetch_todos = lambda url, project, timeout: {
                "available": True,
                "todos": todos,
            }
            try:
                state = {
                    "programmes": [
                        {"slug": "edgar-greenfield", "worktree_roots": [tmp]}
                    ],
                    "armed_rows": [
                        {
                            "project": "edgar-sec",
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
            self.assertEqual(entry["slug"], "edgar-greenfield")
            self.assertEqual(entry["missing"], ["lane-b"])
            self.assertEqual(entry["serial_excluded"], ["shared-step"])

    def test_collect_frontier_attributes_the_supervision_bundle(self):
        # The wb naming seam, reconciled in the registry
        # seed: the supervision bundle is served under
        # "workbench-viewer" while its armed rows key
        # "workrecord" — both names declared for the
        # programme, so the collector attributes the
        # bundle to supreme-octo-robot instead of
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
            wb_client.fetch_projects = lambda url, timeout: ["workbench-viewer"]
            wb_client.fetch_todos = lambda url, project, timeout: {
                "available": True,
                "todos": todos,
            }
            try:
                state = {
                    "programmes": [
                        {"slug": "supreme-octo-robot", "worktree_roots": [tmp]}
                    ],
                    "armed_rows": [
                        {
                            "project": "workrecord",
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
            self.assertEqual(entry["slug"], "supreme-octo-robot")
            self.assertEqual(entry["missing"], ["lane-b"])


def _record(run_id, state, started, finished, caller="steampower-cust"):
    return {
        "id": run_id,
        "job": "steampower-reformed-gate",
        "caller": caller,
        "session": "storm-mosaic-17",
        "state": state,
        "started_at": started,
        "finished_at": finished,
        "evidence_at": finished or started,
    }


class TerminalUnconsumed(unittest.TestCase):
    """The terminal-unconsumed class (commissioned
    2026-11-20): a terminal failed run the owning
    programme's own records never cite in that state.
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
        run = "steampower-reformed-gate-20261121T005537Z"
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
                "steampowernj": {
                    "at": now,
                    "jobs": 1,
                    "terminal_unconsumed": [
                        {
                            "id": "steampower-reformed-gate-20261121T005537Z",
                            "job": "steampower-reformed-gate",
                            "caller": "steampower-cust",
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
                "steampowernj": {"at": now, "consumed": sorted(consumed)}
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
            rows[0]["run_id"], "steampower-reformed-gate-20261121T005537Z"
        )
        consumed = self._state(
            now, finished, consumed=["steampower-reformed-gate-20261121T005537Z"]
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
