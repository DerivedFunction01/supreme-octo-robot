"""Lease unit tests: nameless-assignment adoption — the
endpoint form of adopt, with the assignments/bind seams
stubbed at the sessions module (no subprocess, no library).
The production shapes are the rotated pair: an
endpoint whose listing line wears "?", an identity stamp and
a renewal config surviving under its prior name."""

import json
from datetime import timedelta

from unit_harness import HELP_TEXT, NOW, cp, lease, plant_kit_config, repo  # noqa: F401

EP = "m-hm-ase1a0-11yelhfhxjhw4"
PRIOR = "solar-falcon-70-r1794736255"
ASSIGNMENT = {"endpoint": EP, "shape_class": "high_ram", "variant": "DEFAULT", "accelerator": "NONE"}

sessions_mod = getattr(lease.sessions, "sessions", lease.sessions)


class NamelessWorld:
    """A stateful stub colab: the assignment stands throughout;
    the listing shows the endpoint wearing "?" (or under
    `named`, a usable name) until the bind lands, then the
    minted name. `verify` False models a bind the library
    confirms but the listing never shows — the clobber class
    the verification re-read exists to catch."""

    def __init__(self, named=None, verify=True):
        self.bound_name = None
        self.named = named
        self.verify = verify
        self.bind_calls = []

    def colab(self, *a, **k):
        if a and a[0] == "usage":
            return cp("balance: 500 CU (stub)")
        if a and a[0] == "sessions":
            if self.bound_name and self.verify:
                return cp(f"[{self.bound_name}] {EP} High-RAM\n")
            if self.named:
                return cp(f"[{self.named}] {EP} High-RAM\n")
            return cp(f"[?] {EP} High-RAM\n")
        if a and a[0] == "new":
            return cp(HELP_TEXT)
        return cp("")

    def bind(self, name, endpoint):
        self.bind_calls.append((name, endpoint))
        self.bound_name = name
        return True


def plant_stamp(repo, session=PRIOR, endpoint=EP, captured_at="2026-10-29T10:00:00+00:00"):
    host = f"8080-{endpoint}-b.us-east4.prod.r.colab.dev"
    stamp = {"host": host, "endpoint": f"https://{host}", "boot_id": "boot-1", "session": session, "captured_at": captured_at, "source": "reconcile"}
    (repo / "var" / f"identity-{session}.json").write_text(json.dumps(stamp))


def wire(monkeypatch, world, assignments):
    monkeypatch.setattr(sessions_mod, "assignments_list", lambda: assignments)
    monkeypatch.setattr(sessions_mod, "bind_name_to_endpoint", world.bind)


def test_nameless_adoption_restores_prior_evidence_under_minted_name(repo, monkeypatch):
    world = NamelessWorld()
    wire(monkeypatch, world, [ASSIGNMENT])
    plant_stamp(repo)
    plant_kit_config(repo, PRIOR, deadline=NOW + timedelta(hours=5), acquired_at=NOW - timedelta(hours=2))
    out = lease.adopt_nameless(world.colab, repo, EP, caller="beta", now_dt=NOW)
    assert out["action"] == "adopted"
    minted = world.bound_name
    assert minted and minted != PRIOR
    assert world.bind_calls == [(minted, EP)]
    rec = out["record"]
    assert rec["session"] == minted
    assert rec["deadline"] == (NOW + timedelta(hours=5)).isoformat()
    assert rec["acquired_at"] == (NOW - timedelta(hours=2)).isoformat()
    assert rec["deadline_source"] == "renewal-config"
    assert rec["shape"] == "cpu-highram"
    assert rec["adopted_nameless"] == {"endpoint": EP, "prior_session": PRIOR}
    assert out["adopted_nameless"] == {"endpoint": EP, "prior_session": PRIOR, "session": minted}
    assert lease.load_record(repo, minted) is not None
    assert lease.load_record(repo, PRIOR) is None


def test_nameless_adoption_absent_assignment_refuses(repo, monkeypatch):
    world = NamelessWorld()
    wire(monkeypatch, world, [])
    out = lease.adopt_nameless(world.colab, repo, EP, now_dt=NOW)
    assert out["action"] == "adopt-absent" and out["endpoint"] == EP
    assert world.bind_calls == []


def test_nameless_adoption_unreadable_assignments_is_unknown(repo, monkeypatch):
    world = NamelessWorld()
    wire(monkeypatch, world, None)
    out = lease.adopt_nameless(world.colab, repo, EP, now_dt=NOW)
    assert out["action"] == "adopt-unknown"
    assert world.bind_calls == []


def test_nameless_adoption_named_endpoint_defers_to_named_path(repo, monkeypatch):
    world = NamelessWorld(named="other-name-7")
    wire(monkeypatch, world, [ASSIGNMENT])
    out = lease.adopt_nameless(world.colab, repo, EP, now_dt=NOW)
    assert out["action"] == "adopt-nameless-named" and out["session"] == "other-name-7"
    assert world.bind_calls == []


def test_nameless_adoption_prior_record_refuses(repo, monkeypatch):
    world = NamelessWorld()
    wire(monkeypatch, world, [ASSIGNMENT])
    plant_stamp(repo)
    lease.save_record(repo, {"session": PRIOR, "shape": "cpu-highram", "shape_spec": {"gpu": None, "tpu": None, "high_mem": True}, "rate_cu_per_hour": 0.26, "acquired_at": NOW.isoformat(), "deadline": (NOW + timedelta(hours=5)).isoformat(), "last_used_at": NOW.isoformat(), "jobs": []})
    out = lease.adopt_nameless(world.colab, repo, EP, now_dt=NOW)
    assert out["action"] == "adopt-has-record" and out["session"] == PRIOR
    assert world.bind_calls == []


def test_nameless_adoption_bind_failure_plants_nothing(repo, monkeypatch):
    world = NamelessWorld()
    wire(monkeypatch, world, [ASSIGNMENT])
    monkeypatch.setattr(sessions_mod, "bind_name_to_endpoint", lambda name, endpoint: False)
    out = lease.adopt_nameless(world.colab, repo, EP, hours=4, now_dt=NOW)
    assert out["action"] == "adopt-bind-failed"
    assert lease.all_records(repo) == []


def test_nameless_adoption_unverified_bind_plants_nothing(repo, monkeypatch):
    world = NamelessWorld(verify=False)
    wire(monkeypatch, world, [ASSIGNMENT])
    out = lease.adopt_nameless(world.colab, repo, EP, hours=4, now_dt=NOW)
    assert out["action"] == "adopt-bind-failed"
    assert lease.all_records(repo) == []


def test_nameless_adoption_no_evidence_needs_a_planted_deadline(repo, monkeypatch):
    world = NamelessWorld()
    wire(monkeypatch, world, [ASSIGNMENT])
    out = lease.adopt_nameless(world.colab, repo, EP, shape="cpu-highram", now_dt=NOW)
    assert out["action"] == "adopt-no-deadline"
    assert lease.all_records(repo) == []


def test_nameless_adoption_no_evidence_with_hours_adopts(repo, monkeypatch):
    world = NamelessWorld()
    wire(monkeypatch, world, [ASSIGNMENT])
    out = lease.adopt_nameless(world.colab, repo, EP, hours=6, shape="cpu-highram", caller="alpha", now_dt=NOW)
    assert out["action"] == "adopted"
    rec = out["record"]
    assert rec["session"] == world.bound_name
    assert rec["deadline"] == (NOW + timedelta(hours=6)).isoformat()
    assert rec["deadline_source"] == "hours"
    assert rec["adopted_nameless"] == {"endpoint": EP, "prior_session": None}
    assert rec["caller"] == "alpha"


def test_nameless_census_rows_the_unaccounted_endpoint(repo):
    plant_stamp(repo)
    plant_kit_config(repo, PRIOR, deadline=NOW + timedelta(hours=5), acquired_at=NOW - timedelta(hours=2))
    live = [{"session": "?", "endpoint": EP, "shape_class": "high_ram"}]
    rows = lease.nameless_census(repo, [ASSIGNMENT], live, set())
    assert len(rows) == 1
    row = rows[0]
    assert row["session"] is None and row["nameless"] is True
    assert row["endpoint"] == EP and row["prior_session"] == PRIOR
    assert row["derived_deadline"] == (NOW + timedelta(hours=5)).isoformat()
    assert row["shape"] == "cpu-highram" and row["rate_cu_per_hour"] == 0.26


def test_nameless_census_skips_accounted_endpoints(repo):
    plant_stamp(repo)
    live = [{"session": "named-orphan-1", "endpoint": EP, "shape_class": "high_ram"}]
    # A usable name carries the endpoint: the named orphan row owns it.
    assert lease.nameless_census(repo, [ASSIGNMENT], live, set()) == []
    # A record whose stamp names the endpoint accounts for it too.
    lease.save_record(repo, {"session": PRIOR, "shape": "cpu-highram", "shape_spec": {"gpu": None, "tpu": None, "high_mem": True}, "rate_cu_per_hour": 0.26, "acquired_at": NOW.isoformat(), "deadline": (NOW + timedelta(hours=5)).isoformat(), "last_used_at": NOW.isoformat(), "jobs": []})
    assert lease.nameless_census(repo, [ASSIGNMENT], [], {PRIOR}) == []


def test_detect_nameless_stores_rows_and_reports_once(repo, monkeypatch):
    plant_stamp(repo)
    live = [{"session": "?", "endpoint": EP, "shape_class": "high_ram"}]
    monkeypatch.setattr(sessions_mod, "assignments_list", lambda timeout=120: [ASSIGNMENT])
    out = lease.detect_nameless(repo, live, NOW)
    assert out["detected"] == [EP]
    stored = lease.load_nameless_census(repo)
    assert len(stored) == 1 and stored[0]["prior_session"] == PRIOR
    out = lease.detect_nameless(repo, live, NOW)
    assert out["detected"] == [] and out["cleared"] == []
    monkeypatch.setattr(sessions_mod, "assignments_list", lambda timeout=120: [])
    out = lease.detect_nameless(repo, live, NOW)
    assert out["cleared"] == [EP]
    assert lease.load_nameless_census(repo) == []
    monkeypatch.setattr(sessions_mod, "assignments_list", lambda timeout=120: None)
    out = lease.detect_nameless(repo, live, NOW)
    assert out["unreadable"] is True


def test_state_orphans_merges_stored_nameless_rows(repo):
    from unit_harness import orphan_stub

    plant_stamp(repo)
    row = {"session": None, "nameless": True, "prior_session": PRIOR, "endpoint": EP, "shape_class": "high_ram", "shape": "cpu-highram", "derived_deadline": (NOW + timedelta(hours=5)).isoformat(), "deadline_source": "renewal-config", "conflicts": [], "jobs_in_flight": 0}
    (repo / "var" / "nameless-census.json").write_text(json.dumps({"written_at": NOW.isoformat(), "rows": [row]}))
    census = lease.state_orphans(orphan_stub([]), repo, now_dt=NOW)
    nameless = [o for o in census["orphans"] if o.get("nameless")]
    assert len(nameless) == 1 and nameless[0]["endpoint"] == EP
    assert nameless[0]["deadline_past"] is False
    # A record claiming the endpoint (its stamp names it) retires the row.
    lease.save_record(repo, {"session": "minted-name-1", "shape": "cpu-highram", "shape_spec": {"gpu": None, "tpu": None, "high_mem": True}, "rate_cu_per_hour": 0.26, "acquired_at": NOW.isoformat(), "deadline": (NOW + timedelta(hours=5)).isoformat(), "last_used_at": NOW.isoformat(), "jobs": []})
    plant_stamp(repo, session="minted-name-1")
    census = lease.state_orphans(orphan_stub([]), repo, now_dt=NOW)
    assert [o for o in census["orphans"] if o.get("nameless")] == []


def test_prior_names_for_endpoint_reads_stamps_freshest_first(repo):
    plant_stamp(repo, session="older-name-1", captured_at="2026-10-28T10:00:00+00:00")
    plant_stamp(repo, session=PRIOR, captured_at="2026-10-29T10:00:00+00:00")
    plant_stamp(repo, session="other-ep-1", endpoint="m-hm-use4b0-zzzz", captured_at="2026-10-29T11:00:00+00:00")
    (repo / "var" / "identity-torn-1.json").write_text("{not json")
    assert sessions_mod.prior_names_for_endpoint(repo, EP) == [PRIOR, "older-name-1"]
    assert sessions_mod.prior_names_for_endpoint(repo, "m-hm-absent-0") == []
