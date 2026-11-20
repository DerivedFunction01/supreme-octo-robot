"""Server-area path resolver: the scheduling foundation,
restated for the server package.

Derives from pipeline/scheduling/paths.py (the foundation)
— loaded by path, the tree's standing seam, so this module
resolves identically however the server was entered. The
foundation owns every derivation; this module only names
what the server area consumes.
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "scheduling_paths",
    os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "paths.py")))
_foundation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_foundation)

PACKAGE_ROOT = _foundation.PACKAGE_ROOT
PIPELINE_ROOT = _foundation.PIPELINE_ROOT
REPO_ROOT = _foundation.REPO_ROOT
SERVER_DIR = _foundation.SERVER_DIR
CONFIG_PATH = _foundation.CONFIG_PATH
CONFIG_EXAMPLE_PATH = _foundation.CONFIG_EXAMPLE_PATH
PLATFORM_WRITER = _foundation.PLATFORM_WRITER
PLATFORM_SERVING = _foundation.PLATFORM_SERVING
