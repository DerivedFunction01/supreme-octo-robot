"""Owner writes: triage, presence, rules (API.md).

Each write is validated, applied to state, and read back by
the caller from the same state — the response is the stored
record, never an echo of the request.
"""

from __future__ import annotations

import re
from datetime import datetime

from attention.domain import attention as dom
from attention.errors import NotFound, Validation
from attention.services.writes.ingest import _parse_dt


def unmute_type(state: dict, handle: str, payload: dict) -> dict:
    kind = payload.get("kind")
    pair = [handle, kind]
    if pair not in state["muted"]:
        raise NotFound("That type is not muted for this handler.")
    state["muted"].remove(pair)
    for item in state["items"]:
        if (
            item["handle"] == handle
            and item["kind"] == kind
            and item["triage"] == "muted"
        ):
            item["triage"] = "open"
    return {"handle": handle, "kind": kind, "muted": False}


def mute_type(state: dict, handle: str, payload: dict) -> dict:
    """The handler-page mute (AC-8): the mirror of
    unmute_type. Until now muting a type rode only an
    item's mute_type triage; the handler page's toggle had
    no route. Muting the type adds the pair and mutes the
    handler's open items of that kind, exactly as the
    item-level mute leaves them."""
    kind = payload.get("kind")
    if not kind:
        raise Validation(
            "Mute failed validation.",
            [{"field": "kind", "message": "is required"}],
        )
    pair = [handle, kind]
    if pair not in state["muted"]:
        state["muted"].append(pair)
    for item in state["items"]:
        if (
            item["handle"] == handle
            and item["kind"] == kind
            and item["triage"] == "open"
        ):
            item["triage"] = "muted"
    return {"handle": handle, "kind": kind, "muted": True}


_WINDOW_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _window_time_ok(text) -> bool:
    return isinstance(text, str) and bool(_WINDOW_TIME_RE.match(text))


def set_digest_prefs(state: dict, payload: dict) -> dict:
    """The digest switches' write (AC-8): window enablement
    and the include flags, stored on state so every client
    reads the same digest the owner configured. Windows
    are keyed by their served time; an unlisted time keeps
    its default (enabled).

    The owner may also set the window TIMES themselves
    (window_times, 1-6 HH:MM wall times) with the timezone
    they are wall times in (window_tz, an IANA name) —
    the hardcoded-time cure: the times stop being a
    settings constant read in the server's frame and
    become the owner's, read in the owner's timezone.
    Setting the times prunes the enablement map to the
    new list (a renamed window starts enabled)."""
    prefs = state.setdefault("digest_prefs", {"windows": {}, "include": {}})
    errors: list = []
    if "window_times" in payload or "window_tz" in payload:
        times = payload.get("window_times")
        tz_name = payload.get("window_tz")
        if (
            not isinstance(times, list)
            or not 1 <= len(times) <= 6
            or not all(_window_time_ok(t) for t in times)
        ):
            errors.append(
                {"field": "window_times", "message": "1-6 HH:MM times required"}
            )
        if not isinstance(tz_name, str) or not tz_name:
            errors.append({"field": "window_tz", "message": "is required"})
        else:
            try:
                from zoneinfo import ZoneInfo

                ZoneInfo(tz_name)
            except Exception:  # noqa: BLE001 - any failure names the field
                errors.append({"field": "window_tz", "message": "unknown timezone"})
        if not errors:
            prefs["window_times"] = sorted(set(times))
            prefs["window_tz"] = tz_name
            prefs["windows"] = {
                t: on
                for t, on in prefs["windows"].items()
                if t in prefs["window_times"]
            }
    if "window_time" in payload or "window_enabled" in payload:
        time = payload.get("window_time")
        if not isinstance(time, str) or not time:
            errors.append({"field": "window_time", "message": "is required"})
        else:
            prefs["windows"][time] = bool(payload.get("window_enabled"))
    if "include_key" in payload or "include_enabled" in payload:
        key = payload.get("include_key")
        if key not in ("decisions", "waiting", "fyi"):
            errors.append({"field": "include_key", "message": "unknown key"})
        else:
            prefs["include"][key] = bool(payload.get("include_enabled"))
    if errors:
        raise Validation("Digest preferences failed validation.", errors)
    return {
        "windows": dict(prefs["windows"]),
        "window_times": prefs.get("window_times"),
        "window_tz": prefs.get("window_tz"),
        "include": {
            key: prefs["include"].get(key, True)
            for key in ("decisions", "waiting", "fyi")
        },
    }


def apply_triage(state: dict, item_id: str, payload: dict, now: datetime) -> dict:
    item = next((i for i in state["items"] if i["id"] == item_id), None)
    if item is None:
        raise NotFound("No such item.")
    action = payload.get("action")
    if action == "acknowledge":
        item["triage"] = "acknowledged"
        _mark_acted(state, item)
    elif action == "act":
        item["triage"] = "acknowledged"
        _mark_acted(state, item)
    elif action == "done":
        item["triage"] = "done"
        _mark_acted(state, item)
    elif action == "mute_type":
        item["triage"] = "muted"
        pair = [item["handle"], item["kind"]]
        if pair not in state["muted"]:
            state["muted"].append(pair)
    elif action == "snooze":
        errors: list = []
        return_at = _parse_dt(payload.get("return_at"), "return_at", errors)
        if errors:
            raise Validation("Snooze failed validation.", errors)
        item["triage"] = "snoozed"
        item["snooze_return_at"] = return_at
        item["snooze_on_activity"] = bool(payload.get("return_on_activity"))
        item["resume_note"] = payload.get("resume_note")
    else:
        raise Validation(
            "Triage failed validation.",
            [{"field": "action", "message": "unknown action"}],
        )
    return item


def _mark_acted(state: dict, item: dict) -> None:
    for log in state["action_log"]:
        if log.get("kind") == "breakthrough" and log.get("item_id") == item["id"]:
            log["acted"] = True


def set_presence(state: dict, payload: dict) -> dict:
    errors: list = []
    mode = payload.get("mode")
    if mode not in dom.PRESENCE_MODES:
        errors.append({"field": "mode", "message": "unknown presence mode"})
    expires_at = _parse_dt(payload.get("expires_at"), "expires_at", errors)
    if errors:
        raise Validation("Presence failed validation.", errors)
    state["presence"] = {
        "mode": mode,
        "expires_at": expires_at,
        "expectation": payload.get("expectation", ""),
    }
    return state["presence"]


ACTION_TYPES = ("auto_apply", "surface", "hold", "post", "post_and_apply")
TRIGGER_KINDS = (
    "on_enter",
    "on_age",
    "on_repeat",
    "on_state_change",
    "on_presence_enter",
)


def _check_where(node, fields: set, errors: list) -> None:
    if node is None:
        return
    if not isinstance(node, dict):
        errors.append({"field": "where", "message": "must be a tree object"})
        return
    for key in ("all", "any"):
        for child in node.get(key, []) or []:
            _check_where(child, fields, errors)
    if "not" in node:
        _check_where(node["not"], fields, errors)
    if "field" in node:
        if node["field"] not in fields:
            errors.append(
                {"field": "where", "message": f"unknown field: {node['field']}"}
            )
        if node.get("op") not in dom.OPS:
            errors.append(
                {"field": "where", "message": f"unknown op: {node.get('op')}"}
            )


def add_rule(state: dict, payload: dict) -> dict:
    """Rules are data, validated against the registries. A
    new rule starts in shadow (it logs what it would do)
    unless the owner's write explicitly promotes it."""
    errors: list = []
    match = payload.get("match") or {}
    action = payload.get("action") or {"type": "auto_apply"}
    if isinstance(action, str):
        action = {"type": action}
    rule = {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "match": {
            "wait_class": match.get("wait_class"),
            "status_code": match.get("status_code"),
            "kind": match.get("kind"),
            "handle": match.get("handle"),
        },
        "where": payload.get("where"),
        "action": action,
        "scope": payload.get("scope", "always"),
        "requires": payload.get("requires", []),
        "priority": payload.get("priority", 100),
        "on_scope_miss": payload.get("on_scope_miss", "pending"),
        "trigger": payload.get("trigger") or {"on": "on_enter"},
        "guards": payload.get("guards") or {},
        "mode": payload.get("mode", "shadow"),
    }
    fields = {f["name"] for f in state.get("fields", [])}
    codes = {c["code"] for c in state.get("status_codes", [])}
    classes = {c["name"] for c in state.get("wait_classes", [])}
    templates = {t["kind"] for t in state.get("templates", [])}
    if not rule["id"]:
        errors.append({"field": "id", "message": "is required"})
    if action.get("type") not in ACTION_TYPES:
        errors.append({"field": "action", "message": "unknown action type"})
    if rule["scope"] not in ("always", "away", "active"):
        errors.append({"field": "scope", "message": "unknown scope"})
    if rule["mode"] not in ("active", "shadow"):
        errors.append({"field": "mode", "message": "unknown mode"})
    if rule["on_scope_miss"] not in ("pending", "fallthrough"):
        errors.append({"field": "on_scope_miss", "message": "unknown behaviour"})
    if rule["trigger"].get("on") not in TRIGGER_KINDS:
        errors.append({"field": "trigger", "message": "unknown trigger"})
    if match.get("wait_class") is not None and match["wait_class"] not in classes:
        errors.append({"field": "match.wait_class", "message": "unregistered class"})
    wanted_codes = match.get("status_code")
    if wanted_codes is not None:
        code_list = wanted_codes if isinstance(wanted_codes, list) else [wanted_codes]
        if any(code not in codes for code in code_list):
            errors.append(
                {"field": "match.status_code", "message": "unregistered status code"}
            )
    unknown = [f for f in rule["requires"] if f not in fields]
    if unknown:
        errors.append({"field": "requires", "message": f"unknown fields: {unknown}"})
    _check_where(rule["where"], fields, errors)
    if action.get("type") in ("post", "post_and_apply"):
        kinds = (
            {action.get("template")}
            | set((action.get("variants") or {}).get("presence", {}).values())
            | set((action.get("variants") or {}).get("attempt", {}).values())
        )
        missing = [k for k in kinds if k is not None and k not in templates]
        if missing:
            errors.append(
                {"field": "action.template", "message": f"unknown templates: {missing}"}
            )
    if not errors and not dom.rule_is_legal(rule, state.get("wait_classes")):
        errors.append(
            {
                "field": "match.wait_class",
                "message": "hard-stop classes may not be applied",
            }
        )
    if errors:
        raise Validation("Rule failed validation.", errors)
    state["rules"] = [r for r in state["rules"] if r["id"] != rule["id"]]
    state["rules"].append(rule)
    return rule


def _register(state: dict, key: str, entry: dict, id_field: str) -> dict:
    state[key] = [e for e in state[key] if e[id_field] != entry[id_field]]
    state[key].append(entry)
    return entry


def add_status_code(state: dict, payload: dict) -> dict:
    errors: list = []
    for field in ("code", "short", "label", "need"):
        if not payload.get(field):
            errors.append({"field": field, "message": "is required"})
    if payload.get("need") not in dom.NEEDS:
        errors.append({"field": "need", "message": "unknown need"})
    if errors:
        raise Validation("Status code failed validation.", errors)
    entry = {
        "code": payload["code"],
        "short": payload["short"],
        "label": payload["label"],
        "need": payload["need"],
        "terminal": bool(payload.get("terminal")),
    }
    return _register(state, "status_codes", entry, "code")


def add_item_kind(state: dict, payload: dict) -> dict:
    errors: list = []
    for field in ("kind", "label"):
        if not payload.get(field):
            errors.append({"field": field, "message": "is required"})
    if errors:
        raise Validation("Item kind failed validation.", errors)
    if payload.get("digest_owner") not in (None, "owner", "lane", "self"):
        errors.append(
            {"field": "digest_owner", "message": "must be owner, lane, or self"}
        )
    if errors:
        raise Validation("Item kind failed validation.", errors)
    entry = {
        "kind": payload["kind"],
        "label": payload["label"],
        "status_kind": bool(payload.get("status_kind")),
        "digest_owner": payload.get("digest_owner"),
    }
    return _register(state, "item_kinds", entry, "kind")


def add_field(state: dict, payload: dict) -> dict:
    errors: list = []
    for field in ("name", "type"):
        if not payload.get(field):
            errors.append({"field": field, "message": "is required"})
    if payload.get("type") not in ("bool", "enum", "number", "datetime", "string"):
        errors.append({"field": "type", "message": "unknown field type"})
    if errors:
        raise Validation("Field failed validation.", errors)
    entry = {
        "name": payload["name"],
        "type": payload["type"],
        "source": "poster",
        "poster_settable": True,
    }
    return _register(state, "fields", entry, "name")


def add_wait_class(state: dict, payload: dict) -> dict:
    if not payload.get("name"):
        raise Validation(
            "Class failed validation.",
            [{"field": "name", "message": "is required"}],
        )
    errors: list = []
    stale_after = payload.get("stale_after_hours")
    if stale_after is not None and (
        isinstance(stale_after, bool)
        or not isinstance(stale_after, (int, float))
        or stale_after <= 0
    ):
        errors.append(
            {
                "field": "stale_after_hours",
                "message": "must be null or a positive number",
            }
        )
    on_stale = payload.get("on_stale", "expire")
    if on_stale not in ("expire", "expire_blocked"):
        errors.append({"field": "on_stale", "message": "unknown on_stale disposition"})
    if errors:
        raise Validation("Class failed validation.", errors)
    existing = next(
        (c for c in state["wait_classes"] if c["name"] == payload["name"]), None
    )
    if existing and existing.get("hard_stop"):
        raise Validation(
            "Class failed validation.",
            [{"field": "name", "message": "hard-stop classes are not editable"}],
        )
    entry = {
        "name": payload["name"],
        "hard_stop": False,
        "stale_after_hours": stale_after,
        "on_stale": on_stale,
    }
    return _register(state, "wait_classes", entry, "name")


def add_template(state: dict, payload: dict) -> dict:
    errors: list = []
    for field in ("kind", "text"):
        if not payload.get(field):
            errors.append({"field": field, "message": "is required"})
    if payload.get("audience") not in ("chat", "main"):
        errors.append({"field": "audience", "message": "must be chat or main"})
    if errors:
        raise Validation("Template failed validation.", errors)
    prior = next((t for t in state["templates"] if t["kind"] == payload["kind"]), None)
    entry = {
        "kind": payload["kind"],
        "version": (prior["version"] + 1) if prior else 1,
        "audience": payload["audience"],
        "slots": payload.get("slots", []),
        "text": payload["text"],
    }
    return _register(state, "templates", entry, "kind")


def record_dispatch_failure(state: dict, payload: dict, now: datetime) -> dict:
    """The dispatch consumer's failure report (§1.11
    (f)): recorded against the send, never an ack."""
    errors: list = []
    for field in ("send_id", "consumer", "reason"):
        if not payload.get(field):
            errors.append({"field": field, "message": "is required"})
    if errors:
        raise Validation("Dispatch failure failed validation.", errors)
    send = next(
        (s for s in state.get("sends") or [] if s.get("id") == payload["send_id"]),
        None,
    )
    if send is None:
        raise NotFound("No such send.")
    state.setdefault("dispatch_failures", []).append(
        {
            "send_id": payload["send_id"],
            "consumer": payload["consumer"],
            "reason": payload["reason"],
            "at": now,
        }
    )
    return {"contract": "api/1", "send_id": payload["send_id"], "recorded": True}


def record_verification(state: dict, payload: dict, now: datetime) -> dict:
    """Main's stamp on a blocked record's cited basis
    (§1.11 (i) addenda): verified, or void."""
    errors: list = []
    if not payload.get("handle"):
        errors.append({"field": "handle", "message": "is required"})
    if payload.get("verdict") not in ("verified", "void"):
        errors.append({"field": "verdict", "message": "must be verified or void"})
    if errors:
        raise Validation("Verification failed validation.", errors)
    handle = payload["handle"]
    if handle not in {h["handle"] for h in state.get("handlers", [])}:
        raise NotFound("No such handler.")
    state.setdefault("verifications", []).append(
        {
            "handle": handle,
            "verdict": payload["verdict"],
            "note": payload.get("note") or "",
            "posted_by": payload.get("posted_by"),
            "at": now,
        }
    )
    return {
        "contract": "api/1",
        "handle": handle,
        "verdict": payload["verdict"],
        "recorded": True,
    }


def upsert_programme(state: dict, payload: dict) -> dict:
    """A programme declaration: the registry row a
    programme onboards with — handles, cadence, band,
    escalation, venue, rule text, worktree roots."""
    errors: list = []
    slug = payload.get("slug") or ""
    if not slug or "/" in slug or slug.startswith("."):
        errors.append({"field": "slug", "message": "a plain slug is required"})
    if not payload.get("label"):
        errors.append({"field": "label", "message": "is required"})
    handles = payload.get("handles")
    if handles is not None and (
        not isinstance(handles, list) or not all(isinstance(h, str) for h in handles)
    ):
        errors.append({"field": "handles", "message": "a list of handles"})
    locations = payload.get("record_locations")
    if locations is not None and (
        not isinstance(locations, list)
        or not all(isinstance(x, str) for x in locations)
    ):
        errors.append({"field": "record_locations", "message": "a list of paths"})
    classes = payload.get("idle_classes")
    if classes is not None and (
        not isinstance(classes, list) or not all(isinstance(x, str) for x in classes)
    ):
        errors.append({"field": "idle_classes", "message": "a list of classes"})
    projects = payload.get("wb_projects")
    if projects is not None and (
        not isinstance(projects, list) or not all(isinstance(x, str) for x in projects)
    ):
        errors.append({"field": "wb_projects", "message": "a list of projects"})
    for field in ("cadence_minutes", "escalation_hours"):
        value = payload.get(field)
        if value is not None and (not isinstance(value, (int, float)) or value <= 0):
            errors.append({"field": field, "message": "must be positive"})
    band = payload.get("staffing_band")
    if band is not None and (
        not isinstance(band, dict)
        or not isinstance(band.get("min"), int)
        or not isinstance(band.get("max"), int)
        or band["min"] > band["max"]
    ):
        errors.append({"field": "staffing_band", "message": "min and max, min <= max"})
    if payload.get("venue") not in (None, "colab", "local", "none"):
        errors.append({"field": "venue", "message": "colab, local or none"})
    if errors:
        raise Validation("Programme failed validation.", errors)
    existing = next((p for p in state.get("programmes") or [] if p["slug"] == slug), {})
    entry = dict(existing)
    entry.update(
        {
            "slug": slug,
            "label": payload["label"],
            "handles": payload.get("handles", existing.get("handles", [])),
            "cadence_minutes": payload.get(
                "cadence_minutes", existing.get("cadence_minutes")
            ),
            "staffing_band": payload.get(
                "staffing_band", existing.get("staffing_band")
            ),
            "escalation_hours": payload.get(
                "escalation_hours", existing.get("escalation_hours")
            ),
            "venue": payload.get("venue", existing.get("venue", "none")),
            "rule_text": payload.get("rule_text", existing.get("rule_text", "")),
            "settled": payload.get("settled", existing.get("settled", [])),
            "commissions": payload.get("commissions", existing.get("commissions", [])),
            "worktree_roots": payload.get(
                "worktree_roots", existing.get("worktree_roots", [])
            ),
            "record_locations": payload.get(
                "record_locations", existing.get("record_locations", [])
            ),
            "contract_path": payload.get(
                "contract_path", existing.get("contract_path")
            ),
            "idle_classes": payload.get(
                "idle_classes", existing.get("idle_classes", [])
            ),
            "wb_projects": payload.get("wb_projects", existing.get("wb_projects", [])),
            "retired": payload.get("retired", existing.get("retired", False)),
        }
    )
    state["programmes"] = [
        p for p in state.get("programmes") or [] if p["slug"] != slug
    ]
    state["programmes"].append(entry)
    return entry


def register_handler(state: dict, payload: dict) -> dict:
    errors: list = []
    for field in ("handle", "label"):
        if not payload.get(field):
            errors.append({"field": field, "message": "is required"})
    if errors:
        raise Validation("Handler failed validation.", errors)
    existing = next(
        (h for h in state["handlers"] if h["handle"] == payload["handle"]), {}
    )
    entry = dict(existing)
    entry.update(
        {
            "handle": payload["handle"],
            "label": payload["label"],
            "color_slot": payload.get("color_slot", existing.get("color_slot", 1)),
            "icon": payload.get("icon", existing.get("icon", "dot")),
            "thread_id": payload.get("thread_id", existing.get("thread_id")),
            "ui_surface": bool(
                payload.get("ui_surface", existing.get("ui_surface", False))
            ),
            "retired": bool(payload.get("retired", existing.get("retired", False))),
        }
    )
    state["handlers"] = [h for h in state["handlers"] if h["handle"] != entry["handle"]]
    state["handlers"].append(entry)
    return entry
