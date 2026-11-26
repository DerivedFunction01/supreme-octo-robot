#!/usr/bin/env python3
"""Import-isolation component: a package imports nothing
from sibling surfaces (AC-14 invariant (a), re-expressed
as a registry gate leg).

NOT gate.isolation — that component is the test-isolation
state hash (a suite runs wrapped in a snapshot of its real
state files, and any difference fails the leg). This
component guards a different invariant, the import graph
between surfaces; the names stay visibly distinct because
the invariants are distinct.

The scan is AST-level: every tracked Python source in the
package is parsed, and every import statement (import x,
from x import ...) whose top-level root names a sibling
package is a finding. The forbidden roots are the composed
package list minus the package itself. The pipeline
packages import by their directory names — pipeline/ is
the import root the targeting declarations name
(import_roots ".." against the package root) — so the
package names ARE the import roots: attention, dispatch,
evaluation, gate, platform, registry, scheduling, venue,
workrecord (plus the frontend declarations, whose names
are not import roots any package uses).

Never findings:

- relative imports (from . import ..., from ..x import
  ...) — they resolve inside the package by construction;
- imports of the package's own root;
- stdlib and third-party roots — anything outside the
  composed package list.

Findings name file + imported root, never content.

Exceptions — a ruling that one specific sibling import
is by design (the bootstrap form: a package's own
provisioning script importing the gate package's venv
builder — the gate package is the harness's foundation
layer, and the venv builder is by design one home).
Declared in the package's own gate.json, on the
importisolation leg itself:

    "exceptions": [
      {"path": "init_venv.py", "root": "gate",
       "kind": "bootstrap"}
    ]

- path: the importing file, package-relative — the
  paths-discipline form: exact path, no globs;
- root: the sibling root the declaration covers; a
  declaration covers only imports of that root in that
  file;
- kind: the ruling's name, carried into the output.

Semantics, the registry discipline both ways (the
portability / writer-uniqueness form): a finding whose
file and imported root match a declaration is reported
as a note (exceptioned, with its kind), never a
failure. A declaration whose file is scanned but
carries no import of the declared root is itself a
failure (stale-exception, reported at line 0). A
declaration naming a file the scan does not cover is
not judged by that run. Undeclared findings behave
exactly as without the mechanism, and a package with
no gate.json, no importisolation leg, or no exceptions
key behaves exactly as before it. The declarations are
read by the component from the package root it is
invoked with; the runner's dispatch passes only the
roots, so the leg's declarations travel with the
package, not the runner.

Known limits, stated plainly:

- dynamic imports (importlib.import_module with a literal
  or computed name, __import__) are not import statements;
  they are visible to review, not to this leg — a flow
  pass's business, not this leg's (the paths-discipline
  component's limit form).
- one sibling name, platform, is also a stdlib module
  name. The pipeline platform package carries no
  __init__.py at its root, so a bare import of the name
  resolves to the stdlib module even with pipeline/ on
  sys.path; this leg flags the root by name regardless,
  and a package that means the stdlib module while
  declaring this leg says so in review. No package
  declaring the leg today imports the name at all.
- a file that does not parse yields no findings here; it
  fails the legs that compile it.

Repo form (the runner's repoimportisolation leg): the
invariant is per-package by nature, so the repo leg runs
this component for every composed package automatically
— the population derives from the tree's package set,
never from a per-package declaration. The recorded
exceptions live once, in the gate package's repo leg
declaration (repo-relative paths, rebased per package by
the runner); the per-package leg declarations are
retired.

Usage (module form, from the pipeline root):
python3 -m gate.importisolation [--root DIR]
Exit: 0 = no undeclared findings; 1 = undeclared
findings or stale exceptions; 2 = usage error.
Standalone, the package and its siblings derive from the
gate.json declarations beside the root (the composed list
the runner loads); under the runner, the list is passed in.
"""
import ast
import json
import os
import sys

from .linecap import enumerate_files, expand_equals


def scan_source(text, siblings):
    """[(lineno, root)] — the sibling imports in one
    file's source. Import and ImportFrom nodes anywhere in
    the tree (module level, function level, conditional)
    count; relative imports never do."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in siblings:
                    findings.append((node.lineno, root))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            root = node.module.split(".", 1)[0]
            if root in siblings:
                findings.append((node.lineno, root))
    return findings


def evaluate(files, siblings):
    """Findings over {repo-relative path: source text}:
    [(relpath, lineno, root)], sorted by path then line."""
    findings = []
    for relpath in sorted(files):
        for lineno, root in scan_source(files[relpath], siblings):
            findings.append((relpath, lineno, root))
    return findings


def leg_exceptions(root):
    """The importisolation leg's exception declarations
    from the package's own gate.json: [{"path", "root",
    "kind"}] (the module docstring's schema). [] when
    the file, the leg, or the key is absent, and an
    entry missing a field is not a declaration — a
    package that declares no exceptions behaves exactly
    as one with no gate.json."""
    decl_path = os.path.join(str(root), "gate.json")
    try:
        with open(decl_path, encoding="utf-8") as fh:
            decl = json.load(fh)
    except (OSError, ValueError):
        return []
    for leg in decl.get("legs", []):
        if leg.get("leg") == "importisolation":
            return [
                entry for entry in leg.get("exceptions", [])
                if isinstance(entry, dict)
                and all(key in entry
                        for key in ("path", "root", "kind"))
            ]
    return []


def classify(files, siblings, exceptions):
    """(notes, failures, stale) over {package-relative
    path: source text}, under the leg's declarations:

    - notes: (relpath, lineno, root, kind) — findings a
      declaration covers (same file, same imported root);
    - failures: (relpath, lineno, root) — findings no
      declaration covers, in evaluate()'s form;
    - stale: (path, root, kind) — declarations whose
      file was scanned but carries no import of the
      declared root. A declaration naming a file outside
      the scan is not judged (the registry discipline's
      form)."""
    raw = evaluate(files, siblings)
    covered = {(relpath, root) for relpath, _lineno, root in raw}
    notes = []
    failures = []
    for relpath, lineno, root in raw:
        kind = None
        for decl in exceptions:
            if decl["path"] == relpath and decl["root"] == root:
                kind = decl["kind"]
                break
        if kind is None:
            failures.append((relpath, lineno, root))
        else:
            notes.append((relpath, lineno, root, kind))
    stale = [
        (decl["path"], decl["root"], decl["kind"])
        for decl in exceptions
        if decl["path"] in files
        and (decl["path"], decl["root"]) not in covered
    ]
    notes.sort()
    failures.sort()
    stale.sort()
    return notes, failures, stale


class Findings(list):
    """The leg's failing rows: (repo-relative path,
    lineno, imported root) — the shape the runner's
    dispatch reads, whose truthiness is the leg's code.
    A stale exception is a failing row at lineno 0.
    Exceptioned imports are not failures and never enter
    the list; they ride on the .notes attribute
    ((path, lineno, root, kind) rows) and the stale
    declarations' kinds on .stale_kinds, both for the
    render."""

    notes = ()
    stale_kinds = {}


def _is_python_source(rel, full):
    """A .py file, or an extensionless script whose shebang
    names python (the tree's bin/ entry scripts) — the
    paths-discipline component's source test, in its form."""
    if rel.endswith(".py"):
        return True
    if "." in rel.rsplit("/", 1)[-1]:
        return False
    try:
        with open(full, encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    return first.startswith("#!") and "python" in first


def scan(root, repo_root, siblings, exceptions=None):
    """(findings, scanned) over the tracked Python sources
    under root (a package dir). The package's own gate.json
    supplies the leg's exception declarations, read here
    when exceptions is None — the runner's per-package
    dispatch passes only the roots. The repo leg passes
    exceptions explicitly (package-relative paths): the
    recorded exceptions live once, in the gate package's
    repo leg declaration. Findings are the failures
    (undeclared imports, plus stale exceptions at
    lineno 0) as a Findings list carrying the exceptioned
    notes; paths are repo-relative; scanned is the number
    of Python sources read."""
    files = {}
    scanned = 0
    for rel in enumerate_files(str(root)):
        full = os.path.join(str(root), rel)
        if not os.path.isfile(full) or not _is_python_source(rel, full):
            continue
        with open(full, encoding="utf-8", errors="replace") as fh:
            files[rel.replace(os.sep, "/")] = fh.read()
        scanned += 1
    if exceptions is None:
        exceptions = leg_exceptions(root)
    notes, failures, stale = classify(files, siblings, exceptions)
    prefix = os.path.relpath(
        str(root), str(repo_root)).replace(os.sep, "/")

    def repo_rel(rel):
        return rel if prefix == "." else prefix + "/" + rel

    findings = Findings(
        [(repo_rel(path), lineno, imported)
         for path, lineno, imported in failures]
        + [(repo_rel(path), 0, imported)
           for path, imported, _kind in stale])
    findings.notes = [
        (repo_rel(path), lineno, imported, kind)
        for path, lineno, imported, kind in notes]
    findings.stale_kinds = {
        (repo_rel(path), imported): kind
        for path, imported, kind in stale}
    findings.sort()
    return findings, scanned


def render(findings, scanned=None):
    """The leg's output block, the paths-discipline form:
    exceptioned imports as notes with their kind,
    undeclared imports and stale exceptions as failures,
    then the verdict line."""
    notes = getattr(findings, "notes", ())
    stale_kinds = getattr(findings, "stale_kinds", {})
    rows = [(path, lineno, imported, kind)
            for path, lineno, imported, kind in notes]
    rows += [(path, lineno, imported, None)
             for path, lineno, imported in findings]
    rows.sort(key=lambda row: (row[0], row[1], row[2]))
    lines = []
    for path, lineno, imported, kind in rows:
        if kind is not None:
            lines.append(
                f"import-isolation: note - {path}:{lineno}: "
                f"imports sibling surface '{imported}' "
                f"(exceptioned: {kind})")
        elif lineno == 0:
            lines.append(
                f"IMPORT-ISOLATION: {path}: stale exception "
                f"(declared: {stale_kinds.get((path, imported), '')})"
                f" — no import of sibling surface "
                f"'{imported}' in this file")
        else:
            lines.append(
                f"IMPORT-ISOLATION: {path}:{lineno}: "
                f"imports sibling surface '{imported}'")
    if findings:
        lines.append(
            f"import-isolation: {len(findings)} "
            f"undeclared violation(s)")
    elif scanned is not None:
        lines.append(
            f"import-isolation: ok ({scanned} files scanned)")
    else:
        lines.append("import-isolation: ok")
    return lines


def composed_siblings(root):
    """(package, siblings) for a standalone run: root's own
    gate.json names the package; every sibling directory
    carrying a gate.json names a composed package (the
    runner's load_packages glob, in local form)."""
    with open(os.path.join(root, "gate.json"),
              encoding="utf-8") as fh:
        package = json.load(fh)["package"]
    names = []
    parent = os.path.dirname(os.path.abspath(root))
    for entry in sorted(os.listdir(parent)):
        decl = os.path.join(parent, entry, "gate.json")
        if os.path.isfile(decl):
            with open(decl, encoding="utf-8") as fh:
                names.append(json.load(fh)["package"])
    return package, [name for name in names if name != package]


def main(argv):
    root = os.getcwd()
    args = expand_equals(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = os.path.abspath(args.pop(0))
        else:
            print("usage: importisolation.py [--root DIR]",
                  file=sys.stderr)
            return 2
    try:
        _package, siblings = composed_siblings(root)
    except (OSError, KeyError, ValueError) as exc:
        print(f"import-isolation: no package declaration "
              f"at {root}: {exc}", file=sys.stderr)
        return 2
    findings, scanned = scan(root, root, siblings)
    for line in render(findings, scanned):
        print(line)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
