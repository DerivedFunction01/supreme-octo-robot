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

The formation class (wall-clock discipline): a step
or the plan's Rulings section declaring a worktree
or branch per row, item, or lane (a fan-out whose
lanes are rows of one surface, each with its own
formation), or a gate fire per item where the queue
trigger applies, is refused, the finding naming the
bound it breaks — worktrees are bounded per
formation group, and several items waiting for
tests merge into one union gated once. The class
reads only declarations: the step bodies, the
fan-out values, and the Rulings section. A sentence
carrying a negation or prohibition (never, not, no,
banned, refused, prohibited, avoid) declares the
bound, not the anti-pattern, and makes no finding —
the corpus's own rulings state the bound in those
words.

The headline rule (supervision rules, estimates
passage): a plan's duration is its wall-clock — the
critical path through its steps under their
declared fan-out, never the serial sum of its step
estimates. A plan states a total for itself in its
header fields (the grammar's field form — the
header is where a plan states facts about itself:
Status, Executor, Goal): a Total / Est / Estimate /
Duration / Wall-clock field whose value carries a
duration. When the stated figure exceeds the
computed critical path — the longest path over the
in-plan requires graph with every step at its est=
(a fan-out step's est= is already its longest
lane's wall-clock, per the skill) — the plan is
refused, the finding naming the stated figure, the
critical path, and its chain. A plan stating no
total makes no headline finding. The migration
edit-cap from the same passage is NOT enforced
here: no machine-readable declaration names a
phase migration-class anywhere in the grammar or
the corpus (the one specimen plan declares it in
Rulings prose alone), so there is nothing for a
check to read until the grammar grows one.

On a pass, the frontier adoption will arm: the steps
no in-plan prerequisite holds back (their requires
are empty or resolve outside this plan's minting),
in step order — the adoption-time read of the
frontier reader's eligibility rule (a step is
eligible when every prerequisite reads done; at
adoption, only this plan's own minting can be
undone). The computed critical path (value and
chain) is reported alongside it.
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


# The formation class's declaration shapes: a
# formation noun (worktree / branch) or a gate bound
# to a per-unit construction. Both directions of the
# construction are shapes: "worktree per row" and
# "per-row worktree", "one gate per item" and
# "each row its own worktree".
_FORMATION_DECL_RES = (
    (re.compile(
        r"\b(?:worktrees?|branch(?:es)?)\s+per\s+[\w-]+"
        r"|\bper[-\s](?:row|item|lane|family)[-\s]"
        r"(?:worktrees?|branch(?:es)?)\b"
        r"|\b(?:one|a|an|each|every)\s+(?:worktree|branch)"
        r"\s+(?:per|for\s+each|for\s+every)\b"
        r"|\beach\s+(?:row|item|lane)\s+(?:gets|has)\s+"
        r"(?:its\s+own|a\s+separate)\s+(?:worktree|branch)\b"),
     "formation"),
    (re.compile(
        r"\bgates?\s+per\s+[\w-]+"
        r"|\bper[-\s](?:row|item)[-\s]gates?\b"
        r"|\b(?:one|a|an|each|every)\s+gate\s+"
        r"(?:per|for\s+each|for\s+every)\b"),
     "gate"),
)

_NEGATION_RE = re.compile(
    r"\b(?:never|not|no|banned|refused|prohibited|"
    r"avoid|forbidden)\b")


def _formation_findings(text):
    """The formation-class declarations in one text
    (a step body, a fan-out value, the Rulings
    section): [(kind, matched text)], one per
    sentence carrying a declaration shape and no
    negation. Sentences split on terminal punctuation
    and newlines; a declaration inside a prohibition
    states the bound and is skipped."""
    found = []
    for sentence in re.split(r"[.!?\n]+", text):
        if _NEGATION_RE.search(sentence.lower()):
            continue
        for pattern, kind in _FORMATION_DECL_RES:
            m = pattern.search(sentence.lower())
            if m:
                found.append((kind, m.group(0)))
    return found


def format_minutes(minutes):
    """A duration in minutes, in the corpus's own
    forms: 45m under an hour, 2h on the hour,
    1h30m between."""
    if minutes < 60:
        return f"{minutes:g}m"
    hours = int(minutes // 60)
    rem = minutes - hours * 60
    if rem == 0:
        return f"{hours}h"
    return f"{hours}h{rem:g}m"


# The header keys a plan states its own total under,
# normalized (lower-cased, _ and - read as spaces) —
# the stated-total form the headline rule reads.
_TOTAL_KEYS = {"total", "total est", "total estimate",
               "est", "estimate", "duration",
               "wall clock"}


def _stated_total(doc):
    """The plan's stated total: (key, raw value,
    minutes) from the first header field naming one,
    or None when the header states none. Minutes is
    None when the value carries no duration token —
    an unparseable statement makes no finding."""
    for key, value in doc["fields"].items():
        normalized = key.strip().lower() \
            .replace("_", " ").replace("-", " ")
        if normalized in _TOTAL_KEYS:
            return (key, value.strip(),
                    first_duration_minutes(value))
    return None


def _critical_path(steps, blocks_by_step, minted):
    """The plan's wall-clock: the longest path over
    the in-plan requires graph with every step at
    its est=, as {minutes, serial_sum, chain} with
    the chain's steps in path order ({step, todos,
    minutes} each). None when the path is not
    computable — a step with no single block, or an
    est= carrying no duration: the plan's other
    findings already refuse it, and a wall-clock is
    never guessed. The caller guarantees the graph
    is acyclic (the cycle finding stands in its
    place). Deterministic: predecessors are visited
    in step order and a tie keeps the earlier step."""
    per_step = {}
    for step in steps:
        group = blocks_by_step.get(step["n"], [])
        if len(group) != 1:
            return None
        block = group[0]
        if block["est"] is None:
            return None
        minutes = first_duration_minutes(block["est"])
        if minutes is None:
            return None
        preds = sorted(
            {minted[r] for r in block["requires"]
             if r in minted and minted[r] != step["n"]})
        per_step[step["n"]] = {
            "minutes": minutes,
            "todos": list(block["todos"]),
            "preds": preds}
    best = {}

    def solve(n):
        if n in best:
            return best[n]
        info = per_step[n]
        chosen = None
        for pred in info["preds"]:
            if pred not in per_step:
                # A block naming no parsed step mints
                # the todo; that block is its own
                # finding and carries no path weight.
                continue
            total, _chain = solve(pred)
            if chosen is None or total > chosen[0]:
                chosen = (total, pred)
        if chosen is None:
            best[n] = (info["minutes"], [n])
        else:
            total, chain = solve(chosen[1])
            best[n] = (total + info["minutes"],
                       chain + [n])
        return best[n]

    winner = None
    for step in steps:
        total, chain = solve(step["n"])
        if winner is None or total > winner[0]:
            winner = (total, chain)
    total, chain = winner
    return {
        "minutes": total,
        "serial_sum": sum(i["minutes"]
                          for i in per_step.values()),
        "chain": [{"step": n,
                   "todos": per_step[n]["todos"],
                   "minutes": per_step[n]["minutes"]}
                  for n in chain]}


def _chain_text(chain):
    """A critical-path chain as text: each step named
    by the todos it mints, at its est — the steps'
    identities in this grammar."""
    return " -> ".join(
        f"{'|'.join(e['todos'])} "
        f"({format_minutes(e['minutes'])})"
        for e in chain)


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
    """One plan file's text -> {findings, frontier,
    critical_path}. `plans_dir` (the plan's .plans
    dir) scopes the
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

    for step in steps:
        declared = _formation_findings(step["raw"])
        group = blocks_by_step.get(step["n"], [])
        if len(group) == 1 and group[0]["fanout"]:
            declared += _formation_findings(
                group[0]["fanout"])
        for kind, matched in declared:
            if kind == "formation":
                findings.append(
                    f"step {step['n']} ({step['title']}): "
                    f"per-row formation declared "
                    f"({matched!r}) — worktrees are "
                    f"bounded per formation group, never "
                    f"per row; grouped changes share one "
                    f"worktree and branch")
            else:
                findings.append(
                    f"step {step['n']} ({step['title']}): "
                    f"per-item gate declared "
                    f"({matched!r}) — the queue trigger "
                    f"applies: several items waiting for "
                    f"tests merge into one union gated "
                    f"once")
    for section in doc["sections"]:
        if section["heading"].strip().lower() != "rulings":
            continue
        for kind, matched in _formation_findings(
                section["raw"]):
            if kind == "formation":
                findings.append(
                    f"rulings: per-row formation "
                    f"declared ({matched!r}) — worktrees "
                    f"are bounded per formation group, "
                    f"never per row; grouped changes "
                    f"share one worktree and branch")
            else:
                findings.append(
                    f"rulings: per-item gate declared "
                    f"({matched!r}) — the queue trigger "
                    f"applies: several items waiting for "
                    f"tests merge into one union gated "
                    f"once")

    critical = None
    if cycle is None:
        critical = _critical_path(steps, blocks_by_step,
                                  minted)
    if critical is not None:
        stated = _stated_total(doc)
        if stated is not None:
            key, raw, stated_minutes = stated
            if stated_minutes is not None \
                    and stated_minutes > critical["minutes"]:
                findings.append(
                    f"headline: the plan states a "
                    f"total of "
                    f"{format_minutes(stated_minutes)} "
                    f"({key}: {raw}) but its wall-clock "
                    f"— the critical path through its "
                    f"steps under their declared "
                    f"prerequisites — is "
                    f"{format_minutes(critical['minutes'])} "
                    f"({_chain_text(critical['chain'])}); "
                    f"a plan's stated duration is its "
                    f"wall-clock, never the serial sum "
                    f"of its step estimates (serial sum: "
                    f"{format_minutes(critical['serial_sum'])})")

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
            "critical_path": critical, "doc": doc}


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
