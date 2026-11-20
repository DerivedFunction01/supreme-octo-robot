#!/usr/bin/env python3
"""Venv bootstrap: one find_uv and one builder (plan §4.16).

The per-repo init_venv.py files duplicated this logic and
had already diverged (one hard-fails without uv, the other
falls back to python3 -m venv). The builder is one
implementation parameterized by per-package config:

- root: the package root the venv belongs to.
- venv_dir: where the venv lives (the config's location —
  for workrecord, .venv under the package root, unchanged).
- python_spec: the interpreter spec uv resolves (3.11 for
  workrecord, unchanged).
- requirements: the file installed into the venv, or None.
- fallback: when uv is absent, build with python3 -m venv
  and pip instead of failing (the attention form). The
  default keeps the workbench form: a missing uv is a
  launch-path error, reported, never repaired in place.

uv is resolved by path, never a bare name in automation:
PATH first (uv is absent from PATH in non-login shells on
some machines), then the known per-user install locations
— the astral installer location and the cargo location —
so no single machine's uv location is hardcoded.
"""
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VenvConfig:
    root: Path
    venv_dir: Path
    python_spec: str
    requirements: Path | None = None
    fallback: bool = False


def find_uv() -> str | None:
    """Resolve uv: PATH first, then the per-user installs."""
    found = shutil.which("uv")
    if found:
        return found
    candidates = [Path.home() / ".local" / "bin" / "uv",
                  Path.home() / ".cargo" / "bin" / "uv"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _interpreter_version(python: Path) -> str:
    out = subprocess.run(
        [str(python), "-c",
         "import sys; print(sys.version.split()[0])"],
        capture_output=True, text=True)
    return out.stdout.strip()


def build_venv(config: VenvConfig, recreate: bool = False) -> int:
    """Create (when missing or recreate) and provision the
    configured venv; print the record lines the per-package
    bootstraps printed. Returns the process exit code."""
    root = Path(config.root)
    venv_dir = Path(config.venv_dir)
    if not venv_dir.is_absolute():
        venv_dir = root / venv_dir
    uv = find_uv()
    if uv is None and not config.fallback:
        raise SystemExit(
            "init_venv: uv not found on PATH or at the "
            "per-user install locations ($HOME/.local/bin, "
            "$HOME/.cargo/bin) — install uv first")
    if recreate and venv_dir.exists():
        shutil.rmtree(venv_dir)
    python = venv_dir / "bin" / "python"
    if not venv_dir.exists():
        if uv is not None:
            subprocess.run(
                [uv, "venv", "--python", config.python_spec,
                 str(venv_dir)], check=True)
        else:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True)
        print(f"init_venv: created {venv_dir} "
              f"({'uv' if uv else 'venv'}, "
              f"Python {config.python_spec})")
    if config.requirements is not None:
        req = Path(config.requirements)
        if not req.is_absolute():
            req = root / req
        if uv is not None:
            subprocess.run(
                [uv, "pip", "install", "--python", str(python),
                 "-r", str(req)], check=True)
        else:
            subprocess.run(
                [str(python), "-m", "pip", "install",
                 "-r", str(req)], check=True)
        print(f"init_venv: dependencies installed from {req.name}")
    print(f"init_venv: interpreter: {python} "
          f"(Python {_interpreter_version(python)})")
    return 0
