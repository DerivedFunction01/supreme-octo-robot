"""Stop verdicts (the stopped-lane plan, Step 3): the
pure classifier over one declared stop, homed beside
the register it reads (domain/catalogs.py's wait-class
enumeration).

A stop is posted as a structured line in the lane's
status record:

    stop: {"reason": "<id>", "since": "<ISO>",
           "ref": {"kind": "plan|goal|todo",
                   "id": "<id>"} | null,
           "citation": {"chat": "<chat-id>",
                        "at": "<ISO>"} | null}

The verdict is a value — actuate (with the row's
disposition), owner_item, void, standing, refused,
residue, unrecognized — composed from the parsed line,
the register, and two injected readers, so the module
stays pure and pinnable:

- approval_state(kind, ref_id) -> bool | None: the
  referenced artifact's recorded approval (True =
  approved, False = recorded unapproved, None = no
  record).
- owner_traffic(probe) -> bool: held owner traffic —
  {"chat": ..., "at": ...} asks whether the owner's
  cited message is held; {"act": <class>} asks whether
  a named hard-stop act exists.

The specimen requirements are the module's law, not
commentary. The state string parses by exact match
against the canonical vocabulary — a near-miss reads
unrecognized, never owner-block, and absence of a
signal never reads as one either. An owner-block claim
verdicts only through the verification read: the
claiming lane's own records are not an input this
module accepts, by construction, so a claim can never
verify itself; the default verdict is false, and an
uncited or unverifiable claim is void. A stated cause
naming a hard-stop class refuses before any class
match is attempted.
"""

from __future__ import annotations

import json
from datetime import datetime

from .catalogs import default_status_codes, default_wait_classes

ACTUATE = "actuate"
OWNER_ITEM = "owner_item"
VOID = "void"
STANDING = "standing"
REFUSED = "refused"
RESIDUE = "residue"
UNRECOGNIZED = "unrecognized"
VERDICTS = (ACTUATE, OWNER_ITEM, VOID, STANDING, REFUSED, RESIDUE, UNRECOGNIZED)

BLOCKED_STATES = ("BLOCKED-OWNER", "BLOCKED-HARD")
REF_KINDS = ("plan", "goal", "todo")
_FLAG_FIELDS = ("requires_plan", "requires_goal", "requires_todo")
_STOP_KEYS = {"reason", "since", "ref", "citation"}

# The prose forms a stated cause names the hard-stop
# classes by, beyond each class's own name and its
# space/hyphen renderings: the approval card a
# permission stop rides, and the cron change a schedule
# stop is posted as.
_CAUSE_ALIASES = {
    "approval card": "permission_card",
    "cron change": "schedule_change",
}


class _Malformed:
    """Sentinel: a stop line was posted but does not
    parse to the posting form — never repaired, never
    guessed at."""

    def __repr__(self) -> str:
        return "MALFORMED"


MALFORMED = _Malformed()


def _is_iso(value) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _ref_ok(ref) -> bool:
    if ref is None:
        return True
    if not isinstance(ref, dict) or set(ref) != {"kind", "id"}:
        return False
    return ref["kind"] in REF_KINDS and isinstance(ref["id"], str) and bool(ref["id"])


def _citation_ok(citation) -> bool:
    if citation is None:
        return True
    if not isinstance(citation, dict) or set(citation) != {"chat", "at"}:
        return False
    return (
        isinstance(citation["chat"], str)
        and bool(citation["chat"])
        and _is_iso(citation["at"])
    )


def parse_stop_line(text):
    """The status record's stop line, parsed strictly.

    Returns the normalized stop dict, None when the
    record posts no stop line, or MALFORMED when a line
    was posted but is not the posting form (unparseable
    JSON, an unknown key, a wrong shape). A stop dict
    carries reason (a register id, or None for the
    unreasoned form), since, ref, citation."""
    if not isinstance(text, str):
        return MALFORMED
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("stop:")]
    if not lines:
        return None
    if len(lines) > 1:
        return MALFORMED
    try:
        payload = json.loads(lines[0][len("stop:") :].strip())
    except ValueError:
        return MALFORMED
    if not isinstance(payload, dict) or not set(payload) <= _STOP_KEYS:
        return MALFORMED
    reason = payload.get("reason")
    if reason is not None and not (isinstance(reason, str) and reason):
        return MALFORMED
    if not _is_iso(payload.get("since")):
        return MALFORMED
    ref = payload.get("ref")
    citation = payload.get("citation")
    if not _ref_ok(ref) or not _citation_ok(citation):
        return MALFORMED
    return {
        "reason": reason,
        "since": payload["since"],
        "ref": ref,
        "citation": citation,
    }


def _named_hard_stop_classes(cause, rows: dict) -> set:
    """The hard-stop classes a stated cause names: each
    class's register name and its space/hyphen
    renderings, plus the prose aliases — substring
    reads over the cause text, nothing fuzzier."""
    if not cause:
        return set()
    text = str(cause).lower()
    named = set()
    for name, row in rows.items():
        if not row.get("hard_stop"):
            continue
        forms = {name, name.replace("_", " "), name.replace("_", "-")}
        if any(form in text for form in forms):
            named.add(name)
    for alias, name in _CAUSE_ALIASES.items():
        if alias in text:
            named.add(name)
    return named


def _result(kind, reason=None, disposition=None, detail=""):
    return {
        "verdict": kind,
        "reason": reason,
        "disposition": disposition,
        "detail": detail,
    }


def _citation_verifies(stop: dict, owner_traffic) -> bool:
    citation = stop.get("citation")
    if not citation or owner_traffic is None:
        return False
    return bool(owner_traffic({"chat": citation["chat"], "at": citation["at"]}))


def _act_exists(name: str, owner_traffic) -> bool:
    if owner_traffic is None:
        return False
    return bool(owner_traffic({"act": name}))


def verdict(
    state,
    stop,
    cause=None,
    classes=None,
    codes=None,
    approval_state=None,
    owner_traffic=None,
) -> dict:
    """The verdict over one declared stop.

    state is the status record's state string (or None);
    stop is parse_stop_line's output over the record;
    cause is the record's stated-cause text (or None).
    The claiming lane's records are not a parameter:
    no verdict here can rest on them."""
    if stop is MALFORMED:
        return _result(
            UNRECOGNIZED, detail="stop line does not parse to the posting form"
        )
    vocabulary = {
        entry["code"]
        for entry in (codes if codes is not None else default_status_codes())
    }
    if state is not None and state not in vocabulary:
        return _result(
            UNRECOGNIZED,
            detail=f"state string {state!r} is not the canonical vocabulary",
        )
    if stop is None:
        return _result(RESIDUE, detail="no stop line posted")
    rows = {
        entry["name"]: entry
        for entry in (classes if classes is not None else default_wait_classes())
    }
    reason = stop.get("reason")
    row = rows.get(reason) if reason else None
    named_hard = _named_hard_stop_classes(cause, rows)
    if state in BLOCKED_STATES and not (row and row.get("hard_stop")):
        # An owner-block claim: the verification read is
        # the only path to true, and the default is
        # false — uncited, miscited, or evidenced only
        # by the lane's own stamps, the claim is void.
        if _citation_verifies(stop, owner_traffic):
            return _result(
                OWNER_ITEM,
                reason,
                detail="owner-block claim verified against owner traffic",
            )
        for name in sorted(named_hard):
            if _act_exists(name, owner_traffic):
                return _result(
                    OWNER_ITEM,
                    reason,
                    detail=f"owner-block claim names a hard-stop act "
                    f"that exists: {name}",
                )
        return _result(
            VOID,
            reason,
            detail="owner-block claim unverified — the default verdict is false",
        )
    foreign = named_hard - {reason}
    if foreign:
        return _result(
            REFUSED,
            reason,
            detail="stated cause names a hard-stop class: "
            + ", ".join(sorted(foreign)),
        )
    if reason is None:
        return _result(RESIDUE, detail="unreasoned stop — no reason declared")
    if row is None:
        return _result(
            RESIDUE,
            reason,
            detail="reason is outside the enumeration — a candidate, not a class",
        )
    required = [kind for kind in REF_KINDS if row.get(f"requires_{kind}")]
    if required:
        ref = stop.get("ref")
        if not ref or ref["kind"] not in required:
            return _result(
                STANDING,
                reason,
                detail="the reason requires a reference of kind "
                + "/".join(required)
                + "; the stop carries none",
            )
        approved = (
            approval_state(ref["kind"], ref["id"])
            if approval_state is not None
            else None
        )
        if approved is not True:
            return _result(
                STANDING,
                reason,
                detail="the reference's recorded approval does not validate the stop",
            )
        return _result(
            ACTUATE,
            reason,
            row.get("disposition"),
            "the reference's recorded approval validates — "
            "the row's disposition fires",
        )
    if row.get("hard_stop"):
        return _result(
            OWNER_ITEM,
            reason,
            detail="a hard-stop reason — the owner's, via the digest",
        )
    return _result(ACTUATE, reason, row.get("disposition"))
