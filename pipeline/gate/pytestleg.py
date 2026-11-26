#!/usr/bin/env python3
"""The pytest leg kind (gate.runner dispatch): a package
whose suite is a pytest suite declares it once in its
gate.json `suite` key — the argv with {python} /
{workers}, the requirement pins, the scratch-venv
interpreter story. The leg builds the declared scratch
venv through the gate venvbuild, resolves the argv
against it and the worker count the runner derives,
and verdicts on pytest's exit code. Under targeting,
the declared test-dir positional is replaced by the
resolved test files, the unittest leg's form; an empty
resolution is the no-tests-affected green."""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import venvbuild


def _suite_venv(pkg, suite: dict) -> str | None:
    """Build (or refresh) the suite's scratch venv
    through the gate venvbuild and install the
    declaration's requirement pins into it; returns the
    venv python, or None when either step fails. The
    venv lives under the package's var dir (untracked
    scratch by the package's own ignore rules); the
    interpreter spec is the repo's runtime (3.12)."""
    venv_dir = pkg.root / "var" / "suite-venv"
    try:
        rc = venvbuild.build_venv(venvbuild.VenvConfig(
            root=pkg.root, venv_dir=venv_dir,
            python_spec="3.12", fallback=True))
    except SystemExit:
        rc = 1
    if rc != 0:
        return None
    python = str(venv_dir / "bin" / "python")
    pins = [f"{name}{spec}" for name, spec in
            sorted(suite.get("requirements", {}).items())]
    if pins:
        uv = venvbuild.find_uv()
        install = ([uv, "pip", "install", "--python", python, *pins]
                   if uv is not None
                   else [python, "-m", "pip", "install", *pins])
        if subprocess.run(install, check=False).returncode != 0:
            return None
    return python


def run_pytest(pkg, leg: dict, targeted_files,
               repo_root: Path, workers: int, run_argv) -> int:
    """The leg's run: consume the package's `suite`
    declaration and verdict on pytest's exit code. The
    runner supplies the derived worker count and its
    argv runner, so both stay single-homed there."""
    suite = pkg.decl.get("suite")
    if not isinstance(suite, dict) or not suite.get("argv"):
        print("pytest leg declared without a suite "
              f"declaration (package {pkg.name})")
        return 2
    if targeted_files is not None and not targeted_files:
        print("==> no tests affected by the changes")
        return 0
    python = _suite_venv(pkg, suite)
    if python is None:
        print(f"suite venv build failed (package {pkg.name})")
        return 2
    argv = [
        item.replace("{python}", python)
            .replace("{workers}", str(workers))
        for item in suite["argv"]
    ]
    if targeted_files is not None:
        rel = [str((repo_root / f).relative_to(pkg.root))
               for f in targeted_files]
        expanded: list[str] = []
        for item in argv:
            if item == "tests":
                expanded.extend(rel)
            else:
                expanded.append(item)
        argv = expanded
    return run_argv(argv, pkg.root)
