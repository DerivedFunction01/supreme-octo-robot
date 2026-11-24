"""Lease unit tests: nameless-assignment release — the
endpoint form of release-session, with the assignments
and stop seams stubbed at the sessions module (no
subprocess, no library). The production shape is the
rotated pair's: an endpoint-keyed census row
whose prior name may or may not hold a record."""

import json
from datetime import timedelta

from unit_harness import NOW, lease, repo  # noqa: F401

EP = "m-hm-ase1a0-11yelhfhxjhw4"
OTHER_EP = "m-hm-ase1a0-99zzzzzzzzzzzz"
PRIOR = "solar-falcon-70-r1794736255"
ASSIGNMENT = {"endpoint": EP, "shape_class": "high_ram", "variant": "DEFAULT", "accelerator": "NONE"}

sessions_mod = getattr(lease.sessions, "sessions", lease.sessions)


class StopWorld:
    """The stop seam, stubbed: records its calls and returns
    the planted verdict."""

    def __init__(self, verdict="unassigned-fallback"):
        self.verdict = verdict
        self.calls = []

    def stop(self, colab, endpoint):
        self.calls.append(endpoint)
        return self.verdict


def wire(monkeypatch, assignments, world):
    monkeypatch.setattr(sessions_mod, "assignments_list", lambda: assignments)
    monkeypatch.setattr(sessions_mod, "stop_endpoint_safe", world.stop)


def plant_stamp(repo, session=PRIOR, endpoint=EP):
    host = f"8080-{endpoint}-b.us-east4.prod.r.colab.dev"
    stamp = {"host": host, "endpoint": f"https://{host}", "boot_id": "boot-1", "session": session, "captured_at": "2026-10-29T10:00:00+00:00", "source": "reconcile"}
    (repo / "var" / f"identity-{session}.json").write_text(json.dumps(stamp))


def plant_census(repo, endpoints):
    rows = [{"session": None, "nameless": True, "prior_session": None, "endpoint": ep, "shape_class": "high_ram"} for ep in endpoints]
    (repo / "var" / "nameless-census.json").write_text(json.dumps({"written_at": NOW.isoformat(), "rows": rows}))


def census_endpoints(repo):
    return [row["endpoint"] for row in lease.load_nameless_census(repo)]


def test_endpoint_release_releases_and_clears_the_census_row(repo, monkeypatch):
    world = StopWorld()
    wire(monkeypatch, [ASSIGNMENT], world)
    plant_census(repo, [EP, OTHER_EP])
    out = lease.release_endpoint(None, repo, EP)
    assert out == {"action": "session-released", "endpoint": EP, "stop": "unassigned-fallback"}
    assert world.calls == [EP]
    assert census_endpoints(repo) == [OTHER_EP]


def test_endpoint_release_absent_assignment_refuses(repo, monkeypatch):
    world = StopWorld()
    wire(monkeypatch, [], world)
    out = lease.release_endpoint(None, repo, EP)
    assert out["action"] == "release-absent" and out["endpoint"] == EP
    assert world.calls == []


def test_endpoint_release_unreadable_assignments_is_unknown(repo, monkeypatch):
    world = StopWorld()
    wire(monkeypatch, None, world)
    out = lease.release_endpoint(None, repo, EP)
    assert out["action"] == "release-unknown"
    assert world.calls == []


def test_endpoint_release_prior_record_refuses(repo, monkeypatch):
    world = StopWorld()
    wire(monkeypatch, [ASSIGNMENT], world)
    plant_stamp(repo)
    lease.save_record(repo, {"session": PRIOR, "shape": "cpu-highram", "shape_spec": {"gpu": None, "tpu": None, "high_mem": True}, "rate_cu_per_hour": 0.26, "acquired_at": NOW.isoformat(), "deadline": (NOW + timedelta(hours=5)).isoformat(), "last_used_at": NOW.isoformat(), "jobs": []})
    out = lease.release_endpoint(None, repo, EP)
    assert out["action"] == "session-has-record" and out["session"] == PRIOR
    assert world.calls == []


def test_endpoint_release_stop_failure_keeps_the_census_row(repo, monkeypatch):
    world = StopWorld(verdict="stop-failed")
    wire(monkeypatch, [ASSIGNMENT], world)
    plant_census(repo, [EP])
    out = lease.release_endpoint(None, repo, EP)
    assert out["action"] == "session-stop-failed" and out["stop"] == "stop-failed"
    assert census_endpoints(repo) == [EP]
