"""The handler + programme directory (ATT2/ATT3, §4.1).

The seed/export form of the attention directory: handler
rows and programme rows, written by upsert, read whole.
The upsert semantics are the PINNED attention write
service's, ported field for field (backend/services/
writes.py at the attention pin): handle + label required
on a handler upsert, a plain slug + label on a programme
upsert, omitted fields preserved from the existing entry,
the named defaults where no entry exists, ui_surface and
handler retired coerced to bool, a programme's venue in
{colab, local, none}. Contract 01 §9 annex carries the shapes;
the pin carries the semantics, and where the S0 schema's
guesses differ from the pin (ui_surface typed "string"),
the pin wins — named in the S7 report.

Programmes join the registry here per §9.1: the registry
is their projection; rule_text/cadence_minutes are owned
by the goal record and refreshed from it by their owner.
"""

from .. import store as store_mod

__all__ = ["validate_handler_row", "validate_programme_row",
           "upsert_handler", "upsert_programme", "find_programme",
           "handler_for"]


# -- validation ---------------------------------------------------

def _is_int(value):
    return isinstance(value, int) and not isinstance(value,
                                                      bool)


def validate_handler_row(row):
    """Structural check of a STORED handler row against
    the pinned shapes: handle + label non-empty strings;
    the optional fields, when present and not null, of
    their pinned types (thread_id null = unbound, as the
    captured rows carry it)."""
    problems = []
    if not isinstance(row, dict):
        return ["handler row is not an object"]
    for key in ("handle", "label"):
        if not isinstance(row.get(key), str) \
                or not row.get(key):
            problems.append(f"{key} is required")
    typed = {"color_slot": "int", "icon": str,
             "thread_id": str, "ui_surface": bool,
             "retired": bool}
    for key, check in typed.items():
        value = row.get(key)
        if value is None:
            continue
        ok = _is_int(value) if check == "int" else \
            isinstance(value, check)
        if not ok:
            problems.append(f"{key} has the wrong type")
    return problems


def _programme_problems(row, *, stored):
    problems = []
    if not isinstance(row, dict):
        return ["programme row is not an object"]
    slug = row.get("slug") or ""
    if not slug or "/" in slug or slug.startswith("."):
        problems.append("a plain slug is required")
    if not row.get("label"):
        problems.append("label is required")
    for field in ("handles", "record_locations",
                  "idle_classes", "wb_projects"):
        value = row.get(field)
        if value is not None and (
                not isinstance(value, list)
                or not all(isinstance(x, str) for x in value)):
            problems.append(f"{field} must be a list of "
                            "strings")
    for field in ("cadence_minutes", "escalation_hours"):
        value = row.get(field)
        if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool) or value <= 0):
            problems.append(f"{field} must be positive")
    band = row.get("staffing_band")
    if band is not None and (
            not isinstance(band, dict)
            or not _is_int(band.get("min"))
            or not _is_int(band.get("max"))
            or band["min"] > band["max"]):
        problems.append("staffing_band must be "
                        "{min, max} with min <= max")
    if row.get("venue") not in (None, "colab", "local", "none"):
        problems.append("venue must be colab, local or none")
    if stored:
        for field in ("settled", "commissions",
                      "worktree_roots"):
            value = row.get(field)
            if value is not None and not isinstance(
                    value, list):
                problems.append(f"{field} must be a list")
        rule = row.get("rule_text")
        if rule is not None and not isinstance(rule, str):
            problems.append("rule_text must be a string")
    return problems


def validate_programme_row(row):
    """Structural check of a STORED programme row (the
    pinned payload rules plus the stored list fields)."""
    return _programme_problems(row, stored=True)


# -- upserts (the pinned field-wise merges) ------------------------

def upsert_handler(registry, row):
    """The pinned handler upsert: handle + label required
    in the presented row; the other five fields ride
    payload → existing → default; ui_surface and retired
    coerce to bool; keys outside the seven are the stored
    row's business, not the payload's."""
    if not isinstance(row, dict) or not row.get("handle") \
            or not row.get("label"):
        raise ValueError("handler upsert requires handle "
                         "and label")
    rows = registry.data["handlers"]
    existing = next(
        (h for h in rows if h.get("handle") == row["handle"]),
        {})
    entry = dict(existing)
    entry.update({
        "handle": row["handle"],
        "label": row["label"],
        "color_slot": row.get(
            "color_slot", existing.get("color_slot", 1)),
        "icon": row.get("icon", existing.get("icon", "dot")),
        "thread_id": row.get(
            "thread_id", existing.get("thread_id")),
        "ui_surface": bool(row.get(
            "ui_surface", existing.get("ui_surface", False))),
        "retired": bool(row.get(
            "retired", existing.get("retired", False))),
    })
    rows[:] = [h for h in rows
               if h.get("handle") != entry["handle"]]
    rows.append(entry)
    return entry


def upsert_programme(registry, row):
    """The pinned programme upsert: the payload validates
    under the pinned rules (a bad row raises before any
    merge), then the named fields merge payload →
    existing → default, field for field as the pin."""
    problems = _programme_problems(row, stored=False)
    if problems:
        raise ValueError("programme upsert refused: "
                         + "; ".join(problems))
    slug = row["slug"]
    rows = registry.data["programmes"]
    existing = next(
        (p for p in rows if p.get("slug") == slug), {})
    entry = dict(existing)
    entry.update({
        "slug": slug,
        "label": row["label"],
        "handles": row.get(
            "handles", existing.get("handles", [])),
        "cadence_minutes": row.get(
            "cadence_minutes", existing.get("cadence_minutes")),
        "staffing_band": row.get(
            "staffing_band", existing.get("staffing_band")),
        "escalation_hours": row.get(
            "escalation_hours",
            existing.get("escalation_hours")),
        "venue": row.get("venue", existing.get("venue", "none")),
        "rule_text": row.get(
            "rule_text", existing.get("rule_text", "")),
        "settled": row.get(
            "settled", existing.get("settled", [])),
        "commissions": row.get(
            "commissions", existing.get("commissions", [])),
        "worktree_roots": row.get(
            "worktree_roots", existing.get("worktree_roots", [])),
        "record_locations": row.get(
            "record_locations",
            existing.get("record_locations", [])),
        "contract_path": row.get(
            "contract_path", existing.get("contract_path")),
        "idle_classes": row.get(
            "idle_classes", existing.get("idle_classes", [])),
        "wb_projects": row.get(
            "wb_projects", existing.get("wb_projects", [])),
        "retired": row.get(
            "retired", existing.get("retired", False)),
    })
    rows[:] = [p for p in rows if p.get("slug") != slug]
    rows.append(entry)
    return entry


# -- reads ----------------------------------------------------------

def find_programme(registry, slug):
    """The programme row for a slug, or None (DISP7's
    programme lookup, served from the one registry)."""
    return next((p for p in registry.data["programmes"]
                 if p.get("slug") == slug), None)


def handler_for(registry, handle):
    """The handler row a handle names, or None — a
    programme's handles resolve against the directory or
    the programme is misdeclared (DISP7)."""
    return next((h for h in registry.data["handlers"]
                 if h.get("handle") == handle), None)
