"""S5 venue-keying unit tests (plan §7, §10.3, §4.15).

The extracted core's venue semantics, exercised against
scratch stores: records gain the venue key at write time and
never at read time; the funnel dispatch refuses an
unregistered venue; the served event split derives from the
record alone. No network, no session is dialed.
"""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_lease  # noqa: E402

lease = load_lease("lease_s5")


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


venue_events = _load("sync/venue_events.py", "venue_events_s5")
cli = _load("sync/cli.py", "venue_cli_s5")


def _scratch(tmp_path):
    repo = tmp_path / "venue"
    (repo / "var").mkdir(parents=True)
    (repo / "results" / "runs").mkdir(parents=True)
    return repo


def test_lease_save_stamps_venue_and_evidence(tmp_path):
    repo = _scratch(tmp_path)
    rec = {"session": "amber-otter-42", "shape": "cpu",
           "shape_spec": {"gpu": None, "tpu": None, "high_mem": True},
           "acquired_at": "2026-11-13T10:00:00+00:00",
           "deadline": "2026-11-13T22:00:00+00:00",
           "last_used_at": "2026-11-13T10:00:00+00:00", "jobs": []}
    lease.records.save_record(repo, rec)
    on_disk = json.loads((repo / "var" / "lease-amber-otter-42.json").read_text())
    assert on_disk["venue"] == "colab"
    evidence = json.loads((repo / "var" / "session-evidence-amber-otter-42.json").read_text())
    assert evidence["venue"] == "colab"


def test_no_read_time_venue_default(tmp_path):
    """A legacy record read back carries no venue: readers read
    records exactly as written (§10.3 — the stamp is the
    migration's act, never a reader's default)."""
    repo = _scratch(tmp_path)
    legacy = {"session": "legacy-lease-7", "shape": "cpu",
              "acquired_at": "2026-11-01T10:00:00+00:00",
              "deadline": "2026-11-01T22:00:00+00:00",
              "last_used_at": "2026-11-01T10:00:00+00:00", "jobs": []}
    (repo / "var" / "lease-legacy-lease-7.json").write_text(json.dumps(legacy))
    loaded = lease.records.load_record(repo, "legacy-lease-7")
    assert "venue" not in loaded




def test_funnel_dispatch_refuses_unregistered_venue():
    assert cli.venue_dispatch("colab")["catalog"] == "cli-help"
    try:
        cli.venue_dispatch("codespaces")
    except ValueError as exc:
        assert "unregistered venue" in str(exc)
    else:
        raise AssertionError("an unregistered venue must refuse, not fall back")


def test_funnel_dispatch_registers_local():
    entry = cli.venue_dispatch("local")
    assert entry["catalog"] == "config"
    assert entry["auth"] == "ssh-key"


def test_event_split_is_record_derived():
    out = venue_events.split_event(
        {"at": "2026-11-13T14:02:00+00:00", "kind": "run", "tone": "ok",
         "message": "run finished · smoke", "venue": "colab",
         "detail": {"session": "storm-compass-26", "caller": "panel"}})
    assert out["date_token"] == "Nov 13"
    assert out["time"] == "2:02 PM"
    assert out["headline"] == "run finished · smoke"
    assert out["entity"] == "storm-compass-26"
    assert out["meta"] == "panel"
    bare = venue_events.split_event(
        {"at": "2026-11-13T09:15:00+00:00", "kind": "lease", "tone": "warn",
         "message": "renewal due", "venue": "colab"})
    assert bare["meta"] is None and bare["entity"] is None
