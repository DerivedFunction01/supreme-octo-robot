"""Plan estimate source (estimate-rule enforcement
plan, Step 3): the tracked plan files read as data —
per-step estimates and step state in the forms the
plan corpus actually carries — snapshotted per
programme on the slow loop for the staffing measure's
overdue evaluation.

The forms pinned, from the corpus as it stands:

- Headers: a `# Title` line; a `Status:` line whose
  first word is the plan's state (adopted, approved,
  built, complete) and whose text usually carries the
  adoption date; some plans carry the date on an
  `Adopted:` line instead. The adoption stamp is the
  first date in the Status line, else the Adopted
  line's date, else the filename's leading date —
  a plan with none of the three carries no stamp and
  its steps are unmeasurable, never estimated here.
- Steps: `### Step N — Title` subsections, or the
  numbered items of a `## Steps` section (a bold
  lead-in is the item's title where one is carried,
  else the text up to its first colon or dash).
- Estimates: an inline `[est: ...]` bracket in the
  step's own text, or the plan's `## Estimates`
  section (`- Step N — <duration>: ...`). A duration
  is a leading run of hour/minute counts (`45m`,
  `2h`, `1h30`); a bracket whose text leads with no
  duration is stated but unmeasurable and reads as
  absent — the measure raises nothing on it. A step
  with no estimate at all likewise raises nothing:
  the missing estimate is the starter lint's gate
  finding, not this measure's row.
- Step state: a step is closed when the plan's
  Status reads complete, or when the plan's
  `## Completion record` section names the step —
  the two closure forms the corpus carries. Every
  other step of an adopted plan stands open.
- Owner-only: a step is the owner's act, not the
  executing seat's, when its section heading names
  the owner as decider (the `Decision list (owner)`
  form), or when the plan itself stands unadopted
  (Status: proposed or draft) — the whole plan is
  then owner-held.

Attribution: a plan file belongs to one programme —
the repository root's plans to the programme whose
slug names the repository root, a declared worktree
root's plans to that root's programme; first
attribution wins, and a plan no programme's roots
reach is not read. The `finished/` folder is not
enumerated: its plans read complete and could raise
nothing.
"""

from __future__ import annotations

import glob as glob_mod
import re
from datetime import UTC, date, datetime, time
from pathlib import Path

from attention.services import programmes
from attention.services.measure import registry
from attention.settings import REPO_ROOT

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_STATUS_RE = re.compile(r"^Status:\s*(.+?)\s*$")
_ADOPTED_LINE_RE = re.compile(r"^Adopted:\s*(\d{4}-\d{2}-\d{2})")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
_STEP_HEADING_RE = re.compile(r"^Step\s+(\d+)[a-z]?\s*(?:[—–-]\s*)?(.*)$")
_NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*")
_EST_BRACKET_RE = re.compile(r"\[est:\s*([^\]]+)\]")
_ESTIMATES_ENTRY_RE = re.compile(r"^-\s+Step\s+(\d+)[a-z]?\s*[—–-]\s*(.+?)\s*$")
_COMPLETION_ENTRY_RE = re.compile(r"^-\s+Step\s+(\d+)")
_DURATION_RE = re.compile(r"^\s*(?:(\d+)\s*h(?:\s*(\d+)\s*m?)?|(\d+)\s*m)\b")
_CLOSED_STATUSES = {"complete", "completed", "done", "closed", "landed"}
_UNADOPTED_STATUSES = {"proposed", "draft"}


def parse_duration_minutes(text) -> int | None:
    """A leading duration as minutes: `45m`, `2h`,
    `1h30`, `1h 30m`. Text leading with anything else
    (a condition, a dependency) states no measurable
    duration and returns None."""
    if not text:
        return None
    match = _DURATION_RE.match(str(text))
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or match.group(3) or 0)
    total = hours * 60 + minutes
    return total if total > 0 else None


def _blocks(lines: list) -> list:
    """The document as heading blocks: each heading
    opens a block carrying its level, its title, the
    enclosing `##` section's title, and its own lines
    (up to the next heading of the same or a higher
    level). Lines before the first heading form a
    level-0 block."""
    blocks = []
    current = {"level": 0, "title": "", "section": "", "lines": []}
    blocks.append(current)
    section = ""
    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            if level == 2:
                section = title
            current = {
                "level": level,
                "title": title,
                "section": section if level > 2 else "",
                "lines": [],
            }
            blocks.append(current)
            continue
        current["lines"].append(line)
    return blocks


def _section_block(blocks: list, prefix: str) -> dict | None:
    for block in blocks:
        if block["level"] == 2 and block["title"].lower().startswith(prefix):
            return block
    return None


def _step_title(first_line: str, body: str) -> str:
    """A numbered item's title: its bold lead-in where
    one is carried, else its first line up to the
    first colon or dash — the corpus's two forms."""
    bold = _BOLD_RE.match(first_line.strip())
    if bold:
        return bold.group(1).strip().rstrip("—–-").strip()
    text = first_line.strip()
    for separator in (":", " — ", " – "):
        if separator in text:
            text = text.split(separator, 1)[0]
            break
    return text.strip()[:120]


def _numbered_steps(block: dict) -> list:
    """The numbered items of a `## Steps` block: an
    item opens on its `N.` line and its body runs to
    the next item or the block's end."""
    steps = []
    current = None
    for line in block["lines"]:
        match = _NUMBERED_RE.match(line)
        if match:
            current = {
                "number": int(match.group(1)),
                "first": match.group(2),
                "body": [match.group(2)],
                "section": block["title"],
            }
            steps.append(current)
            continue
        if current is not None:
            current["body"].append(line)
    return [
        {
            "number": step["number"],
            "title": _step_title(step["first"], "\n".join(step["body"])),
            "body": "\n".join(step["body"]),
            "section": step["section"],
        }
        for step in steps
    ]


def parse_plan(text: str, name: str) -> dict:
    """One plan file as data: its title, status word,
    adoption stamp, and its steps with estimates and
    state, in the pinned forms above. A step whose
    estimate is stated but unmeasurable, or never
    stated, carries estimate_minutes None."""
    lines = (text or "").splitlines()
    title = None
    status_text = None
    status_date = None
    adopted_line = None
    for line in lines:
        stripped = line.strip()
        if title is None and stripped.startswith("# "):
            title = stripped[2:].strip()
        if status_text is None:
            match = _STATUS_RE.match(stripped)
            if match:
                status_text = match.group(1)
                found = _DATE_RE.search(status_text)
                if found:
                    status_date = found.group(0)
        if adopted_line is None:
            match = _ADOPTED_LINE_RE.match(stripped)
            if match:
                adopted_line = match.group(1)
    status_word = ""
    if status_text:
        status_word = status_text.split(None, 1)[0].strip("—–-(").lower()
    date_text = status_date or adopted_line
    if date_text is None:
        match = _FILENAME_DATE_RE.match(name)
        if match:
            date_text = match.group(1)
    adopted_at = None
    if date_text:
        try:
            adopted_at = datetime.combine(
                date.fromisoformat(date_text), time.min, tzinfo=UTC
            )
        except ValueError:
            adopted_at = None
    blocks = _blocks(lines)
    steps = []
    for block in blocks:
        if block["level"] != 3:
            continue
        match = _STEP_HEADING_RE.match(block["title"])
        if not match:
            continue
        steps.append(
            {
                "number": int(match.group(1)),
                "title": match.group(2).strip(),
                "body": "\n".join(block["lines"]),
                "section": block["section"],
            }
        )
    if not steps:
        steps_block = _section_block(blocks, "steps")
        if steps_block is not None:
            steps = _numbered_steps(steps_block)
    estimates: dict[int, tuple] = {}
    estimates_block = _section_block(blocks, "estimates")
    if estimates_block is not None:
        for line in estimates_block["lines"]:
            match = _ESTIMATES_ENTRY_RE.match(line.strip())
            if match:
                raw = match.group(2)
                estimates[int(match.group(1))] = (parse_duration_minutes(raw), raw)
    completed: set[int] = set()
    completion_block = _section_block(blocks, "completion")
    if completion_block is not None:
        for line in completion_block["lines"]:
            match = _COMPLETION_ENTRY_RE.match(line.strip())
            if match:
                completed.add(int(match.group(1)))
    plan_closed = status_word in _CLOSED_STATUSES
    unadopted = status_word in _UNADOPTED_STATUSES
    parsed_steps = []
    for step in steps:
        bracket = _EST_BRACKET_RE.search(step["body"])
        if bracket:
            raw = bracket.group(1).strip()
            minutes = parse_duration_minutes(raw)
        elif step["number"] in estimates:
            minutes, raw = estimates[step["number"]]
        else:
            minutes, raw = None, None
        parsed_steps.append(
            {
                "number": step["number"],
                "title": step["title"],
                "estimate_minutes": minutes,
                "estimate_text": raw,
                "closed": plan_closed or step["number"] in completed,
                "owner_only": unadopted or "(owner)" in step["section"].lower(),
            }
        )
    return {
        "name": name,
        "title": title or name,
        "status": status_word,
        "adopted_at": adopted_at.isoformat() if adopted_at else None,
        "steps": parsed_steps,
    }


def _roots(state: dict, store_row: dict | None) -> list:
    """The roots a programme's plan files are read
    from: its declared worktree roots, globbed in the
    frontier collector's discipline. The repository
    root is attributed separately, by slug."""
    roots = []
    for root in (store_row or {}).get("worktree_roots") or []:
        if any(ch in str(root) for ch in "*?["):
            roots.extend(
                Path(p) for p in sorted(glob_mod.glob(str(root))) if Path(p).is_dir()
            )
        else:
            roots.append(Path(str(root)))
    return roots


def collect(state: dict, now: datetime) -> bool:
    """Snapshot, per active programme, the plans its
    roots carry, parsed in the pinned forms. A plan
    file attributes to exactly one programme — the
    repository root's to the programme whose slug
    names the root, a worktree root's to its owner —
    and first attribution wins. True when the
    snapshot changed."""
    snapshot: dict = {}
    seen: set = set()
    declared = {row["slug"]: row for row in registry.active_declarations()}
    store_rows = {p["slug"]: p for p in programmes.active_declarations(state)}
    for slug in sorted(set(declared) | set(store_rows)):
        roots = _roots(state, store_rows.get(slug))
        if slug == REPO_ROOT.name:
            roots.insert(0, REPO_ROOT)
        plans = []
        for root in roots:
            plans_dir = root / ".plans"
            if not plans_dir.is_dir():
                continue
            for path in sorted(plans_dir.glob("*.md")):
                if path in seen:
                    continue
                seen.add(path)
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                plans.append(parse_plan(text, path.name))
        if plans:
            snapshot[slug] = {"at": now, "plans": plans}
    before = {
        slug: entry.get("plans")
        for slug, entry in (state.get("plan_snapshot") or {}).items()
    }
    if {s: e["plans"] for s, e in snapshot.items()} == before:
        return False
    state["plan_snapshot"] = snapshot
    return True
