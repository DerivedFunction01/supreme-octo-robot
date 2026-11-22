"""Supervision registry (superapp supervision plan,
Step 1): the per-programme declarations the measures
read — cadence, staffing band, escalation bound, venue,
coordinator route, measure classes, drain tail set, and
the staffing contract where one is ruled. Seeded from
the live fleet's actual contracts: the edgar family-
concurrency measure (owner enforcement ruling,
2026-11-19), the gap-closure sweep's programme rows and
gap classes, and the armed todos' cadences.

The registry is data the measures read; no measure
hardcodes a programme, and a declaration that is
missing a field — or carries an invalid one — refuses
loudly at load, never silently defaults. The generic
rule text lives in the spec (docs/supervision-rules.md)
and passes down to these declarations; it is never
re-authored here.
"""

from __future__ import annotations

import copy


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
# adoption, 2026-11-19): every programme's tail set
# starts from these; a programme's baked-in extras are
# its own declaration, appended per row below.
DEFAULT_DRAIN_TAIL = (
    {"key": "consolidation", "title": "Consolidation"},
    {"key": "doc-updates", "title": "Doc updates"},
    {"key": "performance", "title": "Performance pass"},
)

# The edgar staffing contract, verbatim as data from
# the edgar-parallel-staffing reminder's measure
# section (owner enforcement ruling, 2026-11-19): the
# unit of staffing is the table family in flight, a
# family counts on a run in flight or evidence
# advancing within 30 minutes, fewer than 2 families
# in flight while 2 or more High-RAM sessions are live
# is a serial staffing defect (as are all compute on
# one session while another live session carries none,
# and a prerequisite-due family sitting unstaffed), a
# research delegate does not count toward family
# concurrency, a no-parallelizable-work claim is void
# unless verified family by family, the defect closes
# only on a later measure showing at least 2 families
# in flight across at least 2 sessions, and a defect
# surviving two consecutive runs names the
# coordinator's non-response. Amended 2026-11-21
# under the owner's fleet ruling of the same day —
# the fleet target is 3 standing High-RAM sessions
# and all three must actually be used — so the
# carrying floor is 3: family work spread over only
# 2 sessions while a third stands live and idle is
# the serial defect, priced by the same condition.
EDGAR_STAFFING_CONTRACT = {
    "unit": "table_family",
    "evidence_window_minutes": 30,
    "min_families_in_flight": 2,
    "min_live_sessions": 2,
    "min_sessions_carrying_work": 3,
    "defect_conditions": [
        "fewer_than_min_families_in_flight",
        "all_compute_on_one_session_while_another_live_session_carries_none",
        "prerequisite_due_family_unstaffed",
    ],
    "delegate_counts_toward_concurrency": False,
    "no_parallel_work_claim": "void_unless_verified_family_by_family",
    "clearing": "later_measure_only",
    "non_response_after_consecutive_runs": 2,
    "reminder_cadence_minutes": 30,
}

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

_VENUES = ("colab", "none")
_ROUTE_KINDS = ("chat", "todo")
_CONTRACT_FIELDS = (
    "unit",
    "evidence_window_minutes",
    "min_families_in_flight",
    "min_live_sessions",
    "min_sessions_carrying_work",
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
        "min_live_sessions",
        "min_sessions_carrying_work",
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


def _tail(*extra: dict) -> list:
    return [dict(item) for item in DEFAULT_DRAIN_TAIL] + [dict(e) for e in extra]


# The seeded declarations: one row per programme the
# live fleet supervises, mirroring its declared
# contract in the attention store, plus the registry's
# own fields — the coordinator route (wb-sent, per the
# amended Step 3), the measure classes the sweep's
# rows enable, the drain tail set, and, for the edgar
# programmes, the staffing contract above. Cadences
# are the armed todos' cadence: conforming
# progress-checkpoints every 15 minutes while doing.
_SEED = (
    {
        "slug": "edgar-greenfield",
        "label": "edgar — greenfield extractor",
        "handles": ["@xbrl"],
        "cadence_minutes": 15,
        "staffing_band": None,
        "escalation_hours": 1,
        "venue": "colab",
        "coordinator_route": {"sender": "wb", "kind": "chat", "handle": "@xbrl"},
        "measure_classes": [
            "idle",
            "serial",
            "stall",
            "orphan",
            "unreported",
            "terminal",
            "unlanded",
        ],
        "drain_tail": _tail(),
        "staffing_contract": copy.deepcopy(EDGAR_STAFFING_CONTRACT),
        "wb_projects": ["edgar-sec"],
        "retired": False,
    },
    {
        "slug": "edgar-sec",
        "label": "edgar — classifier",
        "handles": ["@xbrl"],
        "cadence_minutes": 15,
        "staffing_band": {"min": 10, "max": 12},
        "escalation_hours": 1,
        "venue": "colab",
        "coordinator_route": {"sender": "wb", "kind": "chat", "handle": "@xbrl"},
        "measure_classes": ["idle", "serial", "stall", "orphan", "unreported"],
        "drain_tail": _tail(),
        "staffing_contract": None,
        "wb_projects": [],
        "retired": True,
    },
    {
        "slug": "steampowernj",
        "label": "Steam Power — site rebuild",
        "handles": ["@steampower"],
        "cadence_minutes": 15,
        "staffing_band": None,
        "escalation_hours": 1,
        "venue": "none",
        "coordinator_route": {
            "sender": "wb",
            "kind": "chat",
            "handle": "@steampower",
        },
        "measure_classes": [
            "idle",
            "serial",
            "stall",
            "orphan",
            "unreported",
            "register_seam",
            "terminal",
            "unlanded",
        ],
        # The programme's venue runs ride the caller
        # prefix "steampower" (steampower-cust and its
        # lanes), not the slug stem "steampowernj" —
        # declared so caller attribution stays data.
        "caller_stems": ["steampower"],
        "drain_tail": _tail({"key": "tech-debt-paydown", "title": "Tech-debt paydown"}),
        "staffing_contract": None,
        "wb_projects": ["steampowernj"],
        "retired": False,
    },
    {
        "slug": "supreme-octo-robot",
        "label": "Workhorse superapp — mega app build",
        "handles": ["@workhorse"],
        "cadence_minutes": 15,
        "staffing_band": None,
        "escalation_hours": 1,
        "venue": "colab",
        "coordinator_route": {
            "sender": "wb",
            "kind": "chat",
            "handle": "@workhorse",
        },
        "measure_classes": [
            "idle",
            "serial",
            "stall",
            "orphan",
            "unreported",
            "terminal",
            "unlanded",
        ],
        # The programme's venue runs ride the caller
        # "workhorse", not the slug stem "supreme".
        "caller_stems": ["workhorse"],
        "drain_tail": _tail(),
        "staffing_contract": None,
        # The programme's workbench surface answers to
        # two names, one per surface: the wb server
        # serves the bundle under "workbench-viewer"
        # (its --project slug) while the armed-row
        # file drop keys its rows "workrecord" — both
        # are declared so the frontier attribution and
        # the armed match read the same programme.
        "wb_projects": ["workbench-viewer", "workrecord"],
        "retired": False,
    },
)


def declarations() -> list:
    """Every seeded programme declaration, validated at
    load and returned as deep copies — a caller mutating
    a row never corrupts the registry."""
    return [validate_declaration(copy.deepcopy(row)) for row in _SEED]


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
    same handle (the edgar programmes share @xbrl)."""
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


def wb_projects_for(row: dict) -> list:
    """The workbench projects whose armed rows and
    bundles belong to this programme — the bundle/plan
    linkage Step 2's frontier comparison and Step 4's
    drain read through: its declared list, else its
    slug."""
    return row.get("wb_projects") or [row["slug"]]
