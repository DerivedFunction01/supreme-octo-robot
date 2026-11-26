"""Supervision registry (superapp supervision plan,
Step 1): the per-programme declarations the measures
read — cadence, staffing band, escalation bound, venue,
coordinator route, measure classes, drain tail set, and
the staffing contract where one is ruled.

The declaration rows are instance data: they live in
an untracked configuration file (the settings seam's
supervision_registry_path — env ATTENTION_SUPERVISION_
REGISTRY first, else var/supervision-registry.json
under the attention state home), and this module is
the machinery over them: the loader, the validation
contract, and the lookups, referencing programmes by
key only. An absent config file is an empty registry,
honestly — no row is ever fabricated here. A config
that is present but malformed, or a declaration that
is missing a field — or carries an invalid one —
refuses loudly at load, never silently defaults.

The registry is data the measures read; no measure
hardcodes a programme. The generic rule text lives in
the spec (docs/supervision-rules.md) and passes down
to these declarations; it is never re-authored here.
"""

from __future__ import annotations

import copy
import json

from attention.settings import Settings


class RegistryError(ValueError):
    """A supervision declaration failed validation."""


# The gap-closure sweep's gap classes (its standing
# body, classes 1-6): the vocabulary a programme's
# measure-class enablement draws from. "stall" carries
# the sweep's stall/seam class, prerequisite seams
# included.
MEASURE_CLASSES = (
    "idle",
    "serial",
    "stall",
    "orphan",
    "unreported",
    "register_seam",
    "terminal",
    "unlanded",
)

# The standing drain tail defaults (owner answer at
# adoption): every programme's tail set
# starts from these; a programme's baked-in extras are
# its own declaration, appended per row below.
DEFAULT_DRAIN_TAIL = (
    {"key": "consolidation", "title": "Consolidation"},
    {"key": "doc-updates", "title": "Doc updates"},
    {"key": "performance", "title": "Performance pass"},
)

REQUIRED_FIELDS = (
    "slug",
    "label",
    "handles",
    "cadence_minutes",
    "staffing_band",
    "escalation_hours",
    "venue",
    "coordinator_route",
    "measure_classes",
    "drain_tail",
    "staffing_contract",
    "wb_projects",
    "retired",
)

_VENUES = ("colab", "local", "none")
_ROUTE_KINDS = ("chat", "todo")
_CONTRACT_FIELDS = (
    "unit",
    "evidence_window_minutes",
    "min_families_in_flight",
    "defect_conditions",
    "delegate_counts_toward_concurrency",
    "no_parallel_work_claim",
    "clearing",
    "non_response_after_consecutive_runs",
    "reminder_cadence_minutes",
)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_contract(slug: str, contract, problems: list) -> None:
    if contract is None:
        return
    if not isinstance(contract, dict):
        problems.append(f"{slug}.staffing_contract: must be a mapping or null")
        return
    for field in _CONTRACT_FIELDS:
        if field not in contract:
            problems.append(f"{slug}.staffing_contract.{field}: is required")
    if not isinstance(contract.get("unit"), str) or not contract.get("unit"):
        problems.append(f"{slug}.staffing_contract.unit: a non-empty string")
    for field in (
        "evidence_window_minutes",
        "min_families_in_flight",
        "non_response_after_consecutive_runs",
        "reminder_cadence_minutes",
    ):
        if not _is_number(contract.get(field)) or contract[field] <= 0:
            problems.append(f"{slug}.staffing_contract.{field}: a positive number")
    conditions = contract.get("defect_conditions")
    if (
        not isinstance(conditions, list)
        or not conditions
        or not all(isinstance(c, str) and c for c in conditions)
    ):
        problems.append(
            f"{slug}.staffing_contract.defect_conditions: "
            "a non-empty list of condition names"
        )
    if not isinstance(contract.get("delegate_counts_toward_concurrency"), bool):
        problems.append(
            f"{slug}.staffing_contract.delegate_counts_toward_concurrency: a boolean"
        )
    for field in ("no_parallel_work_claim", "clearing"):
        if not isinstance(contract.get(field), str) or not contract.get(field):
            problems.append(f"{slug}.staffing_contract.{field}: a non-empty string")
    if "staffable_queue" in contract:
        _validate_queue(slug, contract, problems)


def _validate_queue(slug: str, contract: dict, problems: list) -> None:
    """The staffable queue, checked whole: unique
    keys, every gate naming a key in the queue, work
    items carrying a family, markers carrying an
    explicit landed flag and neither a family nor a
    gate of their own."""
    queue = contract.get("staffable_queue")
    prefix = f"{slug}.staffing_contract.staffable_queue"
    if not isinstance(queue, list):
        problems.append(f"{prefix}: a list of queue entries")
        return
    keys: list = []
    for entry in queue:
        if not isinstance(entry, dict):
            problems.append(f"{prefix}: each entry is a mapping")
            return
        key = entry.get("key")
        if not (isinstance(key, str) and key):
            problems.append(f"{prefix}: each entry carries a non-empty key")
            return
        keys.append(key)
        if not (isinstance(entry.get("label"), str) and entry.get("label")):
            problems.append(f"{prefix}.{key}: a non-empty label")
        if entry.get("marker") is True:
            if "family" in entry or "staffable_when" in entry:
                problems.append(
                    f"{prefix}.{key}: a marker carries no family or staffable_when"
                )
            if not isinstance(entry.get("landed"), bool):
                problems.append(
                    f"{prefix}.{key}: a marker carries an explicit landed flag"
                )
        else:
            if not (isinstance(entry.get("family"), str) and entry.get("family")):
                problems.append(f"{prefix}.{key}: a work item carries a family")
            when = entry.get("staffable_when")
            if when is not None and not (isinstance(when, str) and when):
                problems.append(
                    f"{prefix}.{key}: staffable_when is null or a queue key"
                )
    if len(set(keys)) != len(keys):
        problems.append(f"{prefix}: duplicate entry keys")
    known = set(keys)
    for entry in queue:
        when = entry.get("staffable_when")
        if isinstance(when, str) and when and when not in known:
            problems.append(
                f"{prefix}.{entry['key']}: staffable_when names "
                f"unknown queue key {when}"
            )


def _validate_lane_declarations(slug: str, row: dict, problems: list) -> None:
    """The lane declaration, where a programme
    declares one: a declared count and one entry per
    lane. The venue field is always present — a
    session name, or the declared value "none" for an
    authoring-side lane; a lane record without one is
    refused, here as in the record grammar."""
    entries = row.get("lane_declarations")
    count = row.get("lane_declared_count")
    if entries is None and count is None:
        return
    prefix = f"{slug}.lane_declarations"
    if count is not None and not (isinstance(count, int) and count >= 0):
        problems.append(f"{slug}.lane_declared_count: a non-negative integer")
    if not isinstance(entries, list):
        problems.append(f"{prefix}: a list of lane declarations")
        return
    keys = []
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append(f"{prefix}: each entry is a mapping")
            return
        key = entry.get("key")
        keys.append(key)
        if not (isinstance(key, str) and key):
            problems.append(f"{prefix}: each entry carries a key")
            continue
        if not (isinstance(entry.get("label"), str) and entry.get("label")):
            problems.append(f"{prefix}.{key}: a lane carries a label")
        if not (isinstance(entry.get("venue"), str) and entry.get("venue")):
            problems.append(
                f"{prefix}.{key}: a lane always declares its venue — "
                "a session name, or none for an authoring-side lane"
            )
        minutes = entry.get("estimate_minutes")
        if minutes is not None and not (_is_number(minutes) and minutes > 0):
            problems.append(
                f"{prefix}.{key}: estimate_minutes is null or a positive number"
            )
        if not (
            isinstance(entry.get("termination_condition"), str)
            and entry.get("termination_condition")
        ):
            problems.append(f"{prefix}.{key}: a lane carries its termination condition")
        state = entry.get("state")
        if state is not None and state not in LANE_RECORD_STATES:
            problems.append(
                f"{prefix}.{key}: state is one of {list(LANE_RECORD_STATES)}"
            )
    if len(set(keys)) != len(keys):
        problems.append(f"{prefix}: duplicate lane keys")


def validate_declaration(row) -> dict:
    """One declaration, checked whole: every required
    field present and well-formed, or a RegistryError
    naming each problem. Returns the row unchanged."""
    if not isinstance(row, dict):
        raise RegistryError(f"declaration is not a mapping: {row!r}")
    slug = row.get("slug") or "<unnamed>"
    problems: list = []
    for field in REQUIRED_FIELDS:
        if field not in row:
            problems.append(f"{slug}.{field}: is required")
    if not isinstance(row.get("slug"), str) or not row.get("slug"):
        problems.append(f"{slug}.slug: a non-empty string")
    if not isinstance(row.get("label"), str) or not row.get("label"):
        problems.append(f"{slug}.label: a non-empty string")
    handles = row.get("handles")
    if (
        not isinstance(handles, list)
        or not handles
        or not all(isinstance(h, str) and h for h in handles)
    ):
        problems.append(f"{slug}.handles: a non-empty list of handles")
    if not _is_number(row.get("cadence_minutes")) or row["cadence_minutes"] <= 0:
        problems.append(f"{slug}.cadence_minutes: a positive number")
    band = row.get("staffing_band")
    if band is not None and (
        not isinstance(band, dict)
        or not isinstance(band.get("min"), int)
        or not isinstance(band.get("max"), int)
        or band["min"] > band["max"]
    ):
        problems.append(f"{slug}.staffing_band: null or {{min, max}}, min <= max")
    if not _is_number(row.get("escalation_hours")) or row["escalation_hours"] <= 0:
        problems.append(f"{slug}.escalation_hours: a positive number")
    if row.get("venue") not in _VENUES:
        problems.append(f"{slug}.venue: one of {_VENUES}")
    route = row.get("coordinator_route")
    if not isinstance(route, dict):
        problems.append(f"{slug}.coordinator_route: a mapping")
    else:
        if route.get("sender") != "wb":
            problems.append(
                f"{slug}.coordinator_route.sender: 'wb' — wb sends the steers"
            )
        if route.get("kind") not in _ROUTE_KINDS:
            problems.append(f"{slug}.coordinator_route.kind: one of {_ROUTE_KINDS}")
        elif route["kind"] == "chat" and not (
            isinstance(route.get("handle"), str) and route.get("handle")
        ):
            problems.append(
                f"{slug}.coordinator_route.handle: required for a chat route"
            )
        elif route["kind"] == "todo" and not (
            isinstance(route.get("bundle"), str) and route.get("bundle")
        ):
            problems.append(
                f"{slug}.coordinator_route.bundle: required for a todo route"
            )
    classes = row.get("measure_classes")
    if not isinstance(classes, list) or not classes:
        problems.append(f"{slug}.measure_classes: a non-empty list of classes")
    else:
        unknown = [c for c in classes if c not in MEASURE_CLASSES]
        if unknown:
            problems.append(
                f"{slug}.measure_classes: unknown classes {unknown}; "
                f"the vocabulary is {list(MEASURE_CLASSES)}"
            )
        if len(set(classes)) != len(classes):
            problems.append(f"{slug}.measure_classes: duplicates declared")
    tail = row.get("drain_tail")
    if not isinstance(tail, list) or not tail:
        problems.append(f"{slug}.drain_tail: a non-empty list of tail items")
    else:
        keys = []
        for item in tail:
            if (
                not isinstance(item, dict)
                or not (isinstance(item.get("key"), str) and item.get("key"))
                or not (isinstance(item.get("title"), str) and item.get("title"))
            ):
                problems.append(
                    f"{slug}.drain_tail: each item carries a key and a title"
                )
                break
            keys.append(item["key"])
        if len(set(keys)) != len(keys):
            problems.append(f"{slug}.drain_tail: duplicate item keys")
    if "staffing_contract" in row:
        _validate_contract(slug, row.get("staffing_contract"), problems)
    _validate_lane_declarations(slug, row, problems)
    projects = row.get("wb_projects")
    if not isinstance(projects, list) or not all(
        isinstance(p, str) and p for p in projects
    ):
        problems.append(f"{slug}.wb_projects: a list of workbench project slugs")
    if not isinstance(row.get("retired"), bool):
        problems.append(f"{slug}.retired: a boolean")
    stems = row.get("caller_stems")
    if stems is not None and (
        not isinstance(stems, list) or not all(isinstance(s, str) and s for s in stems)
    ):
        problems.append(
            f"{slug}.caller_stems: a list of caller stems the "
            "programme's runs ride under, where it declares any"
        )
    if problems:
        raise RegistryError("supervision declaration refused: " + "; ".join(problems))
    return row


# The lane record's state vocabulary (lane-records
# plan): a lane is declared, running, waiting in a
# declared gap, at hand-back, or terminated — and
# termination counts only on checkable evidence,
# never by silence, expiry, or say-so.
LANE_RECORD_STATES = (
    "declared",
    "running",
    "gap-wait",
    "hand-back",
    "terminated",
)

# The loaded rows, cached against the config file's
# identity: an edit to the file (the amendment form —
# declarations amend by editing the untracked config,
# never by commit) reloads on the next read.
_LOAD_CACHE: dict = {}


def _load_rows() -> list:
    """The configured declaration rows, validated whole
    at load. An absent config file is an empty registry;
    a present but malformed one refuses loudly."""
    path = Settings.from_env().supervision_registry_path
    try:
        stat = path.stat()
    except OSError:
        return []
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if _LOAD_CACHE.get("key") != key:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise RegistryError(
                f"supervision registry at {path} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(data, list):
            raise RegistryError(
                f"supervision registry at {path}: a list of declaration rows"
            )
        rows = [validate_declaration(copy.deepcopy(row)) for row in data]
        _LOAD_CACHE.clear()
        _LOAD_CACHE.update(key=key, rows=rows)
    return _LOAD_CACHE["rows"]


def declarations() -> list:
    """Every configured programme declaration, validated
    at load and returned as deep copies — a caller
    mutating a row never corrupts the registry."""
    return copy.deepcopy(_load_rows())


def active_declarations() -> list:
    """Declarations supervision still evaluates: a
    retired programme leaves the evaluator with it."""
    return [row for row in declarations() if not row["retired"]]


def for_slug(slug: str) -> dict | None:
    """The declaration for one programme slug, or None."""
    for row in declarations():
        if row["slug"] == slug:
            return row
    return None


def for_handle(handle: str | None) -> dict | None:
    """The declaration owning a handle: an active
    programme wins over a retired one declaring the
    same handle (the field programmes share one)."""
    if not handle:
        return None
    match = None
    for row in declarations():
        if handle in row["handles"]:
            if not row["retired"]:
                return row
            match = match or row
    return match


def cadence_for(handle: str | None, default: float) -> float:
    """The checkpoint cadence a lane owes: its
    programme's declared value, else the caller's
    default. Mirrors programmes.cadence_for so a
    measure can swap its parameter source."""
    row = for_handle(handle)
    if row and row.get("cadence_minutes"):
        return float(row["cadence_minutes"])
    return default


def escalation_for(handle: str | None, default: float) -> float:
    """The escalation bound for a lane's rows: declared,
    else the caller's default."""
    row = for_handle(handle)
    if row and row.get("escalation_hours"):
        return float(row["escalation_hours"])
    return default


def measure_classes_for(slug: str) -> list:
    """The measure classes enabled for a programme —
    the sweep's classes live or die by this list,
    never by an evaluator constant."""
    row = for_slug(slug)
    return list(row["measure_classes"]) if row else []


def coordinator_route_for(slug: str) -> dict | None:
    """Where a programme's steers go and who sends
    them: wb, over the declared route (chat or todo)."""
    row = for_slug(slug)
    return copy.deepcopy(row["coordinator_route"]) if row else None


def drain_tail_for(slug: str) -> list:
    """The tail set a drain raises for a programme:
    the standing defaults plus its declared extras."""
    row = for_slug(slug)
    return copy.deepcopy(row["drain_tail"]) if row else []


def staffing_contract_for(slug: str) -> dict | None:
    """The programme's ruled staffing contract (the
    edgar family-concurrency measure), or None where
    no contract is ruled."""
    row = for_slug(slug)
    if row and row.get("staffing_contract"):
        return copy.deepcopy(row["staffing_contract"])
    return None


def lane_declarations_for(slug: str) -> tuple:
    """The programme's declared lane records, in the
    registry-contract form: (declared count or None,
    the lane entries). The declared count is the
    coordinator's posted expected count; the entries
    are the per-lane declarations. (None, []) where
    the programme declares no lanes."""
    row = for_slug(slug)
    if not row:
        return None, []
    entries = row.get("lane_declarations") or []
    return row.get("lane_declared_count"), copy.deepcopy(entries)


def wb_projects_for(row: dict) -> list:
    """The workbench projects whose armed rows and
    bundles belong to this programme — the bundle/plan
    linkage Step 2's frontier comparison and Step 4's
    drain read through: its declared list, else its
    slug."""
    return row.get("wb_projects") or [row["slug"]]
