"""Lib-area path resolver: the work-record foundation,
restated for the lib package.

Derives from pipeline/workrecord/paths.py (the foundation)
— loaded by path, the tree's standing seam, so this module
resolves identically however lib was entered. The
foundation owns every derivation; this module only names
what the lib area consumes.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "workrecord_paths",
    Path(__file__).resolve().parent.parent / "paths.py")
_foundation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_foundation)

PACKAGE_DIR = _foundation.PACKAGE_DIR
PIPELINE_ROOT = _foundation.PIPELINE_ROOT
REPO_ROOT = _foundation.REPO_ROOT
WORKSPACE_ROOT = _foundation.WORKSPACE_ROOT
PLATFORM_WRITER = _foundation.PLATFORM_WRITER
SCHEDULING_REGISTRY = _foundation.SCHEDULING_REGISTRY
SCHEDULING_JOBS_DIR = _foundation.SCHEDULING_JOBS_DIR
WORKTREE_TRIM_SCRIPT = _foundation.WORKTREE_TRIM_SCRIPT
