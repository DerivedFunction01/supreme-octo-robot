"""CLI-area path resolver: the scheduling foundation,
restated for the sched CLI.

Derives from pipeline/scheduling/paths.py (the foundation)
— loaded by path, the tree's standing seam, so this module
resolves identically however the CLI was entered. The
foundation owns every derivation; this module only names
what the CLI area consumes, under the CLI's standing names
(ROOT is the scheduling package root).
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "scheduling_paths",
    os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "paths.py")))
_foundation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_foundation)

ROOT = _foundation.PACKAGE_ROOT
PIPELINE_ROOT = _foundation.PIPELINE_ROOT
REPO_ROOT = _foundation.REPO_ROOT
JOBS_DIR = _foundation.JOBS_DIR
STATE_DIR = _foundation.STATE_DIR
CONFIG_PATH = _foundation.CONFIG_PATH
CONFIG_EXAMPLE_PATH = _foundation.CONFIG_EXAMPLE_PATH
OPS_TOKEN_DIR = _foundation.OPS_TOKEN_DIR
PLATFORM_WRITER = _foundation.PLATFORM_WRITER
