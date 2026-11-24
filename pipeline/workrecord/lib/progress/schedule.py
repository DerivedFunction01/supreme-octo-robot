"""Scheduler entries for armed progress schedules.

RETIRED (supervision plan Step 6): the
scheduler no longer fires progress-check — the
attention tick's armed rows are the check now, and
wb sends the steers. This module is removal-only:
sync_todo and sync_all delete any wb-progress entry
they find and never write one; the render path is
gone. The armed-row sync (lib/progress/attention.py)
is untouched — the tick reads armed rows, not
scheduler entries. The doctor flags any lingering
entry as drift.

The mechanism behind the progress schedules (the owner's
commission: armed work must not stall waiting
for an agent to create a schedule by hand). The scheduler
server's registry is local files — one YAML entry per job,
rescanned every tick — so creating a schedule IS writing
a file, and retiring one is deleting it.

This module was that write path, keyed to the todo
file as the record of truth. What it used to do:

- `sync_todo` ran at the end of the harness's todo
  writers (lib/writes/bundles.py — the one mutation
  path, so the CLI and the server get it alike). Armed
  todo (a `progress_check` field on a live, unarchived
  todo) → its entry existed, rendered from its current
  state. Disarmed, terminal, or archived → its entry
  was gone.
- The entry was a scripted job (classification: a
  fixed command; exit 0 = on track / disarmed / gone,
  exit 3 = stalled, and when it speaks is fully
  determined by that exit code) whose argv ran `wb
  progress-check <id>` in the project root at the
  todo's own cadence. A stall exits non-zero, so the
  scheduler's failure report carried the stall line as
  a ping.
- `sync_all` reconciled the whole registry against
  the swept armed set (the `wb progress
  --sync-entries` backfill); the doctor's entry checks
  flagged any drift that survived — the todo files
  ruled, entries were derived state.

Now both syncs only delete: `sync_todo` removes the
todo's entry if one stands, `sync_all` removes them
all (the `wb progress --sync-entries` retirement
sweep, run only at the coordinated cutover).

Location seam: the jobs dir is the pipeline's own
scheduling registry (`pipeline/scheduling/jobs/` in the
mega repo, beside this service), overridable by the
WB_SCHEDULER_JOBS_DIR env var. No jobs dir → every
sync is a silent no-op (a machine without the pipeline
still gets the full harness). A second seam keeps test
suites out of the live registry: WB_TMP_ROOT names the
machine's temp roots (this box's 512 MB tmpfs, the
disk-backed gate scratch, the system temp), and a project
root under one of them is scratch — its syncs no-op
against the live registry, so a scratch project's
removal never touches live entries. The workspace
root itself (the mega
repo's parent, matching the scheduler's ${WS}
definition) is overridable by WB_WORKSPACE_ROOT, and
this service's root as that anchor sees it by
WB_VIEWER_ROOT. A sync failure NEVER fails the todo
write it rides: the outcome rides the writer's result
dict as `progress_entry`, and the doctor surfaces
persistent divergence.

The render-time paragraphs that used to stand here —
the admission posture (amendment 3) and the
classification backstop (catalog plan Step 4) — are
gone with the render: nothing is written any more, so
there is no admission to model and no fixture class
to stamp.
"""

import os
from pathlib import Path

from . import report as progress_mod
from .. import paths as _paths
from .. import util as util_mod
from ..plans import bundles as bundle_parser

REPO_ROOT = _paths.PACKAGE_DIR

ENTRY_PREFIX = "wb-progress-"
# The stop statuses are homed with the todo vocabulary
# (bundles.TODO_STOP_STATUSES); this module's name for
# the set stays for its own readers.
STOP_STATUSES = bundle_parser.TODO_STOP_STATUSES


def _workspace_root():
    override = os.environ.get("WB_WORKSPACE_ROOT")
    if override:
        return Path(override)
    return REPO_ROOT.parent.parent.parent


def jobs_dir():
    """The pipeline's own scheduling registry dir, or
    None when this machine has no pipeline registry
    (the sync no-ops)."""
    override = os.environ.get("WB_SCHEDULER_JOBS_DIR")
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    candidate = REPO_ROOT.parent / "scheduling" / "jobs"
    return candidate if candidate.is_dir() else None


def entry_id(project_slug: str, todo_id: str) -> str:
    return f"{ENTRY_PREFIX}{project_slug}-{todo_id.lower()}"


def is_armed(todo) -> bool:
    """The entry-existence predicate: an armed todo is a
    live one — a cadence (not the opt-out value) in
    progress_check, not at a stop status, not in an
    archived bundle (arming that outlives its work is
    the doctor's orphan case, and it carries no
    schedule)."""
    return bundle_parser.parse_cadence(
        todo.get("progress_check")) is not None \
        and todo.get("status") not in STOP_STATUSES \
        and not todo.get("archived")


def _project_root(plans_dir):
    """Walk up from a project's plans dir to the dir
    carrying its workbench.yaml (the project root)."""
    current = Path(plans_dir)
    for candidate in (current, *current.parents):
        if (candidate / "workbench.yaml").is_file():
            return candidate
    return None


def _ws_relative(path):
    """`path` relative to the workspace root (this repo's
    parent — the scheduler's ${WS} anchor), or None when
    the path escapes it."""
    try:
        return path.resolve().relative_to(
            _workspace_root().resolve()).as_posix()
    except ValueError:
        return None


def _under_temp(path) -> bool:
    """True when the resolved path sits under a temp
    root — scratch state (test fixtures, gate scratch),
    whose projects are not the live workspace's and
    must never reach the live registry."""
    return util_mod.under_temp_root(path)


def _live_jobs_dir():
    """The live registry dir on THIS machine, from the
    module's own location — never from the (redirect-
    able) workspace-root seam: the pipeline's scheduling
    registry beside this service is the registry the
    real engine scans. A seam-redirected workspace has
    a different parent, so its jobs dir never compares
    equal."""
    return (REPO_ROOT.parent / "scheduling"
            / "jobs").resolve()


def _entry_live(directory) -> bool:
    """An entry written into `directory` is LIVE — it
    will fire against real work — exactly when the
    directory is this machine's real registry."""
    return Path(directory).resolve() == _live_jobs_dir()


def _sync_todo(plans_dir, todo) -> dict:
    # RETIRED (supervision plan Step 6): the scheduler
    # no longer fires progress-check — the tick's armed
    # rows are the check. This sync only removes: an
    # entry found here is deleted, and none is ever
    # written. The guards still apply first: a scratch
    # project's sync never touches the live registry.
    directory = jobs_dir()
    if directory is None:
        return {"action": "skipped",
                "reason": "no scheduler jobs dir"}
    root = _project_root(plans_dir)
    if root is None:
        return {"action": "skipped",
                "reason": "project root not found"}
    if _under_temp(root) and _entry_live(directory):
        # The leak this guards: a test run arms a fixture
        # todo while the jobs dir resolves to the LIVE
        # registry (no seam set); the fixture's tempdir
        # dies with the run and the entry crashes every
        # cycle on a manifest that no longer exists.
        return {"action": "skipped",
                "reason": "scratch project, live jobs dir"}
    if _ws_relative(root) is None \
            and _entry_live(directory):
        # Outside the workspace the ${WS} anchor cannot
        # express the root — and an entry landing in the
        # live registry would fire against a project
        # that is not there.
        return {"action": "skipped",
                "reason": "project outside the workspace root"}
    slug = root.name
    eid = entry_id(slug, todo["id"])
    path = directory / f"{eid}.yaml"
    if path.is_file():
        path.unlink()
        return {"action": "removed", "entry": eid}
    return {"action": "unchanged", "entry": eid}


def sync_todo(plans_dir, todo) -> dict:
    """Delete one todo's scheduler entry if one stands.
    Never raises: the todo file is the record of truth
    and the entry is derived state, so a sync failure
    rides the result, it never fails the write (the
    doctor flags persistent divergence)."""
    try:
        return _sync_todo(plans_dir, todo)
    except Exception as e:
        return {"action": "error", "error": str(e)}


def sync_all(projects) -> dict:
    """Remove every wb-progress entry in the registry:
    the scheduler-entry rendering is retired (Step 6),
    so there is no armed set to reconcile against — the
    sweep deletes what the per-todo syncs have not
    already removed. `projects` is accepted and ignored:
    the retirement is fleet-wide, not per-project. A
    missing jobs dir skips silently, as before. Run
    this only at the coordinated cutover: it deletes
    live scheduler entries, and the tick's armed rows
    are the check from the moment this lands."""
    directory = jobs_dir()
    if directory is None:
        return {"skipped": "no scheduler jobs dir",
                "written": [], "removed": [], "kept": 0}
    removed = []
    for path in sorted(directory.glob(
            f"{ENTRY_PREFIX}*.yaml")):
        path.unlink()
        removed.append(path.stem)
    return {"written": [], "removed": removed,
            "kept": 0}


def parse_entry_todo_id(path: Path):
    """The canonical todo id a wb-progress entry checks,
    read from its argv (the last argv item), or None when
    the file does not parse as one of ours."""
    try:
        lines = path.read_text(
            encoding="utf-8").splitlines()
    except OSError:
        return None
    in_argv = False
    items = []
    for line in lines:
        if line.strip() == "argv:":
            in_argv = True
            continue
        if in_argv:
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip())
            elif stripped:
                break
    if len(items) >= 4 and items[-2] == "progress-check":
        return items[-1]
    return None


def _stop_state(todo):
    """Why a todo's schedule is stopped, or None: its
    stop status (STOP_STATUSES), else "archived" for a
    todo in an archived bundle. Finished or paused work
    has no schedule to stall against, so the check names
    the stop instead of deriving a verdict."""
    status = todo.get("status")
    if status in STOP_STATUSES:
        return status
    if todo.get("archived"):
        return "archived"
    return None


def check_todo(plans_dir, todo_id, *, now=None):
    """The `wb progress-check` verdict: (exit_code, line).
    Exit 0 — on track, not armed, terminal, or not found
    (a missing todo means an orphaned entry, which the
    doctor flags as lingering; pinging about it every
    cadence would only spam). Exit 3 — stalled, with the
    stall line.

    An opted-out todo (progress_check: off) is exempt
    from progress measurement by its own declaration:
    the check names the opt-out and exits 0, deriving
    nothing from the file's checkpoint lines. Deriving
    a verdict from those lines read a deliberate,
    recorded hold as a stall — the Edgar greenfield
    Step 3 hold (progress_check: off, a HOLD RECORD on
    the body, one pre-hold checkpoint) drew repeated
    STALLED escalations from that derivation.
    A stop status is still named first
    (finished or paused work), and a todo whose
    cadence does not parse gets a no-verdict line,
    never an on-track."""
    for todo in bundle_parser.list_todos(plans_dir):
        if todo.get("id") != todo_id:
            continue
        block = progress_mod.todo_progress(todo, now=now)
        if block is None:
            cadence = todo.get("progress_check")
            if not cadence:
                return 0, f"{todo_id}: not armed"
            if cadence != bundle_parser.PROGRESS_OPT_OUT:
                return 0, (
                    f"{todo_id}: invalid progress_check "
                    f"{cadence!r} — no verdict derivable")
            stop = _stop_state(todo)
            if stop is not None:
                return 0, (f"{todo_id}: {stop} — "
                           f"schedule stopped")
            return 0, (
                f"{todo_id}: progress_check off — "
                f"opted out of progress checks")
        stop = _stop_state(todo)
        if stop is not None:
            return 0, (f"{todo_id}: {stop} — "
                       f"schedule stopped")
        if block["stalled"]:
            return 3, (
                f"STALLED {todo.get('bundle')}/{todo_id} "
                f"({todo.get('title') or ''}): "
                f"{block['missed_checks']} missed checks "
                f"at {block['cadence']} cadence, last "
                f"activity {block['last_activity']}")
        return 0, (f"{todo_id}: on track "
                   f"({block['missed_checks']} missed "
                   f"checks)")
    return 0, (f"{todo_id}: not found — entry orphaned "
               f"(the doctor reconciles)")
