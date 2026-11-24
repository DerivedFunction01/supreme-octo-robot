"""Todo edits: status moves, field edits, and commission
planting — split from bundles.py along the edit seam;
lib.writes.bundles re-exports this surface.
"""

from pathlib import Path

from ..plans import bundles as bundle_parser
from ..progress import attention as attention_mod
from ..progress import schedule as progress_schedule_mod
from ..util import now_iso, parse_iso, write_text

from .bundle_core import (
    PROGRESS_STOP_STATUSES,
    TODO_STATUSES,
    BundleError,
    _bundle_dirs,
    _today,
)
from .bundle_create import _check_contract_gate
from .todo_create import _check_progress


def _find_todo_file(plans_dir: Path, todo_id: str):
    """(path, bundle_dir, archived) for a todo id,
    searched across the whole repo's bundles."""
    for archived in (False, True):
        for bundle_dir in _bundle_dirs(plans_dir,
                                       archived=archived):
            todos_dir = bundle_dir / "todos"
            if not todos_dir.is_dir():
                continue
            for f in sorted(todos_dir.glob("*.md")):
                parsed = bundle_parser.parse_todo(
                    f.read_text(encoding="utf-8"))
                if parsed["id"] == todo_id:
                    return f, bundle_dir, archived
    return None


def set_todo_status(plans_dir, todo_id, status, *,
                    note: str = None,
                    today: str = None,
                    progress: str = None,
                    no_progress: bool = False,
                    armed_at: str = None) -> dict:
    """Move one todo's status (todo|doing|blocked|done
    only — anything else refused), stamping `updated:`.
    An optional note is appended to the body (deploy
    records and blocker reasons live there). The rewrite
    is surgical: front-matter lines keep their order and
    unknown fields, the body is preserved verbatim.

    Progress schedules: arming is AUTOMATIC on a move
    to `doing` — a todo that declares neither a cadence
    nor the opt-out is armed at the default cadence in
    the same write, so work never runs unmonitored for
    want of a flag. `progress` (a cadence) overrides:
    it arms or re-arms at that cadence, stamping
    `progress_armed:` from `armed_at` or now. An
    existing cadence or opt-out rides through a doing
    move untouched; `no_progress` writes the opt-out
    (progress_check: off, no armed stamp), disarming a
    live schedule. A move to a stop status
    (done/blocked) clears both progress fields in the
    same write. Arming onto a stop status is refused."""
    if status not in TODO_STATUSES:
        raise BundleError(
            f"todo status must be one of {TODO_STATUSES}, "
            f"got {status!r}")
    _check_progress(progress, status,
                    no_progress=no_progress)
    plans_dir = Path(plans_dir)
    found = _find_todo_file(plans_dir, todo_id)
    if found is None:
        raise BundleError(f"unknown todo id: {todo_id!r}")
    todo_path, bundle_dir, archived = found
    text = todo_path.read_text(encoding="utf-8")
    fields, body, fm_lines = \
        bundle_parser.split_front_matter(text)
    if fields is None:
        raise BundleError(
            f"todo {todo_id} has no front-matter to "
            f"update: {todo_path}")
    today = today or _today()
    disarm = status in PROGRESS_STOP_STATUSES
    armed_stamp = armed_at or now_iso()
    # Resolve this move's progress write: arm_value is a
    # cadence to stamp, opt_out writes the off marker,
    # and neither means the existing fields ride through.
    current_check = fields.get("progress_check") or None
    arm_value = None
    opt_out = False
    if not disarm:
        if no_progress:
            opt_out = True
        elif progress is not None:
            arm_value = progress
        elif status == "doing" \
                and current_check \
                != bundle_parser.PROGRESS_OPT_OUT \
                and bundle_parser.parse_cadence(
                    current_check) is None:
            # No cadence declared (or an unreadable one):
            # the automatic arm. An existing cadence or
            # the opt-out is a declaration and rides.
            arm_value = \
                bundle_parser.PROGRESS_DEFAULT_CADENCE
    if arm_value is not None:
        # This move arms (a fresh arm or an explicit
        # re-arm): a contract-carrying bundle arms
        # only under a complete contract. A move whose
        # existing cadence rides through is not an arm
        # and is not gated.
        _check_contract_gate(plans_dir, bundle_dir)
    new_lines = []
    seen = set()
    for line in fm_lines:
        key = line.partition(":")[0].strip() \
            if ":" in line else None
        if key == "status":
            new_lines.append(f"status: {status}")
            seen.add("status")
        elif key == "updated":
            new_lines.append(f"updated: {today}")
            seen.add("updated")
        elif key in ("progress_check", "progress_armed"):
            if disarm:
                continue
            if opt_out:
                if key == "progress_check":
                    new_lines.append(
                        f"progress_check: "
                        f"{bundle_parser.PROGRESS_OPT_OUT}")
                    seen.add(key)
                continue
            if arm_value is not None:
                value = arm_value \
                    if key == "progress_check" \
                    else armed_stamp
                new_lines.append(f"{key}: {value}")
                seen.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    if "status" not in seen:
        new_lines.append(f"status: {status}")
    if "updated" not in seen:
        new_lines.append(f"updated: {today}")
    if opt_out and "progress_check" not in seen:
        new_lines.append(
            f"progress_check: "
            f"{bundle_parser.PROGRESS_OPT_OUT}")
    if arm_value is not None:
        if "progress_check" not in seen:
            new_lines.append(
                f"progress_check: {arm_value}")
        if "progress_armed" not in seen:
            new_lines.append(
                f"progress_armed: {armed_stamp}")
    if note:
        body = body.rstrip("\n")
        body = (body + "\n\n" if body else "") \
            + note.strip("\n") + "\n"
    out = "---\n" + "\n".join(new_lines) + "\n---\n"
    if body.strip():
        out += "\n" + body.strip("\n") + "\n"
    write_text(todo_path, out)
    rel = todo_path.relative_to(plans_dir).as_posix()
    result = bundle_parser.parse_todo(
        todo_path.read_text(encoding="utf-8"), path=rel)
    result["bundle"] = bundle_dir.name
    result["archived"] = archived
    result["file"] = str(todo_path)
    # Any lingering scheduler entry for the armed todo
    # is removed in the same call
    # (lib/progress/schedule.py — the rendering is
    # retired, so the sync only deletes); its outcome
    # never fails this write.
    result["progress_entry"] = \
        progress_schedule_mod.sync_todo(plans_dir, result)
    # The same transition writes or retires the todo's
    # owner-attention row (lib/progress/attention.py):
    # a terminal move retires the row in this write.
    result["attention_row"] = \
        attention_mod.sync_todo(plans_dir, result)
    return result


_CHECKPOINT_LINE = "progress-checkpoint: "


def set_todo_fields(plans_dir, todo_id, *, title=None,
                    notes=None, today: str = None) -> dict:
    """Edit one todo's title and/or notes (the viewer's
    title+notes save). Surgical, in set_todo_status's
    style: the title front-matter line is replaced in
    place, every other front-matter line rides verbatim,
    and `updated:` is stamped. The notes are the body's
    non-checkpoint lines: checkpoint lines
    (`progress-checkpoint: ...`) are record lines, not
    notes, and are preserved verbatim after the new
    notes — the feed projection splits them back out."""
    plans_dir = Path(plans_dir)
    found = _find_todo_file(plans_dir, todo_id)
    if found is None:
        raise BundleError(f"unknown todo id: {todo_id!r}")
    todo_path, bundle_dir, archived = found
    text = todo_path.read_text(encoding="utf-8")
    fields, body, fm_lines = \
        bundle_parser.split_front_matter(text)
    if fields is None:
        raise BundleError(
            f"todo {todo_id} has no front-matter to "
            f"update: {todo_path}")
    if title is not None:
        if not str(title).strip():
            raise BundleError("title must not be empty")
        title = str(title).strip()
    today = today or _today()
    new_lines = []
    seen = set()
    for line in fm_lines:
        key = line.partition(":")[0].strip() \
            if ":" in line else None
        if key == "title" and title is not None:
            new_lines.append(f"title: {title}")
            seen.add("title")
        elif key == "updated":
            new_lines.append(f"updated: {today}")
            seen.add("updated")
        else:
            new_lines.append(line)
    if title is not None and "title" not in seen:
        new_lines.append(f"title: {title}")
    if "updated" not in seen:
        new_lines.append(f"updated: {today}")
    if notes is not None:
        kept = [ln for ln in body.split("\n")
                if ln.startswith(_CHECKPOINT_LINE)]
        parts = []
        if str(notes).strip():
            parts.append(str(notes).strip("\n"))
        parts.extend(kept)
        body = "\n".join(parts)
    out = "---\n" + "\n".join(new_lines) + "\n---\n"
    if body.strip():
        out += "\n" + body.strip("\n") + "\n"
    write_text(todo_path, out)
    rel = todo_path.relative_to(plans_dir).as_posix()
    result = bundle_parser.parse_todo(
        todo_path.read_text(encoding="utf-8"), path=rel)
    result["bundle"] = bundle_dir.name
    result["archived"] = archived
    result["file"] = str(todo_path)
    return result


# ----------------------------------------------------------------
# Commissions of record (channel-indistinguishability
# cure)
# ----------------------------------------------------------------

# The front-matter keys that make a todo a commission
# of record. They are planted ONLY by plant_commission
# below: no other writer in this module accepts or sets
# them (create_todo has no such parameter; the surgical
# editors ride unknown lines verbatim but never create
# them), and the supervision machinery (progress
# schedule + attention rows) writes no todo files at
# all — so a claim arriving on a chat channel, however
# often repeated, can never mint the entry that would
# verify it. The read side is lib/plans/commissions.py.
COMMISSION_FIELDS = ("commissioned_by", "commissioned_at")


def plant_commission(plans_dir, todo_id, *,
                     commissioned_by: str,
                     commissioned_at: str = None,
                     today: str = None) -> dict:
    """Plant commission provenance on one todo: the
    write that makes it a commission of record.

    Stamps `commissioned_by:` and `commissioned_at:`
    front-matter (the provenance shape goals'
    owner_waiting already uses: who, and when) plus
    `updated:`, surgically — every other front-matter
    line and the body ride verbatim. Refused, with a
    reason: an unknown todo; an archived todo (a closed
    record takes no new direction — commission a fresh
    todo); a todo already carrying commission
    provenance (provenance is planted once; a
    re-commission is a new todo, not an overwrite); an
    empty commissioned_by; a commissioned_at that is
    not an ISO-8601 instant."""
    if not str(commissioned_by or "").strip():
        raise BundleError("commissioned_by must not be empty")
    commissioned_by = str(commissioned_by).strip()
    commissioned_at = commissioned_at or now_iso()
    try:
        parse_iso(commissioned_at)
    except (TypeError, ValueError):
        raise BundleError(
            f"invalid commissioned_at {commissioned_at!r}: "
            f"expected an ISO-8601 timestamp")
    plans_dir = Path(plans_dir)
    found = _find_todo_file(plans_dir, todo_id)
    if found is None:
        raise BundleError(f"unknown todo id: {todo_id!r}")
    todo_path, bundle_dir, archived = found
    if archived:
        raise BundleError(
            f"todo {todo_id} is archived — a closed record "
            f"takes no new commission")
    text = todo_path.read_text(encoding="utf-8")
    fields, body, fm_lines = \
        bundle_parser.split_front_matter(text)
    if fields is None:
        raise BundleError(
            f"todo {todo_id} has no front-matter to "
            f"commission: {todo_path}")
    for key in COMMISSION_FIELDS:
        if fields.get(key):
            raise BundleError(
                f"todo {todo_id} already carries commission "
                f"provenance ({key}: {fields[key]!r}) — a "
                f"re-commission is a new todo")
    today = today or _today()
    new_lines = []
    seen = set()
    for line in fm_lines:
        key = line.partition(":")[0].strip() \
            if ":" in line else None
        if key == "updated":
            new_lines.append(f"updated: {today}")
            seen.add("updated")
        else:
            new_lines.append(line)
    new_lines.append(f"commissioned_by: {commissioned_by}")
    new_lines.append(f"commissioned_at: {commissioned_at}")
    if "updated" not in seen:
        new_lines.append(f"updated: {today}")
    out = "---\n" + "\n".join(new_lines) + "\n---\n"
    if body.strip():
        out += "\n" + body.strip("\n") + "\n"
    write_text(todo_path, out)
    rel = todo_path.relative_to(plans_dir).as_posix()
    result = bundle_parser.parse_todo(
        todo_path.read_text(encoding="utf-8"), path=rel)
    result["bundle"] = bundle_dir.name
    result["archived"] = archived
    result["file"] = str(todo_path)
    return result


# ----------------------------------------------------------------
# DB-todo import (§3.7)
# ----------------------------------------------------------------
