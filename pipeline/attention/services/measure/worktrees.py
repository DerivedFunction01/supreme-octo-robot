"""Worktree presence: filesystem ground truth for
unfinished work — a standing worktree is work in
progress, whatever the posts claim. Collected on the
slow loop into a snapshot the measure reads."""

from __future__ import annotations

import glob as glob_mod
import subprocess
from datetime import datetime
from pathlib import Path

from attention.services import programmes


def _git(repo: Path, *args: str) -> tuple[int, str] | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    return done.returncode, done.stdout.strip()


def _candidates(roots: list) -> list[Path]:
    found: list[Path] = []
    for root in roots or []:
        if any(ch in str(root) for ch in "*?["):
            found.extend(
                Path(p) for p in sorted(glob_mod.glob(str(root))) if Path(p).is_dir()
            )
            continue
        base = Path(str(root))
        if (base / ".git").exists():
            found.append(base)
        elif base.is_dir():
            found.extend(
                child
                for child in sorted(base.iterdir())
                if child.is_dir() and (child / ".git").exists()
            )
    return found


def _measure(path: Path) -> dict:
    tip = _git(path, "rev-parse", "HEAD")
    status = _git(path, "status", "--porcelain")
    ancestor = _git(path, "merge-base", "--is-ancestor", "HEAD", "main")
    return {
        "name": path.name,
        "path": str(path),
        "tip": tip[1] if tip and tip[0] == 0 else None,
        "dirty": None if status is None else bool(status[1]),
        "landed": None if ancestor is None else ancestor[0] == 0,
    }


def collect(state: dict, now: datetime) -> bool:
    """Refresh the worktree snapshot for every declared
    programme; True when the snapshot changed."""
    snapshot: dict = {}
    for programme in programmes.declarations(state):
        roots = programme.get("worktree_roots") or []
        if not roots:
            continue
        snapshot[programme["slug"]] = {
            "at": now,
            "trees": [_measure(p) for p in _candidates(roots)],
        }
    before = {
        slug: entry.get("trees")
        for slug, entry in (state.get("worktree_snapshot") or {}).items()
    }
    if {slug: entry["trees"] for slug, entry in snapshot.items()} == before:
        return False
    state["worktree_snapshot"] = snapshot
    return True
