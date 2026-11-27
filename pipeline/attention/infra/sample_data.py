"""Demo seed for a fresh instance (no data path configured).

Plausible shapes mirroring the storyboard frames; production
state is whatever agents post through the API.
"""

from __future__ import annotations

from datetime import datetime, timedelta

HANDLERS = [
    {
        "handle": "@specimen-viewer",
        "label": "specimen — viewer",
        "color_slot": 1,
        "icon": "grid",
    },
    {
        "handle": "@specimen-field",
        "label": "Specimen — field extractor",
        "color_slot": 2,
        "icon": "table",
    },
    {
        "handle": "@specimen-panel",
        "label": "specimen — panel",
        "color_slot": 3,
        "icon": "server",
    },
    {"handle": "calendar", "label": "Calendar", "color_slot": 4, "icon": "calendar"},
    {"handle": "mail", "label": "Mail", "color_slot": 5, "icon": "mail"},
]


def _item(item_id, handle, kind, title, status_code, now, **extra):
    item = {
        "id": item_id,
        "handle": handle,
        "kind": kind,
        "title": title,
        "status_code": status_code,
        "source_ref": item_id,
        "source_url": "",
        "clears_at_source": True,
        "due_at": None,
        "waiting_since": now - timedelta(hours=2),
        "need": "unclassified",
        "tier": "digest",
        "triage": "open",
        "snooze_return_at": None,
        "snooze_on_activity": False,
        "resume_note": None,
    }
    item.update(extra)
    return item


def sample_state(now: datetime) -> dict:
    from attention.domain.attention import (
        assign_tier,
        classify_need,
        default_action_rules,
        default_fields,
        default_item_kinds,
        default_rules,
        default_status_codes,
        default_templates,
        default_wait_classes,
    )

    items = [
        _item(
            "demo-lease",
            "@specimen-panel",
            "approval",
            "Lease expiring — renew or release",
            "BLOCKED-HARD",
            now,
            waiting_since=now - timedelta(hours=2),
            wait_id="w0001",
        ),
        _item(
            "demo-push",
            "@specimen-viewer",
            "action",
            "Push the wedge fix",
            "BLOCKED-OWNER",
            now,
            due_at=now.replace(hour=9, minute=0),
            waiting_since=now - timedelta(hours=5),
        ),
        _item(
            "demo-denominator",
            "@specimen-field",
            "decision",
            "Rule the labelled-only denominator",
            "BLOCKED-OWNER",
            now,
            waiting_since=now - timedelta(days=3),
            clears_at_source=False,
            options=[
                {"id": "labelled", "label": "Labelled-only denominator"},
                {"id": "all", "label": "All geometries"},
            ],
        ),
        _item(
            "demo-calendar",
            "calendar",
            "action",
            "Confirm the quarterly planning review",
            "BLOCKED-OWNER",
            now,
            due_at=now + timedelta(days=4),
            waiting_since=now - timedelta(days=1),
        ),
        _item(
            "demo-wedge",
            "@specimen-viewer",
            "defect",
            "Wedge: health queue stalls",
            "WORKING",
            now,
            waiting_since=now - timedelta(days=1),
        ),
        _item(
            "demo-fyi",
            "mail",
            "fyi",
            "Recruiter reply draft is ready to review",
            "WORKING",
            now,
            waiting_since=now - timedelta(hours=1),
        ),
    ]
    allowlist = [["@specimen-panel", "approval"]]
    for item in items:
        item["need"] = classify_need(item["status_code"])
        item["tier"] = assign_tier(item, allowlist, now)
    return {
        "handlers": HANDLERS,
        "items": items,
        "presence": {"mode": "active", "expires_at": None, "expectation": ""},
        "waits": [
            {
                "id": "w0001",
                "handle": "@specimen-panel",
                "wait_class": "lease_renewal",
                "summary": "Lease expiring — renew or release",
                "decision": "surfaced",
                "at": now - timedelta(hours=2),
            }
        ],
        "action_log": [],
        "source_health": {
            "mail": {
                "available": False,
                "reason": "Mail source unreachable",
                "last_good_at": now - timedelta(hours=1),
            }
        },
        "muted": [["@specimen-viewer", "fyi"]],
        "allowlist": allowlist,
        "handler_status": {
            "@specimen-viewer": {
                "status_code": "BLOCKED-OWNER",
                "summary": "Push awaiting the tap",
                "at": now - timedelta(minutes=20),
            }
        },
        "rules": default_rules(),
        "status_codes": default_status_codes(),
        "fields": default_fields(),
        "wait_classes": default_wait_classes()
        + [{"name": "lease_renewal", "hard_stop": True}],
        "templates": default_templates(),
        "item_kinds": default_item_kinds(),
        "sends": [],
        "presence_seen": "active",
        "capacity_snapshot": None,
        "capacity_error": None,
        "digest_assembly": None,
        "staffing_rows": {},
        "dispatch_failures": [],
        "verifications": [],
        "action_rules": default_action_rules(),
        "owner_actions": [],
        "tap_counts": {},
        "pings": {},
        "owner_directed": {},
    }
