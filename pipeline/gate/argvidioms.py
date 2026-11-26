#!/usr/bin/env python3
"""Argv-idioms component: one unified argument parser
owns argv parsing (the D2 contract of the unified-argv
programme), re-expressed as a registry gate leg.

NOT gate.writeruniqueness (the write graph) and not
gate.importisolation (the import graph): this component
guards the parse graph — where argv may be turned into
behaviour. Its pattern of record is the
writer-uniqueness leg: a registry component guarding
where a behaviour may be produced, with the home module
itself never scanned.

The invariant: every operator entry point parses argv
through the unified implementations —
pipeline/platform/argv.py (Python), pipeline/platform/
argv.sh (bash), tools/argv.mjs (JS) — under the one
contract stated in the Python home. A hand-rolled
parsing idiom re-derives the contract per tool, and the
audit's finding was that each re-derivation diverges:
what a mistyped, misplaced, or equals-formed flag does
is re-decided at every site, and the silently-wrong
outcomes surface one incident at a time. The leg bans
the idiom shapes, not any tool's behaviour:

- membership-flag-test (Python, AST): a `"--flag" in
  <argv>` membership test — the membership value take
  and the boolean membership scan share this shape;
  both silently miss the equals form and every
  near-miss token.
- index-flag-extraction (Python, AST): a `.index(...)`
  call on an argv-shaped expression — the unbounded
  value take: it crashes on a trailing flag and never
  sees the equals form.
- known-args-forwarding (Python, AST): a
  `parse_known_args` call — unknown tokens forwarded
  instead of refused.
- argparse-abbreviations (Python, AST): an
  `ArgumentParser(...)` construction without
  `allow_abbrev=False`, judged only where the surface
  is a census entry point (the audited population);
  argparse is otherwise a legitimate library shape.
- single-dollar1-flag-test (shell, token level): a
  `[ "$1" = "--flag" ]` test — the flag honoured in
  exactly one position, a typo silently selecting the
  default behaviour.
- argv-membership (JS, token level):
  `process.argv.includes(` / `argv.includes(` — the
  membership scan in its JS form.
- argv-index (JS, token level): `argv.indexOf(` — the
  index extraction in its JS form.

The unified implementations are the homes and are
never scanned, and neither is this component (its own
text carries the shapes as data). Census entries —
the audited entry points recorded in
pipeline/platform/argv_census.json — are declared
exceptions while their record stands migrated false:
their findings are reported as notes, never failures,
and (unlike declared seams) a census entry with no
matching pattern is not a stale-exception finding —
much of the census is clean argparse whose migration
is a defaults change, not an idiom removal. A census
record flipped to migrated true judges its file in
full. Declared seams in the EXCEPTIONS table below
follow the registry discipline both ways, as the
writer-uniqueness leg's do: reliance without
declaration is an ordinary finding, and a declaration
whose file carries no matching pattern is itself a
finding (stale-exception). An entry for a file outside
the scanned package is not judged by that run.

Findings name file + kind, never content.

Known limits, stated plainly:

- the Python checks are AST-level over direct forms.
  A membership test against a variable holding a flag
  literal, or an index take on an argv copy under
  another name, is a flow pass's business, not this
  leg's — the writer-uniqueness component's limit
  form. The leg guards the direct forms, which are
  the forms the audited trees use.
- the shell and JS checks are token-level: they judge
  the literal idiom shapes named above, not shell or
  JS semantics in general.
- a file that does not parse yields no Python
  findings here; it fails the legs that compile it.

Repo form: the component evaluates over every tracked
source in the tree by default — coverage is never
declared. The census is read from the platform
package's argv_census.json when it stands under the
scan root; a package-scoped run whose root has no
census judges without it.

Usage (module form, from the pipeline root):
python3 -m gate.argvidioms [--root DIR]
Exit: 0 = no undeclared findings; 1 = findings;
2 = usage error. Standalone, the scanned package's
argvidioms leg declaration (if any) adds its
exceptions to the component table; under the runner,
the leg's exceptions are passed in.
"""
import ast
import json
import os
import re
import sys

from .linecap import enumerate_files, enumerate_tracked_files

# The unified implementations: the homes, never
# scanned. This component stands beside them.
HOMES = {
    "pipeline/platform/argv.py",
    "pipeline/platform/argv.sh",
    "tools/argv.mjs",
    "pipeline/gate/argvidioms.py",
    "argv.py", "argv.sh", "argv.mjs", "argvidioms.py",
}

CENSUS_PATH = "pipeline/platform/argv_census.json"

# Declared seams, in the paths-discipline declaration
# form ({"path": repo-relative path, "kind": reason}).
# Add a path here only together with the seam it names.
EXCEPTIONS = ()

SHELL_DOLLAR1_RE = re.compile(
    r"\[\[?\s+\"?\$\{?1(?::[-?][^}\"]*)?\}?\"?\s+==?\s+\"--")
JS_MEMBERSHIP_RE = re.compile(r"\bargv\.includes\(")
JS_INDEX_RE = re.compile(r"\bargv\.indexOf\(")


def _mentions_argv(node):
    """True when an expression's own names/attributes
    mention argv or args — the shape test for the
    container an idiom extracts from."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in ("argv", "args"):
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in ("argv", "args"):
            return True
    return False


def _is_flag_literal(node):
    return (isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("--"))


def scan_python_source(text):
    """[(lineno, kind)] — the Python idiom checks over
    one file's source. The argparse-abbreviations check
    is census-gated and lives in scan_python_for, which
    knows the file's census standing."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            if any(isinstance(op, (ast.In, ast.NotIn))
                   for op in node.ops):
                operands = [node.left] + list(node.comparators)
                if any(_is_flag_literal(o) for o in operands) \
                        and any(_mentions_argv(o) for o in operands):
                    findings.append(
                        (node.lineno, "membership-flag-test"))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr == "index" and _mentions_argv(func.value):
                    findings.append(
                        (node.lineno, "index-flag-extraction"))
                elif func.attr == "parse_known_args":
                    findings.append(
                        (node.lineno, "known-args-forwarding"))
    findings.sort()
    return findings


def scan_python_for(text, is_census):
    """scan_python_source plus, for a census entry
    point, the argparse abbreviation check."""
    findings = scan_python_source(text)
    if not is_census:
        return findings
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return findings
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) \
            else func.id if isinstance(func, ast.Name) else ""
        if name != "ArgumentParser":
            continue
        disabled = any(
            kw.arg == "allow_abbrev"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is False
            for kw in node.keywords)
        if not disabled:
            findings.append(
                (node.lineno, "argparse-abbreviations"))
    findings.sort()
    return findings


def scan_shell_source(text):
    """[(lineno, kind)] — the shell idiom check."""
    return [(lineno, "single-dollar1-flag-test")
            for lineno, line in enumerate(text.splitlines(), start=1)
            if SHELL_DOLLAR1_RE.search(line)]


def scan_js_source(text):
    """[(lineno, kind)] — the JS idiom checks."""
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if JS_MEMBERSHIP_RE.search(line):
            findings.append((lineno, "argv-membership"))
        if JS_INDEX_RE.search(line):
            findings.append((lineno, "argv-index"))
    findings.sort()
    return findings


def declared_kind(relpath, exceptions):
    """The declared kind covering relpath (repo-relative),
    or None. Exact path, or a subtree with a trailing
    '/**' — the paths-discipline declaration form."""
    for decl in exceptions:
        path = decl["path"]
        if path.endswith("/**"):
            prefix = path[:-3]
            if relpath == prefix or relpath.startswith(prefix + "/"):
                return decl["kind"]
        elif relpath == path:
            return decl["kind"]
    return None


def _declared_files(relpath, exceptions):
    return [decl for decl in exceptions
            if declared_kind(relpath, [decl]) is not None]


def evaluate(files, exceptions, census=None):
    """(rows, failures) over {repo-relative path: source
    text}. Rows are every finding: (relpath, lineno,
    kind, declared) with declared the covering
    declaration's kind or None; a stale-exception row
    carries lineno 0. Failures are the undeclared
    findings plus the stale declarations. Homes are
    never scanned. census maps repo-relative paths to
    their migrated flag: an unmigrated census entry's
    findings are notes under the census kind and never
    failures, with no stale discipline."""
    census = census or {}
    exceptions = list(EXCEPTIONS) + list(exceptions)
    rows = []
    failures = []
    scanned = {relpath: text for relpath, text in files.items()
               if relpath not in HOMES}
    found_in = {}
    for relpath in sorted(scanned):
        kind = declared_kind(relpath, exceptions)
        census_kind = None
        if relpath in census and not census[relpath]:
            census_kind = "census entry — migration pending"
        effective = kind if kind is not None else census_kind
        text = scanned[relpath]
        if relpath.endswith((".py",)) or _looks_python(relpath, text):
            findings = scan_python_for(text, relpath in census)
        elif relpath.endswith((".sh",)):
            findings = scan_shell_source(text)
        elif relpath.endswith((".mjs", ".js", ".ts", ".tsx")):
            findings = scan_js_source(text)
        else:
            findings = _scan_any(text)
        for lineno, finding in findings:
            row = (relpath, lineno, finding, effective)
            rows.append(row)
            found_in.setdefault(relpath, []).append(finding)
            if effective is None:
                failures.append(row)
    for decl in exceptions:
        matched = [relpath for relpath in scanned
                   if decl in _declared_files(relpath, [decl])]
        if matched and not any(found_in.get(relpath)
                               for relpath in matched):
            row = (decl["path"], 0, "stale-exception",
                   decl["kind"])
            rows.append(row)
            failures.append(row)
    rows.sort(key=lambda row: (row[0], row[1], row[2]))
    failures.sort(key=lambda row: (row[0], row[1], row[2]))
    return rows, failures


def _looks_python(relpath, text):
    if "." in relpath.rsplit("/", 1)[-1]:
        return False
    first = text.splitlines()[0] if text.splitlines() else ""
    return first.startswith("#!") and "python" in first


def _scan_any(text):
    """An extensionless script judged by its shebang:
    python sources take the Python checks, bash/sh
    sources the shell check."""
    first = text.splitlines()[0] if text.splitlines() else ""
    if first.startswith("#!") and "python" in first:
        return scan_python_source(text)
    if first.startswith("#!") and ("bash" in first or "sh" in first):
        return scan_shell_source(text)
    return []


def _is_source(rel, full):
    if rel.endswith((".py", ".sh", ".mjs", ".js", ".ts", ".tsx")):
        return True
    if "." in rel.rsplit("/", 1)[-1]:
        return False
    try:
        with open(full, encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith("#!")


def load_census(repo_root):
    """{repo-relative path: migrated} from the platform
    package's census under repo_root, or {} when no
    census stands there."""
    path = os.path.join(str(repo_root), CENSUS_PATH)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return {entry["path"]: bool(entry.get("migrated"))
            for entry in data.get("entries", [])}


def scan(root, repo_root, exceptions=(), exclude=(),
         tracked=False):
    """(rows, failures, scanned) over the sources under
    root (a package dir, or the repo root for the
    repo-scoped leg)."""
    files = {}
    scanned = 0
    enumerate = enumerate_tracked_files if tracked \
        else enumerate_files
    for rel in enumerate(str(root)):
        repo_rel = os.path.relpath(
            os.path.join(str(root), rel), str(repo_root)
        ).replace(os.sep, "/")
        if any(repo_rel == ex or repo_rel.startswith(ex + "/")
               for ex in exclude):
            continue
        full = os.path.join(str(root), rel)
        if not os.path.isfile(full) or not _is_source(rel, full):
            continue
        with open(full, encoding="utf-8", errors="replace") as fh:
            files[repo_rel] = fh.read()
        scanned += 1
    rows, failures = evaluate(
        files, list(exceptions), census=load_census(repo_root))
    return rows, failures, scanned


def render(rows, failures, scanned=None):
    """The leg's output block, the paths-discipline
    form: declared findings as notes with their kind,
    undeclared as failures, stale declarations named."""
    lines = []
    for relpath, lineno, kind, declared in rows:
        if kind == "stale-exception":
            lines.append(
                f"ARGV-IDIOMS: {relpath}: "
                f"stale exception (declared: {declared}) — "
                f"no matching pattern in this file")
        elif declared is None:
            lines.append(
                f"ARGV-IDIOMS: {relpath}:{lineno}: "
                f"{kind} outside the unified argv parser")
        else:
            lines.append(
                f"argv-idioms: note - {relpath}:{lineno}: "
                f"{kind} (declared: {declared})")
    if failures:
        lines.append(
            f"argv-idioms: {len(failures)} "
            f"undeclared violation(s)")
    elif scanned is not None:
        lines.append(
            f"argv-idioms: ok ({scanned} files scanned)")
    else:
        lines.append("argv-idioms: ok")
    return lines


def _leg_exceptions(root):
    """The scanned package's own argvidioms leg
    exceptions from its gate.json, for a standalone run;
    the component table always applies."""
    decl_path = os.path.join(root, "gate.json")
    if not os.path.isfile(decl_path):
        return []
    with open(decl_path, encoding="utf-8") as fh:
        decl = json.load(fh)
    for leg in decl.get("legs", []):
        if leg.get("leg") == "argvidioms":
            return leg.get("exceptions", [])
    return []


def main(argv):
    root = os.getcwd()
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = os.path.abspath(args.pop(0))
        else:
            print("usage: argvidioms.py [--root DIR]",
                  file=sys.stderr)
            return 2
    rows, failures, scanned = scan(
        root, root, _leg_exceptions(root))
    for line in render(rows, failures, scanned):
        print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
