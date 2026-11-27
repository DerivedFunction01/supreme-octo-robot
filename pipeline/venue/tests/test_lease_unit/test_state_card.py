"""Lease card contract tests: the served lease card
(state/card.py) — the shape both frontends render,
pinned against the panel's own client derivations
for one representative record, and the capability
set's three refusal classes (venue, grant-managed,
unserved), pure and through the state build."""

import sys

from unit_harness import NOW, lease, make_extend_stub, repo, seed_record  # noqa: F401

_card_mod = sys.modules["lease.state.card"]


def _spec(**over):
    spec = {
        "id": "cpu-highram",
        "venue": "colab",
        "label": "CPU High-RAM",
        "gpu": None,
        "tpu": None,
        "high_mem": True,
        "rate_cu_per_hour": 0.26,
        "agent_startable": True,
    }
    spec.update(over)
    return spec


def _entry(**record_over):
    record = {
        "session": "cozy-shore-06-r1234",
        "shape": "cpu-highram",
        "shape_spec": {"gpu": None, "tpu": None, "high_mem": True},
        "rate_cu_per_hour": 0.26,
        "caller": "alpha",
        "account": "primary",
        "acquired_at": "2026-10-29T17:00:00+00:00",
        "deadline": "2026-10-30T01:00:00+00:00",
        "last_used_at": "2026-10-29T17:30:00+00:00",
        "jobs": [],
        "budget_at_acquire": {"projected": 2.08},
        "last_pulse_result": "ok",
    }
    record.update(record_over)
    return {
        "action": "active",
        "record": record,
        "caller": "alpha",
        "sync_claim": None,
        "keepalive_heartbeat_age_s": 42.4,
    }


def test_card_matches_the_panel_derivation_for_a_colab_lease():
    """The pin Step 2 retires the client code against:
    every label below is the value the panel's
    projections.ts derives for this same record —
    displayName (liveSessionName), venueLabel,
    shapeLabel, state/stateLabel/stateTone,
    endsLabel and remainingLabel (fmtTime in
    America/New_York + fmtRemaining), reservedCu,
    and the diagnostics labels — computed by hand
    from those functions for the fixed clock."""
    card = _card_mod.lease_card(
        _entry(), _card_mod.spec_index([_spec()]),
        grant_active_now=False, now_dt=NOW)
    assert card == {
        "session": "cozy-shore-06-r1234",
        "display_name": "Cozy Shore 06",
        "venue": "colab",
        "venue_label": "Colab",
        "target": None,
        "shape": "cpu-highram",
        "shape_label": "CPU High-RAM",
        "shape_descriptor": "CPU · High-RAM",
        "caller": "alpha",
        "account": "primary",
        "state": "running",
        "state_label": "Running",
        "state_tone": "ok",
        "action": "active",
        "standing": False,
        "acquired_at": "2026-10-29T17:00:00+00:00",
        "deadline": "2026-10-30T01:00:00+00:00",
        "deadline_label": "9:00 PM",
        "ends_label": "ends 9:00 PM",
        "expired": False,
        "remaining_ms": 7 * 3600 * 1000,
        "remaining_label": "9:00 PM · 7 h 00 min left",
        "rate_cu_per_hour": 0.26,
        "rate_label": "0.26 CU/h",
        "reserved_cu": 2.08,
        "envelope_id": None,
        "diagnostics": {
            "heartbeat_label": "42s ago",
            "pulse_label": "ok",
            "burn_label": "0.26 CU/h",
            "sync_claim": None,
        },
        "capabilities": {
            "extend": {"applicable": True, "reason": None},
            "shorten": {"applicable": True, "reason": None},
            "release": {"applicable": True, "reason": None},
            "adopt": {"applicable": True, "reason": None},
            "exec": {"applicable": False, "reason": "unserved"},
        },
    }


def test_card_for_a_local_lease_disables_adopt_by_venue():
    entry = _entry(
        session="local-hp", venue="local", target="hp-envy",
        shape="local-hp", rate_cu_per_hour=None,
        caller="workhorse", budget_at_acquire=None,
        last_pulse_result=None)
    entry["keepalive_heartbeat_age_s"] = None
    card = _card_mod.lease_card(
        entry,
        _card_mod.spec_index([_spec(
            id="local-hp", venue="local", label="Local HP",
            high_mem=False, rate_cu_per_hour=None)]),
        grant_active_now=False, now_dt=NOW)
    assert card["venue"] == "local"
    assert card["venue_label"] == "Local"
    assert card["target"] == "hp-envy"
    assert card["display_name"] == "Local Hp"
    assert card["rate_label"] == "Cost unconfirmed"
    assert card["diagnostics"] is None
    caps = card["capabilities"]
    assert caps["adopt"] == {"applicable": False, "reason": "venue"}
    assert caps["extend"] == {"applicable": True, "reason": None}
    assert caps["shorten"] == {"applicable": True, "reason": None}
    assert caps["release"] == {"applicable": True, "reason": None}


def test_card_for_a_grant_managed_lease_disables_extend_and_shorten():
    record = {"standing": True}
    caps = _card_mod.lease_capabilities(record, grant_active_now=True)
    assert caps["extend"] == {
        "applicable": False, "reason": "grant-managed"}
    assert caps["shorten"] == {
        "applicable": False, "reason": "grant-managed"}
    # The core's rule is the conjunction: the standing
    # stamp alone, with no active grant, refuses
    # nothing — and neither does an active grant over
    # an ordinary lease.
    caps = _card_mod.lease_capabilities(record, grant_active_now=False)
    assert caps["extend"]["applicable"] is True
    assert caps["shorten"]["applicable"] is True
    caps = _card_mod.lease_capabilities({}, grant_active_now=True)
    assert caps["extend"]["applicable"] is True
    assert caps["shorten"]["applicable"] is True


def _portion_entry(repo, stub, session):
    portion = lease.state_records(stub, repo)
    return next(
        e for e in portion["records"]
        if e["session"] == session)


def test_state_build_serves_the_card_for_a_colab_lease(repo):
    seed_record(repo)
    entry = _portion_entry(repo, make_extend_stub(["standard"]), "standard")
    card = entry["card"]
    assert card["session"] == "standard"
    assert card["shape"] == "cpu"
    assert card["venue"] == "colab"
    assert card["capabilities"]["adopt"] == {
        "applicable": True, "reason": None}
    assert card["capabilities"]["extend"]["applicable"] is True
    # The added shape leaves the entry's own fields be.
    assert entry["record"]["session"] == "standard"
    assert "card" not in entry["record"]


def test_state_build_serves_the_card_for_a_local_lease(repo):
    lease.save_record(repo, {
        "session": "local-hp",
        "venue": "local",
        "target": "hp-envy",
        "shape": "local-hp",
        "shape_spec": {"gpu": None, "tpu": None, "high_mem": False},
        "rate_cu_per_hour": None,
        "caller": "workhorse",
        "account": "primary",
        "acquired_at": "2026-10-29T08:46:55+00:00",
        "deadline": "2026-11-05T00:00:00+00:00",
        "last_used_at": "2026-10-29T08:46:55+00:00",
        "jobs": [],
    })
    entry = _portion_entry(repo, make_extend_stub([]), "local-hp")
    card = entry["card"]
    assert card["venue"] == "local"
    assert card["venue_label"] == "Local"
    assert card["target"] == "hp-envy"
    assert card["capabilities"]["adopt"] == {
        "applicable": False, "reason": "venue"}
    assert card["capabilities"]["extend"] == {
        "applicable": True, "reason": None}
    assert card["capabilities"]["shorten"] == {
        "applicable": True, "reason": None}


def test_state_build_serves_grant_managed_capabilities(repo):
    lease.save_record(repo, {
        "session": "warm-pool-01",
        "shape": "cpu",
        "shape_spec": {"gpu": None, "tpu": None, "high_mem": False},
        "rate_cu_per_hour": 0.08,
        "caller": "standing",
        "standing": True,
        "acquired_at": "2026-10-29T17:00:00+00:00",
        "deadline": "2027-01-01T00:00:00+00:00",
        "last_used_at": "2026-10-29T17:30:00+00:00",
        "jobs": [],
    })
    lease.write_grant(repo, 3)
    entry = _portion_entry(
        repo, make_extend_stub(["warm-pool-01"]), "warm-pool-01")
    card = entry["card"]
    assert card["standing"] is True
    assert card["capabilities"]["extend"] == {
        "applicable": False, "reason": "grant-managed"}
    assert card["capabilities"]["shorten"] == {
        "applicable": False, "reason": "grant-managed"}
    assert card["capabilities"]["adopt"] == {
        "applicable": True, "reason": None}
