"""Lease unit tests: bind liveness and pin lineage
(adoption-liveness cure), with stub colab callables
(no subprocess).

The defect these pin: adoption bound launches on the session
list's word alone. A renewed lease whose kernel channel was
dead read "alive" and absorbed launch after launch at their
first exec, while a pin written against the pre-renewal name
refused pin-unavailable though the lease stood renewed under
a new name. The cure: a pin resolves to its lineage's live
generation, and one bounded kernel probe (keepalive
.bind_probe) gates every adoption bind.
"""

import json
import subprocess
from datetime import timedelta

from unit_harness import NOW, cp, gate_permissive, lease, repo  # noqa: F401


def _seed_named(repo, session, deadline_h, caller=None):
    rec = {
        "session": session,
        "shape": "cpu",
        "shape_spec": {"gpu": None, "tpu": None, "high_mem": False},
        "rate_cu_per_hour": 0.08,
        "acquired_at": NOW.isoformat(),
        "deadline": (NOW + timedelta(hours=deadline_h)).isoformat(),
        "last_used_at": NOW.isoformat(),
        "jobs": [],
    }
    if caller is not None:
        rec["caller"] = caller
    lease.save_record(repo, rec)
    return rec


def _channel_stub(alive, dead_channels=(), busy_channels=()):
    """The _auto_stub world with per-session kernel channels:
    the session list (control plane) reports every alive name,
    but a dead channel's bind-probe exec refuses — the renewed
    noble shape, alive on the list and dead at the first exec —
    and a busy channel's probe exec times out locally (the
    channel carried the request; the kernel is executing).
    Every other call answers as the healthy stub answers."""

    def stub(*a, **k):
        cmd = a[0] if a else ""
        if cmd == "usage":
            return cp("balance: 500 CU (stub)")
        if cmd == "sessions":
            return cp(json.dumps(sorted(alive)))
        if cmd == "new":
            alive.add(a[a.index("-s") + 1])
            return cp("created")
        if cmd == "download":
            return cp("", rc=1)
        if cmd == "exec":
            session = a[a.index("-s") + 1] if "-s" in a else None
            if any("bind-probe" in str(x) for x in a):
                if session in busy_channels:
                    raise subprocess.TimeoutExpired(cmd="exec", timeout=30)
                if session in dead_channels:
                    return cp("ReadTimeout: kernel channel unreachable", rc=1)
            return cp("")
        return cp("")

    return stub


OLD = "noble-shore-15-r1000000000"
NEW = "noble-shore-15-r2000000000"


def test_pin_resolves_through_a_renewal_tombstone(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stub = _channel_stub({NEW})
    _seed_named(repo, OLD, 6)
    _seed_named(repo, NEW, 6)
    lease.retire_superseded(repo, OLD, NEW, NOW)
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, prefer_session=OLD)
    assert out["action"] == "adopted"
    assert out["record"]["session"] == NEW
    assert out["pin_resolved"] == {"from": OLD, "to": NEW, "via": "superseded"}
    assert out["bind_probe"]["live"] is True


def test_pin_resolves_by_lineage_without_a_tombstone(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stub = _channel_stub({NEW})
    _seed_named(repo, NEW, 6)
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, prefer_session=OLD)
    assert out["action"] == "adopted"
    assert out["record"]["session"] == NEW
    assert out["pin_resolved"] == {"from": OLD, "to": NEW, "via": "lineage"}


def test_pin_to_an_unknown_lineage_still_refuses(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stub = _channel_stub({NEW})
    _seed_named(repo, NEW, 6)
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, prefer_session="other-family-99-r1000000000")
    assert out["action"] == "pin-unavailable"
    assert "lineage" in out["reason"]
    assert lease.load_record(repo, NEW) is not None


def test_pin_probe_failure_refuses_pin_lineage_unhealthy(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stub = _channel_stub({NEW}, dead_channels={NEW})
    _seed_named(repo, NEW, 6)
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, prefer_session=NEW)
    assert out["action"] == "pin-unavailable"
    assert out["reason"].startswith("pin-lineage-unhealthy")
    assert out["probe"]["live"] is False and out["probe"]["result"] == "failed"
    assert lease.load_record(repo, NEW) is not None, "a refused pin destroyed the named record"
    journal = lease.launch_health_path(repo).read_text().splitlines()
    entries = [json.loads(line) for line in journal if line.strip()]
    assert any(e["session"] == NEW and e["stage"] == "bind" and e["ok"] is False for e in entries), "the probe failure was not journaled as launch health"


def test_unpinned_acquire_skips_a_dead_channel_lease(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    dead, healthy = "dead-chan-01", "healthy-chan-02"
    stub = _channel_stub({dead, healthy}, dead_channels={dead})
    _seed_named(repo, dead, 6)  # the deadline winner without the probe
    _seed_named(repo, healthy, 4)
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW)
    assert out["action"] == "adopted"
    assert out["record"]["session"] == healthy
    assert out["bind_probe"]["live"] is True
    assert [f["session"] for f in out["bind_probe_failures"]] == [dead]
    assert lease.load_record(repo, dead) is not None, "the skipped candidate was cleared"


def test_bind_probe_timeout_reads_busy_and_binds(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stub = _channel_stub({NEW}, busy_channels={NEW})
    _seed_named(repo, NEW, 6)
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, prefer_session=NEW)
    assert out["action"] == "adopted"
    assert out["record"]["session"] == NEW
    assert out["bind_probe"]["result"] == "busy"
    assert out["bind_probe"]["live"] is True
