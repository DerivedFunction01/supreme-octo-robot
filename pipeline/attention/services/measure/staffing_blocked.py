"""Staffing rows, blocked family: unrouted defects,
phantom stops, and blocked-state rows — split from
staffing_rows.py; attention.services.measure.
staffing_rows re-exports this surface.
"""

from __future__ import annotations

import re
from datetime import datetime

from attention.services import programmes
from attention.services.reads import digest as digest_mod
from attention.services.reads import model

from .staffing_common import (
    OWNER_THREADS,
    _as_dt,
    _names_workhorse,
    _row,
)


def _unrouted_rows(state: dict) -> list:
    """§1.11 (j): a workhorse defect in a lane's queue item
    with no routing, addressed to the lane; it clears
    when the item carries routing, not on ack."""
    handlers = model.handler_map(state)
    rows = []

    def add(handle, text, key):
        workhorse = _names_workhorse(text)
        if not workhorse:
            return
        rows.append(
            _row(
                digest_mod.topic_of(handle),
                handle,
                handlers.get(handle, {}).get("label", handle),
                "unrouted_defect",
                f"A defect naming the {workhorse} workhorse "
                f"carries no routing: {OWNER_THREADS[workhorse]} "
                f"has not been notified. It clears when the "
                f"item carries its routing.",
                key=key,
            )
        )

    for item in state.get("items", []):
        if (
            item.get("kind") == "defect"
            and item.get("triage") == "open"
            and not item.get("routing")
        ):
            add(item["handle"], item.get("title"), f"unrouted_defect:{item['id']}")
    return rows


_CLAIM_RE = re.compile(
    r"owner.{0,40}(order|instruct|direct|said|asked|told|stop|halt|"
    r"stood|stand[ -]down|pause)|(order|stop|halt|instruction|direction)"
    r".{0,30}owner",
    re.IGNORECASE,
)


def _claims_owner_order(text: str) -> bool:
    return bool(text) and bool(_CLAIM_RE.search(text))


_CITATION_RE = re.compile(
    r"thread[:\s]+\S+.{0,120}?\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",
    re.IGNORECASE,
)


def _find_citation(body: str) -> str | None:
    """A blocked todo's citation: a body line naming the
    owner's message thread and the time — the basis a
    blocked claim stands on. None when no line carries
    both."""
    for line in (body or "").splitlines():
        if _CITATION_RE.search(line):
            return line.strip()
    return None


def _blocked_todos(state: dict) -> list:
    """Every blocked todo in the snapshot, with its
    programme: (programme, entry) pairs."""
    out = []
    for programme in programmes.active_declarations(state):
        entry = (state.get("blocked_snapshot") or {}).get(programme["slug"]) or {}
        for todo in entry.get("blocked") or []:
            out.append((programme, todo))
    return out


def _phantom_rows(state: dict, now: datetime) -> list:
    """§1.11 (i): an uncited owner-instruction claim in a
    blocked todo's body is a defect addressed to main,
    priced with its frozen duration; a cited claim is a
    state. The frozen clock runs from the body's latest
    checkpoint — the lane's last act."""
    rows = []
    for programme, todo in _blocked_todos(state):
        body = todo.get("body") or ""
        if _find_citation(body):
            continue
        if not _claims_owner_order(body):
            continue
        stamp = _as_dt(todo.get("checkpoint_at"))
        frozen = int((now - stamp).total_seconds() // 60) if stamp is not None else None
        detail = (
            f"Frozen {frozen} minutes on a claimed owner "
            f"instruction that cites no owner message. The "
            f"claim is unverified; it is addressed to main "
            f"for verification, never held as a state."
            if frozen is not None
            else "A claimed owner instruction cites no owner "
            "message, and the record carries no checkpoint "
            "to date the claim. The claim is unverified; "
            "it is addressed to main for verification, "
            "never held as a state."
        )
        handle = (programme.get("handles") or [programme["slug"]])[0]
        row = _row(
            programme["slug"],
            handle,
            programme["label"],
            "phantom_stop",
            detail,
            idle_minutes=frozen,
            key=f"phantom_stop:{programme['slug']}:{todo.get('todo')}",
        )
        row["escalation"] = "main"
        rows.append(row)
    return rows


def _blocked_rows(state: dict, now: datetime, cadence_of, skip: set) -> list:
    """Blocked is a supervised state (§1.11 (i)
    addenda): no stated basis, or a cited basis main
    has not stamped past one check cycle, is a row.
    `skip` holds the phantom rows' keys — a claim the
    phantom row already carries is not reported twice."""
    stamped = {v["handle"] for v in state.get("verifications", [])}
    rows = []
    for programme, todo in _blocked_todos(state):
        phantom_key = f"phantom_stop:{programme['slug']}:{todo.get('todo')}"
        if phantom_key in skip:
            continue
        handle = (programme.get("handles") or [programme["slug"]])[0]
        topic = programme["slug"]
        label = programme["label"]
        body = (todo.get("body") or "").strip()
        if not body:
            row = _row(
                topic,
                handle,
                label,
                "blocked_uncited",
                "Blocked with no stated basis: the todo "
                "body carries no blocker note, so nothing "
                "cites what it waits on.",
                key=f"blocked_uncited:{programme['slug']}:{todo.get('todo')}",
            )
            row["escalation"] = "main"
            rows.append(row)
            continue
        citation = _find_citation(body)
        if citation and handle not in stamped:
            stamp = _as_dt(todo.get("checkpoint_at"))
            if stamp is None:
                continue
            age = int((now - stamp).total_seconds() // 60)
            if age > cadence_of(handle):
                row = _row(
                    topic,
                    handle,
                    label,
                    "blocked_unverified",
                    f"Blocked on a cited basis main has not "
                    f"stamped for {age} minutes — past one "
                    f"check cycle. The verification is main's.",
                    idle_minutes=age,
                    key=f"blocked_unverified:{programme['slug']}:{todo.get('todo')}",
                )
                row["escalation"] = "main"
                rows.append(row)
    return rows
