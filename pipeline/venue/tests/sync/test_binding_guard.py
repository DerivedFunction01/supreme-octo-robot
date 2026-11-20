"""Binding-guard units: the funnel's heal is loud and sticky.

Pins the 2026-11-17 cure for the binding-store truncation
class. The old guard restored a clobbered sessions.json from
its per-call snapshot and swallowed every failure: a restore
denied in the same write-denial wave that truncated the file
left it at 0 bytes, later calls snapshotted the damage and
stood down ("no snapshot, no restore"), and the fleet read
blind for hours — twice in one night. The guard now journals
every outcome, serves a binding-state finding, heals a
damaged-at-start call from the persisted last-healthy copy
(filtered to live lease records), and refreshes that copy on
every healthy ending.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cli = load("cli_binding_guard", "sync/cli.py")

HEALTHY = json.dumps({"live-one": {"endpoint": "m-hm-x"}, "dead-one": {"endpoint": "m-hm-y"}}).encode()


@pytest.fixture()
def guard(tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir()
    sessions = tmp_path / "sessions.json"
    monkeypatch.setattr(cli, "SESSIONS", sessions)
    monkeypatch.setattr(cli, "_var_dir", lambda: var)
    (var / "lease-live-one.json").write_text(json.dumps({"session": "live-one", "deadline": "2999-01-01T00:00:00+00:00"}))
    return var, sessions


def journal(var):
    path = var / "binding-journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def served(var):
    path = var / "binding-state.json"
    return json.loads(path.read_text()) if path.exists() else None


def test_sticky_heal_restores_live_entries_only(guard):
    var, sessions = guard
    sessions.write_bytes(b"")
    (var / "binding-last-healthy.json").write_bytes(HEALTHY)
    cli._heal_binding(None)
    restored = json.loads(sessions.read_bytes())
    assert sorted(restored) == ["live-one"]
    assert ("sticky-heal", "restored") in [(e["event"], e["detail"]) for e in journal(var)]
    assert served(var)["state"] == "ok"


def test_sticky_heal_without_persisted_copy_serves_damaged(guard):
    var, sessions = guard
    sessions.write_bytes(b"")
    cli._heal_binding(None)
    assert sessions.read_bytes() == b""
    assert served(var)["state"] == "damaged"
    assert served(var)["detail"] == "no-persisted-copy"


def test_snapshot_restore_failure_is_loud(guard, monkeypatch):
    var, sessions = guard
    sessions.write_bytes(HEALTHY)
    snapshot = cli._binding_snapshot(cli._binding_bytes())
    sessions.write_bytes(b"")
    real_write = cli._staged_write

    def denied(path, data, mode=None):
        if Path(path) == sessions:
            raise PermissionError("denied")
        return real_write(path, data, mode=mode)

    monkeypatch.setattr(cli, "_staged_write", denied)
    cli._heal_binding(snapshot)  # never raises
    assert served(var)["state"] == "damaged"
    assert ("restore-failed", "snapshot restore did not land") in [(e["event"], e["detail"]) for e in journal(var)]


def test_empty_object_is_the_clis_view_never_overridden(guard):
    var, sessions = guard
    sessions.write_bytes(b"{}")
    (var / "binding-last-healthy.json").write_bytes(HEALTHY)
    cli._heal_binding(None)
    assert sessions.read_bytes() == b"{}"


def test_missing_binding_is_not_damage(guard):
    var, sessions = guard
    sessions.unlink(missing_ok=True)
    (var / "binding-last-healthy.json").write_bytes(HEALTHY)
    cli._heal_binding(None)
    assert not sessions.exists()
    assert served(var) is None


def test_healthy_ending_persists_copy_and_serves_ok(guard):
    var, sessions = guard
    sessions.write_bytes(HEALTHY)
    snapshot = cli._binding_snapshot(cli._binding_bytes())
    cli._heal_binding(snapshot)
    assert (var / "binding-last-healthy.json").read_bytes() == HEALTHY
    assert served(var)["state"] == "ok"
