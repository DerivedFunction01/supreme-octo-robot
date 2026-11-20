"""R-2 refusals (2026-11-15): the panel's actuating endpoints must
refuse a body that names no target, exactly like their siblings —
an empty-body POST /api/lease/stop released the standing lease
live during the usability audit, because the handler built
`release` with no session and the core released the standing
lease. The stub lease CLI is the only core these tests reach
(the ui harness boots the server against it); the assertions
check both the 400 and that the core was never invoked.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_harness import UiServer  # noqa: E402


@pytest.fixture()
def ui(tmp_path):
    server = UiServer(tmp_path)
    yield server
    server.close()


def test_stop_refuses_missing_session(ui):
    for payload in ({}, {"session": ""}, {"session": 42}):
        status, result = ui.post("/api/lease/stop", payload)
        assert status == 400
        assert result["error"] == "session is required"
    # No release reached the core, and nothing was announced.
    assert not any(line.startswith("release") for line in ui.invocations())
    assert ui.outbox_events() == []


def test_stop_with_session_still_releases(ui):
    status, result = ui.post("/api/lease/stop", {"session": "amber-otter-42"})
    assert status == 200 and result["action"] == "released"
    assert "release amber-otter-42" in ui.invocations()
    assert [e["kind"] for e in ui.outbox_events()] == ["lease-stopped"]


def test_ungrant_refuses_unconfirmed_body(ui):
    for payload in ({}, {"confirm": False}, {"confirm": "yes"}):
        status, result = ui.post("/api/ungrant", payload)
        assert status == 400
        assert result["error"] == "confirm is required"
    assert "ungrant" not in ui.invocations()
    assert ui.outbox_events() == []


def test_ungrant_with_confirmation_still_ends_grant(ui):
    status, result = ui.post("/api/ungrant", {"confirm": True})
    assert status == 200 and result["action"] == "grant-ended"
    assert "ungrant" in ui.invocations()
    assert [e["kind"] for e in ui.outbox_events()] == ["grant-ended"]
