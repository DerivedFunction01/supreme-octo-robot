#!/usr/bin/env python3
"""Date-uniqueness component: one shared date helper per
intent,
re-expressed as a registry gate leg.

NOT gate.writeruniqueness (the write graph) and not
gate.importisolation (the import graph between
surfaces): this component guards the date-helper graph —
where parse / normalize / format / epoch / now behaviour
is allowed to be implemented.

The invariant: every date/datetime intent has one homed
module per cluster — extension only at the home — because
a private copy drifts: the tree carried 33 production
copies of five intents, several
already divergent in exactly the corners that matter
(naive stamps forced to UTC or not, malformed stamps
raising or serving None, second-precision truncation or
full precision). A divergent copy fails here at birth.

The family -> home map is DATA, not code:
date_families.json beside this module names the families,
each family's homed modules and exports, the sanctioned
private copies (function-level, each with its reason),
and the out-of-scope file classes. Extend the map there,
never here. Homes are per cluster because the tree's
import rules forbid one literal module for every surface
(attention's import isolation, the venue's standalone
by-path loads, the workrecord lib's own root) — the
invariant is one owner per intent per cluster, with the
map naming every owner.

The check, over a package's tracked Python sources, is
AST-level and shape-based (a name registry is proven
insufficient — copies hide under any name): a function
whose own scope (nested scopes pruned) performs one
family's intent as a thin wrapper is a copy of that
family. The shape rules, applied in order (first match
wins), are the census's counting rule, so the leg's
count and the census's count are the same number from
the same tree:

- normalize: the scope checks isinstance(x, datetime)
  AND calls fromisoformat, and returns both the guarded
  argument and a parse-derived value.
- parse: the scope calls fromisoformat or strptime,
  every call is parse machinery (PARSE_OK), and some
  return is parse-derived.
- epoch: some return is/contains a .timestamp() call and
  every call is epoch machinery (EPOCH_OK).
- now: the scope calls datetime.now/utcnow or time.time
  with only now machinery (NOW_OK), or builds a
  strftime(gmtime()) Z-stamp (GMTIME_OK).
- format: some return is/contains an .isoformat() or
  .strftime() call, no parse call, and every call is
  format machinery (FORMAT_OK).

A function that merely uses date operations inside a
larger computation — or composes a home (iso(now()), a
delegation to the home's parse) — is a consumer, not a
copy, and is never a finding.

Declared seams, two forms. The map's sanctioned copies
(function-level, in the map's data) and the leg's own
exceptions (the paths-discipline form {"path", "kind"}:
exact path, or a subtree with a trailing '/**'). A
declared finding is reported as a note with its reason
and never fails the leg. The registry discipline cuts
both ways: reliance without declaration is an ordinary
finding, and a declaration whose file — when its
package's leg scans it — no longer carries a matching
pattern is itself a finding (stale-exception). An entry
for a file outside the scanned package is not judged by
that run. Findings name file + family, never content.

Out of scope, as the map declares: the test class (a
tests/ path segment or a test_*.py basename — local
helpers in test modules are fixtures) and the deployed
class (pipeline/venue/adapters/** — snippets shipped to
sessions, standalone by construction). The client
(TypeScript) surface's per-view homes are recorded in
the map as data; this component parses Python only.

Known limits, stated plainly:

- the scan is AST-level over direct forms. A helper
  assembled through variables (the parse callable held
  in a name, machinery split across functions) is a
  flow pass's business, not this leg's — the
  paths-discipline component's limit form.
- a file that does not parse yields no findings here;
  it fails the legs that compile it.

Usage (module form, from the pipeline root):
python3 -m gate.dateuniqueness [--root DIR]
Exit: 0 = no undeclared findings; 1 = findings;
2 = usage error. Standalone, the scanned package's
dateuniqueness leg declaration (if any) adds its
exceptions to the component data; under the runner, the
leg's exceptions are passed in.
"""
import ast
import json
import os
import subprocess
import sys

from .linecap import enumerate_files, expand_equals

# The family -> home map is scanner data (see the module
# docstring): families, homed modules, sanctioned copies,
# out-of-scope classes.
DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "date_families.json")
with open(DATA_PATH, encoding="utf-8") as _fh:
    DATA = json.load(_fh)

PARSE_OK = {"fromisoformat", "strptime", "replace", "strip",
            "astimezone", "isinstance", "bool", "len", "str"}
EPOCH_OK = PARSE_OK | {"timestamp", "fromtimestamp",
                       "float", "int", "round"}
NOW_OK = {"now", "utcnow", "isoformat", "strftime",
          "timestamp", "astimezone", "time", "replace"}
FORMAT_OK = {"isoformat", "strftime", "astimezone"}
# The ops watches' clock shape: a Z-stamp string built
# from time.gmtime() — a now provider in time-module form.
GMTIME_OK = {"strftime", "gmtime", "localtime", "time"}

DEPLOYED_PREFIXES = tuple(
    entry["path"][:-3] for entry in DATA.get("out_of_scope", [])
    if entry.get("path", "").endswith("/**"))


def _call_name(call):
    """The called function's terminal name: attribute or
    bare, the name is the form."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


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


def _contains_call(node, names):
    return any(isinstance(sub, ast.Call)
               and _call_name(sub) in names
               for sub in ast.walk(node))


def _facts(fn):
    """The shape facts of one function's own scope — the
    census's counting rule, ported verbatim so the leg
    and the census count the same copies."""
    nodes = list(_scope_nodes(fn))
    calls = [(_call_name(n), n) for n in nodes
             if isinstance(n, ast.Call)]
    names = [name for name, _ in calls]
    assignments = {}
    for node in nodes:
        if isinstance(node, ast.Assign) \
                and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            assignments.setdefault(
                node.targets[0].id, []).append(node.value)
    returns = [n.value for n in nodes
               if isinstance(n, ast.Return)
               and n.value is not None]

    def parse_derived(expr, depth=0):
        # A name is parse-derived when ANY of its in-scope
        # assignments is (branchy normalizers assign the
        # parse in one branch, the argument in another).
        if _contains_call(expr, ("fromisoformat", "strptime")):
            return True
        if depth == 0 and isinstance(expr, ast.Name):
            return any(parse_derived(value, 1)
                       for value in assignments.get(expr.id, []))
        return False

    def arg_derived(expr):
        # A return of a name one of whose assignments is a
        # bare name — the isinstance-guarded argument
        # flowing through (the normalize shape).
        if not isinstance(expr, ast.Name):
            return False
        return any(isinstance(value, ast.Name)
                   for value in assignments.get(expr.id, []))

    facts = {
        "calls": sorted(set(names)),
        "fromisoformat": "fromisoformat" in names,
        "strptime": "strptime" in names,
        "isoformat": "isoformat" in names,
        "strftime": "strftime" in names,
        "timestamp": "timestamp" in names,
        "now_call": bool({"now", "utcnow"} & set(names)),
        "time_time": any(
            name == "time" and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "time"
            for name, call in calls),
        "isinstance_dt": any(
            name == "isinstance" and len(call.args) >= 2
            and any(isinstance(sub, ast.Name)
                    and sub.id == "datetime"
                    or isinstance(sub, ast.Attribute)
                    and sub.attr == "datetime"
                    for sub in ast.walk(call.args[1]))
            for name, call in calls),
        "returns_parse": any(parse_derived(r) for r in returns),
        "returns_name": any(isinstance(r, ast.Name) for r in returns),
        "returns_arg": any(arg_derived(r) for r in returns),
        "gmtime": "gmtime" in names,
        "returns_timestamp": any(
            _contains_call(r, ("timestamp",)) for r in returns),
        "returns_now": any(
            _contains_call(r, ("now", "utcnow")) for r in returns),
        "returns_format": any(
            _contains_call(r, ("isoformat", "strftime"))
            for r in returns),
        "n_returns": len(returns),
    }
    facts["date_ops"] = any([
        facts["fromisoformat"], facts["strptime"],
        facts["isoformat"], facts["strftime"],
        facts["timestamp"], facts["now_call"],
        facts["time_time"]])
    return facts


def classify(facts):
    """The family a scope's facts perform, or None (a
    consumer) — the census's rule order, first match."""
    names = set(facts["calls"])
    if facts["isinstance_dt"] and facts["fromisoformat"] \
            and (facts["returns_name"] or facts["returns_arg"]) \
            and facts["returns_parse"]:
        return "normalize"
    if (facts["fromisoformat"] or facts["strptime"]) \
            and facts["returns_parse"] \
            and names <= PARSE_OK:
        return "parse"
    if facts["timestamp"] and facts["returns_timestamp"] \
            and names <= EPOCH_OK:
        return "epoch"
    if facts["strftime"] and facts["gmtime"] \
            and names <= GMTIME_OK:
        return "now"
    if (facts["now_call"] or facts["time_time"]) \
            and facts["returns_now"] or (
            facts["time_time"] and names <= NOW_OK):
        if names <= NOW_OK:
            return "now"
    if facts["returns_format"] \
            and not (facts["fromisoformat"] or facts["strptime"]) \
            and names <= FORMAT_OK:
        return "format"
    return None


def file_class(relpath):
    """The map's file classes: deployed (the adapters
    subtree), test (a tests/ segment or a test_*.py
    basename), else production."""
    parts = relpath.split("/")
    if any(relpath == prefix
           or relpath.startswith(prefix + "/")
           for prefix in DEPLOYED_PREFIXES):
        return "deployed"
    if "tests" in parts or parts[-1].startswith("test_"):
        return "test"
    return "production"


def _functions_of(tree):
    """[(qualified name, def node)] — every function in
    the file, with its enclosing class chain."""
    found = []

    def visit(node, prefix, in_class):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, prefix + [child.name], True)
            elif isinstance(child, (ast.FunctionDef,
                                    ast.AsyncFunctionDef)):
                found.append((".".join(prefix + [child.name]),
                              child))
                visit(child, prefix + [child.name], False)
            else:
                visit(child, prefix, in_class)

    visit(tree, [], False)
    return found


def scan_source(text):
    """[(lineno, family, qualname, name)] — every function
    in one file whose own scope performs a family's
    intent. A file that does not parse yields no findings
    (it fails the legs that compile it)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    findings = []
    for qualname, fn in _functions_of(tree):
        facts = _facts(fn)
        if not facts["date_ops"]:
            continue
        family = classify(facts)
        if family:
            findings.append(
                (fn.lineno, family, qualname, fn.name))
    findings.sort()
    return findings


def _homes(data):
    """{family: {repo-relative path: cluster}} from the
    map's family data."""
    homes = {}
    for family, spec in data.get("families", {}).items():
        homes[family] = {
            home["path"]: home.get("cluster", "")
            for home in spec.get("homes", [])}
    return homes


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


def evaluate(files, exceptions=(), data=None):
    """(rows, failures) over {repo-relative path: source
    text}. Rows are every finding: (relpath, lineno, kind,
    declared) with kind '<family>-copy' and declared the
    home / sanction / exception's kind or None; a
    stale-exception row carries lineno 0 and the
    declaration's kind. Failures are the undeclared
    findings plus the stale declarations, in the same row
    shape. Out-of-scope file classes are never scanned."""
    data = DATA if data is None else data
    homes = _homes(data)
    sanctioned = data.get("sanctioned_copies", [])
    exceptions = list(exceptions)
    rows = []
    failures = []
    scanned = {relpath: text for relpath, text in files.items()
               if file_class(relpath) == "production"}
    found_in = {}
    matched_sanctions = set()
    for relpath in sorted(scanned):
        leg_kind = declared_kind(relpath, exceptions)
        for lineno, family, _qual, name in scan_source(
                scanned[relpath]):
            kind = f"{family}-copy"
            declared = None
            if relpath in homes.get(family, {}):
                declared = (f"home: "
                            f"{homes[family][relpath]}")
            else:
                for idx, entry in enumerate(sanctioned):
                    if entry["path"] == relpath \
                            and entry["function"] == name \
                            and entry["family"] == family:
                        declared = entry["kind"]
                        matched_sanctions.add(idx)
                        break
                if declared is None:
                    declared = leg_kind
            row = (relpath, lineno, kind, declared)
            rows.append(row)
            found_in.setdefault(relpath, []).append(kind)
            if declared is None:
                failures.append(row)
    for idx, entry in enumerate(sanctioned):
        if entry["path"] in scanned \
                and idx not in matched_sanctions:
            row = (entry["path"], 0, "stale-exception",
                   entry["kind"])
            rows.append(row)
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


def scan(root, repo_root, exceptions=(), exclude=()):
    """(rows, failures, scanned) over the tracked Python
    sources under root (a package dir). exclude names
    repo-relative subtree prefixes skipped entirely."""
    files = {}
    scanned = 0
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
                f"DATE-UNIQUENESS: {relpath}: "
                f"stale exception (declared: {declared}) — "
                f"no matching pattern in this file")
        elif declared is None:
            lines.append(
                f"DATE-UNIQUENESS: {relpath}:{lineno}: "
                f"{kind} outside its homed module")
        else:
            lines.append(
                f"date-uniqueness: note - {relpath}:{lineno}: "
                f"{kind} (declared: {declared})")
    if failures:
        lines.append(
            f"date-uniqueness: {len(failures)} "
            f"undeclared violation(s)")
    elif scanned is not None:
        lines.append(
            f"date-uniqueness: ok ({scanned} files scanned)")
    else:
        lines.append("date-uniqueness: ok")
    return lines


def _leg_exceptions(root):
    """The scanned package's own dateuniqueness leg
    exceptions from its gate.json, for a standalone run;
    the component data always applies."""
    decl_path = os.path.join(root, "gate.json")
    if not os.path.isfile(decl_path):
        raise ValueError(f"no package declaration at {root}")
    with open(decl_path, encoding="utf-8") as fh:
        decl = json.load(fh)
    for leg in decl.get("legs", []):
        if leg.get("leg") == "dateuniqueness":
            return leg.get("exceptions", [])
    return []


def _repo_root(root):
    """The mega repo root for a standalone run (the
    runner passes its own): the map's paths are
    repo-relative, so a package-root scan must resolve
    them against the same root the runner uses — the
    git top level of the scanned tree, falling back to
    the root itself when git cannot answer."""
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse",
             "--show-toplevel"],
            capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return root


def main(argv):
    root = os.getcwd()
    args = expand_equals(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = os.path.abspath(args.pop(0))
        else:
            print("usage: dateuniqueness.py [--root DIR]",
                  file=sys.stderr)
            return 2
    try:
        exceptions = _leg_exceptions(root)
    except (OSError, ValueError) as exc:
        print(f"date-uniqueness: no package declaration "
              f"at {root}: {exc}", file=sys.stderr)
        return 2
    rows, failures, scanned = scan(
        root, _repo_root(root), exceptions)
    for line in render(rows, failures, scanned):
        print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
