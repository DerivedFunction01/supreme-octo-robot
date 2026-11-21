"""Condition fields and post templates: the poster-settable
field registry and the template registry — split from
attention.py; attention.domain.attention re-exports
this surface.
"""

from __future__ import annotations


# Condition fields are a registry: poster-settable fields
# ride in on the wait; derived fields are computed by the
# server and can never be posted (the self-attestation fix).
def _field(name, ftype, source):
    return {
        "name": name,
        "type": ftype,
        "source": source,
        "poster_settable": source == "poster",
    }


def default_fields() -> list:
    return [
        _field("wait_class", "enum", "poster"),
        _field("status_code", "enum", "poster"),
        _field("kind", "enum", "poster"),
        _field("handle", "string", "poster"),
        _field("program_approved", "bool", "poster"),
        _field("reversible", "bool", "poster"),
        _field("in_budget", "bool", "poster"),
        _field("only_blocker", "bool", "poster"),
        _field("age_minutes", "number", "derived"),
        _field("repeat_count", "number", "derived"),
        _field("presence", "enum", "derived"),
        _field("handler_status_code", "enum", "derived"),
    ]


# Post templates are data (kind, version, audience, slots,
# text): rules and agents bind slot values, never free text.
def _template(kind, audience, slots, text):
    return {
        "kind": kind,
        "version": 1,
        "audience": audience,
        "slots": slots,
        "text": text,
    }


def default_templates() -> list:
    return [
        _template(
            "continue-settled",
            "chat",
            ["summary"],
            "Continue — settled under a standing rule: {summary}",
        ),
        _template(
            "continue-standing-rule",
            "chat",
            ["summary"],
            "Continue under the standing rule: {summary}",
        ),
        _template(
            "grant-program",
            "chat",
            ["summary", "scope"],
            "Granted — program step inside the approved scope: "
            "{summary}. Scope restated: {scope}",
        ),
        _template(
            "grant-followup",
            "chat",
            ["summary"],
            "Granted — build it in a worktree for accept / reject / modify: {summary}",
        ),
        _template(
            "stall-nudge",
            "chat",
            ["summary", "age_minutes"],
            "Stall check — no report in {age_minutes}m on: {summary}. Status?",
        ),
        _template(
            "status-request",
            "chat",
            ["summary"],
            "Status request — {summary}: reply with the status "
            "form (done / ongoing / blockers).",
        ),
        _template(
            "approval-surface",
            "main",
            ["summary", "handle"],
            "Approval waiting — {summary} ({handle}).",
        ),
        _template(
            "record-reconcile", "chat", ["summary"], "Reconcile the record: {summary}"
        ),
        _template(
            "idleness-nudge",
            "chat",
            ["summary"],
            "Idle with work outstanding: {summary}. Continue, or report PARKED.",
        ),
        _template("venue-question", "chat", ["summary"], "Venue question: {summary}"),
        _template("venue-ping", "chat", ["summary"], "Venue check: {summary}"),
        _template(
            "verdict",
            "chat",
            ["summary", "verb", "note"],
            "Owner verdict — {verb}: {summary} {note}",
        ),
        _template(
            "reply", "chat", ["summary", "note"], "Owner reply on {summary} — {note}"
        ),
        _template(
            "status-ping",
            "chat",
            ["summary"],
            "Status ping — the owner asks for a fresh status on: {summary}. "
            "Reply with the status form (done / ongoing / blockers).",
        ),
        _template(
            "continuation",
            "chat",
            ["summary", "detail"],
            "Continue — {summary} {detail}",
        ),
        _template(
            "status-ping-urgent",
            "chat",
            ["summary"],
            "Status ping (second) — still no fresh status on: {summary}. "
            "Reply now with the status form (done / ongoing / blockers).",
        ),
        _template(
            "parallelize",
            "chat",
            ["summary"],
            "Parallelize — the owner directs this work staffed across "
            "the live fleet now: {summary}",
        ),
        _template(
            "commission",
            "chat",
            ["summary"],
            "Commission from the owner: {summary}",
        ),
    ]


# Program-scope grants (the sweeper's 5A conditions): all
# four flags must hold before that rule may auto-apply.
