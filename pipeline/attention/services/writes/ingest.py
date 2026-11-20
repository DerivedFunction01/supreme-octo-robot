"""Agent posting (API.md, agent posting contract).

Validation lives at the seam; classification and tier are
backend derivations — the poster supplies facts, not verdicts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from attention.domain import attention as dom
from attention.errors import NotFound, Validation
from attention.services.waits import engine


def _require(payload: dict, field: str, errors: list) -> None:
    if payload.get(field) in (None, ""):
        errors.append({"field": field, "message": "is required"})


def _parse_dt(value, field: str, errors: list):
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        errors.append({"field": field, "message": "must be an ISO 8601 datetime"})
        return None


def _handler(state: dict, payload: dict, errors: list):
    handle = payload.get("handle")
    if handle and handle not in {h["handle"] for h in state["handlers"]}:
        errors.append({"field": "handle", "message": "unregistered handle"})
    return handle


WORKHORSES = ("scheduler", "workbench", "colab")


def _routing(value, now: datetime):
    """A defect post's routing (§1.11 (j)): the workhorse,
    the owning thread notified, when, the evidence pointer.
    Returns the cleaned routing, or None when malformed."""
    if not isinstance(value, dict):
        return None
    if value.get("workhorse") not in WORKHORSES:
        return None
    if not (isinstance(value.get("thread"), str) and value["thread"].strip()):
        return None
    return {
        "workhorse": value["workhorse"],
        "thread": value["thread"],
        "at": value.get("at") or now.isoformat(),
        "evidence": value.get("evidence") or "",
    }


def _routing_problem(value) -> str:
    """Why a routing failed _routing, in the poster's
    terms — a routed post names its workhorse and the
    owning thread the routing notifies; the refusal says
    which of the pair is missing rather than "bad"."""
    if not isinstance(value, dict):
        return "must be an object naming workhorse and thread"
    if value.get("workhorse") not in WORKHORSES:
        return "workhorse must be one of: " + ", ".join(WORKHORSES)
    if not (isinstance(value.get("thread"), str) and value["thread"].strip()):
        return "thread is required — the owning thread the routing notifies"
    return "bad routing"


def _options(payload: dict, errors: list) -> list:
    """Poster-attached choices (§1.13): [{id, label,
    effect}], served verbatim; a decision post without
    them is a defective post and is refused (D-A2). The
    effect — what picking the option dispatches — is
    optional at post time and defaults to the
    verdict-send statement (the label the pick's send
    names), so posts that predate the field stay valid.
    """
    raw = payload.get("options")
    if raw is None:
        if payload.get("kind") == "decision":
            errors.append(
                {"field": "options", "message": "a decision post carries its options"}
            )
        return []
    valid = isinstance(raw, list) and all(
        isinstance(o, dict)
        and o.get("id")
        and o.get("label")
        and (o.get("effect") is None or isinstance(o.get("effect"), str))
        for o in raw
    )
    if not valid:
        errors.append(
            {
                "field": "options",
                "message": "must be [{id, label, effect}] entries (effect optional)",
            }
        )
        return []
    if payload.get("kind") == "decision" and not raw:
        errors.append(
            {"field": "options", "message": "a decision post carries its options"}
        )
    return [
        {"id": o["id"], "label": o["label"], "effect": o.get("effect") or o["label"]}
        for o in raw
    ]


OPTION_MODES = ("single", "multi")


def _mode(payload: dict, errors: list) -> str | None:
    """The item's pick mode (options shape v2): single
    takes exactly one option, multi a non-empty subset.
    Absent means the post does not speak to mode — the
    caller applies its own default."""
    mode = payload.get("mode")
    if mode is None:
        return None
    if mode not in OPTION_MODES:
        errors.append({"field": "mode", "message": "must be single or multi"})
        return None
    return mode


def upsert_item(state: dict, payload: dict, now: datetime) -> dict:
    errors: list = []
    for field in ("handle", "source_ref", "kind", "title"):
        _require(payload, field, errors)
    handle = _handler(state, payload, errors)
    known = {e["kind"] for e in state.get("item_kinds", [])} or set(dom.KINDS)
    if payload.get("kind") not in (None, *known):
        errors.append({"field": "kind", "message": "unknown kind"})
    options = _options(payload, errors)
    mode = _mode(payload, errors)
    due_at = _parse_dt(payload.get("due_at"), "due_at", errors)
    provenance = payload.get("provenance", "offer")
    if provenance not in ("commission", "offer"):
        errors.append({"field": "provenance", "message": "must be commission or offer"})
    routing = payload.get("routing")
    if routing is not None:
        cleaned = _routing(routing, now)
        if cleaned is None:
            errors.append({"field": "routing", "message": _routing_problem(routing)})
        routing = cleaned
    repo = payload.get("repo")
    if repo is not None and ("/" in repo or repo.startswith(".")):
        errors.append({"field": "repo", "message": "must name a workspace repository"})
    if errors:
        raise Validation("Item post failed validation.", errors)
    for item in state["items"]:
        if item["handle"] == handle and item["source_ref"] == payload["source_ref"]:
            item.update(
                kind=payload["kind"],
                title=payload["title"],
                status_code=payload.get("status_code"),
                source_url=payload.get("source_url", ""),
                clears_at_source=bool(payload.get("clears_at_source", True)),
                due_at=due_at,
                provenance=provenance,
                options=options,
                mode=mode if mode is not None else item.get("mode", "single"),
                result_preserving=bool(payload.get("result_preserving")),
            )
            if routing is not None:
                item["routing"] = routing
            if repo:
                item["repo"] = repo
            item["need"] = dom.classify_need(
                item["status_code"], state.get("status_codes")
            )
            item["tier"] = dom.assign_tier(item, state["allowlist"], now)
            if item["triage"] == "done":
                item["triage"] = "open"
            return item
    item = {
        "id": f"{handle}:{payload['source_ref']}",
        "handle": handle,
        "kind": payload["kind"],
        "title": payload["title"],
        "status_code": payload.get("status_code"),
        "source_ref": payload["source_ref"],
        "source_url": payload.get("source_url", ""),
        "clears_at_source": bool(payload.get("clears_at_source", True)),
        "due_at": due_at,
        "waiting_since": now,
        "need": "unclassified",
        "tier": "digest",
        "triage": "open",
        "snooze_return_at": None,
        "snooze_on_activity": False,
        "resume_note": None,
        "provenance": provenance,
        "options": options,
        "mode": mode if mode is not None else "single",
        "result_preserving": bool(payload.get("result_preserving")),
        **({"routing": routing} if routing is not None else {}),
        **({"repo": repo} if repo else {}),
    }
    item["need"] = dom.classify_need(item["status_code"], state.get("status_codes"))
    item["tier"] = dom.assign_tier(item, state["allowlist"], now)
    if [handle, item["kind"]] in state["muted"]:
        item["triage"] = "muted"
    state["items"].append(item)
    return item


def resolve_item(state: dict, item_id: str, payload: dict) -> dict:
    for item in state["items"]:
        if item["id"] == item_id:
            if payload.get("resolution") not in ("done", "withdrawn"):
                raise Validation(
                    "Resolve failed validation.",
                    [{"field": "resolution", "message": "must be done or withdrawn"}],
                )
            item["triage"] = "done"
            return item
    raise NotFound("No such item.")


def tail_ref(entry: dict) -> str:
    digest = hashlib.sha1(entry["title"].encode()).hexdigest()[:10]
    return f"tail:{entry['kind']}:{digest}"


def _owner_tail(state: dict, entry: dict) -> bool:
    """A tail entry waits on the owner when the entry says
    so, or its kind's digest placement is the owner."""
    if entry.get("owner") == "owner":
        return True
    owners = {e["kind"]: e.get("digest_owner") for e in state.get("item_kinds", [])}
    return owners.get(entry["kind"]) == "owner"


def promote_tail_items(state: dict, now: datetime) -> bool:
    """Owner-waiting status tail entries become queue items,
    so the queue and the counts read the same store the
    digest reads; a dropped entry clears its item."""
    changed = False
    live: set = set()
    for handle, record in state.get("handler_status", {}).items():
        for entry in record.get("tail") or []:
            if not _owner_tail(state, entry):
                continue
            ref = tail_ref(entry)
            live.add((handle, ref))
            found = any(
                i["handle"] == handle and i["source_ref"] == ref for i in state["items"]
            )
            if found:
                continue
            item = {
                "id": f"{handle}:{ref}",
                "handle": handle,
                "kind": entry["kind"],
                "title": entry["title"],
                "status_code": None,
                "source_ref": ref,
                "source_url": "",
                "clears_at_source": True,
                "due_at": None,
                "waiting_since": now,
                "need": "owner_actionable",
                "tier": "digest",
                "triage": "open",
                "snooze_return_at": None,
                "snooze_on_activity": False,
                "resume_note": None,
                "provenance": record.get("provenance", "offer"),
                "options": [],
                "result_preserving": False,
            }
            item["tier"] = dom.assign_tier(item, state["allowlist"], now)
            if [handle, item["kind"]] in state["muted"]:
                item["triage"] = "muted"
            state["items"].append(item)
            changed = True
    for item in state["items"]:
        if (
            item["source_ref"].startswith("tail:")
            and item["triage"] != "done"
            and (item["handle"], item["source_ref"]) not in live
        ):
            item["triage"] = "done"
            changed = True
    return changed


REPORT_PING_HANDLE = "@workhorse"
"""Scheduler report pings land on the workhorse
programme's handle — the harness's own surface."""


def _ping_title(ping: dict) -> str:
    """A report ping's item title: the job, plus the
    finding line its output tail ends on when it has one."""
    job = ping.get("job_id") or "scheduler"
    detail = ping.get("detail") or {}
    tail = (detail.get("stdout_tail") or detail.get("stderr_tail") or "").strip()
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    if lines:
        return f"{job}: {lines[-1]}"[:240]
    return f"{job}: report"


def _ping_since(ping: dict, now: datetime) -> datetime:
    created = ping.get("created")
    if isinstance(created, str):
        try:
            parsed = datetime.fromisoformat(created)
        except ValueError:
            return now
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=now.tzinfo)
    return now


def ingest_report_pings(state: dict, pings: list, now: datetime) -> bool:
    """Scheduler report-class pings become agent-clearable
    items on the workhorse handle, keyed by ping id
    (S-5): a ping still pending keeps its item open (its
    title refreshes as the ping coalesces new output);
    a ping that leaves the pending set — acked or voided
    at the source — clears its item. The caller fetches;
    a failed fetch never reaches here, so an unreachable
    scheduler clears nothing."""
    changed = False
    live: set = set()
    for ping in pings:
        if not isinstance(ping, dict) or ping.get("kind") != "report":
            continue
        ping_id = ping.get("id")
        if not ping_id:
            continue
        ref = f"ping:{ping_id}"
        live.add(ref)
        found = next(
            (
                i
                for i in state["items"]
                if i["handle"] == REPORT_PING_HANDLE and i["source_ref"] == ref
            ),
            None,
        )
        if found is not None:
            if found["triage"] != "done" and found["title"] != _ping_title(ping):
                found["title"] = _ping_title(ping)
                changed = True
            continue
        item = {
            "id": f"{REPORT_PING_HANDLE}:{ref}",
            "handle": REPORT_PING_HANDLE,
            "kind": "followup",
            "title": _ping_title(ping),
            "status_code": None,
            "source_ref": ref,
            "source_url": "",
            "clears_at_source": True,
            "due_at": None,
            "waiting_since": _ping_since(ping, now),
            "need": "agent_clearable",
            "tier": "digest",
            "triage": "open",
            "snooze_return_at": None,
            "snooze_on_activity": False,
            "resume_note": None,
            "provenance": "offer",
            "options": [],
            "result_preserving": False,
        }
        item["tier"] = dom.assign_tier(item, state["allowlist"], now)
        if [REPORT_PING_HANDLE, item["kind"]] in state["muted"]:
            item["triage"] = "muted"
        state["items"].append(item)
        changed = True
    for item in state["items"]:
        if (
            item["handle"] == REPORT_PING_HANDLE
            and item["source_ref"].startswith("ping:")
            and item["triage"] != "done"
            and item["source_ref"] not in live
        ):
            item["triage"] = "done"
            changed = True
    return changed


def post_wait(state: dict, payload: dict, now: datetime) -> dict:
    errors: list = []
    for field in ("handle", "wait_class", "summary"):
        _require(payload, field, errors)
    _handler(state, payload, errors)
    if errors:
        raise Validation("Wait post failed validation.", errors)
    key = payload.get("idempotency_key")
    if key:
        for wait in state["waits"]:
            if wait.get("idempotency_key") == key:
                return wait
    wait = {
        "id": engine.new_wait_id(state["waits"]),
        "handle": payload["handle"],
        "posted_by": payload.get("posted_by"),
        "wait_class": payload["wait_class"],
        "summary": payload["summary"],
        "status_code": payload.get("status_code"),
        "kind": payload.get("kind"),
        "program_approved": bool(payload.get("program_approved")),
        "reversible": bool(payload.get("reversible")),
        "in_budget": bool(payload.get("in_budget")),
        "only_blocker": bool(payload.get("only_blocker")),
        "idempotency_key": key,
        "posted_at": now,
        "decision": "pending",
        "rule_id": None,
        "decided_at": None,
        "evaluated": False,
        "last_fact_hash": None,
    }
    wait["fact_hash"] = engine.fact_hash(wait)
    state["waits"].append(wait)
    return wait


def get_wait(state: dict, wait_id: str) -> dict:
    for wait in state["waits"]:
        if wait["id"] == wait_id:
            return wait
    raise NotFound("No such wait.")
