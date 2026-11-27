"""Timing-ledger Step 5 (wb timing-ledger plan):
the replay proof over a completed plan.

The plan is 2026-11-26-wall-clock-reduction — eight
steps, all done, executed the day before the ledger
existed, so its todos carry no transitions and no
minted est. This harness rebuilds its store in a
tmp project in the serve tree's own shape — a
bundle directory holding only todos under the
project's .plans, the plan file in a SEPARATE tree
(the seat's plan dir), joined only by the todos'
`plan:` front-matter ref — with each todo's
transitions reconstructed from the surviving
evidence under the backfill-honesty ruling: every
reconstructed line carries `backfilled: true` and
a `source` naming its evidence, at exactly the
precision that evidence carries.

The backfill form (defined by this step): a record
in the ledger's own shape — at, actor, verb,
field, old, new — plus the two marker keys. A
create line rides the front-matter `created:`
stamp, which is date-only, so its instant is
day-grain (2026-11-26T00:00:00+00:00) and its
source says so. A doing line is placed only where
a recorded instant bounds the step's work
independently of its completion (a build commit);
a done line at the completion instant the record
carries (a landing record's landed_at, a run
record's finish, a commit, or the todo file's own
mtime — the write that recorded done). Where no
independent doing bound survives (steps 1, 7, 8),
no doing line is reconstructed: the step renders
no span, which is the honest rendering — a span
needs two bounds, and one bound is not a span.

Hand-computed from the evidence (2026-11-26, UTC):

  step 1 (est 60m) wc-measure: no doing bound;
    done at the todo file's mtime 16:21:48 (the
    write recording done; measurement.md itself
    written 16:21:04) → no measured span
  step 2 (est 40m) wc-verdict-fires: doing
    18:33:04 (git c4d33a12, the build commit) →
    done 18:36:12.526154 (landing record
    99133339344e) = 188.53s ≈ 3.14m
  step 3 (est 45m) wc-union-default: doing
    16:49:24 (git 38a57d82, the contract half —
    the step's first landed piece) → done
    19:21:31.045447 (landing record e46a5d437c74)
    = 9127.05s ≈ 152.12m
  step 4 (est 20m) wc-double-run: doing 16:34:34
    (git 3d2be92d, the gate-form conversion) →
    done 16:44:55 (run record plancheck-gate-
    20261126T164424Z, the green-path verification
    fire's finish) = 621s = 10.35m
  step 5 (est 40m) wc-landing-record: doing
    17:04:56 (git cd973e01, the writer commit) →
    done 17:22:03.944307 (landing record
    99cd586f1737) = 1027.94s ≈ 17.13m
  step 6 (est 35m) wc-plancheck-formations:
    doing 16:24:35 (git 30cf0449, the refusal
    class) → done 18:01:05.2578 (landing record
    c27c2c92c2ef, the precision cure — the step's
    final landing) = 5790.26s ≈ 96.50m
  step 7 (est 35m) wc-overlap: no doing bound;
    done at the todo file's mtime 19:29:19 →
    no measured span
  step 8 (est 30m) wc-spec-transfer: the starter
    commit (19:30:22) and this repo's sync commit
    (19:30:38) are one bound, not two → no doing;
    done 19:30:38 (git 6cbf16b6) → no span

  wall-clock est: every step priced, none
    declaring a position (the blocks predate the
    position grammar) → ruled = serial sum
    60+40+45+20+40+35+35+30 = 305m (5h05m). The
    plan header's stated Total of 170m is the
    critical path over the requires graph
    (60 + max(40,45,20,40,35) + 35 + 30) — a form
    the ledger cannot reproduce without position
    declarations; the account beside this test
    names the gap.
  wall-clock actual: ruled = serial sum over the
    five measured steps ≈ 279.25m (4h39m), with
    3 steps excluded as unmeasured.
  blocked: no step's record carries a blocked
    episode → a measured 0m on every span.
  price book: no todo carries a minted est or
    position → no priced items (honest absence).

Overlap with the plan's own records, asserted
below: each landing record's landed_at is its
step's report end; step 5's record phases
(formation→gate 13.6m, gate→landed 1.8m,
formation→landed 15.5m) sit inside the report's
17.13m step span, which opens 1m40s before the
record's formation (the writer commit precedes
the first gate fire); step 3's proof fire
(union-gate, started 19:22:04) runs AFTER the
step's done (the landing) — post-landing
verification, outside the span; step 6's span
covers both of its landings (first gate green
16:30:30 through the cure's landed_at).

All state lives in tmp dirs — the serve tree's
records are read as evidence at authoring time
and embedded here as constants; nothing live is
touched or mutated.
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

from lib.plans import timing as timing_mod  # noqa: E402
from lib.plans.bundles import list_bundles  # noqa: E402
from lib.util import parse_instant  # noqa: E402
from lib.writes import transitions as tr  # noqa: E402

WB = WB_ROOT / "wb"
PY = sys.executable
SLUG = "2026-11-26-wall-clock-reduction"
DAY = "2026-11-26"
SEAT = "workhorse-successor-v"

# The fixture plan copy: the real plan's headings,
# wb-step blocks, and closing est lines verbatim
# (the surfaces the report reads); the steps'
# prose bodies and step 1's closing-est annotation
# are elided — the account names the elision.
PLAN_TEXT = """# Wall-clock reduction — measurement, target-state steps, mechanical enforcement

Status: adopted
Executor: workhorse successor V (chat 5296ce86-01f9-4341-b9b5-751dc37faeea)
Total: 170m

## Steps

### Step 1 — Inventory the four sources; the inventory is the analysis

Work.

<!-- wb-step
step=1
todos=wc-measure
requires=
est=60m
fanout=memory | chat logs | run logs | commits | external research
-->

files: `.plans/2026-11-26-wall-clock-reduction/measurement.md` (created)
verify: the record's cross-source joins are spot-proven
done when: the measurement record stands
est: 60m [four corpora plus a research lane, priced at the longest lane — the chat-log slice, …]

### Step 2 — No-verdict gate fires: pre-dispatch manifest check and outcome classification

Work.

<!-- wb-step
step=2
todos=wc-verdict-fires
requires=wc-measure
est=40m
fanout=dispatch validation | record classification
-->

files: `pipeline/venue/bin/local-run`
verify: `python3 check.py pipeline/venue/tests --workers 2`
done when: a broken manifest refuses before dispatch
est: 40m

### Step 3 — The union gate becomes the dispatch default for queueable work

Work.

<!-- wb-step
step=3
todos=wc-union-default
requires=wc-measure
est=45m
fanout=union formation | constituent recording
-->

files: `pipeline/venue/bin/local-run`
verify: `python3 check.py pipeline/venue/tests --workers 2`
done when: a two-delta queue gates in one fire
est: 45m

### Step 4 — Price the in-fire double run; keep it, cut it, or convert it on its catch rate

Work.

<!-- wb-step
step=4
todos=wc-double-run
requires=wc-measure
est=20m
fanout=gate job templates | re-proof dispatch form
-->

files: `pipeline/venue/adapters/local/jobs/` (the gate job templates)
verify: `python3 check.py pipeline/venue/tests --workers 2`
done when: the gate form matches the measured catch rate
est: 20m

### Step 5 — The landing record: wall clock per phase, and the gates-per-landing counter

Work.

<!-- wb-step
step=5
todos=wc-landing-record
requires=wc-measure
est=40m
fanout=landing record writer | measure rows
-->

files: `pipeline/venue/results/` (the landing record family)
verify: `python3 check.py pipeline/attention/tests --workers 2`
done when: landings write phase-priced records
est: 40m

### Step 6 — plan-check refuses per-row formations and per-item gates

Work.

<!-- wb-step
step=6
todos=wc-plancheck-formations
requires=wc-measure
est=35m
fanout=refusal class | fixtures and tests
-->

files: `pipeline/workrecord/lib/plans/plan_check.py`
verify: `python3 check.py pipeline/workrecord/tests/harness/test_plan_check.py --workers 2`
done when: a fixture plan staffing per-row formations refuses
est: 35m

### Step 7 — The overlap analysis: where each discipline binds when there is no plan

Work.

<!-- wb-step
step=7
todos=wc-overlap
requires=wc-verdict-fires|wc-union-default|wc-double-run|wc-landing-record|wc-plancheck-formations
est=35m
fanout=planless register form | goal-oriented form
-->

files: `.plans/2026-11-26-wall-clock-reduction/overlap.md` (created)
verify: every discipline × work-form cell carries a disposition
done when: the overlap record stands complete
est: 35m

### Step 8 — Spec transfer: the rules and enforcement forms enter the starter

Work.

<!-- wb-step
step=8
todos=wc-spec-transfer
requires=wc-verdict-fires|wc-union-default|wc-double-run|wc-landing-record|wc-plancheck-formations|wc-overlap
est=30m
serial=docs/supervision-rules.md in spec-driven-starter — shared text with the in-flight estimate-categorization audit
-->

files: `docs/supervision-rules.md` and `docs/estimate-evidence-register.md` (in `spec-driven-starter`)
verify: the starter's narrow check (scan + fast) on the spec change
done when: the starter carries the wall-clock rules and enforcement forms
est: 30m
"""

# The serve-tree todos' bodies, verbatim — the
# completion notes are part of the evidence.
BODIES = {
    "wc-measure": (
        "Step 1 landed: five slices joined into "
        ".plans/2026-11-26-wall-clock-reduction/measurement.md. "
        "Head sink corrected: no-verdict 43.8% (not 57%), a "
        "launch-phase sink (82% pre-job; Colab 64% vs local 9%); "
        "card timeouts 20 / ~7h44m pending 2026-11-25 as second "
        "witness. Double-run catch rate zero over 44 pairs. "
        "Order stands; step 2 widened to the launch phase + "
        "dispatch-route discipline; step 4 pre-priced to "
        "convert."),
    "wc-verdict-fires": (
        "Landed main 9913333 (gate wc2-gate-20261126T183524Z "
        "green on local-main). Composition at landing: local-run "
        "conflict resolved to the preflight fold; the branch's "
        "hand-rolled --caller extraction replaced by flags.get "
        "(argv-idioms RED on the first gate fire, cured on the "
        "landing branch). Smoke record outcome_class ran-green "
        "verified first-hand."),
    "wc-union-default": (
        "Landed main e46a5d4, gate wc3-gate-20261126T192055Z "
        "green; real-fire proof union-gate-20261126T192204Z "
        "ran-green naming both constituents"),
    "wc-double-run": (
        "Landed main a752cd4: venue AGENTS.md gate-form bullet "
        "(check once, re-proof on red). All five standing local "
        "gate jobs converted (attn-fold, plancheck, registries, "
        "settings, staffing): RUN 2 blocks replaced by "
        "conditional RE-PROOF; verdict = run1 green OR re-proof "
        "green. Verified both paths on local-main: fire 163502Z "
        "ran the red path (run1 RED on a real portability "
        "untracked-ref in the bullet itself, re-proof RED, "
        "verdict red — the form caught a genuine defect in its "
        "own landing); fire 164424Z green path (1 GATE RUN, 0 "
        "RE-PROOF, 2x check: green, exit 0). One transport-dead "
        "fire (164038Z, kex reset at mkdir) re-fired after "
        "smoke proved the venue back."),
    "wc-landing-record": (
        "Landed main 99cd586 (gate wc5-gate-20261126T171940Z "
        "green). pipeline/venue/bin/land-record writes the "
        "record at the landing act (formation opened / "
        "gate-green / landed, fires + venue-minutes + "
        "constituents counted; refuses a landing with no green "
        "verdict run); pipeline/attention/services/measure/"
        "landings.py aggregates the family and build_staffing "
        "serves it as the staffing payload landings section on "
        "every return path. First real record written for this "
        "landing itself (2 fires, formation-to-gate 13.6m, "
        "gate-to-landed 1.8m) and read back live in the served "
        "digest after the workhorse.service restart: "
        "landings=1, fires_per_landing 2.0, phase medians "
        "matching the record. Gate caught my own scanner "
        "defects on the first fire (ruff format, date-uniqueness "
        "parse copies in both new files, a paths root-climb) — "
        "cured by riding the homed modules (records/_as_dt via "
        "staffing_rows; venue paths spine + lease foundation "
        "epoch/parse_dt)."),
    "wc-plancheck-formations": (
        "Landed main d02055a (gate plancheck-gate-"
        "20261126T162947Z green, 4x check: green). "
        "plan_check.py formation class: step bodies, fan-out "
        "values, and the Rulings section scanned for per-row "
        "formation / per-item gate declaration shapes (plurals "
        "included), negation-guarded so the bound stated as a "
        "prohibition passes. 3 fixtures + 3 tests; live "
        "read-back with the landed verb: per-item-gate.md "
        "refuses exit 3, bound-stated-in-rulings.md clean "
        "exit 0."),
    "wc-overlap": (
        "overlap.md landed on main; nine disciplines "
        "dispositioned over both planless forms\n\n"
        "overlap.md delivered in the plan dir (plans are "
        "untracked records in this repo); nine disciplines "
        "dispositioned over both planless forms, class count "
        "verified first-hand against the current GOAL.md "
        "(six classes)"),
    "wc-spec-transfer": (
        "Starter 56786fa carries the six payload items; "
        "filtered sync applied to all six carriers and "
        "verified; this repo's copy landed 4d55eee. The "
        "thread-pool capacity candidate went to the spec "
        "seat's judgment unbuilt, as the plan named it"),
}

TITLES = {
    "wc-measure": "Step 1 — Inventory the four sources; "
                  "the inventory is the analysis",
    "wc-verdict-fires": "Step 2 — No-verdict gate fires: "
                        "pre-dispatch manifest check and "
                        "outcome classification",
    "wc-union-default": "Step 3 — The union gate becomes "
                        "the dispatch default for "
                        "queueable work",
    "wc-double-run": "Step 4 — Price the in-fire double "
                     "run; keep it, cut it, or convert "
                     "it on its catch rate",
    "wc-landing-record": "Step 5 — The landing record: "
                         "wall clock per phase, and the "
                         "gates-per-landing counter",
    "wc-plancheck-formations": "Step 6 — plan-check "
                               "refuses per-row formations "
                               "and per-item gates",
    "wc-overlap": "Step 7 — The overlap analysis: where "
                  "each discipline binds when there is "
                  "no plan",
    "wc-spec-transfer": "Step 8 — Spec transfer: the "
                        "rules and enforcement forms "
                        "enter the starter",
}

STEPS = {
    "wc-measure": 1, "wc-verdict-fires": 2,
    "wc-union-default": 3, "wc-double-run": 4,
    "wc-landing-record": 5, "wc-plancheck-formations": 6,
    "wc-overlap": 7, "wc-spec-transfer": 8,
}

CREATED_SOURCE = ("todo front-matter created stamp "
                  "(date-only)")
TODO_MTIME_SOURCE = ("todo file mtime, serve tree "
                     "(the write recording done)")


def backfilled(*, at, actor, verb, old, new, source):
    """One reconstructed transition line: the
    ledger's record shape plus the Step 5 marker
    keys (`backfilled`, `source`)."""
    record = {"at": at, "actor": actor, "verb": verb,
              "field": "status", "old": old, "new": new,
              "backfilled": True, "source": source}
    return "transition: " + json.dumps(
        record, ensure_ascii=False)


def created():
    return backfilled(
        at=f"{DAY}T00:00:00+00:00", actor="create",
        verb="create", old=None, new="todo",
        source=CREATED_SOURCE)


def doing(at, source, actor=SEAT):
    return backfilled(
        at=at, actor=actor, verb="set-status",
        old="todo", new="doing", source=source)


def done(at, source, old="doing"):
    return backfilled(
        at=at, actor=SEAT, verb="set-status",
        old=old, new="done", source=source)


# The reconstruction, per todo: the evidence named
# in the module docstring, line by line.
TRANSITIONS = {
    "wc-measure": [
        created(),
        done(f"{DAY}T16:21:48+00:00", TODO_MTIME_SOURCE,
             old="todo"),
    ],
    "wc-verdict-fires": [
        created(),
        doing(f"{DAY}T18:33:04+00:00",
              "git commit c4d33a12 (the step's build, "
              "formation/wc-verdict-fires tip)",
              actor="local-compute"),
        done(f"{DAY}T18:36:12.526154+00:00",
             "landing record "
             "99133339344e-20261126T183612"),
    ],
    "wc-union-default": [
        created(),
        doing(f"{DAY}T16:49:24+00:00",
              "git commit 38a57d82 (the step's "
              "contract half, landed first)"),
        done(f"{DAY}T19:21:31.045447+00:00",
             "landing record "
             "e46a5d437c74-20261126T192131"),
    ],
    "wc-double-run": [
        created(),
        doing(f"{DAY}T16:34:34+00:00",
              "git commit 3d2be92d (the gate-form "
              "conversion)"),
        done(f"{DAY}T16:44:55+00:00",
             "run record plancheck-gate-"
             "20261126T164424Z (the green-path "
             "verification fire, finished)"),
    ],
    "wc-landing-record": [
        created(),
        doing(f"{DAY}T17:04:56+00:00",
              "git commit cd973e01 (the landing-"
              "record writer)"),
        done(f"{DAY}T17:22:03.944307+00:00",
             "landing record "
             "99cd586f1737-20261126T172203"),
    ],
    "wc-plancheck-formations": [
        created(),
        doing(f"{DAY}T16:24:35+00:00",
              "git commit 30cf0449 (the formation "
              "refusal class)"),
        done(f"{DAY}T18:01:05.257800+00:00",
             "landing record "
             "c27c2c92c2ef-20261126T180105 (the "
             "precision cure, the step's final "
             "landing)"),
    ],
    "wc-overlap": [
        created(),
        done(f"{DAY}T19:29:19+00:00", TODO_MTIME_SOURCE,
             old="todo"),
    ],
    "wc-spec-transfer": [
        created(),
        done(f"{DAY}T19:30:38+00:00",
             "git commit 6cbf16b6 (spec sync: "
             "wall-clock transfer — this repo's "
             "copy landed)", old="todo"),
    ],
}

# Expected gross spans in minutes, hand-computed
# in the module docstring.
GROSS = {2: 3.14, 3: 152.12, 4: 10.35, 5: 17.13,
         6: 96.50}
EST = {1: 60.0, 2: 40.0, 3: 45.0, 4: 20.0, 5: 40.0,
       6: 35.0, 7: 35.0, 8: 30.0}


def todo_text(todo_id, ref):
    lines = ["---", f"id: {todo_id}",
             f"title: {TITLES[todo_id]}",
             "status: done", f"plan: {ref}",
             f"plan_step: {STEPS[todo_id]}",
             f"created: {DAY}", f"updated: {DAY}",
             "---", "", BODIES[todo_id], "",
             tr.TRANSITIONS_HEADER, ""]
    lines += TRANSITIONS[todo_id]
    return "\n".join(lines) + "\n"


def build_store(base, *, write_plan=True):
    """The replay store under `base`, in the serve
    tree's shape: the plan file in its own tree
    (serve/.plans), the bundle — todos only — in
    the project's .plans, joined by the todos'
    plan refs. Returns (project root, plans dir)."""
    serve_plans = base / "serve" / ".plans"
    serve_plans.mkdir(parents=True)
    plan_path = serve_plans / f"{SLUG}.md"
    if write_plan:
        plan_path.write_text(PLAN_TEXT,
                             encoding="utf-8")
    root = base / "proj"
    root.mkdir()
    (root / "workbench.yaml").write_text(
        "name: Fixture\n"
        "registry: workbench/registry.db\n"
        "plans: .plans\n", encoding="utf-8")
    todos_dir = root / ".plans" / SLUG / "todos"
    todos_dir.mkdir(parents=True)
    for todo_id in STEPS:
        (todos_dir / f"{todo_id}.md").write_text(
            todo_text(todo_id, str(plan_path)),
            encoding="utf-8")
    return root, root / ".plans"


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root, self.plans = build_store(
            Path(self.tmp.name))
        self.report = timing_mod.plan_timing(
            self.plans, SLUG)
        self.steps = {s["step"]: s
                      for s in self.report["steps"]}

    def todo_figures(self, todo_id):
        todo = next(
            t for b in list_bundles(self.plans)
            for t in b["todos"] if t["id"] == todo_id)
        return timing_mod.todo_timing(todo)


class TestStepFigures(Store):
    def test_estimates_come_from_the_plan_blocks(self):
        for number, est in EST.items():
            self.assertEqual(
                self.steps[number]["est"], est,
                f"step {number}")

    def test_titles_join_through_the_plan_ref(self):
        # The cure's proof: the bundle carries no
        # plan.md, so titles exist only because the
        # report read the plan through the todos'
        # shared ref.
        self.assertEqual(
            self.steps[1]["title"],
            "Inventory the four sources; the "
            "inventory is the analysis")
        self.assertEqual(
            self.steps[5]["title"],
            "The landing record: wall clock per "
            "phase, and the gates-per-landing "
            "counter")

    def test_measured_spans_match_the_evidence(self):
        for number, gross in GROSS.items():
            step = self.steps[number]
            self.assertAlmostEqual(
                step["gross"], gross, places=2,
                msg=f"step {number}")
            self.assertEqual(step["blocked"], 0.0)
            self.assertAlmostEqual(
                step["net"], gross, places=2)
            self.assertEqual(step["measured"], 1)

    def test_unbounded_steps_render_no_span(self):
        for number in (1, 7, 8):
            step = self.steps[number]
            self.assertIsNone(step["gross"])
            self.assertEqual(step["measured"], 0)

    def test_backfilled_spans_are_marked(self):
        for number in GROSS:
            self.assertTrue(
                self.steps[number]["backfilled"],
                f"step {number}")
        self.assertIn(
            "landing record "
            "99cd586f1737-20261126T172203",
            self.steps[5]["backfilled"])

    def test_editors_are_the_transitions_actors(self):
        # Step 2's build is the local-compute
        # seat's (its landing record says so); the
        # landing is the executor seat's.
        step = self.steps[2]
        self.assertEqual(
            step["editors"],
            ["local-compute", SEAT])


class TestWallClock(Store):
    def test_est_wall_clock_is_the_serial_sum(self):
        # No step declares a position, so the ruled
        # form prices every step in the serial band:
        # ruled == serial sum == 305m — not the
        # plan header's 170m critical-path total,
        # which the requires graph carries and the
        # position grammar cannot reproduce.
        wall = self.report["wall_est"]
        self.assertEqual(wall["ruled"], 305.0)
        self.assertEqual(wall["serial_sum"], 305.0)
        self.assertEqual(wall["unmeasured"], 0)

    def test_actual_wall_clock_excludes_unmeasured(self):
        wall = self.report["wall_actual"]
        self.assertAlmostEqual(
            wall["ruled"], 279.25, places=2)
        self.assertAlmostEqual(
            wall["serial_sum"], 279.25, places=2)
        self.assertEqual(wall["unmeasured"], 3)


class TestRecordOverlap(Store):
    """The report's figures against the plan's own
    records, where the two overlap."""

    def test_step_ends_equal_the_landing_records(self):
        ends = {
            "wc-verdict-fires":
                "2026-11-26T18:36:12.526154+00:00",
            "wc-union-default":
                "2026-11-26T19:21:31.045447+00:00",
            "wc-landing-record":
                "2026-11-26T17:22:03.944307+00:00",
            "wc-plancheck-formations":
                "2026-11-26T18:01:05.257800+00:00",
        }
        for todo_id, landed_at in ends.items():
            self.assertEqual(
                self.todo_figures(todo_id)["end"],
                parse_instant(landed_at), todo_id)

    def test_step5_span_contains_its_landing_phases(self):
        # The landing record prices formation→
        # landed at 15.5m (13.6 + 1.8); the report's
        # step span opens at the writer commit,
        # 1m40s before the record's formation, and
        # closes at the same landed_at.
        figures = self.todo_figures("wc-landing-record")
        formation = parse_instant(
            "2026-11-26T17:06:36.358548+00:00")
        gate_green = parse_instant(
            "2026-11-26T17:20:13+00:00")
        self.assertLess(figures["start"], formation)
        self.assertLess(formation, gate_green)
        self.assertLess(gate_green, figures["end"])
        self.assertGreater(figures["gross"], 15.5)

    def test_step3_proof_fire_is_post_landing(self):
        # The union proof fire ran after the step's
        # landing — verification of the landed form,
        # outside the step's span.
        figures = self.todo_figures("wc-union-default")
        proof_start = parse_instant(
            "2026-11-26T19:22:04.798951+00:00")
        self.assertLess(figures["end"], proof_start)

    def test_step6_span_covers_both_landings(self):
        figures = self.todo_figures(
            "wc-plancheck-formations")
        first_gate_green = parse_instant(
            "2026-11-26T16:30:30+00:00")
        self.assertLess(figures["start"],
                        first_gate_green)
        self.assertLess(first_gate_green,
                        figures["end"])


class TestRender(Store):
    def setUp(self):
        super().setUp()
        self.text = timing_mod.render_plan(
            self.report)

    def test_render_carries_the_figures(self):
        self.assertIn(
            "step 1 — Inventory the four sources; "
            "the inventory is the analysis",
            self.text)
        self.assertIn("actual 2h32m", self.text)
        self.assertIn(
            "wall-clock (est): ruled 5h05m  "
            "serial sum 5h05m", self.text)
        self.assertIn(
            "wall-clock (actual): ruled 4h39m  "
            "serial sum 4h39m  (3 step(s) without "
            "a figure, excluded)", self.text)

    def test_render_marks_backfill_and_absence(self):
        self.assertIn("[backfilled: ", self.text)
        self.assertIn(
            "no measured span — the step's todos "
            "carry no doing→done record (honest "
            "absence)", self.text)
        self.assertNotIn("actual 0m", self.text)

    def test_price_book_is_honest_absence(self):
        # No todo in this pre-ledger plan carries a
        # minted est or position, so the book has
        # no priced items to distribute.
        book = timing_mod.price_book(self.plans)
        self.assertEqual(book["kinds"], {})
        self.assertEqual(book["unmeasured_priced"], 0)
        self.assertIn(
            "no priced, measured items recorded "
            "yet (honest absence)",
            timing_mod.render_book(book))


class TestSplitStoreWithoutPlanFile(unittest.TestCase):
    """The cure's honesty boundary: the same split
    store with the plan file missing renders the
    steps' estimates and titles as absence — the
    join never invents a plan."""

    def test_missing_plan_file_is_absence(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        _, plans = build_store(
            Path(tmp.name), write_plan=False)
        report = timing_mod.plan_timing(plans, SLUG)
        steps = {s["step"]: s
                 for s in report["steps"]}
        self.assertIsNone(steps[2]["est"])
        self.assertIsNone(steps[2]["title"])
        # The transitions still measure: the span
        # does not depend on the plan file.
        self.assertAlmostEqual(
            steps[2]["gross"], GROSS[2], places=2)


class TestReplayCli(unittest.TestCase):
    """The verb itself over the replay store."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root, _ = build_store(Path(self.tmp.name))

    def wb(self, *argv):
        return subprocess.run(
            [PY, str(WB), "--root", str(self.root),
             *argv], capture_output=True, text=True)

    def test_plan_report_over_cli(self):
        r = self.wb("todo", "timing", SLUG)
        self.assertEqual(
            r.returncode, 0,
            f"{r.stdout}\n{r.stderr}")
        self.assertIn(
            "wall-clock (actual): ruled 4h39m",
            r.stdout)
        self.assertIn(
            "step 3 — The union gate becomes the "
            "dispatch default", r.stdout)

    def test_price_book_over_cli(self):
        r = self.wb("todo", "timing")
        self.assertEqual(
            r.returncode, 0,
            f"{r.stdout}\n{r.stderr}")
        self.assertIn("price book", r.stdout)
        self.assertIn("honest absence", r.stdout)


if __name__ == "__main__":
    unittest.main()
