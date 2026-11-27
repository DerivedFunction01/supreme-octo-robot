"""Bundle + file-todo mutations (live-work-tracking
spec §3.4): the ONE write path for bundles and todo
files. The `wb` CLI calls these functions; the server
will call the same ones — no second path, and file
writes never happen anywhere else in lib/ for todos.

Reads live in the plans parser family
(lib/plans/bundles.py) — writers scan through it, so a
write can never disagree with what the feeds will read.

Front-matter is written in the §3.2 field order, with
optional fields (feature / plan / plan_step / worktree)
present only when set — present-or-omitted exactly.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from .. import registry as reg
from ..plans import bundles as bundle_parser
from ..plans.parser import parse_plan
from ..progress import attention as attention_mod
from ..progress import schedule as progress_schedule_mod
from ..util import now_iso, parse_iso, write_text

from .bundle_core import (  # noqa: F401
    PROGRESS_STOP_STATUSES,
    TODO_STATUSES,
    BundleError,
    _all_bundle_dirs,
    _bundle_dirs,
    _check_slug,
    _SLUG_RE,
    _today,
    check_todo_name,
    derive_todo_name,
    find_bundle_dir,
    slugify_title,
)
from .bundle_create import (  # noqa: F401
    _check_contract_gate,
    _plan_skeleton,
    create_bundle,
    set_bundle_contract,
)
from .todo_create import (  # noqa: F401
    _FRONT_MATTER_ORDER,
    FANOUT_POSITIONS,
    _bundle_feature,
    _check_progress,
    _render_todo,
    create_todo,
)
from .transitions import (  # noqa: F401
    TRANSITION_PREFIX,
    TRANSITIONS_HEADER,
    append_transition,
    parse_transition,
    transitions_in,
)
from .todo_edit import (  # noqa: F401
    COMMISSION_FIELDS,
    _CHECKPOINT_LINE,
    _find_todo_file,
    plant_commission,
    set_todo_fields,
    set_todo_status,
)


def import_db_todos(plans_dir, db_path, *,
                    bundle_slug: str = "project-zero-starter",
                    today: str = None) -> dict:
    """Import a project's registry-DB todos into a
    starter bundle of file todos, through the SAME
    writer as `wb todo new` (create_bundle/create_todo
    above — not a second path). DB rows are read only
    (lib.registry.list_todos) and never altered. Titles
    already present in the starter bundle are skipped,
    so a re-run imports nothing twice. The file todo
    keeps the DB row's id as its name when that id
    satisfies the slug rule and is free in the project
    (DB ids are caller-chosen slugs already); otherwise
    the name derives from the title."""
    plans_dir = Path(plans_dir)
    db_todos = reg.list_todos(db_path)
    bundle_dir = find_bundle_dir(plans_dir, bundle_slug)
    if bundle_dir is None:
        created = create_bundle(plans_dir, bundle_slug,
                                today=today)
        bundle_id = created["id"]
        bundle_created = True
    else:
        bundle_id = bundle_dir.name
        bundle_created = False
    imported = []
    skipped = []
    present = {t["title"] for t in bundle_parser.list_todos(
        plans_dir, bundle=bundle_id) if t["title"]}
    taken = bundle_parser.all_todo_ids(plans_dir)
    for db_todo in db_todos:
        if db_todo["title"] in present:
            skipped.append(db_todo["id"])
            continue
        created_date = (db_todo.get("created_at")
                        or "")[:10] or None
        updated_date = (db_todo.get("updated_at")
                        or "")[:10] or None
        keep_name = db_todo["id"] \
            if bundle_parser.check_todo_name(
                db_todo["id"]) is None \
            and db_todo["id"] not in taken else None
        todo = create_todo(
            plans_dir, bundle_id, db_todo["title"],
            status=db_todo["status"],
            body=db_todo.get("notes") or "",
            created=created_date, updated=updated_date,
            name=keep_name, verb="import-db")
        taken.add(todo["id"])
        imported.append({
            "db_id": db_todo["id"],
            "id": todo["id"],
            "title": todo["title"],
            "status": todo["status"],
        })
        present.add(db_todo["title"])
    bundle_path = find_bundle_dir(plans_dir, bundle_slug)
    return {
        "bundle": bundle_id,
        "bundle_path": str(bundle_path),
        "bundle_created": bundle_created,
        "imported": imported,
        "skipped": skipped,
    }
