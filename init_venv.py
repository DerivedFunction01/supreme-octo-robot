#!/usr/bin/env python3
"""Create the mega repo's root driver virtualenv and build
the package venvs the gate legs need — a thin config caller
over the pipeline gate's one venv bootstrap (pipeline/gate/
venvbuild.py, plan §4.16), in the same form as the packages'
own init_venv.py scripts.

The root venv (.venv/) is a pinned toolchain driver: the
venue's colab-check route gates under it and refuses the
system python, and env provisioning (job zero, driven by
the venue's repo registry) invokes this script as the
clone's init. The packages keep their own venvs; this
script also runs the two package inits that exist
(attention, workrecord) so a fresh clone is gate-ready in
one act. Packages without an init_venv.py are stdlib-only
under the driver and need nothing.

Usage:  python3 init_venv.py [--recreate]
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_PIPELINE_ROOT = ROOT / "pipeline"
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from gate.venvbuild import VenvConfig, build_venv  # noqa: E402

PACKAGE_INITS = ("attention", "workrecord")

_DECL = {
    "name": "init_venv",
    "summary": "Create the mega repo's root driver "
    "virtualenv and build the package venvs.",
    "flags": {"recreate": {"help": "rebuild the venv from scratch"}},
}


def _load_uargv():
    """The unified argv module (pipeline/platform/
    argv.py), loaded by path — the tree's cross-package
    form for the platform home."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_argv", _PIPELINE_ROOT / "platform" / "argv.py"
    )
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
    recreate = parsed["flags"]["recreate"]
    config = VenvConfig(
        root=ROOT,
        venv_dir=ROOT / ".venv",
        python_spec="3.11",
        requirements=ROOT / "requirements.txt",
    )
    rc = build_venv(config, recreate=recreate)
    if rc != 0:
        return rc
    for package in PACKAGE_INITS:
        init = _PIPELINE_ROOT / package / "init_venv.py"
        args = [sys.executable, str(init)]
        if recreate:
            args.append("--recreate")
        done = subprocess.run(args)
        if done.returncode != 0:
            return done.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
