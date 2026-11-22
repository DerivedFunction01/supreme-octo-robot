"""Action-rule evaluation (§1.13 seeds): standing
approve rules decide waits, and the R1-R3 seeds act
or record in shadow, beside the wait engine."""

from __future__ import annotations

from datetime import datetime

from attention.domain import attention as dom
from attention.services.waits import engine
from attention.services.waits.actions import _record, _window_start
from attention.settings import Settings


def _approve_rules(state: dict, rules: list, now: datetime) -> list:
    """Active approve rules decide matching undecided
    waits — never a hard-stop class, whatever it says."""
    events = []
    for wait in state.get("waits", []):
        if wait["decision"] not in ("pending", "surfaced"):
            continue
        if dom.class_is_hard_stop(wait.get("wait_class"), state["wait_classes"]):
            continue
        for rule in rules:
            if rule.get("verb") != "approve" or rule.get("mode") != "active":
                continue
            match = rule.get("match") or {}
            if match.get("handle") and match["handle"] != wait["handle"]:
                continue
            if match.get("wait_class") and match["wait_class"] != wait.get(
                "wait_class"
            ):
                continue
            wait["decision"] = "owner_approved"
            wait["decided_at"] = now
            wait["owner_note"] = "approved under a standing owner rule"
            standing = next(
                (i for i in state["items"] if i["id"] == f"wait-{wait['id']}"), None
            )
            if standing is not None and standing["triage"] == "open":
                standing["triage"] = "done"  # the rule decided what it stood for
            engine.record_send(
                state,
                "verdict",
                wait["handle"],
                {
                    "summary": wait["summary"],
                    "verb": "Approve",
                    "note": "under your standing rule",
                },
                now,
                rule_id=rule["id"],
                wait_id=wait["id"],
            )
            _record(
                state,
                now,
                handle=wait["handle"],
                verb="approve_once",
                actor="rule",
                rule_id=rule["id"],
                note="standing owner rule",
            )
            events.append(wait)
            break
    return events


def evaluate_action_rules(state: dict, settings: Settings, now: datetime) -> list:
    """The R1–R3 seeds, evaluated beside the wait
    engine. Shadow rules record what they would do and
    act on nothing; active rules act and record."""
    events = []
    rules = state.get("action_rules", [])
    events += _approve_rules(state, rules, now)
    for rule in rules:
        if rule.get("id", "").startswith("R1"):
            events += _r1(state, rule, now)
        elif rule.get("id", "").startswith("R2"):
            events += _r2(state, rule, settings, now)
        elif rule.get("id", "").startswith("R3"):
            events += _r3(state, rule, now)
    return events


def _terminal_handles(state: dict) -> set:
    terminal = {e["code"] for e in state.get("status_codes", []) if e.get("terminal")}
    return {
        handle
        for handle, record in state.get("handler_status", {}).items()
        if record.get("status_code") in terminal
    }


def _already_recorded(state: dict, rule: dict, item: dict, verb: str) -> bool:
    """One record per rule + item + verb: the evaluation
    tick must not re-record the same shadow verdict every
    pass while the item stands open."""
    return any(
        a.get("rule_id") == rule["id"]
        and a.get("item_id") == item["id"]
        and a.get("verb") == verb
        for a in state.get("owner_actions", [])
    )


def _r1(state: dict, rule: dict, now: datetime) -> list:
    done_handles = _terminal_handles(state)
    events = []
    for item in state["items"]:
        if item["kind"] != "defect" or item["triage"] in ("done", "muted"):
            continue
        if item["handle"] not in done_handles:
            continue
        if _already_recorded(state, rule, item, "close_on_verify"):
            continue
        shadow = rule.get("mode") == "shadow"
        _record(
            state,
            now,
            handle=item["handle"],
            verb="close_on_verify",
            item_id=item["id"],
            actor="rule",
            rule_id=rule["id"],
            shadow=shadow,
            note="defect clears on the handler's terminal status (R1)",
        )
        if not shadow:
            item["triage"] = "done"
        events.append(item)
    return events


def _r2(state: dict, rule: dict, settings: Settings, now: datetime) -> list:
    from attention.services.reads import model as _reads_model
    events = []
    shadow = rule.get("mode") == "shadow"
    for handle, record in state.get("handler_status", {}).items():
        if record.get("status_code") not in ("WORKING", "CONTINUE"):
            continue
        if not (record.get("refs") or record.get("workers") is not None):
            continue
        age = (now - record["at"]).total_seconds() / 3600
        if age < settings.stall_after_hours:
            continue
        pings = state.setdefault("pings", {})
        mine = pings.setdefault(handle, {"count": 0, "last_at": None})
        last = mine.get("last_at")
        if last is not None and last >= _window_start(
            now,
            tuple(_reads_model.digest_window_times(state, settings)),
            _reads_model.digest_window_tz(state),
        ):
            continue
        if mine["count"] >= 3:
            continue
        mine["count"] += 1
        mine["last_at"] = now
        if shadow:
            _record(
                state,
                now,
                handle=handle,
                verb="status_ping",
                actor="rule",
                rule_id=rule["id"],
                shadow=True,
                note="stale status would draw a ping (R2)",
            )
        else:
            kind = "status-ping" if mine["count"] == 1 else "status-ping-urgent"
            target = "main" if mine["count"] >= 3 else None
            engine.record_send(
                state,
                kind,
                handle,
                {"summary": record.get("summary") or handle},
                now,
                rule_id=rule["id"],
                target=target,
            )
            _record(
                state,
                now,
                handle=handle,
                verb="status_ping",
                actor="rule",
                rule_id=rule["id"],
                note="stale status ping (R2)",
            )
        events.append(record)
    return events


def _r3(state: dict, rule: dict, now: datetime) -> list:
    events = []
    for item in state["items"]:
        if item["kind"] != "performance" or item["triage"] in ("done", "muted"):
            continue
        if item.get("provenance", "offer") != "offer":
            continue
        if not item.get("result_preserving"):
            continue
        if _already_recorded(state, rule, item, "clear_fyi"):
            continue
        shadow = rule.get("mode") == "shadow"
        _record(
            state,
            now,
            handle=item["handle"],
            verb="clear_fyi",
            item_id=item["id"],
            actor="rule",
            rule_id=rule["id"],
            shadow=shadow,
            note="result-preserving performance clears as FYI (R3)",
        )
        if not shadow:
            item["triage"] = "done"
        events.append(item)
    return events
