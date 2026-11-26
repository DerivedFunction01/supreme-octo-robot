#!/usr/bin/env python3
"""Portability scanner: tracked text references only what a
fresh clone resolves.

The pipeline gate's portability/denylist component (plan
§4.10, completed by §4.16): lifted whole from the scheduler's
tools/portability_scan.py, which now re-points here. One
component serves every package; one untracked denylist per
deployment feeds the personal-literal leg.

Legs, all generic and always on (a finding fails the gate):

- abs-path: absolute paths (POSIX roots for home, users,
  opt, tmp; Windows drive forms).
- home-path: home-anchored tilde paths. The sanctioned
  anchors (${REPO}, ${WS}, ${HOME}) are dollar forms, not
  tilde forms, and never fire.
- untracked-ref: a specific plan file under .plans/, or a
  dated home-memory log path. A bare directory-convention
  mention does not fire; a specific file inside does.

Plus the personal-literal leg:

- denylist: personal literals (the owner's name included)
  from an untracked file, resolved env-first
  (SCHEDULER_DENYLIST_FILE), else state/denylist.txt under
  the scan root when present. Matching is case-insensitive:
  the matching and list-parsing semantics live in
  denylist_match.py beside this component (the one home,
  a synced mirror of the starter scanner's module); this
  component consumes them and never re-implements the
  comparison. Absent, the leg prints a one-line NOTICE and skips.
  Findings are reported in their own section and fail only
  under --fail-on-denylist, which the gate passes whenever
  a denylist is provisioned — so an installation that has
  one gates on it, and a fresh clone without one stays
  green. The list file itself is never scanned. No personal
  literal ever appears in tracked source, split or otherwise.

Exceptions: only files named in EXCEPTION_FILES may carry
directive lines of the form

    portability-exception: <exact string> <em-dash> <reason>

where <em-dash> is a literal em-dash character. A directive exempts
that one exact matched string in that one file. A
directive-shaped line in any other file is itself a
finding, and a match in a registry file that its
directives do not name is an ordinary finding — reliance
without declaration is not an exception. Exceptions
apply to the generic legs only, never to the denylist.

Findings never print matched content: rule, path, line.

Usage: portability.py [--root DIR] [--fail-on-denylist]
Exit: 0 = no failing findings; 1 = findings; 2 = usage error.
The gate runner always passes --root (the package root being
gated); standalone, the root defaults to the current dir.
"""
import os
import re
import subprocess
import sys

try:
    from . import denylist_match
except ImportError:  # standalone script use
    import denylist_match

SCAN_SUFFIXES = (
    ".py", ".md", ".toml", ".yaml", ".yml", ".json",
    ".ts", ".tsx", ".js", ".mjs", ".sh", ".tmpl", ".txt",
)
SCAN_NAMES = {"bin/sched", ".gitignore"}
WALK_SKIP_DIRS = {".git", "state", ".plans", "__pycache__", "node_modules"}

# Files that may declare portability-exception directives.
# Add a path here only together with the directive it relies
# on, in that file. Paths are scan-root relative: each package
# gate scans with its own root, so an entry names the file
# within the package that carries it (the venue package's
# tool-layout and specimen strings, and two workrecord test
# files' synthetic plan-file fixture names).
EXCEPTION_FILES = (
    # venue
    "AGENTS.md",
    "adapters/colab/snippets/limits/bert_batch_ramp.py",
    "adapters/colab/snippets/probes/bootstrap_remote.py",
    "adapters/colab/snippets/lease/unassign_orphans.py",
    "config/repos.example.json",
    "config/transient.json",
    "docs/auth.md",
    "ops/bootstrap_local.sh",
    "sync/cli.py",
    "sync/transfer.py",
    "tests/env/test_env_registry_unit.py",
    "tests/fixtures/env_fixtures.py",
    "tests/fixtures/fake_colab.py",
    "tests/fixtures/venue_preflight_fixture.py",
    "tests/guards/test_repo_portability.py",
    "tests/sync/test_cli_output_parse.py",
    "ui/README.md",
    # workrecord (the two production carriers name the harness's
    # standing active-plan declaration file — the package's own
    # data contract; the two test files carry synthetic plan-file
    # fixture names)
    "lib/derived/active.py",
    "wbcli/drivers.py",
    "tests/harness/test_doctor.py",
    "tests/lib/test_attribution.py",
    # repo root (the rootportability leg's scan root: the
    # artifact tree's SDK tarball specifier — the commissioned
    # consumption form, no relative specifier exists)
    "artifact/package.json",
)

_MARKER = "portability" + "-exception:"
EXCEPTION_DIRECTIVE_RE = re.compile(
    re.escape(_MARKER) + r"\s*(\S+)\s+—\s*(\S.*)$"
)

_BOUNDARY = r"(?<![\w/.-])"
_PATH_TAIL = r"[\w.-]+(?:/[\w.-]+)*"

ABS_HOME_RE = re.compile(_BOUNDARY + "/home/" + _PATH_TAIL)
ABS_USERS_RE = re.compile(_BOUNDARY + "/Users/" + _PATH_TAIL)
ABS_OPT_RE = re.compile(_BOUNDARY + "/opt/" + _PATH_TAIL)
ABS_TMP_RE = re.compile(_BOUNDARY + "/tmp/" + _PATH_TAIL)
_DRIVE_RE = re.compile(
    r"(?<![\w])[A-Za-z]" + ":" + r"\\"
    + r"|(?<=[\s\"'(=])[A-Za-z]" + ":" + "/"
)
TILDE_RE = re.compile(_BOUNDARY + r"~/[\w.-][\w./-]*")

PLAN_FILE_RE = re.compile(
    r"\.plans/(?!finished/)[\w.-]+\.(?:md|json|ya?ml)"
    r"|\.plans/(?!finished/)[\w.-]+/"
    r"|\.plans/finished/[\w.-]+\.(?:md|json|ya?ml)"
)
DATED_MEMORY_RE = re.compile(_BOUNDARY + r"memory/\d{4}-\d{2}-\d{2}")

GENERIC_LEGS = (
    ("portability/abs-path", ABS_HOME_RE),
    ("portability/abs-path", ABS_USERS_RE),
    ("portability/abs-path", ABS_OPT_RE),
    ("portability/abs-path", ABS_TMP_RE),
    ("portability/abs-path", _DRIVE_RE),
    ("portability/home-path", TILDE_RE),
    ("portability/untracked-ref", PLAN_FILE_RE),
    ("portability/untracked-ref", DATED_MEMORY_RE),
)


def _scannable(relpath):
    if relpath in SCAN_NAMES:
        return True
    return relpath.endswith(SCAN_SUFFIXES)


def _tracked_files(root):
    """Repo-relative paths to scan: git's tracked set when
    git answers, else a walk with the runtime dirs skipped
    (a fresh copy may have no .git at all)."""
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files", "--cached"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            return sorted(
                p for p in out.stdout.splitlines()
                if p and _scannable(p)
                and os.path.isfile(os.path.join(root, p))
            )
    except (OSError, subprocess.SubprocessError):
        pass
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in WALK_SKIP_DIRS]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, name)
            relpath = os.path.relpath(full, root).replace(os.sep, "/")
            if _scannable(relpath):
                found.append(relpath)
    return sorted(found)


def _read_lines(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return None


def _declared_exceptions(relpath, lines):
    """Exact strings this file's directives exempt — only
    registry files may declare any."""
    if relpath not in EXCEPTION_FILES:
        return set()
    found = set()
    for line in lines:
        match = EXCEPTION_DIRECTIVE_RE.search(line)
        if match:
            found.add(match.group(1))
    return found


def scan_generic(root, files):
    findings = []
    for relpath in files:
        lines = _read_lines(os.path.join(root, relpath))
        if lines is None:
            continue
        exceptions = _declared_exceptions(relpath, lines)
        for lineno, line in enumerate(lines, start=1):
            if relpath not in EXCEPTION_FILES and EXCEPTION_DIRECTIVE_RE.search(line):
                findings.append(
                    ("portability/exception-misuse", relpath, lineno)
                )
            for rule, pattern in GENERIC_LEGS:
                for match in pattern.finditer(line):
                    if match.group(0) in exceptions:
                        continue
                    findings.append((rule, relpath, lineno))
    return findings


def _denylist_path(root):
    """(path, notice) — the env var wins; a set-but-unreadable
    env path reports a NOTICE rather than falling through."""
    env = os.environ.get("SCHEDULER_DENYLIST_FILE")
    if env:
        if os.path.isfile(env):
            return env, None
        return None, (
            "denylist: NOTICE - SCHEDULER_DENYLIST_FILE is set but "
            "unreadable; personal-literal leg skipped"
        )
    candidate = os.path.join(root, "state", "denylist.txt")
    if os.path.isfile(candidate):
        return candidate, None
    return None, (
        "denylist: NOTICE - no denylist provisioned (env "
        "SCHEDULER_DENYLIST_FILE or state/denylist.txt); "
        "personal-literal leg skipped"
    )


def scan_denylist(root, files):
    """(findings, notice, provisioned) — findings carry rule,
    path, line; the literal itself is never reported."""
    path, notice = _denylist_path(root)
    if path is None:
        return [], notice, False
    with open(path, encoding="utf-8") as fh:
        literals = denylist_match.parse_literals(fh)
    list_real = os.path.realpath(path)
    findings = []
    for relpath in files:
        full = os.path.join(root, relpath)
        if os.path.realpath(full) == list_real:
            continue
        lines = _read_lines(full)
        if lines is None:
            continue
        for lineno, line in enumerate(lines, start=1):
            if denylist_match.line_matches(line, literals):
                findings.append(("denylist/personal-literal", relpath, lineno))
    return findings, None, True


def denylist_provisioned(root):
    """True when a denylist resolves for this root — the gate
    uses it for the declaration's fail_on_denylist: auto form
    (the retired check.sh passed --fail-on-denylist exactly
    when a denylist was provisioned)."""
    path, _notice = _denylist_path(root)
    return path is not None


def main(argv):
    root = os.getcwd()
    fail_on_denylist = False
    # The unified contract's value forms (BT12): the
    # --flag=value form expands to the two-token form, so
    # both are the same flag. (linecap.expand_equals,
    # inlined: this component's standalone form imports
    # nothing from the package.)
    args = []
    for token in argv:
        if token.startswith("--") and "=" in token:
            name, value = token.split("=", 1)
            args += [name, value]
        else:
            args.append(token)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = os.path.abspath(args.pop(0))
        elif arg == "--fail-on-denylist":
            fail_on_denylist = True
        else:
            print(f"usage: portability.py [--root DIR] "
                  f"[--fail-on-denylist]", file=sys.stderr)
            return 2
    files = _tracked_files(root)
    findings = scan_generic(root, files)
    for rule, relpath, lineno in findings:
        print(f"{rule}: {relpath}:{lineno} (content withheld)")
    denylist_findings, notice, provisioned = scan_denylist(root, files)
    if notice:
        print(notice)
    if provisioned:
        for rule, relpath, lineno in denylist_findings:
            print(f"{rule}: {relpath}:{lineno} (content withheld)")
        print(f"denylist: {len(denylist_findings)} finding(s)"
              + ("" if fail_on_denylist else " (advisory)"))
    failed = bool(findings) or (fail_on_denylist and bool(denylist_findings))
    if not findings:
        print(f"portability: ok ({len(files)} files scanned)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
