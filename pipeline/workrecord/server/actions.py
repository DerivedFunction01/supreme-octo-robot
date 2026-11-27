"""Mutation endpoints: entries, todos, plan resolves.

One slice of the companion server: the thin callers
over lib/ mutations (the one-mutation-path rule).
Every mutation pairs with the entry-detail payload
for its response and the shared post-mutation work
(annotation sidecar, export regeneration, repos-cache
invalidation).

Target-shape note (S11): the pinned module imported its
siblings flat (donor-style); here the package's __init__
owns the seams, siblings are relative imports, and lib/
comes through the sys.path seam the package installs —
the same conversion the S8 feed modules carry.
"""

from lib.writes import bundles as bundle_mod  # noqa: E402
from lib import drain as drain_mod  # noqa: E402
from lib.registry import export as export_mod  # noqa: E402
from lib.writes import files as files_mod  # noqa: E402
from lib import registry as reg  # noqa: E402
from lib.plans import parser as plan_parser  # noqa: E402
from lib.util import now_iso  # noqa: E402

from . import config as cfgmod  # noqa: E402
from .common import CFG, ApiError, layout_of  # noqa: E402
from .feeds import entry_detail  # noqa: E402


# ----------------------------------------------------------------
# Mutations (delegate to lib/, actor=viewer, then regenerate)
# ----------------------------------------------------------------


def _require_registry(project):
    m = project.manifest
    if m.registry is None or not m.registry.is_file():
        raise ApiError(409, "project has no initialized "
                            "registry")
    return m.registry


def _after_mutation(project, entry_id):
    db = project.manifest.registry
    try:
        export_mod.regenerate(db, project=project.slug)
    except Exception as e:
        raise ApiError(500, f"mutation landed but export "
                            f"regeneration failed: {e}",
                       mutated=True)
    return entry_detail(db, entry_id)


def entry_action(project, entry_id, body: dict) -> dict:
    db = _require_registry(project)
    verb = body.get("verb")
    layout = layout_of(project)
    try:
        if verb == "set":
            reg.set_fields(db, entry_id, body.get("fields") or {},
                           actor="viewer",
                           expect_version=body.get(
                               "expect_version"))
        elif verb == "set-status":
            reg.set_status(db, entry_id, body.get("status"),
                           actor="viewer",
                           ruling=body.get("ruling"),
                           gate=body.get("gate"),
                           expect_version=body.get(
                               "expect_version"),
                           layout=layout)
        elif verb == "verify":
            reg.verify_entry(db, entry_id, actor="viewer",
                             accept_drift=bool(
                                 body.get("accept_drift")))
        elif verb == "archive":
            reg.archive_entry(db, layout, entry_id,
                              actor="viewer",
                              resume=bool(body.get("resume")))
        elif verb == "unarchive":
            reg.unarchive_entry(db, layout, entry_id,
                                actor="viewer")
        elif verb == "supersede":
            if not body.get("new_id"):
                raise ApiError(400, "supersede needs new_id")
            reg.supersede(db, entry_id, body["new_id"],
                          actor="viewer",
                          ruling=body.get("ruling"))
        elif verb == "review":
            reg.review_entry(db, entry_id,
                             body.get("disposition"),
                             actor="viewer",
                             comment=body.get("comment"),
                             layout=layout)
        elif verb == "set-state":
            reg.set_state(db, entry_id, body.get("state") or {},
                          actor="viewer",
                          expect_version=body.get(
                              "expect_version"))
        elif verb == "set-state-schema":
            reg.set_state_schema(db, entry_id,
                                 body.get("schema"),
                                 actor="viewer")
        else:
            raise ApiError(400, f"unknown verb: {verb!r}")
    except ApiError:
        raise
    except reg.VersionConflict as e:
        raise ApiError(409, str(e))
    except reg.UniformityRefused as e:
        raise ApiError(422, str(e),
                       findings=getattr(e, "findings", []))
    except reg.RulingRequired as e:
        raise ApiError(400, str(e))
    except reg.RegistryError as e:
        raise ApiError(400, str(e))
    return _after_mutation(project, entry_id)


def todo_action(project, body: dict) -> dict:
    """The server's todo mutations on bundle todo FILES,
    through the same lib writers `wb todo` calls
    (lib.writes.bundles — one mutation path; the server
    holds no file-writing logic of its own). The retired
    registry-DB todo verbs are gone: file todos are the
    store (§3.7). Verbs: set-status (a status move, with
    the writer's note / progress-cadence / worktree
    passthrough),
    set-fields (title / notes), create (a new todo in a
    bundle)."""
    m = project.manifest
    if m.plans is None or not m.plans.is_dir():
        raise ApiError(409, "project declares no plans dir "
                            "— it has no bundle todos")
    verb = body.get("verb")
    try:
        if verb == "set-status":
            if not body.get("id"):
                raise ApiError(400, "set-status needs a "
                                    "todo id")
            todo = bundle_mod.set_todo_status(
                m.plans, body["id"], body.get("status"),
                note=body.get("note"),
                progress=body.get("progress"),
                no_progress=bool(body.get("no_progress")),
                worktree=body.get("worktree"))
        elif verb == "set-fields":
            if not body.get("id"):
                raise ApiError(400, "set-fields needs a "
                                    "todo id")
            if body.get("title") is None \
                    and body.get("notes") is None:
                raise ApiError(400, "set-fields needs a "
                                    "title or notes")
            todo = bundle_mod.set_todo_fields(
                m.plans, body["id"], title=body.get("title"),
                notes=body.get("notes"))
        elif verb == "create":
            if not body.get("bundle") \
                    or not body.get("title"):
                raise ApiError(400, "create needs a bundle "
                                    "and a title")
            todo = bundle_mod.create_todo(
                m.plans, body["bundle"], body["title"],
                step=body.get("step"),
                worktree=body.get("worktree"),
                body=body.get("body") or "")
        else:
            raise ApiError(400, f"unknown verb: {verb!r}")
    except bundle_mod.BundleError as e:
        raise ApiError(400, str(e))
    return {"todo": todo}


def drain_action(project, body: dict) -> dict:
    """POST /api/projects/<slug>/drain — one drain pass
    (supervision plan Step 4): the attention tick hands
    over its programme declarations and lib/drain runs
    the detector for this project — drained bundles
    raise their registry tail sets through the writer
    path, and a programme that raised archives its
    repo's worktrees through the trim lifecycle. The
    computation and both acts are lib's; this layer
    validates the request shape only."""
    m = project.manifest
    if m.plans is None or not m.plans.is_dir():
        raise ApiError(409, "project declares no plans dir "
                            "— it has no bundle todos")
    declarations = body.get("programmes")
    if not isinstance(declarations, list) \
            or not all(isinstance(d, dict)
                       for d in declarations):
        raise ApiError(400, "drain needs a programmes list "
                            "of declaration objects")
    try:
        outcomes = drain_mod.run_project(
            m.plans, project.root, declarations)
    except drain_mod.DrainError as e:
        raise ApiError(400, str(e))
    return {"drain": outcomes}


def plan_resolve(project, body: dict) -> dict:
    """POST /api/projects/<slug>/plan/resolve — the
    resolvable-questions write (plan syntax standard):
    the owner answers a plan's sentinel questions and the
    answers land in the plan file itself. The composition
    is lib's (plan_parser.apply_answers — box checked,
    answer filled, every other byte preserved); the write
    is the guarded save (lib/files.guarded_save_file —
    editing flag, sha compare-and-swap, atomic replace).
    This layer validates the request shape and maps lib
    outcomes to statuses; it holds no write logic of its
    own and touches no registry."""
    m = project.manifest
    if m.plans is None or not m.plans.is_dir():
        raise ApiError(409, "project declares no plans dir")
    rel = body.get("path")
    base_sha256 = body.get("base_sha256")
    answers = body.get("answers")
    if not isinstance(rel, str) or not rel:
        raise ApiError(400, "resolve needs a plan \"path\"")
    if not isinstance(base_sha256, str):
        raise ApiError(400, "resolve needs \"base_sha256\"")
    if not isinstance(answers, dict) or not answers:
        raise ApiError(400, "resolve needs a non-empty "
                            "\"answers\" map")
    try:
        doc = plan_parser.load_plan(m.plans, rel)
    except (ValueError, FileNotFoundError) as e:
        raise ApiError(404, str(e))
    if not doc["questions"]:
        raise ApiError(400, "plan carries no resolvable "
                            "questions")
    if base_sha256 != doc["file_sha256"]:
        raise ApiError(
            409, "plan changed on disk since it was opened",
            current_sha256=doc["file_sha256"])
    try:
        new_text = plan_parser.apply_answers(doc["markdown"],
                                             answers)
    except ValueError as e:
        raise ApiError(400, str(e))
    backup_root = cfgmod.state_dir(CFG) \
        / CFG["edit_backups_dir"]
    try:
        result = files_mod.guarded_save_file(
            m.plans, rel, new_text, doc["file_sha256"],
            editing_enabled=CFG["file_editing_enabled"],
            backup_root=backup_root,
            backup_key=project.slug)
    except files_mod.FileError_ as e:
        raise ApiError(e.status, str(e),
                       **{k: v for k, v in e.payload.items()
                          if k != "error"})
    return {"path": rel, "sha256": result["sha256"],
            "resolved": sorted(answers),
            "backup": result["backup"],
            "captured_at": now_iso()}
