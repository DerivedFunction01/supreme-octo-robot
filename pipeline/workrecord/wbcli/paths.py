"""Wbcli-area path resolver: the work-record foundation,
restated for the wb command modules.

Derives from pipeline/workrecord/paths.py (the foundation)
— loaded by path, the tree's standing seam, so this module
resolves identically however the CLI was entered. The
foundation owns every derivation; this module only names
what the wbcli area consumes, in its vocabulary: REPO_ROOT
is the work-record package root (the harness's own tree),
WORKSPACE_ROOT the sweep fallback above it, and
project_root_from_cwd the foundation's one cwd site.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "workrecord_paths",
    Path(__file__).resolve().parent.parent / "paths.py")
_foundation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_foundation)

REPO_ROOT = _foundation.PACKAGE_DIR
WORKSPACE_ROOT = _foundation.WORKSPACE_ROOT
PIPELINE_ROOT = _foundation.PIPELINE_ROOT
project_root_from_cwd = _foundation.project_root_from_cwd
