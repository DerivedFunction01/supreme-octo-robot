"""Owner actions (§1.13): the verdict is the tap.
The tap records the verdict on the item — and through
wait_id, on the wait it stands for — immediately;
delivery never gates the decision."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from attention.domain import attention as dom
from attention.errors import Conflict, NotFound, Validation
from attention.services.waits import engine, fulfillment
from attention.settings import Settings

DECISION_VERBS = (
    "approve_once",
    "deny",
    "pick",
    "rule_it",
    "accept",
    "reject",
    "close_on_verify",
    "close",
    "push",
)

PASS_VERBS = {
    "critic_pass": "Critic pass",
    "perf_pass": "Performance pass",
    "consolidation_pass": "Consolidation pass",
    "organize_pass": "Organize pass",
}
HANDLER_VERBS = (
    "status_ping",
    "parallelize",
    "critic_pass",
    "perf_pass",
    "consolidation_pass",
    "organize_pass",
    "stop",
    "park",
    "resume",
)
# The quick verbs placed on a status ride the handler
# endpoint too: a status has no poll, so dispatch is
# its return path (§1.13 amendment).
STATUS_QUICK_VERBS = (
    "continue",
    "go",
    "accept_review",
    "reject_incomplete",
    "close",
    "leave_it",
)


def _find_item(state: dict, item_id: str) -> dict:
    item = next((i for i in state["items"] if i["id"] == item_id), None)
    if item is None:
        raise NotFound("No such item.")
    return item


def _find_wait(state: dict, wait_id: str | None) -> dict | None:
    if not wait_id:
        return None
    return next((w for w in state["waits"] if w["id"] == wait_id), None)


def _new_action_id(state: dict) -> str:
    top = 0
    for entry in state.get("owner_actions", []):
        aid = str(entry.get("id", ""))
        if aid.startswith("oa") and aid[2:].isdigit():
            top = max(top, int(aid[2:]))
    return f"oa{top + 1:04d}"


def _record(
    state: dict,
    now: datetime,
    *,
    handle: str,
    verb: str,
    item_id: str | None = None,
    option_id: str | None = None,
    option_ids: list | None = None,
    note: str = "",
    actor: str = "owner",
    rule_id: str | None = None,
    shadow: bool = False,
    idempotency_key: str | None = None,
) -> dict:
    entry = {
        "id": _new_action_id(state),
        "at": now,
        "handle": handle,
        "item_id": item_id,
        "verb": verb,
        "option_id": option_id,
        "option_ids": list(option_ids) if option_ids else [],
        "note": note,
        "actor": actor,
        "rule_id": rule_id,
        "shadow": shadow,
        "idempotency_key": idempotency_key,
    }
    state.setdefault("owner_actions", []).append(entry)
    return entry


def _send_verdict(state, item, verb, note, now, template="verdict"):
    slots = {"summary": item["title"], "verb": dom.VERB_LABELS.get(verb, verb)}
    if template == "verdict":
        slots["note"] = note or ""
    elif template == "reply":
        slots = {"summary": item["title"], "note": note or ""}
    return engine.record_send(
        state,
        template,
        item["handle"],
        slots,
        now,
        rule_id=f"owner:{verb}",
        wait_id=item.get("wait_id"),
    )


def _count_tap(state: dict, item: dict, verb: str, now: datetime) -> None:
    """Repetition proposes the rule (D-A7): identical
    taps counted per handler + class + verb; at the
    threshold a rule_proposal item surfaces."""
    if verb not in dom.COUNTED_VERBS:
        return
    wait = _find_wait(state, item.get("wait_id"))
    cls = (wait or {}).get("wait_class") or item["kind"]
    counts = state.setdefault("tap_counts", {})
    key = f"{item['handle']}|{cls}|{verb}"
    entry = counts.setdefault(key, {"count": 0, "cycles": 0})
    entry["count"] += 1
    if entry["count"] < dom.PROPOSAL_THRESHOLD:
        return
    if any(r for r in state.get("action_rules", []) if _rule_matches(r, item, verb)):
        return
    source_ref = f"rule-proposal:{cls}:{verb}:{entry['cycles']}"
    if any(
        i["source_ref"] == source_ref and i["handle"] == item["handle"]
        for i in state["items"]
    ):
        return
    label = dom.VERB_LABELS.get(verb, verb)
    proposal = {
        "id": f"{item['handle']}:{source_ref}",
        "handle": item["handle"],
        "kind": "rule_proposal",
        "title": (
            f"You have tapped {label} on {cls} items from this "
            f"lane {entry['count']} times — make it a rule?"
        ),
        "status_code": None,
        "source_ref": source_ref,
        "source_url": "",
        "clears_at_source": False,
        "due_at": None,
        "waiting_since": now,
        "need": "owner_actionable",
        "tier": "digest",
        "triage": "open",
        "snooze_return_at": None,
        "snooze_on_activity": False,
        "resume_note": None,
        "provenance": "offer",
        "options": [],
        "proposal": {
            "cls": cls,
            "verb": verb,
            "count": entry["count"],
            "key": key,
        },
    }
    proposal["tier"] = dom.assign_tier(proposal, state["allowlist"], now)
    state["items"].append(proposal)


def _rule_matches(rule: dict, item: dict, verb: str) -> bool:
    if rule.get("verb") != verb:
        return False
    match = rule.get("match") or {}
    if match.get("handle") and match["handle"] != item["handle"]:
        return False
    if match.get("kind") and match["kind"] != item["kind"]:
        return False
    return True


def _create_rule(
    state: dict,
    now: datetime,
    *,
    match: dict,
    verb: str,
    mode: str,
    created_from: str,
    option_id: str | None = None,
    option_ids: list | None = None,
) -> dict:
    rule = {
        "id": f"tap-{_new_action_id(state)}",
        "match": match,
        "verb": verb,
        "mode": mode,
        "created_from": created_from,
        "at": now,
    }
    if option_id:
        rule["option_id"] = option_id
    if option_ids:
        rule["option_ids"] = list(option_ids)
    state.setdefault("action_rules", []).append(rule)
    return rule


def _promote(
    state: dict,
    item: dict,
    verb: str,
    now: datetime,
    option_id: str | None,
    option_ids: list | None = None,
) -> dict:
    """A deliberate make_rule tap (D-A8): shadow for
    every verb except wait approvals (D-A1 active)."""
    wait = _find_wait(state, item.get("wait_id"))
    if wait is not None:
        if dom.class_is_hard_stop(wait.get("wait_class"), state["wait_classes"]):
            raise Validation(
                "Promotion failed validation.",
                [
                    {
                        "field": "make_rule",
                        "message": "a hard-stop approval can never become a rule",
                    }
                ],
            )
        return _create_rule(
            state,
            now,
            match={"handle": item["handle"], "wait_class": wait["wait_class"]},
            verb="approve",
            mode="active",
            created_from="make_rule",
        )
    return _create_rule(
        state,
        now,
        match={"handle": item["handle"], "kind": item["kind"]},
        verb=verb,
        mode="shadow",
        created_from="make_rule",
        option_id=option_id,
        option_ids=option_ids,
    )


def _payload_picks(payload: dict) -> list:
    """The payload's picked option ids (options shape
    v2): the multi form carries option_ids; the legacy
    form carries the one option_id. Unvalidated — the
    caller checks them against the item's options."""
    raw = payload.get("option_ids")
    if isinstance(raw, list):
        return list(raw)
    if payload.get("option_id") is not None:
        return [payload["option_id"]]
    return []


def _recorded_picks(record: dict) -> list:
    """A decision/last-action record's picked set, read
    across both shapes: option_ids when present, else
    the legacy singular option_id."""
    ids = record.get("option_ids")
    if isinstance(ids, list) and ids:
        return list(ids)
    if record.get("option_id"):
        return [record["option_id"]]
    return []


def apply_item_action(
    state: dict, settings: Settings, item_id: str, payload: dict, now: datetime
) -> dict:
    """The action endpoint: validate the verb against
    the served set, record the verdict, write the send.
    Returns the updated item."""
    from attention.services.reads import model

    item = _find_item(state, item_id)
    verb = payload.get("verb")
    key = payload.get("idempotency_key")
    if key:
        prior = next(
            (
                a
                for a in state.get("owner_actions", [])
                if a.get("idempotency_key") == key
            ),
            None,
        )
        if prior is not None:
            return item
    prior_view = None
    if item.get("decision"):
        fact = None
        if item["kind"] == "push_needed" and item.get("repo"):
            from attention.services.waits import facts as facts_mod
            from attention.settings import REPO_ROOT

            fact = facts_mod.measure(item, REPO_ROOT.parent, now)
        prior_view = fulfillment.derive(item, state, now, settings, fact)
        if prior_view and prior_view["state"] == "fulfilled":
            raise Conflict(
                "This decision is already fulfilled; a change is a new item."
            )
        standing = item["decision"]
        payload_picks = _payload_picks(payload)
        if payload.get("verb") in DECISION_VERBS and standing.get(
            "verb"
        ) == payload.get("verb"):
            standing_ids = _recorded_picks(standing)
            if standing_ids or payload_picks:
                same_pick = set(standing_ids) == set(payload_picks)
            else:
                same_pick = standing.get("option_id") == payload.get("option_id")
            if same_pick:
                # A replayed tap on the standing decision: the
                # verdict already stands and its send already
                # exists — record nothing, send nothing.
                return item
    served = {v["verb"] for v in model.verbs_for(item, state, prior_view)}
    if verb not in served:
        raise Validation(
            "Action failed validation.",
            [{"field": "verb", "message": "verb not served for this item"}],
        )
    note = payload.get("note") or ""
    option_id = payload.get("option_id")
    picks: list = []
    if verb in ("pick", "rule_it"):
        # Options shape v2: validation is by the item's
        # mode. The recorded picked set is ordered as the
        # item declares its options (deterministic, not
        # payload order); the legacy singular option_id is
        # kept in sync as the pick when the pick is a
        # single id, and None when several are picked.
        options = item.get("options") or []
        known = {o["id"] for o in options}
        raw_picks = _payload_picks(payload)
        if (item.get("mode") or "single") == "multi":
            if not raw_picks:
                raise Validation(
                    "Action failed validation.",
                    [
                        {
                            "field": "option_ids",
                            "message": "a multi-choice pick names at least one option",
                        }
                    ],
                )
            if any(p not in known for p in raw_picks):
                raise Validation(
                    "Action failed validation.",
                    [{"field": "option_ids", "message": "unknown option"}],
                )
        else:
            if not raw_picks:
                raise Validation(
                    "Action failed validation.",
                    [{"field": "option_id", "message": "unknown option"}],
                )
            if len(set(raw_picks)) > 1:
                raise Validation(
                    "Action failed validation.",
                    [
                        {
                            "field": "option_ids",
                            "message": "a single-choice item takes exactly one option",
                        }
                    ],
                )
            if raw_picks[0] not in known:
                raise Validation(
                    "Action failed validation.",
                    [{"field": "option_id", "message": "unknown option"}],
                )
        picked = set(raw_picks)
        picks = [o["id"] for o in options if o["id"] in picked]
        option_id = picks[0] if len(picks) == 1 else None
    if payload.get("make_rule") and verb == "approve_rule":
        raise Validation(
            "Action failed validation.",
            [{"field": "make_rule", "message": "approve_rule already promotes"}],
        )
    wait = _find_wait(state, item.get("wait_id"))
    created_rule = None
    if verb == "approve_rule":
        if wait is None or dom.class_is_hard_stop(
            wait.get("wait_class"), state["wait_classes"]
        ):
            raise Validation(
                "Action failed validation.",
                [
                    {
                        "field": "verb",
                        "message": "hard-stop approvals are approved once, never ruled",
                    }
                ],
            )
        created_rule = _create_rule(
            state,
            now,
            match={"handle": item["handle"], "wait_class": wait["wait_class"]},
            verb="approve",
            mode="active",
            created_from="approve_rule",
        )
        verb_effective = "approve_once"
    else:
        verb_effective = verb
    send = _apply_effects(
        state, item, wait, verb_effective, option_id, picks, note, payload, now
    )
    if verb_effective in DECISION_VERBS:
        if item.get("decision"):
            item.setdefault("decision_history", []).append(
                {
                    **item["decision"],
                    "outcome": prior_view["state"] if prior_view else "recorded",
                }
            )
        item["decision"] = {
            "verb": verb_effective,
            "at": now,
            "option_id": option_id,
            "option_ids": picks,
            "note": note,
            "send_id": send["id"] if send else None,
        }
    if payload.get("make_rule"):
        created_rule = _promote(state, item, verb, now, option_id, picks)
    _record(
        state,
        now,
        handle=item["handle"],
        verb=verb,
        item_id=item["id"],
        option_id=option_id,
        option_ids=picks,
        note=note,
        rule_id=created_rule["id"] if created_rule else None,
        idempotency_key=key,
    )
    item["last_action"] = {
        "verb": verb,
        "at": now,
        "option_id": option_id,
        "option_ids": picks,
        "note": note,
    }
    _count_tap(state, item, verb, now)
    return item


def _apply_effects(state, item, wait, verb, option_id, picks, note, payload, now):
    """State changes per verb. The send is written here,
    after the verdict is recorded on the item/wait."""
    if verb in ("approve_once", "deny"):
        if wait is not None and wait["decision"] in ("pending", "surfaced"):
            wait["decision"] = (
                "owner_approved" if verb == "approve_once" else "owner_denied"
            )
            wait["decided_at"] = now
            wait["owner_note"] = note
        item["triage"] = "done"
        return _send_verdict(state, item, verb, note, now)
    elif verb in ("pick", "rule_it"):
        item["triage"] = "done"
        picked = set(picks)
        labels = [o["label"] for o in item.get("options") or [] if o["id"] in picked]
        label = ", ".join(labels) if labels else (option_id or "")
        if verb == "rule_it":
            _create_rule(
                state,
                now,
                match={"handle": item["handle"], "kind": item["kind"]},
                verb="pick",
                mode="shadow",
                created_from="rule_it",
                option_id=option_id,
                option_ids=picks,
            )
        return _send_verdict(state, item, verb, label or "", now)
    elif verb == "accept":
        item["triage"] = "done"
        return _send_verdict(state, item, verb, note, now)
    elif verb == "reject":
        item["triage"] = "done"
        return _send_verdict(state, item, verb, note, now)
    elif verb == "modify":
        _send_verdict(state, item, verb, note, now, template="reply")
    elif verb == "reply":
        _send_verdict(state, item, verb, note, now, template="reply")
        if item["handle"] != "main":
            # Decision 1: replies route direct to the
            # owning thread; main is copied on each.
            label = next(
                (
                    h["label"]
                    for h in state["handlers"]
                    if h["handle"] == item["handle"]
                ),
                item["handle"],
            )
            engine.record_send(
                state,
                "reply",
                "main",
                {
                    "summary": f"Copy of a reply to {label} — {item['title']}",
                    "note": note or "",
                },
                now,
                rule_id="owner:reply-copy",
            )
    elif verb == "push":
        return _send_verdict(state, item, verb, note, now)
    elif verb == "close_on_verify":
        item["triage"] = "done"
        return _send_verdict(state, item, verb, note, now)
    elif verb == "accept_proposal":
        proposal = item.get("proposal") or {}
        _create_rule(
            state,
            now,
            match={"handle": item["handle"], "kind": proposal.get("cls")},
            verb=proposal.get("verb"),
            mode="shadow",
            created_from="proposal",
        )
        counts = state.setdefault("tap_counts", {})
        entry = counts.get(proposal.get("key") or "")
        if entry is not None:
            entry["count"] = 0
            entry["cycles"] += 1
        item["triage"] = "done"
    elif verb == "reject_proposal":
        proposal = item.get("proposal") or {}
        counts = state.setdefault("tap_counts", {})
        entry = counts.get(proposal.get("key") or "")
        if entry is not None:
            entry["count"] = 0
            entry["cycles"] += 1
        item["triage"] = "done"
    elif verb in ("snooze", "done", "mute_type", "leave_it"):
        # Bookmarks ride the store's triage mechanics —
        # the endpoint retired, the mechanics did not.
        from attention.services.writes import writes

        mapped = "done" if verb == "leave_it" else verb
        writes.apply_triage(
            state,
            item["id"],
            {
                "action": mapped,
                "return_at": payload.get("return_at"),
                "return_on_activity": payload.get("return_on_activity"),
                "resume_note": payload.get("resume_note") or note or None,
            },
            now,
        )
    elif verb in ("continue", "go", "accept_review", "reject_incomplete"):
        _send_verdict(state, item, verb, note, now)
    elif verb == "close":
        item["triage"] = "done"
        return _send_verdict(state, item, verb, note, now)
    elif verb == "park":
        _send_verdict(state, item, verb, note, now)


def _window_start(now: datetime, windows: tuple) -> datetime:
    """The most recent digest window at or before now —
    the ping cooldown's unit (D-A4)."""
    starts = []
    for text in windows:
        hour, minute = (int(part) for part in text.split(":"))
        at = datetime.combine(now.date(), time(hour, minute), tzinfo=now.tzinfo)
        if at > now:
            at -= timedelta(days=1)
        starts.append(at)
    return max(starts)


def apply_handler_action(
    state: dict, settings: Settings, handle: str, payload: dict, now: datetime
) -> dict:
    """Handler-level verbs: status ping, parallelize,
    the pass commissions, directed control. Each records
    an owner action and dispatches."""
    if handle not in {h["handle"] for h in state["handlers"]}:
        raise NotFound("No such handler.")
    verb = payload.get("verb")
    if verb not in HANDLER_VERBS + STATUS_QUICK_VERBS:
        raise Validation(
            "Action failed validation.",
            [{"field": "verb", "message": "verb not served for a handler"}],
        )
    note = payload.get("note") or ""
    status = state.get("handler_status", {}).get(handle) or {}
    summary = status.get("summary") or handle
    handler = next(h for h in state["handlers"] if h["handle"] == handle)
    if verb == "status_ping":
        pings = state.setdefault("pings", {})
        mine = pings.setdefault(handle, {"count": 0, "last_at": None})
        last = mine.get("last_at")
        if last is not None and last >= _window_start(now, settings.digest_windows):
            raise Conflict("A status ping already went out this digest window.")
        mine["count"] += 1
        mine["last_at"] = now
        kind = "status-ping" if mine["count"] == 1 else "status-ping-urgent"
        engine.record_send(
            state, kind, handle, {"summary": summary}, now, rule_id="owner:status_ping"
        )
    elif verb == "parallelize":
        from attention.services.reads.digest import topic_of

        state.setdefault("owner_directed", {})[topic_of(handle)] = {
            "at": now,
            "handle": handle,
        }
        engine.record_send(
            state,
            "parallelize",
            handle,
            {"summary": summary},
            now,
            rule_id="owner:parallelize",
        )
    elif verb in PASS_VERBS:
        item = {
            "id": f"{handle}:commission:{verb}:{_new_action_id(state)}",
            "handle": handle,
            "kind": "action",
            "title": f"{PASS_VERBS[verb]} — {handler['label']}",
            "status_code": None,
            "source_ref": f"commission:{verb}:{_new_action_id(state)}",
            "source_url": "",
            "clears_at_source": False,
            "due_at": None,
            "waiting_since": now,
            "need": "agent_clearable",
            "tier": "digest",
            "triage": "open",
            "snooze_return_at": None,
            "snooze_on_activity": False,
            "resume_note": None,
            "provenance": "commission",
            "options": [],
        }
        state["items"].append(item)
        engine.record_send(
            state,
            "commission",
            handle,
            {"summary": item["title"]},
            now,
            rule_id=f"owner:{verb}",
        )
    elif verb == "leave_it":
        pass  # a bookmark even at status level: recorded, sends nothing
    else:  # directed control + status quick verbs
        pseudo = {"title": summary, "handle": handle, "wait_id": None}
        _send_verdict(state, pseudo, verb, note, now)
    entry = _record(
        state,
        now,
        handle=handle,
        verb=verb,
        note=note,
        idempotency_key=payload.get("idempotency_key"),
    )
    return {"contract": "api/1", "handle": handle, "action": entry["id"], "verb": verb}
