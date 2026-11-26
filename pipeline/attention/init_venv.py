#!/usr/bin/env python3
"""Create this package's virtualenv and install its pinned
toolchain — a thin config caller over the pipeline gate's one
venv bootstrap (pipeline/gate/venvbuild.py, plan §4.16).

The venv lives at var/venv under the package root, the
original owner-attention repo's location: that repo's gate
ran every leg under var/venv and refused (exit 2, with this
script as the instruction) when it was missing. The config
is this package's form of the shared builder: a CPython 3.12
venv built by uv, with the fallback the original carried —
when uv is absent, build with python3 -m venv and pip
instead of failing (venvbuild's "attention form"). The one
pinned dependency (requirements.txt) is ruff, the tool the
package's declared ruff legs run; the package's code and
suite are stdlib-only.

Usage:  python3 init_venv.py [--recreate]
"""

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "attention_paths", Path(__file__).resolve().parent / "paths.py"
)
_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paths)

ROOT = _paths.PACKAGE_ROOT
_PIPELINE_ROOT = _paths.PIPELINE_ROOT
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from gate.venvbuild import VenvConfig, build_venv  # noqa: E402

_DECL = {
    "name": "init_venv",
    "summary": "Create this package's virtualenv and "
               "install its pinned toolchain.",
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
        venv_dir=ROOT / "var" / "venv",
        python_spec="3.12",
        requirements=ROOT / "requirements.txt",
        fallback=True,
    )
    return build_venv(config, recreate=parsed["flags"]["recreate"])


if __name__ == "__main__":
    raise SystemExit(main())
