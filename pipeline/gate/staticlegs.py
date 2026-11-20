#!/usr/bin/env python3
"""Static legs: ruff format/lint and the policy-scanner leg,
as components (plan §4.16).

The shapes are the source repos' check.py legs, factored
so a package declaration names them instead of a fourth
copy of the driver living in a per-repo check file:

- ruff format: [python, -m, ruff, format, --check, *targets]
  (or without --check under fix).
- ruff lint:   [python, -m, ruff, check, *targets]
  (or with --fix under fix).
- scanners:    import the package's registered scanner
  runner from the package root and call it — the runner
  module and the argument form ("root" passes the package
  root path; "none" passes nothing) are declaration data,
  because the two reference houses differ on exactly that
  seam and both forms must be receivable at S7.

Each function runs its command in the package root and
returns the exit code; the gate runner owns the reporting.
"""
import subprocess
import sys


def _run(cmd, cwd):
    print(f"==> {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def ruff_format(root, targets, python, fix=False):
    cmd = [python, "-m", "ruff", "format"]
    if not fix:
        cmd.append("--check")
    cmd.extend(targets)
    return _run(cmd, root)


def ruff_lint(root, targets, python, fix=False):
    cmd = [python, "-m", "ruff", "check"]
    if fix:
        cmd.append("--fix")
    cmd.extend(targets)
    return _run(cmd, root)


def scanners(root, module, function="run_all", args="root",
             python=None):
    """Invoke the package's scanner runner in a subprocess
    under the package's own interpreter, package root on
    sys.path — the same isolation the root gates run it in.
    """
    python = python or sys.executable
    if args == "root":
        call = f"{function}(__import__('pathlib').Path.cwd())"
    else:
        call = f"{function}()"
    program = (
        "import sys; sys.path.insert(0, '.'); "
        f"from {module} import {function}; "
        f"raise SystemExit({call})"
    )
    return _run([python, "-c", program], root)
