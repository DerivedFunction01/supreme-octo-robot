"""Server-area path resolver: the work-record foundation,
restated for the server package.

Derives from pipeline/workrecord/paths.py (the foundation)
— loaded by path, the tree's standing seam, so this module
resolves identically however the server was entered. The
foundation owns every derivation; this module only names
what the server area consumes, in its vocabulary: the
work-record root the server inserts on sys.path and serves
from, and the pipeline root beside it.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "workrecord_paths",
    Path(__file__).resolve().parent.parent / "paths.py")
_foundation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_foundation)

WORKRECORD_ROOT = _foundation.PACKAGE_DIR
PIPELINE_ROOT = _foundation.PIPELINE_ROOT
LOAD_MONITOR_SNAPSHOT = _foundation.LOAD_MONITOR_SNAPSHOT
