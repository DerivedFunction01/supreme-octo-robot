"""The freshness writer: the reconciler's composed
per-handler verdict records (the handler-freshness
plan, step 1) — its own module because the write is a
distinct seam from the registry writes in writes.py:
one writer composes nothing and interprets nothing,
it validates the record against the freshness
registry's vocabularies and stores it verbatim under
handler_freshness; the serve derives labels and
staleness from the stored record."""

from __future__ import annotations

from datetime import datetime

from attention.domain import attention as dom
from attention.errors import NotFound, Validation
from attention.services.writes.ingest import _parse_dt


def record_freshness(state: dict, handle: str, payload: dict, now: datetime) -> dict:
    """Store one composed freshness verdict for a
    handler. A verdict, binding state, or cause outside
    the registry refuses, as does a retired-with-cause
    verdict carrying no cause."""
    if handle not in {h["handle"] for h in state.get("handlers", [])}:
        raise NotFound("No such handler.")
    registry = dom.freshness_registry(state)
    verdicts = {e["code"] for e in registry["verdicts"]}
    binding_states = {e["code"] for e in registry["binding_states"]}
    errors: list = []
    verdict = payload.get("verdict")
    if verdict not in verdicts:
        errors.append({"field": "verdict", "message": "must be a registered verdict"})
    binding_state = payload.get("binding_state")
    if binding_state not in binding_states:
        errors.append(
            {
                "field": "binding_state",
                "message": "must be a registered binding state",
            }
        )
    cause = payload.get("cause") or None
    if verdict == "retired-with-cause" and cause is None:
        errors.append(
            {"field": "cause", "message": "is required for retired-with-cause"}
        )
    if cause is not None and not dom.freshness_cause_ok(state, cause):
        errors.append({"field": "cause", "message": "must be a registered cause"})
    for field in ("bound_chat", "seat_chat"):
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            errors.append({"field": field, "message": "must be a string or null"})
    evidence = payload.get("last_evidence")
    evidence_record = None
    if evidence is not None:
        if not isinstance(evidence, dict) or evidence.get("kind") not in (
            "posting",
            "run",
        ):
            errors.append(
                {
                    "field": "last_evidence.kind",
                    "message": "must be posting or run",
                }
            )
        elif not evidence.get("ref"):
            errors.append({"field": "last_evidence.ref", "message": "is required"})
        else:
            before = len(errors)
            at = _parse_dt(evidence.get("at"), "last_evidence.at", errors)
            if at is None and len(errors) == before:
                errors.append({"field": "last_evidence.at", "message": "is required"})
            elif at is not None:
                evidence_record = {
                    "kind": evidence["kind"],
                    "at": at,
                    "ref": evidence["ref"],
                }
    age = payload.get("declaration_age_days")
    if age is not None and not isinstance(age, (int, float)):
        errors.append(
            {"field": "declaration_age_days", "message": "must be a number or null"}
        )
    if errors:
        raise Validation("Freshness failed validation.", errors)
    state.setdefault("handler_freshness", {})[handle] = {
        "handle": handle,
        "verdict": verdict,
        "binding_state": binding_state,
        "bound_chat": payload.get("bound_chat"),
        "seat_chat": payload.get("seat_chat"),
        "last_reconcile_at": now,
        "last_evidence": evidence_record,
        "declaration_age_days": age,
        "cause": cause,
    }
    return {
        "contract": "api/1",
        "handle": handle,
        "verdict": verdict,
        "recorded": True,
    }
