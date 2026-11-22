"""Staffing row commons: the shared row shape, the kind
labels, and the small helpers every row family uses —
split from staffing_rows.py;
attention.services.measure.staffing_rows re-exports
this surface.
"""

from __future__ import annotations

from datetime import UTC, datetime


def _as_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            stamp = datetime.fromisoformat(value)
        except ValueError:
            return None
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    return None


KIND_LABELS = {
    "understaffed": "Understaffed",
    "fleet_idle": "Idle session",
    "idle_unlanded": "Idle — work complete",
    "no_successor": "No successor staffed",
    "record_gap": "Record not moving",
    "phantom_stop": "Unverified owner stop",
    "unrouted_defect": "Unrouted defect",
    "blocked_uncited": "Blocked — no basis",
    "blocked_unverified": "Blocked — unverified",
    "steer_undeliverable": "Steer undeliverable",
    "owner_waiting": "Owner waiting",
    "owner_waiting_unanswered": "Owner waiting — ask unanswered",
    "armed_unreported": "Armed — no checkpoint yet",
    "unlanded_claim": "Done claimed — worktree unlanded",
    "unarmed_work": "Worktree standing — unarmed",
    "orphan_record": "Orphaned run record",
    "terminal_unconsumed": "Terminal run — unconsumed",
    "unlanded_build": "Build claimed complete — unlanded",
    "serial_staffing": "Serial staffing",
    "frontier_shortfall": "Frontier shortfall",
}
WORKHORSE_TERMS = {
    "scheduler": ("scheduler",),
    "workbench": ("workbench", "harness"),
    "colab": ("colab", "lease runner", "lease panel"),
}
OWNER_THREADS = {
    "scheduler": "the scheduler thread",
    "workbench": "the workbench viewer thread",
    "colab": "the Colab panel thread",
}


def _names_workhorse(text) -> str | None:
    low = (text or "").lower()
    for name, terms in WORKHORSE_TERMS.items():
        if any(term in low for term in terms):
            return name
    return None


def _row(topic, handle, label, kind, detail, **evidence) -> dict:
    row = {
        "topic": topic,
        "handle": handle,
        "handler_label": label,
        "kind": kind,
        "kind_label": KIND_LABELS[kind],
        "workers": evidence.get("workers"),
        "child_workers": evidence.get("child_workers"),
        "sessions_used": evidence.get("sessions_used", 0),
        "sessions_live": evidence.get("sessions_live", 0),
        "idle_minutes": evidence.get("idle_minutes"),
        "checkpoint_gap_minutes": evidence.get("checkpoint_gap_minutes"),
        "stall_minutes": None,
        "jobs_run": evidence.get("jobs_run"),
        "expected_minutes": None,
        "owner_directed": False,
        "escalation": "lane",
        "detail": detail,
    }
    row.update(evidence.get("extra") or {})
    row["_key"] = evidence.get("key") or f"{kind}:{topic or handle or ''}"
    return row
