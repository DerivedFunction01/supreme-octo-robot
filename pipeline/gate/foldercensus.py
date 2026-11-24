#!/usr/bin/env python3
"""Folder-census component: no long lists of flat files in
a single folder (a flat folder is the same
serialization defect as a fat file — one folder's growth
serializes every change that has to find, order, or merge
files in it).

The census counts tracked files per directory over the
tracked enumeration (gate.linecap's
enumerate_tracked_files: git ls-files --cached, run at
the repo root). Tracked only: untracked staging in a
working tree is not the tree the verdict names, and an
earlier form of
this census that counted untracked files failed a clean
tracked tree on venue job staging. Every folder counts
by default — a folder is never registered into the
census; the family declarations below are the exception
form, not the entry ticket. Folders at or over the warn
threshold print in the gate output on every run, so an
approach is visible before it trips:

- at or over WARN (16): a warning row;
- at or over FAIL (24): the leg fails —

unless the folder is DECLARED a family: single-kind
folders (a jobs registry, fixtures, schemas, snippets,
bin scripts, held archive copies, test modules) are flat
by form, not by defect. A family is declared in a
package's gate.json as data — {"path": <repo-relative
folder>, "kind": <the one kind it holds>} — and is a
structural fact reviewed like code, never a defect
exemption: the census still reports the folder, marked
with its kind, and the declaration covers exactly that
path — or, with a trailing "/**", that folder's whole
subtree (held archive copies live in per-source
subfolders).

Thresholds are the composed gate's config: the gate
package's gate.json declares them on its foldercensus
leg (warn/fail); the values here are the defaults.
"""
from collections import Counter
from pathlib import PurePosixPath

from .linecap import enumerate_tracked_files

DEFAULT_WARN = 16
DEFAULT_FAIL = 24


def count_by_folder(relpaths):
    """Direct tracked files per folder: {folder: count},
    folders repo-relative ('' is the repo root)."""
    counts = Counter()
    for relpath in relpaths:
        folder = PurePosixPath(relpath).parent.as_posix()
        counts["" if folder == "." else folder] += 1
    return dict(counts)


def is_family(folder, families):
    """The declared kind covering folder, or None. A
    declaration covers its exact path, or a whole subtree
    when its path ends in '/**'."""
    for decl in families:
        path = decl["path"]
        if path.endswith("/**"):
            prefix = path[:-3]
            if folder == prefix or folder.startswith(prefix + "/"):
                return decl["kind"]
        elif folder == path:
            return decl["kind"]
    return None


def evaluate(counts, families, warn=DEFAULT_WARN,
             fail=DEFAULT_FAIL):
    """(rows, failures). Rows cover every folder at or
    over warn, sorted by count descending then path:
    (folder, count, status, kind) with status 'family',
    'warn', or 'fail'. Failures are the undeclared folders
    at or over fail."""
    rows = []
    failures = []
    for folder, count in counts.items():
        if count < warn:
            continue
        kind = is_family(folder, families)
        if kind is not None:
            rows.append((folder, count, "family", kind))
        elif count >= fail:
            rows.append((folder, count, "fail", None))
            failures.append(folder)
        else:
            rows.append((folder, count, "warn", None))
    rows.sort(key=lambda row: (-row[1], row[0]))
    return rows, failures


def scan(root, families, warn=DEFAULT_WARN, fail=DEFAULT_FAIL):
    """Census the tree at root (repo-relative enumeration)
    and evaluate it against the declared families."""
    counts = count_by_folder(enumerate_tracked_files(str(root)))
    return evaluate(counts, families, warn, fail)


def render(rows, failures, warn=DEFAULT_WARN, fail=DEFAULT_FAIL):
    """The census block as printed in the gate output."""
    lines = ["== folder census (tracked files per folder; "
             f"warn {warn}, fail {fail})"]
    if not rows:
        lines.append(f"folder-census: ok (no folder at {warn})")
    for folder, count, status, kind in rows:
        shown = folder if folder else "(repo root)"
        if status == "family":
            lines.append(
                f"folder-census: {shown}: {count} files "
                f"(family: {kind})")
        elif status == "warn":
            lines.append(
                f"folder-census: WARN {shown}: {count} files "
                f"(fail at {fail})")
        else:
            lines.append(
                f"folder-census: FAIL {shown}: {count} files "
                f"(at/over the {fail} limit, no family "
                "declaration)")
    return lines
