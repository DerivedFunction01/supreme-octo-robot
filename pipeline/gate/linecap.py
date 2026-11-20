#!/usr/bin/env python3
"""Line-cap component: no tracked source file at or over the
cap (800 lines; spec Rulings — modularity is enforced
mechanically, counted the way wc -l counts).

The enumeration is the scheduler check.sh form, the one
surviving enumeration (plan §4.16): git ls-files --cached
--others --exclude-standard run in the package root, with
the .git/* and state/* skips; when git cannot answer, the
same script's find fallback. The dispatch package's
find-based variant retires with its check.sh.

One behavior differs from the retired shell form, by
design: the shell script died mid-loop when an enumerated
file was missing from the working tree (an indexed file a
sibling step had moved), before printing the findings it
had already collected. The component completes the
enumeration, reports every over-cap file, and notes the
missing ones. The verdict is unchanged: a tree the shell
gate failed at this leg, this leg fails.

Usage: linecap.py [--root DIR] [--cap N]
Exit: 0 = no file at or over the cap; 1 = findings.
"""
import os
import subprocess
import sys

DEFAULT_CAP = 800


def enumerate_files(root):
    """Package-relative paths, the surviving enumeration."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others",
             "--exclude-standard"],
            cwd=root, capture_output=True, text=True, timeout=60,
        )
        if out.returncode == 0:
            return [
                p for p in out.stdout.splitlines()
                if p and not p.startswith(".git/")
                and not p.startswith("state/")
            ]
    except (OSError, subprocess.SubprocessError):
        pass
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        dirnames[:] = [
            d for d in dirnames
            if d != ".git" and not (
                rel_dir == "." and d == "state")
        ]
        for name in filenames:
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            found.append(rel)
    return sorted(found)


def count_lines(path):
    """wc -l semantics: the number of newline bytes."""
    count = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            count += chunk.count(b"\n")
    return count


def scan(root, cap=DEFAULT_CAP):
    """(findings, missing) — findings are (relpath, lines)."""
    findings = []
    missing = []
    for relpath in enumerate_files(root):
        full = os.path.join(root, relpath)
        if not os.path.isfile(full):
            missing.append(relpath)
            continue
        lines = count_lines(full)
        if lines >= cap:
            findings.append((relpath, lines))
    return findings, missing


def main(argv):
    root = os.getcwd()
    cap = DEFAULT_CAP
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = os.path.abspath(args.pop(0))
        elif arg == "--cap" and args:
            cap = int(args.pop(0))
        else:
            print("usage: linecap.py [--root DIR] [--cap N]",
                  file=sys.stderr)
            return 2
    findings, missing = scan(root, cap)
    for relpath, lines in findings:
        print(f"LINE LIMIT: {relpath} has {lines} lines")
    for relpath in missing:
        print(f"line-limit: note - enumerated file missing "
              f"from the working tree: {relpath}")
    if findings:
        return 1
    print("line-limit: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
