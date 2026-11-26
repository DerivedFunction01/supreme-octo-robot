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

_DECL = {
    "name": "init_venv",
    "summary": "Create this package's virtualenv and "
               "install its declared dependencies.",
    "flags": {"recreate": {"help": "rebuild the venv "
                                   "from scratch"}},
}


def _load_uargv():
    """The unified argv module (pipeline/platform/
    argv.py), loaded by path — the tree's cross-package
    form for the platform home."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_argv",
        _PIPELINE_ROOT / "platform" / "argv.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    uargv = _load_uargv()
    try:
        parsed = uargv.parse(_DECL, sys.argv[1:])
    except uargv.UsageError as exc:
        print(f"init_venv: {exc}", file=sys.stderr)
        print(uargv.help_text(_DECL), file=sys.stderr, end="")
        return 2
    if "help" in parsed:
        print(parsed["help"], end="")
        return 0
    config = VenvConfig(
        root=ROOT,
        venv_dir=ROOT / ".venv",
        python_spec="3.11",
        requirements=ROOT / "requirements.txt",
    )
    return build_venv(config, recreate=parsed["flags"]["recreate"])


if __name__ == "__main__":
    raise SystemExit(main())
