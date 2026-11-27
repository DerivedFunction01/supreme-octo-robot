"""The timing ledger's transition block — the ONE
append-transition helper every file-todo writer calls
(wb timing-ledger plan, Step 2).

A todo file carries its own transition ledger in its
body: a `## Transitions` block holding one line per
mutation, each line a `transition: ` prefix plus a JSON
object — {"at", "actor", "verb", "field", "old", "new"}.
JSON because the values are free text (titles, names)
and the line must stay single-line and parseable
without an escaping dialect of its own. `at` is a full
ISO instant: the front-matter `updated:` stamp is
date-only, so durations derive from these lines, never
from front-matter.

This module is the block's one home: the line format,
the block predicates (the fields editor's verbatim
preservation and the rename driver's no-rewrite rule
both consume them), and `append_transition` — a pure
content transformation: body text in, body text with
the line appended out. Each writer folds the result
into its existing single write, so a transition and
the mutation it records land in the same write and
cannot be lost without losing the mutation itself.

Actor: a writer records the caller identity it was
given; the file writers receive none today, so each
passes actor=None and the helper records the verb's
own name — the record says which verb wrote it rather
than inventing an identity no caller supplied.

Worktree: a move whose caller knows the acting
worktree (the activation move, timing-ledger Step 3)
records it as an extra `worktree` key on that line —
present only on lines whose writer supplied one, so
older lines read exactly as before. Editor identity
(the actor) and worktree stay independent fields: a
fan-out runs N editors over M worktrees, and a line
names the one worktree its move ran in beside the
editor who made it.
"""

import json

from ..util import now_iso

TRANSITIONS_HEADER = "## Transitions"
TRANSITION_PREFIX = "transition: "


def transition_line(*, verb, field=None, old=None,
                    new=None, actor=None, at=None,
                    worktree=None) -> str:
    """One transition line in the block's format."""
    record = {
        "at": at or now_iso(),
        "actor": actor if actor is not None else verb,
        "verb": verb,
        "field": field,
        "old": old,
        "new": new,
    }
    if worktree is not None:
        record["worktree"] = worktree
    return TRANSITION_PREFIX + json.dumps(
        record, ensure_ascii=False)


def parse_transition(line: str):
    """One transition line → its record dict, or None
    when the line is not a transition line (or carries
    a malformed record — read-side honesty, never a
    guess)."""
    if not is_transition_line(line):
        return None
    try:
        record = json.loads(line[len(TRANSITION_PREFIX):])
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def is_transition_line(line: str) -> bool:
    return line.startswith(TRANSITION_PREFIX)


def is_block_line(line: str) -> bool:
    """The lines the transitions block is made of — the
    set every other writer must preserve verbatim and
    never rewrite."""
    return line.strip() == TRANSITIONS_HEADER \
        or is_transition_line(line)


def block_lines(text: str) -> list:
    """A text's transition lines, in order (the block's
    payload without its header) — the carry-over form
    for a writer that regenerates its file wholesale
    (the bundle contract) and must not lose the ledger
    it already carries."""
    return [ln for ln in (text or "").split("\n")
            if is_transition_line(ln)]


def transitions_in(text: str) -> list:
    """Every parsed transition record in a body or file
    text, in file order."""
    out = []
    for line in (text or "").split("\n"):
        record = parse_transition(line)
        if record is not None:
            out.append(record)
    return out


def append_transition_line(body: str, line: str) -> str:
    """Body text with one already-formatted transition
    line appended into its transitions block: inside
    the existing block when the body carries one (after
    its last transition line, wherever the block sits),
    else as a new block at the body's end."""
    text = (body or "").strip("\n")
    lines = text.split("\n") if text else []
    header_at = None
    for i, existing in enumerate(lines):
        if existing.strip() == TRANSITIONS_HEADER:
            header_at = i
            break
    if header_at is None:
        if lines:
            lines += ["", TRANSITIONS_HEADER, "", line]
        else:
            lines = [TRANSITIONS_HEADER, "", line]
        return "\n".join(lines)
    insert_at = header_at + 1
    j = header_at + 1
    while j < len(lines):
        if is_transition_line(lines[j]):
            insert_at = j + 1
            j += 1
        elif lines[j].strip() == "" and insert_at == j:
            j += 1
        else:
            break
    if insert_at == header_at + 1:
        lines.insert(header_at + 1, "")
        insert_at = header_at + 2
    lines.insert(insert_at, line)
    return "\n".join(lines)


def append_transition(body: str, *, verb, field=None,
                      old=None, new=None, actor=None,
                      at=None, worktree=None) -> str:
    """THE helper: body text + one transition → body
    text with the transition appended, in the block.
    Pure — no I/O; the caller folds the result into
    its own single write."""
    return append_transition_line(
        body,
        transition_line(verb=verb, field=field, old=old,
                        new=new, actor=actor, at=at,
                        worktree=worktree))
