"""Read-model labels: the label registries and the small
read helpers (handler maps, digest prefs, presence) —
split from model.py along the label seam;
attention.services.reads.model re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime

from attention.domain import attention as dom
from attention.settings import Settings

CONTRACT = "api/1"

KIND_LABELS = {
    "decision": "Decision",
    "action": "Action",
    "defect": "Defect",
    "approval": "Approval",
    "fyi": "FYI",
}
TIER_LABELS = {
    "breakthrough": "Breakthrough",
    "due_today": "Due today",
    "digest": "Digest",
    "fyi": "FYI",
}
BAND_LABELS = {
    "breakthrough": "Breakthrough",
    "due_today": "Due today",
    "needs_decision": "Needs a decision",
    "waiting": "Waiting on agents",
    "fyi": "FYI",
}
DECISION_LABELS = {
    "auto_applied": "Auto-applied",
    "surface": "Surfaced",
    "pending": "Held pending",
    "held": "Held",
    "post": "Posted",
    "posted": "Posted",
    "fallthrough": "Fell through",
}
OUTCOME_LABELS = {
    "recorded": "Recorded",
    "deduped": "Held — facts unchanged",
    "cooldown": "Held — cooldown",
    "max_posts": "Held — max posts",
    "no_template": "Held — no template",
}
BAND_ORDER = ("breakthrough", "due_today", "needs_decision", "waiting", "fyi")
MODE_LABELS = {"active": "Active", "focus": "Focus", "away": "Away"}
PROVENANCE_LABELS = {
    "commission": "Owner commission",
    "offer": "Agent offer — awaiting your tap",
}
DIGEST_OWNER_LABELS = {
    "owner": "Waiting on you",
    "lane": "Back with the lane",
    "self": "Poster closeout",
}


def status_label(state: dict, code: str) -> str:
    """A status code's display label from the registry —
    every surface renders the label, never the raw code."""
    for entry in state.get("status_codes") or dom.default_status_codes():
        if entry["code"] == code:
            return entry["label"]
    return code


def class_label(name: str) -> str:
    """A wait class's display name (classes carry no label
    field; the name title-cased is the display form)."""
    text = name.replace("_", " ")
    return text[:1].upper() + text[1:]


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _kind_label(state: dict, kind: str) -> str:
    for entry in state.get("item_kinds", []):
        if entry["kind"] == kind:
            return entry["label"]
    return KIND_LABELS.get(kind, kind)


def handler_map(state: dict) -> dict:
    return {h["handle"]: h for h in state["handlers"]}


def digest_windows(state: dict, settings: Settings) -> list:
    """The digest windows in force (AC-8): the configured
    times minus any the owner switched off on state
    (digest_prefs — the digest page's and the shell
    Settings row's write). One home: the digest's next_at,
    the glance clock, and the snooze "next digest" time
    all read windows through here, so a disabled window
    disappears from every surface at once."""
    prefs = (state.get("digest_prefs") or {}).get("windows") or {}
    return [t for t in settings.digest_windows if prefs.get(t, True)]


def digest_include(state: dict) -> dict:
    """The digest include flags in force (AC-8): stored
    prefs over the all-on default."""
    stored = (state.get("digest_prefs") or {}).get("include") or {}
    return {key: stored.get(key, True) for key in ("decisions", "waiting", "fyi")}


def handler_presentation(handler: dict) -> dict:
    """A handler's presentation pair, defaulted at read
    (AC-12): registration writes color_slot/icon with the
    defaults below (writes.register_handler), but a record
    that reaches state without passing registration — a
    hand-edited or partially migrated store — must not
    KeyError the reads that serve it (item views, the
    glance dots, the registries list). This is the one
    home for the read-side defaults; they mirror the
    registration defaults exactly."""
    return {
        "color_slot": handler.get("color_slot", 1),
        "icon": handler.get("icon", "dot"),
    }


def handler_order(state: dict) -> dict:
    return {h["handle"]: i for i, h in enumerate(state["handlers"])}


def effective_mode(state: dict, now: datetime) -> str:
    """The served presence mode: a declared mode whose
    expiry has passed no longer holds — the owner is
    back, and no surface keeps withholding for it."""
    mode = state["presence"]["mode"]
    expires = state["presence"].get("expires_at")
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if mode != "active" and expires is not None and expires <= now:
        return "active"
    return mode


def presence_view(state: dict, now: datetime) -> dict:
    presence = state["presence"]
    mode = effective_mode(state, now)
    return {
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "expires_at": _iso(presence.get("expires_at")),
        "expectation": presence.get("expectation", ""),
    }
