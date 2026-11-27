"""The replay store fixture for
test_timing_replay: the completed
wall-clock-reduction plan's evidence as
constants — the plan copy, the todos' bodies
and titles, the reconstructed (backfilled)
transition lines, and the hand-computed
figure tables — plus the store builder that
plants them in a tmp project in the serve
tree's split shape. The harness beside this
module asserts the report's figures against
these constants; nothing here touches a
live tree."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
WB_ROOT = HERE.parents[2]
sys.path.insert(0, str(WB_ROOT))

from lib.writes import transitions as tr  # noqa: E402

SLUG = "2026-11-26-wall-clock-reduction"
DAY = "2026-11-26"
SEAT = "workhorse-successor-v"

# The fixture plan copy: the real plan's headings,
# wb-step blocks, and closing est lines verbatim
# (the surfaces the report reads); the steps'
# prose bodies and step 1's closing-est annotation
# are elided — the account names the elision. The
# two files: lines naming plan-dir artefacts
# render them by file name only: tracked text
# carries no untracked path.
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

files: `measurement.md` in the plan's own dir (created)
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

files: `overlap.md` in the plan's own dir (created)
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
# completion notes are part of the evidence —
# bar the one untracked path in wc-measure's
# body, rendered by file name as above.
BODIES = {
    "wc-measure": (
        "Step 1 landed: five slices joined into "
        "the plan dir's measurement.md. "
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
