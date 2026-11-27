"""Todo creation — split from bundles.py along the
creation seam; lib.writes.bundles re-exports this
surface.
"""

from pathlib import Path

from ..plans import bundles as bundle_parser
from ..plans.parser import parse_plan
from ..progress import attention as attention_mod
from ..progress import schedule as progress_schedule_mod
from ..util import now_iso, write_text

from .bundle_core import (
    PROGRESS_STOP_STATUSES,
    TODO_STATUSES,
    BundleError,
    _today,
    check_todo_name,
    derive_todo_name,
    find_bundle_dir,
)
from .bundle_create import _check_contract_gate
from .transitions import append_transition

# Todo creation (§3.4)
# ----------------------------------------------------------------

_FRONT_MATTER_ORDER = ("id", "legacy_id", "title",
                       "status", "feature",
                       "plan", "plan_step", "est",
                       "fanout_position", "worktree",
                       "created", "updated",
                       "progress_check", "progress_armed")

# The fan-out positions a step's record may carry
# (timing-ledger plan): serial prefix, fan-out branch,
# fan-in. The plan grammar validates the same set on
# the wb-step block; the writer refuses anything else
# at the mint, like every other field rule here.
FANOUT_POSITIONS = ("serial", "branch", "fan-in")


def _check_progress(progress, status, *,
                    no_progress=False):
    """Validate an arming request: a cadence the parser
    accepts, never armed onto a status whose move would
    disarm it in the same write, and never combined
    with the opt-out — a move declares a cadence, the
    opt-out, or neither (the automatic default)."""
    if no_progress and progress is not None:
        raise BundleError(
            "conflicting progress options: pass a "
            "cadence or the opt-out, not both")
    if progress is None:
        return
    if bundle_parser.parse_cadence(progress) is None:
        raise BundleError(
            f"bad progress cadence {progress!r}: "
            f"expected a cadence like 30m or 2h")
    if status in PROGRESS_STOP_STATUSES:
        raise BundleError(
            f"cannot arm a progress schedule on a move "
            f"to {status}: the schedule stops at that "
            f"status")


def _render_todo(fields: dict, body: str) -> str:
    lines = ["---"]
    for key in _FRONT_MATTER_ORDER:
        value = fields.get(key)
        if value is not None and value != "":
            lines.append(f"{key}: {value}")
    for key, value in fields.items():
        if key not in _FRONT_MATTER_ORDER \
                and value is not None and value != "":
            lines.append(f"{key}: {value}")
    lines.append("---")
    text = "\n".join(lines) + "\n"
    if body and body.strip():
        text += "\n" + body.strip("\n") + "\n"
    return text


def _bundle_feature(bundle_dir: Path):
    plan_file = bundle_dir / "plan.md"
    if plan_file.is_file():
        doc = parse_plan(
            plan_file.read_text(encoding="utf-8"))
        return doc["fields"].get("Feature") \
            or doc["fields"].get("feature")
    return None


def create_todo(plans_dir, bundle_ref, title, *, step=None,
                worktree=None, plan=None, feature=None,
                status: str = "todo", body: str = "",
                created: str = None,
                updated: str = None,
                progress: str = None,
                no_progress: bool = False,
                armed_at: str = None,
                name: str = None,
                est: str = None,
                fanout_position: str = None,
                actor: str = None,
                verb: str = "create") -> dict:
    """Write one todo file into a bundle's todos/ dir,
    with complete §3.2 front-matter. The todo's name —
    its id, a GitHub-like slug — is assigned here: an
    explicit `name` is validated against the slug rule
    and refused when it collides with any name in the
    project; without one, the name derives from the
    title (slugified, suffixed until free). Uniqueness
    is project-wide (the namespace every lookup
    resolves in). The file is `<name>.md`. Refuses a
    duplicate title in the bundle. Defaults: plan → the
    bundle's plan.md when it has one; feature → the
    bundle plan's Feature header when it declares one.
    Progress schedules: `progress` arms at creation
    with that cadence; `no_progress` records the
    explicit opt-out; and a todo created straight into
    `doing` with neither is armed at the default
    cadence — monitored by default, like the doing
    move in set_todo_status.

    Timing ledger (Step 2): `est` and `fanout_position`
    are additive front-matter — carried when a caller
    supplies them, absent otherwise, and a file without
    them reads exactly as before. The creation itself
    is recorded as the body's first transition line
    through the one helper (lib/writes/transitions.py),
    in the same write as the file. `verb` names the
    creating path (the drain's tail raise and the DB
    import mint through here and say so); `actor` is
    the caller identity when one is supplied — none
    is today, so the helper records the verb's name.
    """
    if not title or not title.strip() \
            or "\n" in title:
        raise BundleError(
            "todo title must be a single non-empty line")
    title = title.strip()
    if est is not None and (not str(est).strip()
                            or "\n" in str(est)):
        raise BundleError(
            "est must be a single non-empty line")
    if fanout_position is not None \
            and fanout_position not in FANOUT_POSITIONS:
        raise BundleError(
            f"fanout_position must be one of "
            f"{FANOUT_POSITIONS}, got {fanout_position!r}")
    if not title or not title.strip() \
            or "\n" in title:
        raise BundleError(
            "todo title must be a single non-empty line")
    title = title.strip()
    if status not in TODO_STATUSES:
        raise BundleError(
            f"todo status must be one of {TODO_STATUSES}")
    _check_progress(progress, status,
                    no_progress=no_progress)
    if no_progress:
        progress_value = bundle_parser.PROGRESS_OPT_OUT
        armed_value = None
    elif progress is not None:
        progress_value = progress
        armed_value = armed_at or now_iso()
    elif status == "doing":
        progress_value = \
            bundle_parser.PROGRESS_DEFAULT_CADENCE
        armed_value = armed_at or now_iso()
    else:
        progress_value = None
        armed_value = None
    if step is not None and (not isinstance(step, int)
                             or step < 1):
        raise BundleError(
            f"plan step must be a positive integer, "
            f"got {step!r}")
    plans_dir = Path(plans_dir)
    bundle_dir = find_bundle_dir(plans_dir, bundle_ref)
    if bundle_dir is None:
        raise BundleError(
            f"unknown bundle: {bundle_ref!r} "
            f"(no such bundle under {plans_dir})")
    existing = bundle_parser.list_todos(
        plans_dir, bundle=bundle_dir.name)
    wanted = " ".join(title.lower().split())
    for t in existing:
        if t["title"] and " ".join(
                t["title"].lower().split()) == wanted:
            raise BundleError(
                f"duplicate todo title in bundle "
                f"{bundle_dir.name}: {title!r} already "
                f"exists as {t['id']}")
    if armed_value is not None:
        # This create arms: a contract-carrying bundle
        # arms only under a complete contract.
        _check_contract_gate(plans_dir, bundle_dir)
    if plan is None and (bundle_dir / "plan.md").is_file():
        plan = "plan.md"
    if feature is None:
        feature = _bundle_feature(bundle_dir)
    taken = bundle_parser.all_todo_ids(plans_dir)
    if name is not None:
        check_todo_name(name)
        if name in taken:
            raise BundleError(
                f"todo name {name!r} already exists in "
                f"this project — names are unique "
                f"project-wide; pick another or let the "
                f"title derive one")
    else:
        name = derive_todo_name(title, taken)
    today = _today()
    fields = {
        "id": name,
        "title": title,
        "status": status,
        "feature": feature,
        "plan": plan,
        "plan_step": step,
        "est": est,
        "fanout_position": fanout_position,
        "worktree": worktree,
        "created": created or today,
        "updated": updated or created or today,
        "progress_check": progress_value,
        "progress_armed": armed_value,
    }
    todos_dir = bundle_dir / "todos"
    todos_dir.mkdir(exist_ok=True)
    filename = f"{fields['id']}.md"
    todo_path = todos_dir / filename
    if todo_path.exists():
        raise BundleError(
            f"todo file already exists: {todo_path}")
    body = append_transition(
        body, verb=verb, actor=actor, field="status",
        old=None, new=status)
    write_text(todo_path, _render_todo(fields, body))
    rel = todo_path.relative_to(plans_dir).as_posix()
    result = bundle_parser.parse_todo(
        todo_path.read_text(encoding="utf-8"), path=rel)
    result["bundle"] = bundle_dir.name
    result["file"] = str(todo_path)
    # Any lingering scheduler entry for the armed todo
    # is removed in the same call
    # (lib/progress/schedule.py — the rendering is
    # retired, so the sync only deletes); its outcome
    # never fails this write.
    result["progress_entry"] = \
        progress_schedule_mod.sync_todo(plans_dir, result)
    # The same arming writes the todo's owner-attention
    # row (lib/progress/attention.py): supervision
    # attaches at work start, beside the schedule.
    result["attention_row"] = \
        attention_mod.sync_todo(plans_dir, result)
    return result


# ----------------------------------------------------------------
# Todo status moves (§3.4)
# ----------------------------------------------------------------
