#!/usr/bin/env python3
"""Line-cap component: no tracked code file over the cap
(800 lines; a file AT the cap passes, over the cap is a
finding), and no file in the creep band growing past its
committed count.

Repo-scoped by default: the composed gate runs this
once over the whole tracked tree — every tracked code
file counts, and no package or
folder declares or registers for coverage. The repo
population is tracked files (git ls-files --cached) with
a code extension; the find fallback applies the same
extension and skip rules in a git-less tree. (The older
per-package form survives as this module's scan() over a
package root, with the surviving enumeration — git
ls-files --cached --others --exclude-standard, the
scheduler check.sh form — because a pre-landing check on
a package counts the file about to be added. The folder
census deliberately does NOT share that choice: it counts
tracked files only. The asymmetry is stated here and in
foldercensus.py.)

The creep band (owner doctrine: a file approaching the
cap is a warning to decompose, not to work around): a
non-test code file at or over BAND (700) and not over
the cap is listed on every run, and may not grow — its
baseline is its committed line count at HEAD, read via
git show, and a working-tree count over that baseline is
a finding. There is no register and no allowlist: git is
the baseline. Test suites are exempt from the band (a
suite grows by cases, not by behaviour mixture); they
stay under the hard cap. Shared test infrastructure is
not a suite and stays in the band.

One behaviour is carried from the retired shell form's
successor by design: the enumeration completes and
reports every finding, noting enumerated files missing
from the working tree, instead of dying mid-loop.

Usage: linecap.py [--root DIR] [--cap N] [--band N]
       [--tracked] [--ext .py,.ts]
Exit: 0 = no findings; 1 = findings (over cap, or a band
file grown past its committed count).
"""
import os
import re
import subprocess
import sys
from collections import namedtuple

DEFAULT_CAP = 800
DEFAULT_BAND = 700
CODE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".mjs", ".css")

ScanResult = namedtuple(
    "ScanResult", ["findings", "missing", "band", "growth"])

_TEST_SUITE_RE = re.compile(
    r"(^test_.*|.*_test|.*\.test|.*\.spec)\."
    r"(py|ts|tsx|js|mjs)$")
_INFRA_BASENAMES = {
    "conftest.py", "support.py", "helpers.py", "fakes.py",
    "fixtures.py", "factories.py",
}


def is_test_suite(relpath):
    """A test suite by file name (Steam's form): test_*,
    *_test, *.test.*, *.spec.*. Shared test infrastructure
    (conftest/support/fakes and the like) is not a suite,
    wherever it lives."""
    base = relpath.rsplit("/", 1)[-1]
    if base in _INFRA_BASENAMES:
        return False
    return bool(_TEST_SUITE_RE.match(base))


def enumerate_files(root):
    """Package-relative paths, the surviving enumeration
    (cached + others, .gitignore-respecting)."""
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
    return _walk(root)


def enumerate_tracked_files(root):
    """Repo-relative tracked paths only (git ls-files
    --cached); the walk fallback in a git-less tree."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached"],
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
    return _walk(root)


def _walk(root):
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


def committed_lines(root, relpath):
    """The file's line count as committed at HEAD, or
    None when it has no committed version (a new file —
    the band lists it; the growth ban takes its baseline
    from its first commit)."""
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{relpath}"],
            cwd=root, capture_output=True, timeout=60,
        )
        if out.returncode == 0:
            return out.stdout.count(b"\n")
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def scan(root, cap=DEFAULT_CAP, band=DEFAULT_BAND,
         extensions=None, tracked=False, baseline=False):
    """ScanResult over the tree at root.

    findings: [(relpath, lines)] over the cap.
    band: [(relpath, lines)] at/over band, not over the
    cap, not a test suite — listed on every run.
    growth: [(relpath, lines, baseline)] band files whose
    count exceeds their committed baseline (only when
    baseline=True; the repo leg passes it, package-form
    callers in a package root pass their package-relative
    paths against the repo HEAD the same way).
    missing: enumerated files absent from the working
    tree."""
    findings = []
    band_rows = []
    growth = []
    missing = []
    paths = (enumerate_tracked_files(root) if tracked
             else enumerate_files(root))
    for relpath in paths:
        if extensions is not None and not relpath.endswith(
                tuple(extensions)):
            continue
        full = os.path.join(root, relpath)
        if not os.path.isfile(full):
            missing.append(relpath)
            continue
        lines = count_lines(full)
        if lines > cap:
            findings.append((relpath, lines))
        elif lines >= band and not is_test_suite(relpath):
            band_rows.append((relpath, lines))
            if baseline:
                base = committed_lines(root, relpath)
                if base is not None and lines > base:
                    growth.append((relpath, lines, base))
    findings.sort(key=lambda row: (-row[1], row[0]))
    band_rows.sort(key=lambda row: (-row[1], row[0]))
    return ScanResult(findings, missing, band_rows, growth)


def scan_repo(root, cap=DEFAULT_CAP, band=DEFAULT_BAND):
    """The repo-scoped form the composed gate runs: the
    whole tracked tree, code extensions, growth baselines
    from HEAD."""
    return scan(root, cap=cap, band=band,
                extensions=CODE_EXTENSIONS, tracked=True,
                baseline=True)


def render(result, cap=DEFAULT_CAP, band=DEFAULT_BAND):
    """The leg's output block as printed in the gate."""
    lines = []
    for relpath, count in result.band:
        lines.append(
            f"line-cap: BAND {relpath}: {count} lines "
            f"(cap {cap}; decompose along real seams — "
            "growth past the committed count is a finding)")
    for relpath, count, base in result.growth:
        lines.append(
            f"LINE LIMIT: {relpath} grew in the band: "
            f"{base} committed -> {count} lines")
    for relpath, count in result.findings:
        lines.append(
            f"LINE LIMIT: {relpath} has {count} lines "
            f"(cap {cap})")
    for relpath in result.missing:
        lines.append(
            f"line-limit: note - enumerated file missing "
            f"from the working tree: {relpath}")
    if not result.findings and not result.growth:
        lines.append(
            f"line-limit: ok ({len(result.band)} file(s) "
            f"in the {band}+ band)")
    return lines


def main(argv):
    root = os.getcwd()
    cap = DEFAULT_CAP
    band = DEFAULT_BAND
    tracked = False
    extensions = None
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = os.path.abspath(args.pop(0))
        elif arg == "--cap" and args:
            cap = int(args.pop(0))
        elif arg == "--band" and args:
            band = int(args.pop(0))
        elif arg == "--tracked":
            tracked = True
        elif arg == "--ext" and args:
            extensions = tuple(args.pop(0).split(","))
        else:
            print("usage: linecap.py [--root DIR] [--cap N] "
                  "[--band N] [--tracked] [--ext .py,.ts]",
                  file=sys.stderr)
            return 2
    result = scan(root, cap=cap, band=band,
                  extensions=extensions, tracked=tracked,
                  baseline=tracked)
    for line in render(result, cap, band):
        print(line)
    return 1 if (result.findings or result.growth) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
