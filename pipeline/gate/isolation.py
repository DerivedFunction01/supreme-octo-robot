#!/usr/bin/env python3
"""Test-isolation state hash: the component form of the
attention check.py proof (plan §4.16). A package's suite
runs wrapped in a snapshot of its real state files; any
difference after the run means a test touched real state,
and the leg fails even when every test passes.

Parameterized the way the attention gate hardcodes it:
a base root, the state subpaths under it, and the first
path components to exclude (its venv form: the state tree
minus the venv directory). Snapshot keys are base-relative
POSIX paths; values are SHA-256 digests.
"""
import hashlib
import os


def state_snapshot(base, subpaths, exclude_first=()):
    """{relative path: sha256} over the given state subpaths
    of base. Keys are base-relative; a file is skipped when
    the first component of its path within its subpath is
    in exclude_first (the attention form: the state tree
    minus the venv directory inside it)."""
    base = os.path.abspath(base)
    snapshot = {}
    for sub in subpaths:
        start = os.path.join(base, sub) if sub else base
        if not os.path.isdir(start):
            continue
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(dirnames)
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                within = os.path.relpath(full, start).replace(
                    os.sep, "/")
                if within.split("/", 1)[0] in exclude_first:
                    continue
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                digest = hashlib.sha256()
                with open(full, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        digest.update(chunk)
                snapshot[rel] = digest.hexdigest()
    return snapshot


def changed_paths(before, after):
    """Sorted paths whose digest differs or that exist on
    only one side of the comparison."""
    return sorted(
        path for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )


class IsolationGuard:
    """Context manager: snapshot on entry; on exit, `changed`
    lists what the wrapped run touched (empty = proof ok)."""

    def __init__(self, base, subpaths, exclude_first=()):
        self.base = base
        self.subpaths = subpaths
        self.exclude_first = tuple(exclude_first)
        self.before = {}
        self.changed = []

    def __enter__(self):
        self.before = state_snapshot(
            self.base, self.subpaths, self.exclude_first)
        return self

    def __exit__(self, *exc):
        after = state_snapshot(
            self.base, self.subpaths, self.exclude_first)
        self.changed = changed_paths(self.before, after)
        return False

    def report(self):
        if self.changed:
            print("==> test-isolation proof FAILED: "
                  "the suite changed real state")
            for path in self.changed:
                print(f"    state changed: {path}")
            return 1
        if self.before:
            print(f"==> test-isolation proof ok "
                  f"({len(self.before)} state file(s))")
        return 0
