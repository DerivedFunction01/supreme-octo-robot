"""wb plan-check: the plan-syntax gate over one plan
file (coding_plan skill: a plan is unfinished until
`wb plan-check` passes on it).

The check is a composition, not a second grammar:
the document, its steps, its wb-step blocks, and its
wb-question sentinels all come from lib/plans/parser;
the Status/filing agreement is lib/plans/bundles'
closeout rule; the estimate surfaces are read the
doctor's estimate family reads them (the block's
est= is the machine form of the closing est: line —
doctor_estimates._step_estimate's semantics, re-read
here over the parser's step raw because the
evaluation package sits downstream of lib); a
prerequisite resolves the way the check verbs
resolve a todo id — in the plan's own project store
(lib/plans/bundles' todo read over the plan's .plans
dir), extended to the sibling plans the skill names
("todo ids anywhere under the same goal, this plan's
steps or a sibling plan's"). No registry beyond the
project's own files is invented: an edge that
resolves nowhere in that scope is refused as
dangling or cross-goal, named as such.

Refusals, one finding each: no Status header; a
Status/filing contradiction; no steps at all; a
prose-only step (no wb-step sentinel); a sentinel
with no requires= field (undeclared prerequisites —
the field must be present, empty allowed); a
sentinel carrying neither fanout= nor serial=, or
both; a step missing a closing files: / verify: /
done when: / est: line; a sentinel with no est=, or
whose est= disagrees with the closing est: line; a
prerequisite no step in the plan mints and nothing
in the project resolves; a cycle in the requires
graph; a wb-step block naming no parsed step, or a
second block for one step; a broken wb-question
sentinel (the parser's sentinel_errors, verbatim);
an owner-ruling question whose sentinel carries no
recommended field. A question with no sentinel is
not a finding — agent-settleable questions carry
none, per the skill.

On a pass, the frontier adoption will arm: the steps
no in-plan prerequisite holds back (their requires
are empty or resolve outside this plan's minting),
in step order — the adoption-time read of the
frontier reader's eligibility rule (a step is
eligible when every prerequisite reads done; at
adoption, only this plan's own minting can be
undone).
"""

import re
from pathlib import Path

from .bundles import _closeout_error, all_todo_ids
from .parser import (extract_step_blocks,
                     first_duration_minutes, parse_plan)

_EST_LINE_RE = re.compile(r"^\s*est:\s*(.*)$")


def _closing_est(step):
    """The step's closing est: line value (the last
    one in its raw), or None when the step carries
    none — the doctor estimate family's read, over
    the step's raw lines so the line is found
    wherever the closing labels sit."""
    value = None
    for line in step["raw"].splitlines():
        m = _EST_LINE_RE.match(line)
        if m:
            value = m.group(1).strip()
    return value


def _est_agrees(block_est, line_est):
    """Whether the sentinel's est= and the closing
    est: line state the same estimate: equal as
    durations when both carry one (30m == 0.5h),
    equal as text when neither does."""
    block_minutes = first_duration_minutes(block_est)
    line_minutes = first_duration_minutes(line_est)
    if block_minutes is not None and line_minutes is not None:
        return block_minutes == line_minutes
    if (block_minutes is None) != (line_minutes is None):
        return False
    return (block_est or "").strip() == (line_est or "").strip()


def _find_cycle(deps):
    """One cycle in the todo -> prerequisites graph,
    as a path [a, b, ..., a], or None. Deterministic:
    nodes and edges are visited in sorted order."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {node: WHITE for node in deps}
    path = []

    def visit(node):
        color[node] = GREY
        path.append(node)
        for nxt in sorted(deps.get(node, ())):
            if nxt not in color:
                continue
            if color[nxt] == GREY:
                return path[path.index(nxt):] + [nxt]
            if color[nxt] == WHITE:
                found = visit(nxt)
                if found is not None:
                    return found
        path.pop()
        color[node] = BLACK
        return None

    for node in sorted(deps):
        if color[node] == WHITE:
            found = visit(node)
            if found is not None:
                return found
    return None


def check_plan(text, *, name="", plans_dir=None,
               archived=False, self_rel=None):
    """One plan file's text -> {findings, frontier}.
    `plans_dir` (the plan's .plans dir) scopes the
    prerequisite resolution: sibling plans' minted
    todos plus the project's bundle todo store.
    `archived` is the filing fact the closeout rule
    reads (the file lives under finished/).
    `self_rel` names the checked plan inside
    plans_dir so it is not read again as a sibling."""
    findings = []
    doc = parse_plan(text, path=name)
    blocks = extract_step_blocks(text)
    blocks_by_step = {}
    for block in blocks:
        blocks_by_step.setdefault(block["step"], []).append(block)

    if doc["status_raw"] is None:
        findings.append(
            "header: no Status field — a plan declares "
            "its Status in its header fields")
    else:
        closeout = _closeout_error(doc["status_raw"], archived)
        if closeout is not None:
            findings.append(f"header: {closeout}")

    steps = doc["steps"]
    if not steps:
        findings.append(
            "steps: no steps declared — the plan arms "
            "nothing for adoption to arm")

    step_numbers = {s["n"] for s in steps}
    for number, group in sorted(blocks_by_step.items()):
        if number not in step_numbers:
            findings.append(
                f"step {number}: a wb-step block names "
                f"no step in the plan's Steps section")
        elif len(group) > 1:
            findings.append(
                f"step {number}: {len(group)} wb-step "
                f"blocks for one step — exactly one "
                f"sentinel per step")

    minted = {}
    for block in blocks:
        for todo in block["todos"]:
            minted.setdefault(todo, block["step"])

    external = set()
    if plans_dir is not None:
        plans_dir = Path(plans_dir)
        sibling_files = sorted(plans_dir.glob("*.md"))
        finished = plans_dir / "finished"
        if finished.is_dir():
            sibling_files += sorted(finished.glob("*.md"))
        for sibling in sibling_files:
            if self_rel is not None \
                    and sibling == Path(plans_dir) / self_rel:
                continue
            try:
                sibling_text = sibling.read_text(
                    encoding="utf-8")
            except OSError:
                continue
            for block in extract_step_blocks(sibling_text):
                external.update(block["todos"])
        try:
            external.update(all_todo_ids(plans_dir))
        except Exception:
            # A plans dir with no readable bundle store
            # resolves through its sibling plans alone;
            # the store is one resolution source, not
            # the gate's precondition.
            pass
    external -= set(minted)

    for step in steps:
        n = step["n"]
        title = step["title"]
        group = blocks_by_step.get(n, [])
        block = group[0] if len(group) == 1 else None
        if block is None:
            if not group:
                findings.append(
                    f"step {n} ({title}): prose-only "
                    f"step — no wb-step sentinel block; "
                    f"a step's prerequisites, estimate, "
                    f"and fan-out are declared in its "
                    f"block, never left to prose")
            continue
        if not block["requires_present"]:
            findings.append(
                f"step {n} ({title}): undeclared "
                f"prerequisites — the wb-step block "
                f"carries no requires= field (the field "
                f"is always present; an empty value "
                f"declares none)")
        fanout = block["fanout"]
        serial = block["serial"]
        has_fanout = fanout is not None and fanout.strip() != ""
        has_serial = serial is not None and serial.strip() != ""
        if has_fanout and has_serial:
            findings.append(
                f"step {n} ({title}): the wb-step block "
                f"carries both fanout= and serial= — "
                f"exactly one: a fan-out split, or the "
                f"named shared file or state that forces "
                f"the step serial")
        elif not has_fanout and not has_serial:
            findings.append(
                f"step {n} ({title}): the wb-step block "
                f"carries neither fanout= nor serial= — "
                f"every step declares its lane split or "
                f"names what forces it serial")
        for key, label in (("files", "files:"),
                           ("verify", "verify:"),
                           ("done_when", "done when:")):
            if not step[key].strip():
                findings.append(
                    f"step {n} ({title}): missing "
                    f"closing {label} line")
        line_est = _closing_est(step)
        if line_est is None:
            findings.append(
                f"step {n} ({title}): missing closing "
                f"est: line")
        if block["est"] is None:
            findings.append(
                f"step {n} ({title}): the wb-step "
                f"block declares no est= — the machine "
                f"form of the closing est: line")
        elif line_est is not None \
                and not _est_agrees(block["est"], line_est):
            findings.append(
                f"step {n} ({title}): estimate "
                f"disagreement — the wb-step block "
                f"declares est={block['est']} but the "
                f"closing line reads est: {line_est}")

    for block in blocks:
        for req in block["requires"]:
            if req in minted or req in external:
                continue
            findings.append(
                f"step {block['step']}: prerequisite "
                f"{req!r} is minted by no step in this "
                f"plan and resolves nowhere in the "
                f"plan's project (sibling plans, the "
                f"bundle todo store) — a dangling edge, "
                f"or a cross-goal edge the harness has "
                f"no registry to resolve; either is "
                f"refused, never guessed")

    deps = {}
    for block in blocks:
        for todo in block["todos"]:
            deps.setdefault(todo, set()).update(
                r for r in block["requires"] if r in minted)
    cycle = _find_cycle(deps)
    if cycle is not None:
        findings.append(
            "requires cycle: " + " -> ".join(cycle))

    for err in doc["sentinel_errors"]:
        subject = f"question sentinel (line {err['line']}"
        if err.get("id"):
            subject += f", id {err['id']}"
        findings.append(f"{subject}): {err['reason']}")
    for question in doc["questions"]:
        if question["recommended"] is None:
            findings.append(
                f"question {question['id']!r}: the "
                f"wb-question sentinel carries no "
                f"recommended field — an owner-ruling "
                f"question states its recommendation")

    frontier = []
    if not findings:
        for step in steps:
            group = blocks_by_step.get(step["n"], [])
            if len(group) != 1:
                continue
            block = group[0]
            if any(r in minted for r in block["requires"]):
                continue
            frontier.append({
                "step": step["n"],
                "todos": list(block["todos"]),
                "serial": block["serial"] is not None
                and block["serial"].strip() != "",
            })
    return {"findings": findings, "frontier": frontier,
            "doc": doc}


def check_plan_file(path):
    """check_plan over a plan file on disk: the
    filing fact is its parent dir's name, and the
    resolution scope is the .plans dir it lives in
    (its parent, or its grandparent when filed under
    finished/)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    archived = path.parent.name == "finished"
    plans_dir = path.parent.parent if archived \
        else path.parent
    return check_plan(
        text, name=path.name, plans_dir=plans_dir,
        archived=archived,
        self_rel=path.relative_to(plans_dir))
