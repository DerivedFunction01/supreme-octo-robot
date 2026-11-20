"""Shared context for the wb command modules: the
tree roots, the doctor loader, the sweep-root seam,
and the two resolved project contexts every verb
runs against."""
import json
import os
import sys
from pathlib import Path

from lib.registry import export as export_mod  # noqa: E402
from lib import registry as reg  # noqa: E402
from lib.discovery.manifest import load_manifest  # noqa: E402
from lib.discovery.sweep import sweep  # noqa: E402

from . import paths as _paths

REPO_ROOT = _paths.REPO_ROOT


WORKSPACE_ROOT = _paths.WORKSPACE_ROOT


def _doctor_mod():
    """The doctor lives in the pipeline's evaluation
    package (step S4); load it through the pipeline
    path seam, the mega repo's cross-pipeline pattern."""
    pipeline_root = _paths.PIPELINE_ROOT
    if str(pipeline_root) not in sys.path:
        sys.path.insert(0, str(pipeline_root))
    from evaluation import doctor
    return doctor


def _sweep_roots(args):
    """Sweep roots for the read-side verbs: explicit
    --root, else the WB_VIEWER_SWEEP_ROOTS env seam,
    else the workspace root."""
    if getattr(args, "root", None):
        return [Path(r) for r in args.root]
    env_roots = os.environ.get("WB_VIEWER_SWEEP_ROOTS")
    if env_roots:
        return [Path(r) for r in
                env_roots.split(os.pathsep) if r]
    return [WORKSPACE_ROOT]


class Ctx:
    """Resolved project context for one invocation."""

    def __init__(self, args):
        self.db_path = None
        self.layout = None
        self.project_meta = None
        if args.db:
            self.db_path = Path(args.db)
            parent = self.db_path.parent
            self.layout = (parent / "entries",
                           parent / "archive")
            self.project_meta = {"slug": parent.parent.name,
                                 "name": parent.parent.name}
            return
        manifest = None
        if args.root:
            manifest = load_manifest(
                Path(args.root) / "workbench.yaml")
        if manifest is None and not args.project:
            project_root = _paths.project_root_from_cwd()
            if project_root is not None:
                manifest = load_manifest(
                    project_root / "workbench.yaml")
        if manifest is None:
            env_roots = os.environ.get("WB_VIEWER_SWEEP_ROOTS")
            roots = [Path(r) for r in
                     env_roots.split(os.pathsep) if r] \
                if env_roots else [WORKSPACE_ROOT]
            result = sweep(roots)
            if args.project:
                project = result.by_slug(args.project)
                if project is None:
                    raise SystemExit(
                        f"wb: project {args.project!r} not "
                        f"found by the sweep of {roots}")
                manifest = project.manifest
            elif result.projects:
                raise SystemExit(
                    "wb: no project selected — use --project,"
                    " --root, --db, or run inside a project")
            else:
                raise SystemExit(
                    "wb: no projects found by the sweep")
        self.manifest = manifest
        self.project_meta = {"slug": manifest.slug,
                             "name": manifest.name}
        if manifest.registry is None:
            raise SystemExit(
                f"wb: project {manifest.slug} declares no "
                f"registry — Mockups/Todos are absent for it")
        self.db_path = manifest.registry
        self.layout = (manifest.mockups, manifest.archive)

    def regenerate(self):
        if self.db_path and self.db_path.is_file():
            export_mod.regenerate(
                self.db_path, project=self.project_meta)


class PlansCtx:
    """Resolved project context for the bundle/file-todo
    verbs (live-work-tracking spec §3.4). Unlike Ctx, a
    registry is NOT required — bundles live in the plans
    dir; the DB is only needed by todo import-db."""

    def __init__(self, args, project_slug=None):
        self.db_path = None
        self.plans_dir = None
        self.root = None
        self.project_meta = None
        if args.db:
            self.db_path = Path(args.db)
            self.root = self.db_path.parent.parent
            manifest = None
            candidate = self.root / "workbench.yaml"
            if candidate.is_file():
                manifest = load_manifest(candidate)
            self.plans_dir = manifest.plans \
                if manifest is not None and manifest.plans \
                else self.root / ".plans"
            self.project_meta = {"slug": self.root.name,
                                 "name": self.root.name}
            return
        manifest = None
        if args.root:
            manifest = load_manifest(
                Path(args.root) / "workbench.yaml")
        slug = project_slug or args.project
        if manifest is None and not slug:
            project_root = _paths.project_root_from_cwd()
            if project_root is not None:
                manifest = load_manifest(
                    project_root / "workbench.yaml")
        if manifest is None:
            env_roots = os.environ.get("WB_VIEWER_SWEEP_ROOTS")
            roots = [Path(r) for r in
                     env_roots.split(os.pathsep) if r] \
                if env_roots else [WORKSPACE_ROOT]
            result = sweep(roots)
            if slug:
                project = result.by_slug(slug)
                if project is None:
                    raise SystemExit(
                        f"wb: project {slug!r} not found "
                        f"by the sweep of {roots}")
                manifest = project.manifest
            else:
                raise SystemExit(
                    "wb: no project selected — use --project,"
                    " --root, --db, or run inside a project")
        self.manifest = manifest
        self.root = manifest.root
        self.plans_dir = manifest.plans \
            or manifest.root / ".plans"
        self.db_path = manifest.registry
        self.project_meta = {"slug": manifest.slug,
                             "name": manifest.name}


def _print(obj):
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, sort_keys=True,
                         ensure_ascii=False))
    else:
        print(obj)


def _latest_reviews(ctx):
    entries = reg.list_entries(ctx.db_path, archived=None)
    return {e["id"]: reg.latest_review(ctx.db_path, e["id"])
            for e in entries}
