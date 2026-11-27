"""Timing-ledger Step 4 (wb timing-ledger plan):
the timing report.

`wb todo timing <bundle>` renders one plan's
per-step estimate vs actual from the file store's
transition ledger — gross actual (first doing →
terminal done), blocked time as its own figure
beside it, position, editors, worktree — and the
plan's wall-clock in the ruled form (serial sum +
longest branch + fan-in sum) beside the plain
serial sum. `wb todo timing` with no bundle renders
the cross-plan price book: priced, measured todos
grouped by kind (the minted fan-out position — the
only kind the records carry; titles are unique
prose), with the two lazy shapes flagged. Steps
and todos the record does not price or measure
render as honest absence, never as zeros.

All figures below are hand-computed from the
planted transition stamps (the fixture day, UTC):

Bundle one (timing-demo):
  step 1 serial est 30m — groundwork (est 30m):
    doing 09:05, blocked 09:20→09:35, done 09:50
    → gross 45m, blocked 15m, net 30m
  step 2 branch est 45m — lane-a (est 20m) 10:00→
    10:30 = 30m; lane-b (est 25m) 10:10→10:50 = 40m
    → step span 50m; items overlapped (30+40 > 50)
    and items' ests sum to the step's 45m
    → PRICED-AS-SERIAL-SUM
  step 3 branch est 40m — lane-c (est 40m)
    10:05→10:35 = 30m
  step 4 fan-in est 20m — join-up (est 20m)
    11:00→11:10 = 10m (ratio 0.50)
  step 5 serial, NO est — unpriced 12:00→12:15
    = 15m (est renders as absence)
  step 6 serial est 15m — never-started: created,
    never doing → no measured span (absence)
  in-flight: doing 15:00, never done, no plan step
    → open span, unstepped
  wall-clock actual: serial 45+15 + longest branch
    max(50, 30) + fan-in 10 = 120m (2h);
    serial sum 45+50+30+10+15 = 150m (2h30m)
  wall-clock est: serial 30+15 (step 5 unpriced,
    excluded) + longest branch max(45, 40) + fan-in
    20 = 110m (1h50m); serial sum 150m (2h30m)

Bundle two (second-plan) — two fan-in items, the
first's transitions carrying the backfill marker:
  join-two (est 30m) 13:00→13:10 = 10m (ratio 1/3)
  join-three (est 40m) 14:00→14:20 = 20m (ratio 0.50)

Price book over both bundles:
  serial: groundwork only (30/45, ratio 1.50)
  branch: lane-a 1.50, lane-b 1.60, lane-c 0.75
  fan-in: join-up 0.50, join-two 1/3, join-three
    0.50 — 3 items, all at or under 0.50
    → FAR-UNDER
  priced but unmeasured: never-started (1)

All state lives in tmp dirs — no live store touched.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
WB_ROOT = HERE.parents[2]
sys.path.insert(0, str(WB_ROOT))

from lib.plans import bundles as parser  # noqa: E402
from lib.plans import timing as timing_mod  # noqa: E402
from lib.writes import bundles as bundle_mod  # noqa: E402
from lib.writes import transitions as tr  # noqa: E402

WB = WB_ROOT / "wb"
PY = sys.executable
DAY = "2026-11-27"


def at(hhmm):
    return f"{DAY}T{hhmm}:00+00:00"


def moves(*specs):
    """A todo body carrying exactly the given
    transitions, built through the one helper so the
    lines are the ledger's real format."""
    body = ""
    for spec in specs:
        body = tr.append_transition(body, **spec)
    return body


def status(new, hhmm, **kw):
    spec = {"verb": "set-status", "field": "status",
            "new": new, "at": at(hhmm)}
    spec.update(kw)
    return spec


def created(hhmm):
    return {"verb": "create", "field": "status",
            "old": None, "new": "todo", "at": at(hhmm)}


def todo_file(*, id, title, status, step=None, est=None,
              position=None, worktree=None, body=""):
    lines = ["---", f"id: {id}", f"title: {title}",
             f"status: {status}", f"created: {DAY}",
             f"updated: {DAY}"]
    if step is not None:
        lines.append(f"plan_step: {step}")
    if est is not None:
        lines.append(f"est: {est}")
    if position is not None:
        lines.append(f"fanout_position: {position}")
    if worktree is not None:
        lines.append(f"worktree: {worktree}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body + "\n"


def plan_text(steps):
    """A plan in the house shape from (number, title,
    block fields, closing est or None) tuples."""
    out = ["# Fixture plan", "", "Status: complete",
           "Feature: timing-fixture", "", "## Steps", ""]
    for number, title, block, closing in steps:
        out += [f"### Step {number} — {title}", "",
                "Work.", "", "<!-- wb-step",
                f"step={number}"]
        out += block
        out += ["-->", "", "files: lib/a.py",
                "verify: fixture", "done when: done"]
        if closing is not None:
            out.append(f"est: {closing}")
        out.append("")
    return "\n".join(out)


PLAN_ONE = plan_text([
    (1, "Groundwork",
     ["todos=groundwork", "requires=", "est=30m",
      "position=serial", "serial=the ground"], "30m"),
    (2, "Parallel lanes",
     ["todos=lane-a|lane-b", "requires=groundwork",
      "est=45m", "position=branch",
      "fanout=two lanes over one worktree"], "45m"),
    (3, "Second lane",
     ["todos=lane-c", "requires=groundwork", "est=40m",
      "position=branch", "fanout=one more lane"], "40m"),
    (4, "Join",
     ["todos=join-up", "requires=lane-a|lane-b|lane-c",
      "est=20m", "position=fan-in",
      "serial=the join is one act"], "20m"),
    (5, "Unpriced tidy",
     ["todos=unpriced", "requires=join-up",
      "position=serial", "serial=a tidy"], None),
    (6, "Never started",
     ["todos=never-started", "requires=unpriced",
      "est=15m", "position=serial",
      "serial=still waiting"], "15m"),
])

PLAN_TWO = plan_text([
    (1, "First join",
     ["todos=join-two", "requires=", "est=30m",
      "position=fan-in", "serial=one act"], "30m"),
    (2, "Second join",
     ["todos=join-three", "requires=join-two",
      "est=40m", "position=fan-in",
      "serial=one act"], "40m"),
])


def backfilled_move(new, hhmm, old):
    """A status transition line in the ledger's
    format carrying the backfill marker (Step 5's
    form, planted here as raw JSON — the reader
    honours the keys when a record carries them)."""
    record = {"at": at(hhmm), "actor": "backfill",
              "verb": "set-status", "field": "status",
              "old": old, "new": new,
              "backfilled": True,
              "source": "landing record"}
    return "transition: " + json.dumps(record)


def _write_bundle(plans, slug, plan):
    bundle_mod.create_bundle(plans, slug, plan=True,
                             today=DAY)
    bundle_dir = bundle_mod.find_bundle_dir(plans, slug)
    (bundle_dir / "plan.md").write_text(
        plan, encoding="utf-8")
    return bundle_dir


def _write_todo(bundle_dir, text):
    todo_id = next(
        ln.split(": ", 1)[1] for ln in
        text.splitlines() if ln.startswith("id: "))
    (bundle_dir / "todos" / f"{todo_id}.md") \
        .write_text(text, encoding="utf-8")


def build_store(plans):
    """The two-bundle fixture store under `plans`,
    every figure hand-computed in the docstring.
    Returns (bundle one's dir, bundle two's dir)."""
    one = _write_bundle(plans, "timing-demo", PLAN_ONE)
    _write_todo(one, todo_file(
        id="groundwork", title="Groundwork",
        status="done", step=1, est="30m",
        position="serial",
        body=moves(
            created("09:00"),
            status("doing", "09:05", old="todo",
                   actor="ed-a", worktree="wt-1"),
            status("blocked", "09:20", old="doing",
                   actor="ed-a"),
            status("doing", "09:35", old="blocked",
                   actor="ed-a"),
            status("done", "09:50", old="doing",
                   actor="ed-a"))))
    _write_todo(one, todo_file(
        id="lane-a", title="Lane A", status="done",
        step=2, est="20m", position="branch",
        body=moves(
            created("09:55"),
            status("doing", "10:00", old="todo",
                   actor="ed-a", worktree="wt-1"),
            status("done", "10:30", old="doing",
                   actor="ed-a"))))
    _write_todo(one, todo_file(
        id="lane-b", title="Lane B", status="done",
        step=2, est="25m", position="branch",
        body=moves(
            created("09:56"),
            status("doing", "10:10", old="todo",
                   actor="ed-b", worktree="wt-1"),
            status("done", "10:50", old="doing",
                   actor="ed-b"))))
    _write_todo(one, todo_file(
        id="lane-c", title="Lane C", status="done",
        step=3, est="40m", position="branch",
        body=moves(
            created("09:57"),
            status("doing", "10:05", old="todo",
                   actor="ed-c", worktree="wt-2"),
            status("done", "10:35", old="doing",
                   actor="ed-c"))))
    _write_todo(one, todo_file(
        id="join-up", title="Join up", status="done",
        step=4, est="20m", position="fan-in",
        body=moves(
            created("10:55"),
            status("doing", "11:00", old="todo",
                   actor="ed-a"),
            status("done", "11:10", old="doing",
                   actor="ed-a"))))
    _write_todo(one, todo_file(
        id="unpriced", title="Unpriced tidy",
        status="done", step=5, position="serial",
        body=moves(
            created("11:55"),
            status("doing", "12:00", old="todo",
                   actor="ed-a"),
            status("done", "12:15", old="doing",
                   actor="ed-a"))))
    _write_todo(one, todo_file(
        id="never-started", title="Never started",
        status="todo", step=6, est="15m",
        position="serial",
        body=moves(created("12:30"))))
    _write_todo(one, todo_file(
        id="in-flight", title="In flight",
        status="doing",
        body=moves(
            created("14:55"),
            status("doing", "15:00", old="todo",
                   actor="ed-a"))))
    two = _write_bundle(plans, "second-plan", PLAN_TWO)
    join_two_body = "\n".join([
        tr.TRANSITIONS_HEADER, "",
        backfilled_move("doing", "13:00", "todo"),
        backfilled_move("done", "13:10", "doing")])
    _write_todo(two, todo_file(
        id="join-two", title="Join two",
        status="done", step=1, est="30m",
        position="fan-in", body=join_two_body))
    _write_todo(two, todo_file(
        id="join-three", title="Join three",
        status="done", step=2, est="40m",
        position="fan-in",
        body=moves(
            created("13:55"),
            status("doing", "14:00", old="todo",
                   actor="ed-b"),
            status("done", "14:20", old="doing",
                   actor="ed-b"))))
    return one, two


class Store(unittest.TestCase):
    """The fixture store in a tmp dir, as a base for
    the lib-level tests."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plans = Path(self.tmp.name) / ".plans"
        self.plans.mkdir(parents=True)
        self.one, self.two = build_store(self.plans)

    def todo(self, bundle_dir, todo_id):
        text = (bundle_dir / "todos"
                / f"{todo_id}.md").read_text(
                    encoding="utf-8")
        return parser.parse_todo(text)


class TestTodoTiming(Store):
    def test_blocked_interval_is_its_own_figure(self):
        figures = timing_mod.todo_timing(
            self.todo(self.one, "groundwork"))
        self.assertEqual(figures["est"], 30.0)
        self.assertEqual(figures["gross"], 45.0)
        self.assertEqual(figures["blocked"], 15.0)
        self.assertEqual(figures["net"], 30.0)
        self.assertEqual(figures["editors"], ["ed-a"])
        self.assertEqual(figures["worktrees"], ["wt-1"])
        self.assertFalse(figures["open"])

    def test_open_span_carries_no_actual(self):
        figures = timing_mod.todo_timing(
            self.todo(self.one, "in-flight"))
        self.assertTrue(figures["open"])
        self.assertIsNone(figures["gross"])
        self.assertIsNone(figures["blocked"])
        self.assertIsNone(figures["net"])

    def test_never_started_is_absence_not_zero(self):
        figures = timing_mod.todo_timing(
            self.todo(self.one, "never-started"))
        self.assertEqual(figures["est"], 15.0)
        self.assertIsNone(figures["gross"])
        self.assertFalse(figures["open"])

    def test_backfilled_span_is_marked(self):
        figures = timing_mod.todo_timing(
            self.todo(self.two, "join-two"))
        self.assertEqual(figures["gross"], 10.0)
        self.assertEqual(figures["backfilled"],
                         ["landing record"])


class TestPlanTiming(Store):
    def setUp(self):
        super().setUp()
        self.report = timing_mod.plan_timing(
            self.plans, "timing-demo")
        self.steps = {s["step"]: s
                      for s in self.report["steps"]}

    def test_step_figures(self):
        one = self.steps[1]
        self.assertEqual(one["est"], 30.0)
        self.assertEqual(one["gross"], 45.0)
        self.assertEqual(one["blocked"], 15.0)
        self.assertEqual(one["net"], 30.0)
        self.assertEqual(one["position"], "serial")
        self.assertEqual(one["title"], "Groundwork")

    def test_branch_step_span_and_items(self):
        two = self.steps[2]
        # The step's span is earliest doing → latest
        # done across its lanes, not their sum.
        self.assertEqual(two["gross"], 50.0)
        self.assertEqual(two["blocked"], 0.0)
        self.assertEqual(two["position"], "branch")
        self.assertEqual(
            {i["id"] for i in two["items"]},
            {"lane-a", "lane-b"})
        # N editors over M worktrees: two editors,
        # one shared worktree.
        self.assertEqual(set(two["editors"]),
                         {"ed-a", "ed-b"})
        self.assertEqual(two["worktrees"], ["wt-1"])

    def test_est_less_step_is_honest_absence(self):
        five = self.steps[5]
        self.assertIsNone(five["est"])
        self.assertEqual(five["gross"], 15.0)
        # Its todo carries no est, so no item line.
        self.assertEqual(five["items"], [])

    def test_unmeasured_step_is_honest_absence(self):
        six = self.steps[6]
        self.assertEqual(six["est"], 15.0)
        self.assertIsNone(six["gross"])
        self.assertEqual(six["measured"], 0)

    def test_wall_clock_is_the_ruled_form(self):
        wall = self.report["wall_actual"]
        # serial 45+15, longest branch max(50, 30),
        # fan-in 10 — not the 150m serial sum.
        self.assertEqual(wall["ruled"], 120.0)
        self.assertEqual(wall["serial_sum"], 150.0)
        self.assertEqual(wall["unmeasured"], 1)
        wall_est = self.report["wall_est"]
        self.assertEqual(wall_est["ruled"], 110.0)
        self.assertEqual(wall_est["serial_sum"], 150.0)
        self.assertEqual(wall_est["unmeasured"], 1)

    def test_unstepped_todos_are_named(self):
        self.assertEqual(self.report["unstepped"],
                         ["in-flight"])

    def test_backfilled_step_is_marked(self):
        report = timing_mod.plan_timing(
            self.plans, "second-plan")
        self.assertEqual(report["steps"][0]["backfilled"],
                         ["landing record"])

    def test_unknown_bundle_is_named(self):
        with self.assertRaises(ValueError):
            timing_mod.plan_timing(self.plans, "nope")


class TestPriceBook(Store):
    def setUp(self):
        super().setUp()
        self.book = timing_mod.price_book(self.plans)

    def test_distribution_by_kind(self):
        kinds = self.book["kinds"]
        self.assertEqual(kinds["serial"]["count"], 1)
        self.assertEqual(kinds["serial"]["est"], 30.0)
        self.assertEqual(kinds["serial"]["actual"], 45.0)
        branch = kinds["branch"]
        self.assertEqual(branch["count"], 3)
        self.assertEqual(branch["est"], 85.0)
        self.assertEqual(branch["actual"], 100.0)
        self.assertEqual(branch["median_ratio"], 1.5)
        self.assertFalse(branch["far_under"])

    def test_far_under_kind_is_flagged(self):
        fan_in = self.book["kinds"]["fan-in"]
        self.assertEqual(fan_in["count"], 3)
        self.assertTrue(fan_in["far_under"])
        self.assertEqual(fan_in["max_ratio"], 0.5)

    def test_priced_as_serial_sum_is_flagged(self):
        flags = self.book["priced_as_serial_sum"]
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["step"], 2)
        self.assertEqual(flags[0]["est"], 45.0)
        self.assertEqual(flags[0]["items_est"], 45.0)

    def test_priced_unmeasured_is_counted_not_faked(self):
        self.assertEqual(self.book["unmeasured_priced"], 1)


class TestRender(Store):
    def test_plan_render_carries_the_figures(self):
        text = timing_mod.render_plan(
            timing_mod.plan_timing(self.plans,
                                   "timing-demo"))
        self.assertIn("step 1 — Groundwork", text)
        self.assertIn("blocked 15m", text)
        self.assertIn("wall-clock (actual): ruled 2h",
                      text)
        self.assertIn("serial sum 2h30m", text)
        # Absence renders as absence, never as 0m.
        self.assertIn("est —", text)
        self.assertNotIn("actual 0m", text)

    def test_book_render_flags_both_shapes(self):
        text = timing_mod.render_book(
            timing_mod.price_book(self.plans))
        self.assertIn("kind fan-in", text)
        self.assertIn("FAR-UNDER", text)
        self.assertIn("PRICED-AS-SERIAL-SUM", text)


class TestTimingCli(unittest.TestCase):
    """The verb itself over a fixture project."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir(parents=True)
        (self.root / "workbench.yaml").write_text(
            "name: Fixture\n"
            "registry: workbench/registry.db\n"
            "plans: .plans\n")
        plans = self.root / ".plans"
        plans.mkdir(parents=True)
        self.one, _ = build_store(plans)

    def wb(self, *argv, expect=0):
        r = subprocess.run(
            [PY, str(WB), "--root", str(self.root), *argv],
            capture_output=True, text=True)
        if expect is not None:
            self.assertEqual(
                r.returncode, expect,
                f"wb {argv} -> {r.returncode}\n{r.stdout}\n"
                f"{r.stderr}")
        return r

    def test_plan_report_over_cli(self):
        r = self.wb("todo", "timing", self.one.name)
        self.assertIn("wall-clock (actual): ruled 2h",
                      r.stdout)
        self.assertIn("step 2 — Parallel lanes",
                      r.stdout)

    def test_price_book_over_cli(self):
        r = self.wb("todo", "timing")
        self.assertIn("price book", r.stdout)
        self.assertIn("FAR-UNDER", r.stdout)

    def test_unknown_bundle_fails_loud(self):
        r = self.wb("todo", "timing", "nope", expect=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown bundle", r.stderr)


if __name__ == "__main__":
    unittest.main()
