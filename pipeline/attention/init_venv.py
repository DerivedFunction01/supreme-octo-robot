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


def main() -> int:
    config = VenvConfig(
        root=ROOT,
        venv_dir=ROOT / "var" / "venv",
        python_spec="3.12",
        requirements=ROOT / "requirements.txt",
        fallback=True,
    )
    return build_venv(config, recreate="--recreate" in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
