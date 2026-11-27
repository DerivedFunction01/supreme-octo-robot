"""The timing report's read side (wb timing-ledger
plan, Step 4): per plan and per step, estimate vs
actual from the file store's transition ledger,
rendered by the `wb todo timing` verb. Read-only —
this module writes nothing, backfills nothing, and
renders honest absence for a step or todo the record
does not price or measure.

Where the figures come from (the plan's Step 4 files
line cites `lib/registry/todos.py` read side; Step
1's census retired that surface — the DB todo tables
have no production writers — so the report reads the
FILE store, the ledger's actual home):
  - bundles and todos: lib/plans/bundles.py
    (list_bundles / parse_todo — front-matter est,
    fanout_position, plan_step, worktree);
  - transitions: lib/writes/transitions.py
    (transitions_in over the todo's body), their
    instants parsed by lib/util.py's parse_instant
    (the shared tolerant parse — a stamp that does
    not parse bounds nothing);
  - step structure: lib/plans/parser
    (extract_step_blocks for est= / position= /
    todos=, parse_plan for step titles and the
    closing est: lines; first_duration_minutes is
    the house reading of an estimate — its first
    duration token, the same reading plan-check
    compares the two est surfaces by).

Semantics (the plan's Rulings, implemented once here):
  - A todo's actual span is its first doing
    transition to its first terminal (done)
    transition after it, over status transitions
    only. A span still open (doing, never done) is
    in flight and carries no actual.
  - Blocked time inside a closed span is its own
    figure beside the gross: the intervals the span
    spent at status blocked. Net = gross - blocked
    where both are known. A step's blocked figure
    is the union of its todos' blocked intervals
    inside the step's span (overlapping blockage
    counted once); a step's gross is its todos'
    earliest doing to latest done.
  - Position: the block's position=, else the
    step's todos' minted fanout_position when they
    agree, else undeclared. For the wall-clock an
    undeclared step prices in the serial band (the
    conservative reading — it never invents
    parallelism the plan did not declare).
  - Plan wall-clock, the ruled form: serial-band
    sum + longest branch + fan-in sum, over the
    steps the record measures; the plain serial sum
    of every step stands beside it. Steps without a
    figure are excluded and counted, never zeroed.
  - Editors are a step's transitions' actors, with
    one exclusion: the transition helper records
    the verb's own name as the actor when no caller
    supplied an identity (Step 2), so a line whose
    actor equals its verb names no editor.
  - Backfilled events render marked: a transition
    carrying a truthy `backfilled` key (with its
    `source` when present) marks the figures its
    span bounds. No writer emits that key today —
    Step 5's backfill defines it; this read honours
    it when it lands.

The price book (across one project's plans) groups
priced, measured todos by KIND. The grouping rule,
named: an item's kind is its minted fan-out
position (serial / branch / fan-in; undeclared
when the mint carried none). Titles present no
recurring kind — the corpus's step and todo titles
are unique prose in every project the census
swept — so no title taxonomy is invented; the
position is the kind the records themselves carry,
and it is the axis the lazy shapes live on (branch
work priced as if serial). The two lazy shapes:
  - PRICED_AS_SERIAL_SUM: a branch step whose est
    matches the sum of its items' ests (within
    SERIAL_SUM_TOLERANCE) while the items' measured
    spans overlapped — priced as a serial sum of
    work the record shows ran in parallel.
  - FAR_UNDER: a kind whose measured items land
    consistently far under their price — at least
    FAR_UNDER_MIN_ITEMS items, every one's actual
    at most FAR_UNDER_RATIO of its est. (The plan's
    Step 4 names the shape without a number; these
    constants are the report's stated threshold,
    printed with the book so the flag is auditable.)
"""

import re
from pathlib import Path

from .bundles import list_bundles
from .parser import (extract_step_blocks,
                     first_duration_minutes, parse_plan)
from ..util import parse_instant
from ..writes.transitions import transitions_in

SERIAL_SUM_TOLERANCE = 0.10
FAR_UNDER_RATIO = 0.5
FAR_UNDER_MIN_ITEMS = 2

_EST_LINE_RE = re.compile(r"^\s*est:\s*(.*)$")
_POSITIONS = ("serial", "branch", "fan-in")


def _minutes(delta):
    return delta.total_seconds() / 60.0


def fmt_minutes(minutes):
    """A duration in minutes → the report's text form
    (45m, 1h35m, 2h); None renders as honest absence."""
    if minutes is None:
        return "—"
    total = int(round(minutes))
    if total < 60:
        return f"{total}m"
    hours, rest = divmod(total, 60)
    if rest == 0:
        return f"{hours}h"
    return f"{hours}h{rest:02d}m"


def est_minutes(raw):
    """An est surface (block est=, a closing est:
    line, a todo's minted est) → minutes by the
    house reading, or None when it carries no
    duration token."""
    if not raw:
        return None
    return first_duration_minutes(raw)


def _status_moves(todo):
    """A todo's status transitions as (instant,
    record) pairs, in file order — the only
    transitions that bound spans."""
    moves = []
    for record in transitions_in(todo.get("body") or ""):
        if record.get("field") != "status":
            continue
        at = parse_instant(record.get("at"))
        if at is not None:
            moves.append((at, record))
    return moves


def _marked(records):
    """The backfill sources named on a set of
    transitions: [] when none carries the marker."""
    sources = []
    for record in records:
        if record.get("backfilled"):
            source = record.get("source") or "unnamed"
            if source not in sources:
                sources.append(source)
    return sources


def todo_timing(todo):
    """One parsed todo (lib/plans/bundles.parse_todo's
    dict) → its timing figures. Every figure is None
    when the record does not hold it: no est, no
    doing transition, or a span still open."""
    moves = _status_moves(todo)
    start = end = None
    for at, record in moves:
        if start is None and record.get("new") == "doing":
            start = at
        elif start is not None and end is None \
                and record.get("new") == "done":
            end = at
    gross = blocked = net = None
    blocked_intervals = []
    if start is not None and end is not None:
        gross = _minutes(end - start)
        open_since = None
        for at, record in moves:
            if at < start or at > end:
                continue
            if record.get("new") == "blocked":
                open_since = at
            elif open_since is not None:
                blocked_intervals.append((open_since, at))
                open_since = None
        if open_since is not None:
            blocked_intervals.append((open_since, end))
        blocked = sum(_minutes(b - a)
                      for a, b in blocked_intervals)
        net = gross - blocked
    editors = []
    worktrees = []
    if todo.get("worktree"):
        worktrees.append(todo["worktree"])
    for record in transitions_in(todo.get("body") or ""):
        actor = record.get("actor")
        if actor and actor != record.get("verb") \
                and actor not in editors:
            editors.append(actor)
        wt = record.get("worktree")
        if wt and wt not in worktrees:
            worktrees.append(wt)
    span_records = [r for at, r in moves
                    if start is not None and end is not None
                    and start <= at <= end]
    return {
        "id": todo.get("id"),
        "title": todo.get("title"),
        "est": est_minutes(todo.get("est")),
        "start": start,
        "end": end,
        "gross": gross,
        "blocked": blocked,
        "net": net,
        "blocked_intervals": blocked_intervals,
        "open": start is not None and end is None,
        "editors": editors,
        "worktrees": worktrees,
        "backfilled": _marked(span_records),
    }


def _merge_intervals(intervals):
    """Overlapping (start, end) pairs merged, so a
    union measure counts shared time once."""
    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            if b > merged[-1][1]:
                merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def _step_position(block, items):
    if block and block.get("position") in _POSITIONS:
        return block["position"]
    minted = {t.get("fanout_position") for t in items}
    minted.discard(None)
    if len(minted) == 1:
        return minted.pop()
    return None


def step_timing(block, title, items):
    """One plan step: its wb-step block (or None), its
    title, and its parsed todos → the step's figures,
    with per-item figures for the todos that carry
    their own est (the only item grain the records
    declare — no enumeration grammar exists to read
    finer)."""
    figures = [todo_timing(t) for t in items]
    est = est_minutes(block.get("est")) if block else None
    closed = [f for f in figures if f["gross"] is not None]
    gross = blocked = net = None
    if closed:
        start = min(f["start"] for f in closed)
        end = max(f["end"] for f in closed)
        gross = _minutes(end - start)
        intervals = []
        for f in closed:
            intervals.extend(f["blocked_intervals"])
        blocked = sum(_minutes(b - a) for a, b in
                      _merge_intervals(intervals))
        net = gross - blocked
    editors = []
    worktrees = []
    for f in figures:
        for name in f["editors"]:
            if name not in editors:
                editors.append(name)
        for wt in f["worktrees"]:
            if wt not in worktrees:
                worktrees.append(wt)
    return {
        "step": block["step"] if block else
            (items[0].get("plan_step") if items else None),
        "title": title,
        "est": est,
        "position": _step_position(block, items),
        "gross": gross,
        "blocked": blocked,
        "net": net,
        "editors": editors,
        "worktrees": worktrees,
        "items": [f for f in figures
                  if f["est"] is not None],
        "todos": len(figures),
        "measured": len(closed),
        "open": sum(1 for f in figures if f["open"]),
        "backfilled": sorted({s for f in closed
                              for s in f["backfilled"]}),
    }


def _closing_est(step_doc):
    """A parsed step's closing est: line → minutes,
    the fallback surface when its block declares no
    est= (the two surfaces plan-check keeps in
    agreement)."""
    if step_doc is None:
        return None
    for line in (step_doc.get("body") or "").splitlines():
        m = _EST_LINE_RE.match(line)
        if m:
            return est_minutes(m.group(1))
    return None


def plan_timing(plans_dir, bundle_ref):
    """One bundle's timing report, as data: the plan's
    steps in declared order (blocks joined to the
    bundle's todos by plan_step), the ruled wall-clock
    and the serial sum for estimate and actual, and
    the counts of what the record does not measure.
    Raises ValueError naming the ref when no bundle
    matches."""
    plans_dir = Path(plans_dir)
    bundle = None
    for candidate in list_bundles(plans_dir):
        if bundle_ref in (candidate["id"],
                          candidate["slug"]):
            bundle = candidate
            break
    if bundle is None:
        raise ValueError(f"unknown bundle: {bundle_ref!r}")
    plan_text = ""
    plan_path = None
    if bundle["kind"] == "bundle":
        candidate = plans_dir / bundle["path"] / "plan.md"
        if candidate.is_file():
            plan_path = candidate
    elif bundle.get("plan"):
        candidate = plans_dir / bundle["path"]
        if candidate.is_file():
            plan_path = candidate
    if plan_path is not None:
        plan_text = plan_path.read_text(encoding="utf-8")
    blocks = {b["step"]: b
              for b in extract_step_blocks(plan_text)}
    doc = parse_plan(plan_text) if plan_text else \
        {"steps": [], "title": ""}
    titles = {s["n"]: s["title"] for s in doc["steps"]}
    step_docs = {s["n"]: s for s in doc["steps"]}
    by_step = {}
    unstepped = []
    for todo in bundle["todos"]:
        if todo.get("plan_step") is None:
            unstepped.append(todo.get("id"))
        else:
            by_step.setdefault(todo["plan_step"],
                               []).append(todo)
    steps = []
    for number in sorted(set(blocks) | set(by_step)):
        block = blocks.get(number)
        figures = step_timing(
            block, titles.get(number), by_step.get(number, []))
        if figures["est"] is None:
            figures["est"] = _closing_est(
                step_docs.get(number))
        steps.append(figures)
    return {
        "bundle": bundle["id"],
        "title": doc["title"] or bundle["id"],
        "steps": steps,
        "wall_est": _wall_clock(steps, "est"),
        "wall_actual": _wall_clock(steps, "gross"),
        "unstepped": unstepped,
    }


def _wall_clock(steps, key):
    """The ruled wall-clock over one figure (est or
    gross): serial-band sum + longest branch + fan-in
    sum, beside the plain serial sum of every step.
    Steps without the figure are excluded from both
    and counted — the sums are over measured steps,
    never silently completed with zeros."""
    bands = {"serial": [], "branch": [], "fan-in": []}
    unmeasured = 0
    for step in steps:
        value = step[key]
        if value is None:
            unmeasured += 1
            continue
        band = step["position"] \
            if step["position"] in bands else "serial"
        bands[band].append(value)
    ruled = sum(bands["serial"]) + sum(bands["fan-in"])
    if bands["branch"]:
        ruled += max(bands["branch"])
    return {
        "ruled": ruled if steps and unmeasured < len(steps)
            else None,
        "serial_sum": sum(sum(v) for v in bands.values())
            if steps and unmeasured < len(steps) else None,
        "unmeasured": unmeasured,
    }


def _overlapped(figures):
    """True when a step's measured items ran
    concurrently: their gross spans sum past the
    step's own span, which serial work cannot do."""
    closed = [f for f in figures if f["gross"] is not None]
    if len(closed) < 2:
        return False
    span = _minutes(max(f["end"] for f in closed)
                    - min(f["start"] for f in closed))
    return sum(f["gross"] for f in closed) > span


def price_book(plans_dir):
    """The ledger's price book over one project's
    plans, as data: per kind (the grouping rule in
    the module docstring), the distribution of
    actual-vs-estimate over priced, measured todos;
    and the two lazy shapes, flagged where they
    occur — PRICED_AS_SERIAL_SUM per step,
    FAR_UNDER per kind."""
    plans_dir = Path(plans_dir)
    kinds = {}
    serial_priced = []
    unmeasured = 0
    for bundle in list_bundles(plans_dir):
        by_step = {}
        for todo in bundle["todos"]:
            figures = todo_timing(todo)
            if todo.get("plan_step") is not None:
                by_step.setdefault(todo["plan_step"],
                                   []).append(figures)
            if figures["gross"] is None \
                    or not figures["est"]:
                # Unpriced, unmeasured, or priced at
                # zero (no ratio exists): excluded
                # from the distributions; a priced
                # item is counted, never faked.
                if figures["est"] is not None:
                    unmeasured += 1
                continue
            kind = todo.get("fanout_position") or "undeclared"
            kinds.setdefault(kind, []).append({
                "id": todo.get("id"),
                "bundle": bundle["id"],
                "est": figures["est"],
                "actual": figures["gross"],
                "ratio": figures["gross"] / figures["est"],
            })
        if bundle["kind"] != "bundle":
            continue
        plan_path = plans_dir / bundle["path"] / "plan.md"
        if not plan_path.is_file():
            continue
        blocks = {b["step"]: b for b in extract_step_blocks(
            plan_path.read_text(encoding="utf-8"))}
        for number, figures in by_step.items():
            block = blocks.get(number)
            if block is None:
                continue
            step = step_timing(block, None,
                               [t for t in bundle["todos"]
                                if t.get("plan_step") == number])
            if step["position"] != "branch" \
                    or step["est"] is None:
                continue
            priced = [f for f in figures
                      if f["est"] is not None]
            if len(priced) < 2 or not _overlapped(figures):
                continue
            item_sum = sum(f["est"] for f in priced)
            if item_sum and abs(step["est"] - item_sum) \
                    <= SERIAL_SUM_TOLERANCE * item_sum:
                serial_priced.append({
                    "bundle": bundle["id"],
                    "step": number,
                    "est": step["est"],
                    "items_est": item_sum,
                })
    book = {}
    for kind, items in sorted(kinds.items()):
        ratios = sorted(i["ratio"] for i in items)
        book[kind] = {
            "items": items,
            "count": len(items),
            "est": sum(i["est"] for i in items),
            "actual": sum(i["actual"] for i in items),
            "median_ratio": ratios[len(ratios) // 2]
                if len(ratios) % 2 else
                (ratios[len(ratios) // 2 - 1]
                 + ratios[len(ratios) // 2]) / 2,
            "min_ratio": ratios[0],
            "max_ratio": ratios[-1],
            "far_under": len(items) >= FAR_UNDER_MIN_ITEMS
                and all(i["ratio"] <= FAR_UNDER_RATIO
                        for i in items),
        }
    return {
        "kinds": book,
        "priced_as_serial_sum": serial_priced,
        "unmeasured_priced": unmeasured,
        "far_under_ratio": FAR_UNDER_RATIO,
        "far_under_min_items": FAR_UNDER_MIN_ITEMS,
    }


def _figures_text(figures):
    """One line's figures: est / gross / blocked /
    net, each absent as — when the record holds
    none."""
    return (f"est {fmt_minutes(figures['est'])}  "
            f"actual {fmt_minutes(figures['gross'])}  "
            f"blocked {fmt_minutes(figures['blocked'])}  "
            f"net {fmt_minutes(figures['net'])}")


def render_plan(report):
    """One plan's timing report as terminal text:
    per step the figures, position, editors, and
    worktree; per item (a step's est-carrying todos)
    the same figures; then the ruled wall-clock
    beside the serial sum, for estimate and actual.
    Unmeasured steps render as absence and are
    counted in the summary — never zeroed."""
    lines = [f"timing: {report['bundle']} — "
             f"{report['title']}"]
    for step in report["steps"]:
        head = f"step {step['step']}"
        if step["title"]:
            head += f" — {step['title']}"
        lines.append(head)
        detail = "  " + _figures_text(step)
        detail += f"  position {step['position'] or '—'}"
        if step["editors"]:
            detail += "  editors " + ", ".join(
                step["editors"])
        if step["worktrees"]:
            detail += "  worktree " + ", ".join(
                step["worktrees"])
        if step["backfilled"]:
            detail += "  [backfilled: " + ", ".join(
                step["backfilled"]) + "]"
        lines.append(detail)
        if step["todos"] and not step["measured"]:
            lines.append(
                "  no measured span — the step's todos "
                "carry no doing→done record (honest "
                "absence)")
        elif step["measured"] < step["todos"]:
            lines.append(
                f"  measured over {step['measured']} of "
                f"{step['todos']} todos"
                + (f"; {step['open']} still open"
                   if step["open"] else ""))
        for item in step["items"]:
            line = (f"  item {item['id']}  "
                    + _figures_text(item))
            if item["backfilled"]:
                line += "  [backfilled: " + ", ".join(
                    item["backfilled"]) + "]"
            lines.append(line)
    for label, wall in (("est", report["wall_est"]),
                        ("actual", report["wall_actual"])):
        lines.append(
            f"wall-clock ({label}): ruled "
            f"{fmt_minutes(wall['ruled'])}  "
            f"serial sum {fmt_minutes(wall['serial_sum'])}"
            + (f"  ({wall['unmeasured']} step(s) without "
               f"a figure, excluded)"
               if wall["unmeasured"] else ""))
    if report["unstepped"]:
        lines.append(
            "todos with no plan step (outside the step "
            "figures): " + ", ".join(
                str(t) for t in report["unstepped"]))
    return "\n".join(lines)


def render_book(book):
    """The price book as terminal text: per kind the
    recorded distribution, the far-under flag with
    its stated threshold, and the steps priced as a
    serial sum of overlapped items."""
    lines = ["price book: priced, measured todos by "
             "kind (kind = minted fan-out position)"]
    if not book["kinds"]:
        lines.append(
            "  no priced, measured items recorded yet "
            "(honest absence)")
    for kind, data in book["kinds"].items():
        lines.append(
            f"kind {kind}: {data['count']} item(s)  "
            f"est {fmt_minutes(data['est'])}  "
            f"actual {fmt_minutes(data['actual'])}  "
            f"median ratio {data['median_ratio']:.2f}  "
            f"range {data['min_ratio']:.2f}–"
            f"{data['max_ratio']:.2f}")
        if data["far_under"]:
            lines.append(
                f"  FAR-UNDER: every one of the "
                f"{data['count']} items landed at or "
                f"under {book['far_under_ratio']:.2f} of "
                f"its price (flag threshold: "
                f">= {book['far_under_min_items']} items, "
                f"all <= {book['far_under_ratio']:.2f})")
            for item in data["items"]:
                lines.append(
                    f"    {item['id']} ({item['bundle']})"
                    f"  est {fmt_minutes(item['est'])}  "
                    f"actual {fmt_minutes(item['actual'])}")
    for flag in book["priced_as_serial_sum"]:
        lines.append(
            f"PRICED-AS-SERIAL-SUM: {flag['bundle']} "
            f"step {flag['step']} — est "
            f"{fmt_minutes(flag['est'])} matches the sum "
            f"of its items' ests "
            f"({fmt_minutes(flag['items_est'])}), and the "
            f"record shows the items overlapped")
    if book["unmeasured_priced"]:
        lines.append(
            f"priced items with no measured span: "
            f"{book['unmeasured_priced']} (excluded from "
            f"the distributions)")
    return "\n".join(lines)
