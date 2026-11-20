#!/usr/bin/env python3
"""Create this package's virtualenv and install its
declared dependencies — a thin config caller over the
pipeline gate's one venv bootstrap (pipeline/gate/
venvbuild.py, plan §4.16).

The config is this package's, unchanged from the bootstrap
it replaces: a uv-managed CPython 3.11 venv at .venv/,
built by uv (never system python — system-site installs do
not survive VM replacement, and a missing system package
is a sign the launch path is wrong, not something to
repair in place). lib/ and server/ are stdlib-only, so
requirements.txt installs the one ruled dependency today;
the venv exists so the interpreter is pinned and the
launch path is uniform (systemd unit, watchdog, tests all
go through .venv/bin/python).

Usage:  python3 init_venv.py [--recreate]
"""

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "workrecord_paths",
    Path(__file__).resolve().parent / "paths.py")
_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paths)

ROOT = _paths.PACKAGE_DIR
_PIPELINE_ROOT = _paths.PIPELINE_ROOT
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from gate.venvbuild import VenvConfig, build_venv  # noqa: E402


def main() -> int:
    config = VenvConfig(
        root=ROOT,
        venv_dir=ROOT / ".venv",
        python_spec="3.11",
        requirements=ROOT / "requirements.txt",
    )
    return build_venv(config, recreate="--recreate" in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
