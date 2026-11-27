"""The classified schedule catalog.

The tracked examples layer is a catalog: examples/registry/
catalog.yaml indexes every file in the layer, and each entry
file carries a `catalog:` block classifying it on the shared
axes (origin, generality, use_case, declared parameters).
Classification is descriptive, not activating — being in the
catalog admits nothing. Adoption is a separate act (the
`bin/sched adopt` verb): copy a generalized or parameterized
entry into the live overlay, substitute the declared
parameters plus the standard adoption set (id, title, owner,
owner_reason, timezone), refuse machine literals, then run the
registry's admission back half. The adopted entry is stamped
with a `source:` block (catalog id, catalog version, the
effective parameters), so the drift census can re-render the
expected live form and diff — drift is a diff, not a mystery.

Generality speaks beyond the standard adoption set:
generalized = nothing entry-specific to fill; parameterized =
entry-specific parameters are declared and must be filled (or
defaulted); deployment-specific = the entry carries a
deployment's own content and no copy is offered. Files in the
layer that are not entries at all (config specimens for one
named entry) are classified config-example and ride with their
entry's adoption as data, never adopted standalone.

The setup axis declares what an adoption must establish
beyond the entry itself — an adopted entry alone may run
nothing (the sweeper specimen: its state directory, its
ledger store, its config data files). state_dirs are created
by the verb; files are copied from a catalog specimen
(from_catalog) or verified present; stores are verified
present or initialized by their declared init argv;
companions are verified adopted; registrations are declared
manual steps the verb surfaces in its report; docs are
Markdown files traveling with the example that describe
documentation amendments (AGENTS.md edits) the adoption
requires — the verb copies them into the deployment's
adoption record (state/adoptions/<live-id>/) and names them,
but never performs an amendment itself: a described,
recorded step, not an invisible side effect. Every
state_paths entry must be covered by the setup declaration —
an uncovered state path is an adoption that would run
against nothing.

All parsing uses the registry's YAML subset; the serializer
here emits exactly that subset (round-trip tested).
"""

import copy
import os
import re

from .. import registry
from ..registry import EntryError

EXAMPLES_DIR = os.path.join("examples", "registry")
CATALOG_NAME = "catalog.yaml"

STANDARD_PARAMS = ("id", "title", "owner", "owner_reason", "timezone")

FIELD_ORDER = (
    "id", "title", "kind", "status", "cadence", "timezone",
    "owner", "owner_reason", "run", "body", "escalate_body",
    "timeout_secs", "report", "state_paths", "classification",
    "source", "lifetime", "catalog",
)

_LITERAL_RES = (
    re.compile(r"(?<![\w./${-])/(home|Users|tmp|private|etc|var|opt)/"),
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"(?<![\w./-])~/"),
)


# ---------------------------------------------------------------- loading

def _read_yaml(path, where):
    with open(path, "r", encoding="utf-8") as fh:
        return registry.parse_yaml(fh.read(), where=where)


def load_catalog(root):
    """Load and check the catalog. Returns (catalog, errors):
    catalog is {version, rows: {row_id: row}, entries: {row_id:
    parsed entry data for class-entry rows}}."""
    layer = os.path.join(root, EXAMPLES_DIR)
    errors = []
    catalog_path = os.path.join(layer, CATALOG_NAME)
    try:
        raw = _read_yaml(catalog_path, CATALOG_NAME)
    except (EntryError, OSError) as exc:
        return None, [f"catalog: {exc}"]
    version = raw.get("version")
    if not isinstance(version, int) or version <= 0:
        errors.append("catalog: version must be a positive integer")
    rows = raw.get("entries")
    if not isinstance(rows, dict) or not rows:
        errors.append("catalog: entries must be a non-empty map keyed by id")
        rows = {}
    entries = {}
    for row_id in sorted(rows):
        row = rows[row_id]
        where = f"catalog row {row_id}"
        if not isinstance(row, dict):
            errors.append(f"{where}: row is not a map")
            continue
        fname = row.get("file")
        if not isinstance(fname, str) or not fname:
            errors.append(f"{where}: file is required")
            continue
        fpath = os.path.join(layer, fname)
        if not os.path.isfile(fpath):
            errors.append(f"{where}: file does not exist: {fname}")
            continue
        cls = row.get("class")
        if cls not in ("entry", "config-example"):
            errors.append(f"{where}: class must be entry or config-example")
            continue
        if row.get("origin") not in registry.ORIGINS:
            errors.append(f"{where}: origin must be one of {registry.ORIGINS}")
        if row.get("generality") not in registry.GENERALITIES:
            errors.append(f"{where}: generality must be one of {registry.GENERALITIES}")
        if not registry.USE_CASE_RE.match(str(row.get("use_case", ""))):
            errors.append(f"{where}: use_case is a lowercase hyphenated label")
        if cls == "config-example":
            if not row.get("companion_of"):
                errors.append(f"{where}: a config-example names its companion_of entry")
            continue
        try:
            data = _read_yaml(fpath, fname)
        except (EntryError, OSError) as exc:
            errors.append(f"{where}: {exc}")
            continue
        entries[row_id] = data
        if data.get("id") != row_id:
            errors.append(f"{where}: entry id {data.get('id')!r} does not match the row id")
        block = data.get("catalog")
        if not isinstance(block, dict):
            errors.append(f"{where}: entry carries no catalog block")
            continue
        for axis in ("origin", "generality", "use_case"):
            if block.get(axis) != row.get(axis):
                errors.append(
                    f"{where}: catalog block {axis} {block.get(axis)!r} "
                    f"!= catalog row {row.get(axis)!r}")
        for field in ("body", "escalate_body"):
            rel = data.get(field)
            if rel:
                sibling = os.path.basename(rel)
                if not os.path.isfile(os.path.join(layer, sibling)):
                    errors.append(f"{where}: {field} sibling missing in the layer: {sibling}")
        setup = block.get("setup") or {}
        for comp in setup.get("companions") or []:
            target = rows.get(comp)
            if not isinstance(target, dict) or target.get("class") != "entry":
                errors.append(f"{where}: setup companion names no entry row: {comp}")
        for name, spec in (setup.get("files") or {}).items():
            src = spec.get("from_catalog")
            if src and src not in rows:
                errors.append(f"{where}: setup file {name} copies from unknown row: {src}")
        for doc_name in setup.get("docs") or []:
            if not os.path.isfile(os.path.join(layer, doc_name)):
                errors.append(f"{where}: setup doc missing in the layer: {doc_name}")
        covered = list(setup.get("state_dirs") or [])
        covered += [s.get("path") for s in (setup.get("stores") or {}).values()]
        covered += [f.get("target") for f in (setup.get("files") or {}).values()]
        for sp in data.get("state_paths") or []:
            if not any(sp == c or sp.startswith(str(c) + "/") for c in covered):
                errors.append(
                    f"{where}: state_paths entry not covered by the setup "
                    f"declaration: {sp}")
    on_disk = {
        name[: -len(".yaml")]
        for name in os.listdir(layer)
        if name.endswith(".yaml") and name != CATALOG_NAME
    }
    file_stems = {
        row.get("file", "")[: -len(".yaml")]
        for row in rows.values() if isinstance(row, dict)
    }
    for stem in sorted(on_disk - file_stems):
        errors.append(f"catalog: layer file not classified: {stem}.yaml")
    for row_id in sorted(rows):
        row = rows[row_id]
        if isinstance(row, dict) and row.get("class") == "config-example":
            if row.get("companion_of") not in rows:
                errors.append(f"catalog row {row_id}: companion_of names no catalog row")
    return {"version": version, "rows": rows, "entries": entries}, errors


# ---------------------------------------------------------------- adoption

def _set_field(data, dotted, value):
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def render_adoption(example_id, example, params, catalog_version):
    """Render the live entry an adoption of `example` produces
    with the given parameters. Returns (live_data, errors).
    Pure: no IO. The rendered entry carries no admission
    field — admission is the writer-path write itself, after
    the adoption's admission back half passes (amendment 3)."""
    errors = []
    block = example.get("catalog") or {}
    declared = block.get("parameters") or {}
    supplied = dict(params)
    for name in supplied:
        if name not in STANDARD_PARAMS and name not in declared:
            errors.append(f"undeclared parameter: {name}")
    effective = {}
    data = copy.deepcopy(example)
    data.pop("catalog", None)

    live_id = supplied.get("id") or (
        example_id[len("example-"):] if example_id.startswith("example-") else example_id)
    if not registry.USE_CASE_RE.match(str(live_id)):
        errors.append(f"live id {live_id!r} is not a lowercase hyphenated id")
    data["id"] = live_id
    effective["id"] = live_id

    if "title" in supplied:
        data["title"] = supplied["title"]
        effective["title"] = supplied["title"]
    elif str(data.get("title", "")).startswith("Example "):
        data["title"] = data["title"][len("Example "):]

    if "owner" not in supplied:
        errors.append("the adoption must declare its owner (standard parameter)")
    else:
        data["owner"] = supplied["owner"]
        effective["owner"] = supplied["owner"]
    if "owner_reason" in supplied:
        data["owner_reason"] = supplied["owner_reason"]
        effective["owner_reason"] = supplied["owner_reason"]
    elif supplied.get("owner") != example.get("owner"):
        data.pop("owner_reason", None)
    if "timezone" in supplied:
        data["timezone"] = supplied["timezone"]
        effective["timezone"] = supplied["timezone"]

    for field, new_rel in (("body", f"bodies/{live_id}.md"),
                           ("escalate_body", f"bodies/{live_id}-escalation.md")):
        if data.get(field):
            data[field] = new_rel

    for name, spec in declared.items():
        if name in supplied:
            value = supplied[name]
        elif "default" in spec:
            value = spec["default"]
        elif spec.get("required") is True:
            errors.append(f"missing required parameter: {name}")
            continue
        else:
            continue
        _set_field(data, spec["field"], value)
        effective[name] = value

    data["source"] = {
        "catalog": example_id,
        "catalog_version": catalog_version,
        "parameters": effective,
    }
    ordered = {}
    for key in FIELD_ORDER:
        if key in data:
            ordered[key] = data[key]
    for key in data:
        if key not in ordered:
            ordered[key] = data[key]
    return ordered, errors


def setup_actions(example):
    """The setup an adoption must establish, as a flat action
    list the adopt verb executes in order:
    ("mkdir", path) — create a state directory;
    ("file", name, target, from_catalog|None) — copy the named
    catalog row's file to target, or verify target exists;
    ("store", name, path, init|None) — verify the store exists
    or initialize it with the declared argv;
    ("companion", catalog_id) — verify that entry is adopted;
    ("registration", text) — a declared manual step, surfaced
    in the verb's report, never machine-acted;
    ("doc", filename) — a setup doc traveling with the
    example: recorded with the adoption, never performed."""
    setup = (example.get("catalog") or {}).get("setup") or {}
    actions = []
    for path in setup.get("state_dirs") or []:
        actions.append(("mkdir", path))
    for name, spec in (setup.get("files") or {}).items():
        actions.append(("file", name, spec["target"], spec.get("from_catalog")))
    for name, spec in (setup.get("stores") or {}).items():
        actions.append(("store", name, spec["path"], spec.get("init")))
    for comp in setup.get("companions") or []:
        actions.append(("companion", comp))
    for reg in setup.get("registrations") or []:
        actions.append(("registration", reg))
    for doc_name in setup.get("docs") or []:
        actions.append(("doc", doc_name))
    return actions


def adoption_files(example, live_id):
    """(layer sibling name, live relative path) pairs for the
    body files an adoption must copy."""
    pairs = []
    for field, new_rel in (("body", f"bodies/{live_id}.md"),
                           ("escalate_body", f"bodies/{live_id}-escalation.md")):
        rel = example.get(field)
        if rel:
            pairs.append((os.path.basename(rel), new_rel))
    return pairs


def machine_literals(data):
    """Machine/deployment literals hiding in the structural
    fields of a rendered adoption (the portability discipline,
    applied at the adopt boundary). Returns a list of findings."""
    findings = []

    def walk(value, trail):
        if isinstance(value, str):
            for rx in _LITERAL_RES:
                if rx.search(value) and not value.startswith(("${REPO}", "${WS}", "${HOME}")):
                    findings.append(f"{trail}: machine literal in {value!r}")
                    return
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{trail}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{trail}[{i}]")

    for field in ("run", "state_paths", "body", "escalate_body"):
        if field in data:
            walk(data[field], field)
    return findings


# ---------------------------------------------------------------- serializer

def _needs_quote(text):
    if text == "" or text != text.strip():
        return True
    if text in ("null", "~", "true", "false"):
        return True
    try:
        int(text)
        return True
    except ValueError:
        pass
    if text[0] in "['\"#-":
        return True
    if " #" in text or ": " in text or text.endswith(":"):
        return True
    return False


def _fmt_scalar(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if "\n" in text or _needs_quote(text):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return text


def _emit(data, indent, out):
    pad = " " * indent
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)) and value:
                out.append(f"{pad}{key}:")
                _emit(value, indent + 2, out)
            elif isinstance(value, dict):
                out.append(f"{pad}{key}: []")
            elif isinstance(value, list):
                out.append(f"{pad}{key}: []")
            else:
                out.append(f"{pad}{key}: {_fmt_scalar(value)}")
    elif isinstance(data, list):
        for item in data:
            out.append(f"{pad}- {_fmt_scalar(item)}")


def serialize_yaml(data):
    """Serialize a parsed entry (registry YAML subset) back to
    text the registry parser reads identically."""
    out = []
    _emit(data, 0, out)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- drift

# `source` is the stamp of the adoption act itself; `config`
# is the entry's live-tunable block — its knob values and
# version stamp move by design on every guarded save
# (server/entries/configblocks.py), each one a ledgered act, so the
# adoption render is never expected to match them after the
# first save. Neither is drift.
_VOLATILE = ("source", "config")


def _comparable(data):
    return {k: v for k, v in data.items() if k not in _VOLATILE}


def drift(root, catalog):
    """Diff adopted live entries against their catalog renders.
    Returns (lines, problems): one line per adopted entry, plus
    summary lines for the unadopted classes."""
    lines, problems = [], 0
    jobs_dir = os.path.join(root, "jobs")
    adopted, hand, machine, per_session = [], 0, 0, 0
    for name in sorted(os.listdir(jobs_dir)):
        if not name.endswith(".yaml"):
            continue
        job_id = name[: -len(".yaml")]
        try:
            data = _read_yaml(os.path.join(jobs_dir, name), name)
        except (EntryError, OSError) as exc:
            lines.append(f"{job_id}: UNREADABLE ({exc})")
            problems += 1
            continue
        src = data.get("source")
        if isinstance(src, dict) and "writer" in src:
            machine += 1  # machine-form source stamp (wb-progress)
            continue
        if not isinstance(src, dict) or "catalog" not in src:
            if job_id.startswith("wb-progress-"):
                machine += 1
            elif job_id.startswith("venue-liveness-"):
                per_session += 1
            else:
                hand += 1
            continue
        adopted.append((job_id, data, src))
    for job_id, data, src in adopted:
        example_id = src.get("catalog")
        if example_id not in catalog["entries"]:
            lines.append(f"{job_id}: DRIFT — catalog entry gone: {example_id}")
            problems += 1
            continue
        if src.get("catalog_version") != catalog["version"]:
            lines.append(
                f"{job_id}: catalog moved (adopted at v{src.get('catalog_version')}, "
                f"catalog now v{catalog['version']}) — re-adoption is a fresh adopt act")
            problems += 1
            continue
        expected, errors = render_adoption(
            example_id, catalog["entries"][example_id],
            src.get("parameters") or {}, catalog["version"])
        if errors:
            lines.append(f"{job_id}: DRIFT — recorded parameters no longer render: {errors}")
            problems += 1
            continue
        exp_cmp, live_cmp = _comparable(expected), _comparable(data)
        if exp_cmp == live_cmp:
            lines.append(f"{job_id}: adopted-and-current (from {example_id})")
        else:
            fields = sorted(
                k for k in set(exp_cmp) | set(live_cmp)
                if exp_cmp.get(k) != live_cmp.get(k))
            lines.append(f"{job_id}: DRIFT — fields differ from the catalog render: "
                         f"{', '.join(fields)}")
            problems += 1
    lines.append(
        f"unadopted: {hand} hand-written (no source stamp), "
        f"{machine} machine-written, {per_session} per-session — "
        "their writers own their lifecycle")
    return lines, problems
