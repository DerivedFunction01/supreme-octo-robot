"""Read-model verbs: the served verb derivation and the
item staleness view — split from model.py;
attention.services.reads.model re-exports this surface.
"""

from __future__ import annotations

from datetime import timedelta

from attention.domain import attention as dom
from attention.services.waits import basis, engine

from .labels import _iso

OFFER_KINDS = ("followup", "improvement", "consolidation", "performance")


def _verb_entry(verb: str, primary: bool = False, hint: str | None = None) -> dict:
    return {
        "verb": verb,
        "label": dom.VERB_LABELS.get(verb, verb),
        "primary": primary,
        "rule_hint": hint,
        "sends": verb not in dom.BOOKMARK_VERBS,
    }


def _shadow_hint(state: dict, item: dict, verb: str) -> str | None:
    """A shadow action rule that would fire on this item
    makes its verb primary (§1.13)."""
    for rule in state.get("action_rules", []):
        if rule.get("mode") != "shadow" or rule.get("verb") != verb:
            continue
        match = rule.get("match") or {}
        if match.get("handle") and match["handle"] != item["handle"]:
            continue
        if match.get("kind") and match["kind"] != item["kind"]:
            continue
        if match.get("wait_class"):
            continue
        return (
            f"A shadow rule would {dom.VERB_LABELS.get(verb, verb).lower()} "
            "this — the tap applies it once."
        )
    return None


def verbs_for(item: dict, state: dict, fulfillment_view: dict | None = None) -> list:
    """The served verb list (§1.13): derived from kind,
    provenance, wait class, and state — the frontend
    renders these and derives nothing."""
    if item["triage"] in ("done", "muted"):
        # A decided item keeps its verbs while its
        # fulfillment is unfulfilled or returned; a
        # fulfilled decision is closed for good.
        if not (
            item.get("decision")
            and fulfillment_view
            and fulfillment_view["state"] != "fulfilled"
        ):
            return []
    verbs: list[str] = []
    kind = item["kind"]
    wait = None
    if item.get("wait_id"):
        wait = next(
            (w for w in state.get("waits", []) if w["id"] == item["wait_id"]), None
        )
    if kind == "rule_proposal":
        verbs = ["accept_proposal", "reject_proposal"]
    elif (
        kind == "approval"
        and wait is not None
        and wait["decision"]
        in (
            "pending",
            "surfaced",
        )
    ):
        verbs = ["approve_once"]
        if not dom.class_is_hard_stop(wait.get("wait_class"), state["wait_classes"]):
            verbs.append("approve_rule")
        verbs.append("deny")
    elif kind == "decision":
        verbs = ["pick", "rule_it", "reply"]
    elif kind in OFFER_KINDS and item.get("provenance", "offer") == "offer":
        verbs = ["accept", "reject", "modify"]
    elif kind == "push_needed":
        verbs = ["push"]
    elif kind == "defect":
        verbs = ["close_on_verify", "reply"]
    if item.get("status_code") == "REVIEW" and kind != "rule_proposal":
        verbs += ["accept_review", "reject_incomplete"]
    if item["need"] == "agent_clearable" and kind not in (
        "rule_proposal",
        "push_needed",
    ):
        verbs.append("continue")
    verbs += ["reply", "snooze", "done", "mute_type", "leave_it"]
    seen: list[str] = []
    for verb in verbs:
        if verb not in seen:
            seen.append(verb)
    out = []
    for verb in seen:
        hint = _shadow_hint(state, item, verb)
        out.append(_verb_entry(verb, primary=hint is not None, hint=hint))
    return out


def quick_verbs_for_status(state: dict, handle: str, record: dict) -> list:
    """The quick action buttons on a status (§1.13
    amendment): named from the owner's one-tap patterns,
    placed by the status code."""
    code = record.get("status_code")
    verbs: list[str] = []
    if code == "REVIEW":
        verbs = ["accept_review", "reject_incomplete"]
    elif code == "DONE":
        verbs = ["close"]
    elif code in ("WORKING", "CONTINUE", "BLOCKED-OWNER", "BLOCKED-HARD"):
        verbs = ["park"]
    if code not in ("CLOSED",):
        verbs.append("leave_it")
    return [_verb_entry(v) for v in verbs]


def handler_verbs(exclude: set | None = None) -> list:
    from attention.services.waits.actions import HANDLER_VERBS

    skip = exclude or set()
    return [_verb_entry(v) for v in HANDLER_VERBS if v not in skip]


def item_staleness(item: dict, state: dict, facts: dict | None = None) -> dict:
    """The served staleness fields (the decision-
    staleness plan, Step 3): the basis evidence when a
    detector currently prices the item stale (None when
    live or undecidable — a decided or closed item is
    not priced at all), the moment the item's age cap
    falls due under its kind's current registry entry
    (None for an uncapped kind or a hard-stop-bearing
    record, which never age-expires), and the expiry
    record when one stands."""
    entry = engine.registry_entry(
        state.get("item_kinds"), "kind", item["kind"], dom.default_item_kinds()
    )
    cap = entry.get("stale_after_hours") if entry else None
    expires_at = None
    if cap is not None and not engine.item_hard_stop(state, item):
        expires_at = _iso(item["waiting_since"] + timedelta(hours=cap))
    stale_basis = None
    if item["triage"] not in ("done", "muted") and not item.get("decision"):
        verdict = basis.basis_for(item, engine.basis_facts(state, push_facts=facts))
        if verdict is not None and verdict[0]:
            stale_basis = verdict[1]
    expired = item.get("expired")
    return {
        "stale_basis": stale_basis,
        "expires_at": expires_at,
        "expired": (
            {
                "at": _iso(expired["at"]),
                "basis": expired["basis"],
                "evidence": expired["evidence"],
                "blocked": bool(expired.get("blocked")),
            }
            if expired
            else None
        ),
    }
