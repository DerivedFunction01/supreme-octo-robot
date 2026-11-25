"""wb doctor, plan-estimate family: the plan
grammar's estimate discipline over one plan file.

Split from doctor.py along its family seam (the repo
line cap): the doctor's plan-todo family calls
plan_estimate_findings with its own finding
constructor, so the finding shape stays the doctor's
one home. The threshold and the long-duration class
set are the plan parser's data (lib/plans/parser),
the synced mirror of the starter estimate scanner's
— not a second copy here.
"""

import re

from lib.plans.parser import (
    ESTIMATE_OVERRUN_MINUTES, extract_step_blocks,
    first_duration_minutes, names_long_duration_class,
    parse_plan)


# The plan grammar's estimate discipline, in the
# starter estimate scanner's semantics: a step's
# estimate is its step block's est= (the machine form)
# or its closing est: line; past the overrun threshold
# the estimate carries a justification (at least
# JUSTIFICATION_WORDS words of prose) and the
# justification names one of the closed long-duration
# classes. The threshold and the class set are the
# grammar's data (lib/plans/parser), the synced mirror
# of the scanner's — not a second copy here.
JUSTIFICATION_WORDS = 3
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_EST_LINE_RE = re.compile(r"^\s*est:\s*(.*)$")
_DURATION_LEAD_RE = re.compile(
    r"^[\s,+]*(?:\d+(?:\.\d+)?\s*"
    r"(?:hours?|hrs?|h|minutes?|mins?|m)(?![A-Za-z])"
    r"[\s,+]*)+")


def _step_prose(step):
    """A parsed step's body prose with its wb-step
    sentinel removed: the justification the grammar
    asks for is body prose, never a sentinel field.
    The step's own anchor line (its heading or item
    line, the body bucket's first line) is not prose
    and is dropped."""
    lines = []
    in_sentinel = False
    for line in step["body"].splitlines()[1:]:
        if "<!--" in line and "wb-step" in line:
            in_sentinel = True
        if in_sentinel:
            if "-->" in line:
                in_sentinel = False
            continue
        lines.append(line)
    return "\n".join(lines)


def _step_estimate(step, block):
    """A step's declared estimate surfaces, in order:
    (the est= value, the closing est: line's value) —
    either may be None. The block's est= is the machine
    form; the closing line is the step's own statement
    of the same estimate."""
    est_value = block["est"] if block else None
    line_value = None
    for line in step["body"].splitlines():
        m = _EST_LINE_RE.match(line)
        if m:
            line_value = m.group(1)
    return est_value, line_value


def _justification_text(step):
    """A step's justification prose: its body prose
    (sentinel removed) with the closing est: line
    reduced to its post-duration remainder — a bare
    `est: 2h` line justifies nothing; the words after
    its durations, and the body's own prose, are the
    justification."""
    out = []
    for line in _step_prose(step).splitlines():
        m = _EST_LINE_RE.match(line)
        if m:
            rest = _DURATION_LEAD_RE.sub("", m.group(1))
            out.append(rest.strip(" \t—–-:"))
        else:
            out.append(line)
    return "\n".join(out)


def plan_estimate_findings(slug, plan, plans_dir, finding):
    """One plan summary → its plan-estimate findings.
    Shared by flat plans and bundle plan.md files, on
    the same plan-file scope as _plan_status_finding.
    Steps, header fields, and the step blocks all
    derive from the plan parser — the same blocks the
    frontier reader arms from, read lib-side here."""
    text = (plans_dir / plan["path"]).read_text(
        encoding="utf-8")
    doc = parse_plan(text, path=plan["path"])
    blocks = {b["step"]: b
              for b in extract_step_blocks(text)}
    out = []
    for step in doc["steps"]:
        n = step["n"]
        subject = f"{plan['path']} step {n}"
        block = blocks.get(n)
        est_value, line_value = _step_estimate(step, block)
        declared = [v for v in (est_value, line_value)
                    if v is not None]
        if not declared:
            out.append(finding(
                slug, "plan-estimate", subject,
                f"step {n} ({step['title']}) carries no "
                f"estimate — every step or entry "
                f"carries an estimate at the scale the "
                f"work runs; plain code edits are "
                f"normally minutes, many under five"))
            continue
        minutes = None
        for value in declared:
            minutes = first_duration_minutes(value)
            if minutes is not None:
                break
        if minutes is None:
            out.append(finding(
                slug, "plan-estimate", subject,
                f"step {n} estimate {declared[0]!r} "
                f"carries no duration — an estimate "
                f"states its duration (<n>m / <n>h) at "
                f"the scale the work runs"))
            continue
        if minutes > ESTIMATE_OVERRUN_MINUTES:
            justification = _justification_text(step)
            words = len(_WORD_RE.findall(justification))
            if words < JUSTIFICATION_WORDS:
                out.append(finding(
                    slug, "plan-estimate", subject,
                    f"step {n} estimate "
                    f"{declared[0]} runs past the "
                    f"overrun threshold "
                    f"({ESTIMATE_OVERRUN_MINUTES} "
                    f"minutes) with no justification — "
                    f"an over-threshold estimate states "
                    f"why it takes that long and why "
                    f"the estimate should not be lower"))
            elif not names_long_duration_class(
                    justification):
                out.append(finding(
                    slug, "plan-estimate", subject,
                    f"step {n} estimate "
                    f"{declared[0]} runs past the "
                    f"overrun threshold "
                    f"({ESTIMATE_OVERRUN_MINUTES} "
                    f"minutes), but its justification "
                    f"names no long-duration class from "
                    f"the grammar's closed set — an "
                    f"unclassed overrun is mis-scoped, "
                    f"not slow"))
    return out

