"""Paths-discipline component: one paths spine owns path
derivation (owner direction 2026-11-13, on the one-spine
form: a foundation resolver plus per-area resolvers, every
consumer importing from them — which is why a packaging
change touches only the resolvers).

This leg guards the discipline mechanically. In a scanned
package's tracked Python sources it fails on:

- root climbs — a derivation that walks UP from a module's
  own location to a package/repo root: nested dirname
  chains over the file dunder, the pathlib parents[N]
  form (N >= 1), parent-chain forms, and ".." join
  segments in a file-dunder expression;
- cwd roots — the cwd accessors used as a root;
- hardcoded roots — string literals anchored at a home
  directory path.

What it does NOT flag (the discipline's own forms):

- the paths modules themselves — any file named paths.py
  or paths.sh IS the derivation home; its arithmetic is
  the one sanctioned derivation;
- the bootstrap — an expression that loads a paths module
  by path (it references paths.py / paths.sh) is how a
  consumer reaches the spine before the spine is
  importable; it derives nothing of its own;
- module-relative resource reads (census class (c)) — a
  single-level derivation from a module's own directory
  (dirname(abspath(__file__)), Path(__file__).parent) to
  its own sibling assets never leaves the module's dir;
- declared exceptions — per-file or subtree declarations
  in the leg's config, as data beside the leg
  ({"path": <repo-relative>, "kind": <why>}), the folder
  census's family form: a structural fact reviewed like
  code. Declared findings are still reported, marked with
  their kind; they never fail the leg. Test trees are the
  standing declaration (census class (d), fixture
  location), as are whole subtrees a parallel lane owns
  (named in the leg's "exclude", skipped entirely).

Known limit, stated plainly: the scan is text-level (the
gate's scanner form). A derivation mediated through a
variable assigned in one statement and climbed in another
is the census's flow pass, not this leg; this leg guards
the direct forms, which are the forms every consumer in
the consolidated trees used.
"""
import os
import re

from .linecap import enumerate_files

CLIMB_PARENTS = re.compile(r"__file__[^\n]*\.parents\[\s*[1-9]")
CLIMB_PARENT_CHAIN = re.compile(r"__file__[^\n]*\.parent\.parent")
DIRNAME = re.compile(r"dirname\s*\(")
JOIN_SEGMENT = re.compile(r"[\"']\.\.[\"']")
CWD_ROOT = re.compile(r"os\.getcwd\(\)|Path\.cwd\(\)")
HARDCODED_ROOT = re.compile(r"[\"']/home/")

PATHS_MODULE_NAMES = ("paths.py", "paths.sh")


def _references_paths_module(text):
    return "paths.py" in text or "paths.sh" in text


def scan_text(text):
    """Findings in one file's source: [(lineno, kind)] with
    kind 'root-climb', 'cwd-root', or 'hardcoded-root'. A
    two-line window covers the standing multi-line join
    idiom (the __file__ line and its continuation)."""
    findings = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        ctx = lines[i - 1] + "\n" + line if i else line
        lineno = i + 1
        if _references_paths_module(ctx):
            pass  # bootstrap: reaching the spine, not deriving
        elif "__file__" in ctx and (
                CLIMB_PARENTS.search(ctx)
                or CLIMB_PARENT_CHAIN.search(ctx)
                or len(DIRNAME.findall(ctx)) >= 2
                or (JOIN_SEGMENT.search(line)
                    and ("__file__" in ctx or "dirname" in ctx))):
            findings.append((lineno, "root-climb"))
            continue
        if CWD_ROOT.search(line):
            findings.append((lineno, "cwd-root"))
        elif HARDCODED_ROOT.search(line):
            findings.append((lineno, "hardcoded-root"))
    return findings


def declared_kind(relpath, exceptions):
    """The declared kind covering relpath (repo-relative),
    or None. Exact path, or a subtree with a trailing '/**'
    — the folder census's declaration form."""
    for decl in exceptions:
        path = decl["path"]
        if path.endswith("/**"):
            prefix = path[:-3]
            if relpath == prefix or relpath.startswith(prefix + "/"):
                return decl["kind"]
        elif relpath == path:
            return decl["kind"]
    return None


def evaluate(files, exceptions):
    """(rows, failures) over {repo-relative path: source
    text}. Rows are every finding: (relpath, lineno, kind,
    declared) with declared the exception's kind or None.
    Failures are the undeclared findings. Paths modules
    (any paths.py / paths.sh) are the derivation home and
    are never scanned."""
    rows = []
    failures = []
    for relpath in sorted(files):
        if relpath.rsplit("/", 1)[-1] in PATHS_MODULE_NAMES:
            continue
        kind = declared_kind(relpath, exceptions)
        for lineno, finding in scan_text(files[relpath]):
            rows.append((relpath, lineno, finding, kind))
            if kind is None:
                failures.append((relpath, lineno, finding))
    return rows, failures


def _is_python_source(rel, full):
    """A .py file, or an extensionless script whose shebang
    names python (the tree's bin/ entry scripts)."""
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


def scan(root, repo_root, exceptions=(), exclude=()):
    """(rows, failures) over the tracked Python sources
    under root (a package dir). exclude names repo-relative
    subtree prefixes skipped entirely (a parallel lane's
    tree, a wave not yet landed)."""
    files = {}
    for rel in enumerate_files(str(root)):
        repo_rel = os.path.relpath(
            os.path.join(str(root), rel), str(repo_root)
        ).replace(os.sep, "/")
        if any(repo_rel == ex or repo_rel.startswith(ex + "/")
               for ex in exclude):
            continue
        full = os.path.join(str(root), rel)
        if not os.path.isfile(full) or not _is_python_source(rel, full):
            continue
        with open(full, encoding="utf-8", errors="replace") as fh:
            files[repo_rel] = fh.read()
    return evaluate(files, list(exceptions))


def render(rows, failures):
    """The leg's output block, linecap's shape: declared
    findings as notes with their kind, undeclared as
    failures."""
    lines = []
    for relpath, lineno, kind, declared in rows:
        if declared is None:
            lines.append(f"PATHS: {relpath}:{lineno}: {kind} "
                         f"outside a paths module")
        else:
            lines.append(f"paths: note - {relpath}:{lineno}: "
                         f"{kind} (declared: {declared})")
    if failures:
        lines.append(f"paths-discipline: {len(failures)} "
                     f"undeclared derivation(s)")
    else:
        lines.append("paths-discipline: ok")
    return lines
