"""Git status parser and per-package change classifier.

Ported from the source reference (foundation/checks/
git_diff.py): the porcelain snapshot is unchanged; the
classifiers, which the source house hardcodes to its own
tree, are parameterized here by a PackageLayout — the
package's repo-relative root, its test directories, and
the paths whose change forces the package's full suite.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GitStatusSnapshot:
    """Snapshot of working tree changes relative to HEAD."""

    modified_files: tuple[str, ...] = field(default_factory=tuple)
    deleted_files: tuple[str, ...] = field(default_factory=tuple)
    untracked_files: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_changes(self) -> bool:
        return bool(self.modified_files or self.deleted_files
                    or self.untracked_files)

    @property
    def all_active_files(self) -> tuple[str, ...]:
        """All modified or newly created files (excluding deleted)."""
        return tuple(dict.fromkeys(
            (*self.modified_files, *self.untracked_files)))

    def excluding(self, paths) -> "GitStatusSnapshot":
        """Drop the given paths, so they no longer satisfy
        any classifier (the prose-only exclusion seam)."""
        drop = frozenset(paths)
        if not drop:
            return self
        return GitStatusSnapshot(
            modified_files=tuple(
                f for f in self.modified_files if f not in drop),
            deleted_files=self.deleted_files,
            untracked_files=tuple(
                f for f in self.untracked_files if f not in drop),
        )


@dataclass(frozen=True)
class PackageLayout:
    """Where one package sits in the repo and how its
    changes classify. Paths are POSIX, package-relative
    except root, which is repo-relative."""

    root: str
    test_dirs: tuple[str, ...] = ("tests",)
    full_suite_triggers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangeSet:
    """One package's changed files, package-relative."""

    sources: tuple[str, ...] = field(default_factory=tuple)
    tests: tuple[str, ...] = field(default_factory=tuple)
    conftests: tuple[str, ...] = field(default_factory=tuple)
    touches_trigger: bool = False
    has_changes: bool = False
    docs_only: bool = False


def classify(snapshot: GitStatusSnapshot,
             layout: PackageLayout) -> ChangeSet:
    prefix = layout.root.strip("/") + "/"
    active = []
    deleted = []
    for path in snapshot.all_active_files:
        if path.startswith(prefix):
            active.append(path[len(prefix):])
    for path in snapshot.deleted_files:
        if path.startswith(prefix):
            deleted.append(path[len(prefix):])
    if not active and not deleted:
        return ChangeSet()

    def is_test(rel: str) -> bool:
        parts = rel.split("/")
        return (len(parts) > 1 and parts[0] in layout.test_dirs
                and parts[-1].endswith(".py")
                and parts[-1] != "conftest.py")

    tests = tuple(p for p in active if is_test(p))
    conftests = tuple(
        p for p in active if p.split("/")[-1] == "conftest.py")
    sources = tuple(
        p for p in active
        if p.endswith(".py") and not is_test(p)
        and p.split("/")[-1] != "conftest.py")
    touches = any(
        p in layout.full_suite_triggers for p in (*active, *deleted))
    docs_only = (
        not sources and not tests and not conftests and not touches
        and not any(p.endswith((".py", ".sh"))
                    for p in (*active, *deleted)))
    return ChangeSet(
        sources=sources, tests=tests, conftests=conftests,
        touches_trigger=touches, has_changes=True,
        docs_only=docs_only)


def parse_porcelain_output(stdout: str) -> GitStatusSnapshot:
    """Parse output from `git status --porcelain=v1`."""
    modified: list[str] = []
    deleted: list[str] = []
    untracked: list[str] = []

    for line in stdout.splitlines():
        if not line or len(line) < 4:
            continue
        status = line[:2]
        path_part = line[3:].strip()
        # Handle rename format: "R  old -> new"
        if " -> " in path_part:
            path_part = path_part.split(" -> ")[1].strip()

        # Strip optional quotes if git quoted paths
        if path_part.startswith('"') and path_part.endswith('"'):
            path_part = path_part[1:-1]

        if status == "??":
            untracked.append(path_part)
        elif "D" in status:
            deleted.append(path_part)
        else:
            modified.append(path_part)

    return GitStatusSnapshot(
        modified_files=tuple(dict.fromkeys(modified)),
        deleted_files=tuple(dict.fromkeys(deleted)),
        untracked_files=tuple(dict.fromkeys(untracked)),
    )


def get_git_status(repo_root: Path | None = None) -> GitStatusSnapshot:
    """Run `git status --porcelain` in the repo root and
    return the parsed snapshot."""
    root = repo_root or Path.cwd()
    cmd = ["git", "status", "--porcelain=v1"]
    proc = subprocess.run(
        cmd, cwd=root, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        # Fallback for non-git environments: report no changes
        # so the caller handles safely.
        return GitStatusSnapshot()
    return parse_porcelain_output(proc.stdout)
