#!/usr/bin/env python3
"""Writer-uniqueness component: one unified writer owns
state mutation (contract 15 / plan §4.15, AC-14 invariant
(b), static half), re-expressed as a registry gate leg.

NOT gate.isolation (the test-isolation state hash) and
not gate.importisolation (the import graph between
surfaces): this component guards the write graph — where
state bytes are allowed to be produced.

The invariant: every state mutation rides
pipeline/platform/writer.py's protocol — stage to a fresh
sibling, flush + fsync, read back and compare, rename
over, directory fsync — because a denial or failure at
any stage must leave the target byte-identical. A second
implementation of that protocol, or a direct write that
bypasses it, re-opens exactly the torn-write failure the
contract exists to close. The writer module itself is
the one home and is never scanned.

Two checks over a package's tracked Python sources, both
AST-level:

- truncate-write — a write-mode open(...) or a
  write_text / write_bytes call whose target is a
  state-shaped path, outside the writer and outside a
  declared seam. State-shaped is derived from the tree's
  own state homes: a path segment named var or state in
  any literal of the target expression (the packages'
  runtime state homes — the platform declaration names
  var/ and state/ its real state homes, and every paths
  spine derives its STATE_DIR the same way); a literal
  ending in .jsonl (the append-only store logs — the
  release record's releases.jsonl, the ledger stores);
  or a reference to a state constant (STATE, STATE_DIR,
  STATE_FILE, STORE_FILE, LEDGER_FILE, or any STATE_*
  name — the spines' and stores' standing names for
  their state paths). A target that is a bare name
  resolves one level through a simple assignment in the
  same scope. A write whose target is renamed over
  another path in the same scope is staging, not a
  truncate-write — the staged-write check judges it; a
  target visibly derived as a temp (a tempfile origin,
  or a .tmp / tmp- / .staging- / sched-tmp marker in its
  literals) is likewise staging-shaped, never a
  truncate-write.

- duplicate-staged-write — a scope (one function, or a
  module body) that both writes a target and renames
  that same target over another path (os.replace /
  os.rename, or the pathlib .replace / .rename form):
  the stage + rename protocol re-implemented outside
  the writer. When the scope also fsyncs, the copy is
  the full protocol (duplicate-staged-write); without
  an fsync it is a partial copy — stage + rename with
  no durability step — and is reported as
  partial-staged-write, the weaker and worse form.

Declared seams: the EXCEPTIONS table below, in the
paths-discipline declaration form ({"path": repo-relative
path, "kind": reason}) — the portability registry's
discipline in the paths leg's shape. A declared file's
findings are reported as notes with their reason and
never fail the leg. The registry discipline cuts both
ways: reliance without declaration is an ordinary
finding, and a declaration whose file — when its
package's leg scans it — carries no matching pattern is
itself a finding (stale-exception). The table's standing
entries are the stores' documented standalone fallbacks:
seams that delegate to the platform writer where the
pipeline tree exists and perform the same protocol
inline where a package runs outside it (the venue
foundation states the form: the protocol, not the
module, is the invariant there). An entry for a file
outside the scanned package is not judged by that run.

Findings name file + kind, never content.

Known limits, stated plainly:

- the scan is AST-level over direct forms. A write
  mediated through a variable assigned in one scope and
  written in another, a mode held in a variable, or a
  staging split across functions (one writes the temp,
  another renames it) is a flow pass's business, not
  this leg's — the paths-discipline component's limit
  form. The leg guards the direct forms, which are the
  forms the consolidated trees use.
- state-shapedness is judged from the target
  expression's own literals and names; a state path
  computed opaquely (a caller-supplied argument, a
  config value) is not visible to the leg. The stores'
  seams are pinned separately, by the platform suite's
  writer census (the invariant's live-store half).
- a file that does not parse yields no findings here;
  it fails the legs that compile it.

Repo form (the runner's repowriteruniqueness leg): the
component evaluates over every tracked Python source in
the tree by default — coverage is never declared. The
exceptions are recorded once, in the gate package's repo
leg declaration (repo-relative paths); the per-package
leg declarations this component once read are retired.
Opt-out exists only as those recorded exceptions, under
the registry discipline both ways.

Usage (module form, from the pipeline root):
python3 -m gate.writeruniqueness [--root DIR]
Exit: 0 = no undeclared findings; 1 = findings;
2 = usage error. Standalone, the scanned package's
writeruniqueness leg declaration (if any) adds its
exceptions to the component table; under the runner,
the leg's exceptions are passed in.
"""
import ast
import json
import os
import sys

from .linecap import (enumerate_files, enumerate_tracked_files,
                      expand_equals)

# The one home: the unified writer itself is never
# scanned (repo-relative, and the bare name at the
# platform package root for a standalone run there).
WRITER_HOME = "pipeline/platform/writer.py"

# The declared seams, in the paths-discipline form.
# Add a path here only together with the seam it names:
# a store whose writer delegates to the platform writer
# in-tree and performs the same protocol inline only
# where its package runs standalone, outside the tree.
EXCEPTIONS = (
    {"path": "pipeline/venue/sync/lease/core/foundation.py",
     "kind": "standalone fallback seam — the venue lease "
             "foundation's one writer (register E5)"},
    {"path": "pipeline/venue/sync/cli.py",
     "kind": "the venue sync funnel's binding-journal "
             "append — an append-only evidence line "
             "(var/binding-journal.jsonl), never a state "
             "store the staged protocol protects; the "
             "funnel's staged writes ride sync/"
             "writer_route.py"},
    {"path": "pipeline/venue/sync/writer_route.py",
     "kind": "standalone fallback seam — the venue sync "
             "writer route's inline protocol: the one "
             "writer home for the funnel's and the "
             "liveness entries' state writes, delegating "
             "to the platform writer (performed by the "
             "/ops service first) in-tree"},
    {"path": "pipeline/venue/sync/sealed.py",
     "kind": "standalone fallback seam — the sealed-jobs "
             "store's one writer: the dispatcher's own "
             "key, blob and register writes, performed "
             "inline where venue-run loads the module by "
             "path outside the server context the writer "
             "route's /ops leg needs"},
    {"path": "pipeline/scheduling/ops/watches/file_registry.py",
     "kind": "standalone fallback seam — the scheduling "
             "file registry watch's state writes"},
    {"path": "pipeline/workrecord/lib/util.py",
     "kind": "standalone fallback seam — the workrecord "
             "staged_write_bytes seam"},
    {"path": "pipeline/venue/bin/venue-lease",
     "kind": "append-only evidence log — the rc120 chain "
             "log (var/rc120-chain.jsonl) is diagnostic "
             "evidence, not a state store: one O_APPEND "
             "line per stamp; a torn final line loses one "
             "evidence line and corrupts nothing, so the "
             "staged-write protocol has nothing to "
             "protect there"},
)

STATE_SEGMENTS = {"var", "state"}
STATE_IDENTIFIERS = {
    "STATE", "STATE_DIR", "STATE_FILE", "STORE_FILE",
    "LEDGER_FILE",
}
TEMP_MARKERS = (".tmp", "tmp-", ".staging-", "sched-tmp")
WRITE_MODE_CHARS = set("wax")
WRITE_CALLS = ("write_text", "write_bytes")
RENAME_CALLS = ("replace", "rename")


def _call_name(call):
    """The called function's terminal name: open, fsync,
    replace — attribute or bare, the name is the form."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _expr_facts(node):
    """(string literals, identifier segments) anywhere in
    an expression — the raw material of the shape tests."""
    strings = []
    idents = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) \
                and isinstance(sub.value, str):
            strings.append(sub.value)
        elif isinstance(sub, ast.Name):
            idents.append(sub.id)
        elif isinstance(sub, ast.Attribute):
            idents.append(sub.attr)
    return strings, idents


def _is_state_shaped(node, assignments, depth=0):
    """The state-shape test (see the module docstring for
    the derivation). A bare name resolves one level
    through its scope's simple assignments."""
    strings, idents = _expr_facts(node)
    for text in strings:
        segments = text.replace("\\", "/").split("/")
        if any(seg in STATE_SEGMENTS for seg in segments):
            return True
        if text.endswith(".jsonl"):
            return True
    for ident in idents:
        if ident in STATE_IDENTIFIERS \
                or ident.startswith("STATE_"):
            return True
    if depth == 0 and isinstance(node, ast.Name) \
            and node.id in assignments:
        return _is_state_shaped(
            assignments[node.id], assignments, depth=1)
    return False


def _is_temp_shaped(node, assignments):
    """A target visibly derived as a staging temp: a
    temp marker in its own literals, or a name assigned
    from a tempfile call or a temp-marked expression."""
    strings, _idents = _expr_facts(node)
    if any(marker in text
           for text in strings for marker in TEMP_MARKERS):
        return True
    if isinstance(node, ast.Name) and node.id in assignments:
        value = assignments[node.id]
        for sub in ast.walk(value):
            if isinstance(sub, ast.Call) and _call_name(sub) in (
                    "mkstemp", "NamedTemporaryFile", "mktemp"):
                return True
        strings, _idents = _expr_facts(value)
        if any(marker in text
               for text in strings for marker in TEMP_MARKERS):
            return True
    return False


def _scope_nodes(scope):
    """The nodes of one scope with nested scopes pruned:
    a nested def / class / lambda is its own scope, judged
    on its own statements, never its enclosing scope's."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef,
                             ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _assignments(nodes, base):
    """Simple name assignments over a scope's nodes,
    overlaid on the enclosing (module) map: one name, one
    expression — the one-level resolution the shape tests
    perform."""
    found = dict(base)
    for node in nodes:
        if isinstance(node, ast.Assign) \
                and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) \
                and isinstance(node.target, ast.Name) \
                and node.value is not None:
            found[node.target.id] = node.value
    return found


def _mode_of(call):
    """An open() call's literal mode, or None when the
    mode is absent (a read) or not a literal (not judged —
    the stated limit)."""
    candidate = None
    if len(call.args) >= 2:
        candidate = call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "mode":
            candidate = keyword.value
    if isinstance(candidate, ast.Constant) \
            and isinstance(candidate.value, str):
        return candidate.value
    return None


def _write_events(nodes):
    """[(target expression, lineno)] — write-mode opens
    and write_text / write_bytes calls in one scope."""
    events = []
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == "open" and node.args:
            mode = _mode_of(node)
            if mode is not None \
                    and WRITE_MODE_CHARS & set(mode):
                events.append((node.args[0], node.lineno))
        elif name in WRITE_CALLS \
                and isinstance(node.func, ast.Attribute):
            events.append((node.func.value, node.lineno))
    return events


def _rename_events(nodes):
    """[(source expression, lineno)] — os.replace /
    os.rename calls, and the pathlib method form where
    the renamed object is the expression itself."""
    events = []
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) \
                or func.attr not in RENAME_CALLS:
            continue
        if isinstance(func.value, ast.Name) \
                and func.value.id == "os":
            if node.args:
                events.append((node.args[0], node.lineno))
        else:
            events.append((func.value, node.lineno))
    return events


def _scan_scope(nodes, assignments):
    """[(lineno, kind)] — both checks over one scope."""
    findings = []
    writes = _write_events(nodes)
    renames = _rename_events(nodes)
    renamed = {ast.dump(source) for source, _ln in renames}
    for target, lineno in writes:
        if ast.dump(target) in renamed:
            continue  # staging: the staged-write check's
            # jurisdiction, never a truncate-write
        if _is_temp_shaped(target, assignments):
            continue
        if _is_state_shaped(target, assignments):
            findings.append((lineno, "truncate-write"))
    if writes and renames:
        written = {ast.dump(target) for target, _ln in writes}
        hits = [lineno for source, lineno in renames
                if ast.dump(source) in written]
        if hits:
            has_fsync = any(
                isinstance(node, ast.Call)
                and _call_name(node) == "fsync"
                for node in nodes)
            kind = ("duplicate-staged-write" if has_fsync
                    else "partial-staged-write")
            findings.append((min(hits), kind))
    return findings


def scan_source(text):
    """[(lineno, kind)] — both checks over one file's
    source, scope by scope: the module body, then every
    function and class body on its own statements."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    module_nodes = list(_scope_nodes(tree))
    module_assignments = _assignments(module_nodes, {})
    findings = _scan_scope(module_nodes, module_assignments)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,
                             ast.AsyncFunctionDef,
                             ast.ClassDef)):
            nodes = list(_scope_nodes(node))
            assignments = _assignments(nodes, module_assignments)
            findings.extend(_scan_scope(nodes, assignments))
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
    """The exception entries a relpath matches (for the
    stale-declaration census)."""
    return [decl for decl in exceptions
            if declared_kind(relpath, [decl]) is not None]


def evaluate(files, exceptions):
    """(rows, failures) over {repo-relative path: source
    text}. Rows are every finding: (relpath, lineno, kind,
    declared) with declared the exception's kind or None;
    a stale-exception row carries lineno 0 and the
    declaration's kind. Failures are the undeclared
    findings plus the stale declarations, in the same
    row shape. The writer module itself is the home and
    is never scanned."""
    exceptions = list(EXCEPTIONS) + list(exceptions)
    rows = []
    failures = []
    scanned = {relpath: text for relpath, text in files.items()
               if relpath != WRITER_HOME
               and relpath != "writer.py"}
    found_in = {}
    for relpath in sorted(scanned):
        kind = declared_kind(relpath, exceptions)
        for lineno, finding in scan_source(scanned[relpath]):
            row = (relpath, lineno, finding, kind)
            rows.append(row)
            found_in.setdefault(relpath, []).append(finding)
            if kind is None:
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


def scan(root, repo_root, exceptions=(), exclude=(),
         tracked=False):
    """(rows, failures, scanned) over the Python sources
    under root (a package dir, or the repo root for the
    repo-scoped leg). exclude names repo-relative subtree
    prefixes skipped entirely. tracked=True restricts the
    population to tracked files (the repo leg's form: an
    untracked staging file is not yet the tree's code)."""
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
        if not os.path.isfile(full) or not _is_python_source(rel, full):
            continue
        with open(full, encoding="utf-8", errors="replace") as fh:
            files[repo_rel] = fh.read()
        scanned += 1
    rows, failures = evaluate(files, list(exceptions))
    return rows, failures, scanned


def render(rows, failures, scanned=None):
    """The leg's output block, the paths-discipline form:
    declared findings as notes with their kind, undeclared
    as failures, stale declarations named."""
    lines = []
    for relpath, lineno, kind, declared in rows:
        if kind == "stale-exception":
            lines.append(
                f"WRITER-UNIQUENESS: {relpath}: "
                f"stale exception (declared: {declared}) — "
                f"no matching pattern in this file")
        elif declared is None:
            lines.append(
                f"WRITER-UNIQUENESS: {relpath}:{lineno}: "
                f"{kind} outside the unified writer")
        else:
            lines.append(
                f"writer-uniqueness: note - {relpath}:{lineno}: "
                f"{kind} (declared: {declared})")
    if failures:
        lines.append(
            f"writer-uniqueness: {len(failures)} "
            f"undeclared violation(s)")
    elif scanned is not None:
        lines.append(
            f"writer-uniqueness: ok ({scanned} files scanned)")
    else:
        lines.append("writer-uniqueness: ok")
    return lines


def _leg_exceptions(root):
    """The scanned package's own writeruniqueness leg
    exceptions from its gate.json, for a standalone run;
    the component table always applies."""
    decl_path = os.path.join(root, "gate.json")
    if not os.path.isfile(decl_path):
        raise ValueError(f"no package declaration at {root}")
    with open(decl_path, encoding="utf-8") as fh:
        decl = json.load(fh)
    for leg in decl.get("legs", []):
        if leg.get("leg") == "writeruniqueness":
            return leg.get("exceptions", [])
    return []


def main(argv):
    root = os.getcwd()
    args = expand_equals(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = os.path.abspath(args.pop(0))
        else:
            print("usage: writeruniqueness.py [--root DIR]",
                  file=sys.stderr)
            return 2
    try:
        exceptions = _leg_exceptions(root)
    except (OSError, ValueError) as exc:
        print(f"writer-uniqueness: no package declaration "
              f"at {root}: {exc}", file=sys.stderr)
        return 2
    rows, failures, scanned = scan(root, root, exceptions)
    for line in render(rows, failures, scanned):
        print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
