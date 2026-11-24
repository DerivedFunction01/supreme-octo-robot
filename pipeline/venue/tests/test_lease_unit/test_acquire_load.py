"""Lease unit tests: load-aware acquire —
the pool sort spreads unpinned fires across live
sessions instead of concentrating them on the
longest deadline: warm before cold, least in-flight
load next, and a window floor that skips (never
clears) a lease too short for the fire."""

import json

from unit_harness import NOW, _auto_stub, gate_permissive, lease, repo  # noqa: F401


def _seed(repo, session, deadline, caller="panel", provisioning=None):
    rec = {
        "session": session,
        "shape": "cpu",
        "shape_spec": {"gpu": None, "tpu": None, "high_mem": False},
        "rate_cu_per_hour": 0.08,
        "acquired_at": "2026-10-29T17:00:00+00:00",
        "deadline": deadline,
        "last_used_at": "2026-10-29T17:30:00+00:00",
        "jobs": [],
        "caller": caller,
    }
    if provisioning is not None:
        rec["provisioning"] = provisioning
    lease.save_record(repo, rec)
    return rec


def _seed_run(repo, run_id, session, state="running", started="2026-10-29T17:30:00+00:00"):
    runs = repo / "results" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "job": "j", "session": session, "state": state, "started_at": started})
    )


def test_unpinned_acquire_spreads_to_the_unloaded_session(repo, tmp_path, monkeypatch):
    """The loaded session holds the later deadline —
    the old sort's winner. The load term outranks the
    deadline tiebreak, so the fire lands on the idle
    session."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _seed(repo, "loaded-late", "2026-10-30T02:00:00+00:00")
    _seed(repo, "idle-early", "2026-10-30T01:00:00+00:00")
    _seed_run(repo, "run-1", "loaded-late")
    _seed_run(repo, "run-2", "loaded-late")
    stub = _auto_stub({"loaded-late", "idle-early"})
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, caller="lane")
    assert out["action"] == "adopted"
    assert out["record"]["session"] == "idle-early"


def test_terminal_and_stale_runs_do_not_count_as_load(repo, tmp_path, monkeypatch):
    """A terminal run and a run started outside the
    load window are not in flight: the session they
    name reads unloaded."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _seed(repo, "busy-late", "2026-10-30T02:00:00+00:00")
    _seed(repo, "free-early", "2026-10-30T01:00:00+00:00")
    _seed_run(repo, "run-done", "busy-late", state="complete")
    _seed_run(repo, "run-stale", "busy-late", started="2026-10-29T10:00:00+00:00")
    stub = _auto_stub({"busy-late", "free-early"})
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, caller="lane")
    assert out["action"] == "adopted"
    assert out["record"]["session"] == "busy-late"


def test_a_warm_loaded_session_beats_a_cold_idle_one(repo, tmp_path, monkeypatch):
    """Warmth ranks before load: a session whose
    provisioning is still in flight pays an env build
    on landing, so a warm session carrying work still
    wins over a cold idle one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _seed(repo, "warm", "2026-10-30T01:00:00+00:00", provisioning={"state": "verdict"})
    _seed(repo, "cold", "2026-10-30T02:00:00+00:00", provisioning={"state": "launched"})
    _seed_run(repo, "run-1", "warm")
    stub = _auto_stub({"warm", "cold"})
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, caller="lane")
    assert out["action"] == "adopted"
    assert out["record"]["session"] == "warm"


def test_a_cold_session_is_adopted_when_it_is_the_only_candidate(repo, tmp_path, monkeypatch):
    """Cold ranks last, never out: alone in the pool,
    the cold session is adopted."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _seed(repo, "cold", "2026-10-30T02:00:00+00:00", provisioning={"state": "launched"})
    stub = _auto_stub({"cold"})
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, caller="lane")
    assert out["action"] == "adopted"
    assert out["record"]["session"] == "cold"


def test_the_window_floor_skips_without_clearing(repo, tmp_path, monkeypatch):
    """A live lease whose remaining window cannot
    cover the fire is skipped and left standing — the
    call creates a lease that covers instead."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _seed(repo, "short", "2026-10-29T18:30:00+00:00")
    alive = {"short"}
    stub = _auto_stub(alive)
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, caller="lane", min_window_s=3600)
    assert out["action"] == "created"
    assert out["record"]["session"] != "short"
    assert lease.load_record(repo, "short") is not None


def test_a_pin_adopts_its_session_regardless_of_load(repo, tmp_path, monkeypatch):
    """The pin narrows the pool before any ranking:
    the named session is adopted even while it is the
    loaded one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _seed(repo, "loaded-late", "2026-10-30T02:00:00+00:00")
    _seed(repo, "idle-early", "2026-10-30T01:00:00+00:00")
    _seed_run(repo, "run-1", "loaded-late")
    _seed_run(repo, "run-2", "loaded-late")
    stub = _auto_stub({"loaded-late", "idle-early"})
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, caller="lane", prefer_session="loaded-late")
    assert out["action"] == "adopted"
    assert out["record"]["session"] == "loaded-late"


def test_a_pin_on_a_window_short_session_refuses_by_name(repo, tmp_path, monkeypatch):
    """A pin the window floor cannot honour refuses
    pin-unavailable naming the window — never a silent
    retarget to another session."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _seed(repo, "short", "2026-10-29T18:30:00+00:00")
    _seed(repo, "long", "2026-10-30T02:00:00+00:00")
    stub = _auto_stub({"short", "long"})
    out = lease.acquire(stub, repo, "cpu", now_dt=NOW, caller="lane", prefer_session="short", min_window_s=3600)
    assert out["action"] == "pin-unavailable"
    assert "window" in out["reason"]
    assert lease.load_record(repo, "short") is not None
