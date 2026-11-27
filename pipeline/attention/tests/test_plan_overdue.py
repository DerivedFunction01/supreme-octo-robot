"""Plan-step overdue tests (estimate-rule enforcement
plan, Step 3): the plan estimate source reads the
tracked plan files in the forms the corpus carries —
inline [est: ...] brackets on numbered steps, and
`### Step N` subsections with an Estimates section
and a Completion record — and the measure actuates
on an open step past its estimate: the row names the
plan, the step, the estimate, and the overrun; the
sweep steer names the step as a staffing commission;
an owner-only step stands in the served view the
digest embeds and never steers a coordinator.
"""

import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import store as store_mod  # noqa: E402
from attention.services.measure import (  # noqa: E402
    continuation,
    plans,
    staffing,
    staffing_plans,
)
from attention.settings import Settings  # noqa: E402

SLUG = "specimen-platform"
ADOPTED = datetime(2026, 11, 24, tzinfo=UTC)

BRACKET_PLAN = """# Estimate rule — system enforcement build

Status: adopted (owner enforcement ruling, 2026-11-24)
Executor: specimen platform seat

## Steps

1. **Spec text** — the rule and its enforcement statement enter
   `docs/supervision-rules.md` in spec-driven-starter.
   [est: 20m]
2. **Estimate lint (starter gate)** — a scanner in the starter's
   own form, the living-dates scanner its template.
   [est: 55m — the template scanner carries the population,
   masking, and registration mechanics]
3. **Workhorse actuation (Sentinel form)** — the attention
   measure reads plan and todo estimates beside the lane records.
"""

SECTIONS_PLAN = """# Multi-venue, multi-account venue support

Status: built — gate-green in the working tree, unlanded
Executor: specimen platform seat

## Estimates (per step, recorded at the plan's next touch)

- Step 1 — 45m: five shared-core edits plus their pinning tests.
- Step 6 — 1h30: novel work — a new execution adapter against a
  live host; not lower because the dial had no existing local
  shape to copy.

## Steps

### Step 1 — Backend core safety for non-home records

The shared core refuses nothing it carried before.

### Step 6 — Local venue execution adapter

The runner dispatches to the local venue.

## Completion record

- Step 1 — landed at the seat, gate green.
"""

PROPOSED_PLAN = """# A plan awaiting its ruling

Status: proposed — awaiting the owner's ruling
Executor: specimen platform seat

## Steps

1. **First step** — the thing itself, once ruled.
   [est: 30m]
"""


def at(minutes):
    return ADOPTED + timedelta(minutes=minutes)


def snapshot_state(text, name):
    state = store_mod.empty_state()
    state["programmes"] = []
    state["plan_snapshot"] = {
        SLUG: {"at": ADOPTED, "plans": [plans.parse_plan(text, name)]}
    }
    return state


def overdue(state, now):
    return staffing_plans._overdue_rows(state, now)


def sweep_sends(state):
    return [
        s
        for s in state.get("sends") or []
        if s.get("rule_id") == continuation.SWEEP_RULE_ID
    ]


class ParserForms(unittest.TestCase):
    def test_bracket_form(self):
        plan = plans.parse_plan(BRACKET_PLAN, "2026-11-24-estimate-rule.md")
        self.assertEqual(plan["status"], "adopted")
        self.assertEqual(plan["adopted_at"], "2026-11-24T00:00:00+00:00")
        self.assertEqual(
            [(s["number"], s["title"], s["estimate_minutes"]) for s in plan["steps"]],
            [
                (1, "Spec text", 20),
                (2, "Estimate lint (starter gate)", 55),
                (3, "Workhorse actuation (Sentinel form)", None),
            ],
        )
        self.assertTrue(all(not s["closed"] for s in plan["steps"]))
        self.assertTrue(all(not s["owner_only"] for s in plan["steps"]))

    def test_estimates_section_and_completion_record(self):
        plan = plans.parse_plan(
            SECTIONS_PLAN, "2026-11-23-multi-venue-multi-account.md"
        )
        # No date in the Status line and no Adopted line:
        # the filename's leading date is the stamp.
        self.assertEqual(plan["adopted_at"], "2026-11-23T00:00:00+00:00")
        by_number = {s["number"]: s for s in plan["steps"]}
        self.assertEqual(by_number[1]["estimate_minutes"], 45)
        self.assertTrue(by_number[1]["closed"])
        self.assertEqual(by_number[6]["estimate_minutes"], 90)
        self.assertFalse(by_number[6]["closed"])

    def test_duration_forms(self):
        self.assertEqual(plans.parse_duration_minutes("45m"), 45)
        self.assertEqual(plans.parse_duration_minutes("2h"), 120)
        self.assertEqual(plans.parse_duration_minutes("1h30"), 90)
        self.assertEqual(plans.parse_duration_minutes("1h 30m"), 90)
        self.assertEqual(plans.parse_duration_minutes("45m once authorized"), 45)
        self.assertIsNone(plans.parse_duration_minutes("their landing + 15m"))
        self.assertIsNone(plans.parse_duration_minutes(""))


class OverdueRows(unittest.TestCase):
    def test_overdue_open_step_raises_and_names(self):
        state = snapshot_state(BRACKET_PLAN, "2026-11-24-estimate-rule.md")
        rows = overdue(state, at(50))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["kind"], "step_overdue")
        self.assertEqual(row["kind_label"], "Step overdue")
        self.assertEqual(row["expected_minutes"], 20)
        self.assertEqual(row["elapsed_minutes"], 50)
        self.assertEqual(row["overrun_minutes"], 30)
        self.assertIn("Step 1 (Spec text)", row["detail"])
        self.assertIn("30 minutes past its 20-minute estimate", row["detail"])
        self.assertFalse(row["owner_only"])

    def test_completed_step_raises_nothing(self):
        state = snapshot_state(
            SECTIONS_PLAN, "2026-11-23-multi-venue-multi-account.md"
        )
        adopted = datetime(2026, 11, 23, tzinfo=UTC)
        rows = overdue(state, adopted + timedelta(hours=10))
        # Step 1 is closed by the completion record; only
        # Step 6, long past its 90-minute estimate, stands.
        self.assertEqual([r["step"] for r in rows], [6])

    def test_complete_plan_raises_nothing(self):
        text = BRACKET_PLAN.replace(
            "Status: adopted (owner enforcement ruling, 2026-11-24)",
            "Status: complete (2026-11-24)",
        )
        state = snapshot_state(text, "2026-11-24-estimate-rule.md")
        self.assertEqual(overdue(state, at(600)), [])

    def test_step_without_estimate_raises_nothing(self):
        state = snapshot_state(BRACKET_PLAN, "2026-11-24-estimate-rule.md")
        rows = overdue(state, at(600))
        self.assertEqual([r["step"] for r in rows], [1, 2])

    def test_over_hour_estimate_not_yet_elapsed_raises_nothing(self):
        state = snapshot_state(
            SECTIONS_PLAN, "2026-11-23-multi-venue-multi-account.md"
        )
        adopted = datetime(2026, 11, 23, tzinfo=UTC)
        self.assertEqual(overdue(state, adopted + timedelta(minutes=60)), [])


class Actuation(unittest.TestCase):
    def test_steer_names_overdue_step_as_commission(self):
        state = snapshot_state(BRACKET_PLAN, "2026-11-24-estimate-rule.md")
        self.assertTrue(continuation.run_sweep_pass(state, Settings(), at(50)))
        sends = sweep_sends(state)
        self.assertEqual(len(sends), 1)
        send = sends[0]
        self.assertEqual(send["handle"], "@specimen-platform")
        self.assertIn(
            "Staffing commission — staff: step 1 (Spec text)", send["text"]
        )
        self.assertIn("Estimate rule — system enforcement build", send["text"])
        # A second pass on the same tick mints no twin.
        self.assertFalse(continuation.run_sweep_pass(state, Settings(), at(50)))
        self.assertEqual(len(sweep_sends(state)), 1)

    def test_owner_only_step_stands_in_view_but_never_steers(self):
        state = snapshot_state(PROPOSED_PLAN, "2026-11-20-proposed-plan.md")
        now = datetime(2026, 11, 20, 2, tzinfo=UTC)
        rows = overdue(state, now)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["owner_only"])
        # The digest surface: the row stands in the
        # served staffing view build_digest embeds.
        view = staffing.build_staffing(state, Settings(), now)
        self.assertIn(
            "step_overdue", [r["kind"] for r in view["rows"]]
        )
        # And no coordinator is steered for the owner's act.
        self.assertFalse(continuation.run_sweep_pass(state, Settings(), now))
        self.assertEqual(sweep_sends(state), [])


class CollectorAttribution(unittest.TestCase):
    def test_repo_root_plans_attribute_to_the_slug_naming_the_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / SLUG
            plans_dir = root / ".plans"
            plans_dir.mkdir(parents=True)
            (plans_dir / "2026-11-24-estimate-rule.md").write_text(
                BRACKET_PLAN, encoding="utf-8"
            )
            state = store_mod.empty_state()
            state["programmes"] = []
            with mock.patch.object(plans, "REPO_ROOT", root):
                self.assertTrue(plans.collect(state, ADOPTED))
            snapshot = state["plan_snapshot"]
            self.assertEqual(list(snapshot), [SLUG])
            parsed = snapshot[SLUG]["plans"]
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0]["steps"][0]["estimate_minutes"], 20)
            # A second collection over the same files
            # changes nothing.
            with mock.patch.object(plans, "REPO_ROOT", root):
                self.assertFalse(plans.collect(state, ADOPTED))


if __name__ == "__main__":
    unittest.main()
