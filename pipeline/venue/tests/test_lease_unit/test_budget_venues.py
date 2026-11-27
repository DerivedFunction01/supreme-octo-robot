"""Lease unit tests: the per-venue/account budget set (FU-2).

Budgets are per venue and per account, never one mass: the
served budget set spans every venue the config names, each
entry carrying its own figures and caps. A local machine
venue has NO budget at all — its entry carries a null budget
(honest absence), never zero or fabricated figures. These
tests pin the set's composition against the scratch fixture
repo (no subprocess, no live config).
"""

import json
from datetime import datetime, timedelta, timezone

from unit_harness import NOW, cp, lease, repo  # noqa: F401

USAGE = lambda *a, **k: cp("Current balance: 768.38 compute units")  # noqa: E731


def _config(repo):
    return json.loads((repo / "config" / "lease.json").read_text())


def _write_config(repo, cfg):
    (repo / "config" / "lease.json").write_text(json.dumps(cfg, sort_keys=True, separators=(",", ":")))


def _multi_venue(repo):
    cfg = _config(repo)
    cfg["accounts"] = {
        "colab": [
            {"id": "primary", "label": "Primary"},
            {"id": "backup", "label": "Backup", "token_file": "accounts/backup.token.json"},
        ],
        "ec2": [{"id": "primary", "label": "EC2 main"}],
        "local": [{"id": "primary", "label": "This machine"}],
    }
    cfg["budgets"] = {
        "colab": {"primary": {"daily": 15, "monthly": 150, "standing_daily": 4}, "backup": {"daily": 40}},
        "ec2": {"primary": {"daily": 20, "monthly": 200}},
    }
    _write_config(repo, cfg)
    return cfg


def test_configured_venues_union_in_config_order(repo):
    # The fixture config names the home venue in its budgets
    # block (the primary account's caps live there now).
    assert lease.accounts.configured_venues(_config(repo)) == ["colab"]
    # Pinned on an in-memory dict: the accounts block's venues
    # first, then venues named only in budgets; a venue named
    # twice appears once. (The fixture writes config files with
    # sorted keys, so document order there is alphabetical —
    # the semantics here are the dict's own order.)
    cfg = {
        "accounts": {"ec2": [{"id": "primary"}], "colab": [{"id": "primary"}]},
        "budgets": {"local": {}, "ec2": {"primary": {}}},
    }
    assert lease.accounts.configured_venues(cfg) == ["ec2", "colab", "local"]


def test_budgetless_venue_rule(repo):
    assert lease.accounts.venue_budgetless("local") is True
    assert lease.accounts.venue_budgetless("colab") is False
    assert lease.accounts.venue_budgetless("ec2") is False


def test_budgets_state_home_venue_only_by_default(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    entries = lease.budgets_state(USAGE, repo, now_dt=NOW)
    # No venues configured beyond the home venue: the set is
    # the home venue's accounts — one entry, the primary, with
    # the snapshot's own figures (fixture caps 15/150/4).
    assert [(e["venue"], e["account"]) for e in entries] == [("colab", "primary")]
    entry = entries[0]
    assert entry["label"] == "primary"
    assert entry["credential"] == "live"
    assert entry["budget"]["balance"] == 768.38
    assert entry["budget"]["caps"] == {"daily": 15, "monthly": 150, "standing_daily": 4}


def test_budgets_state_spans_venues_and_local_is_null(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    _multi_venue(repo)
    entries = lease.budgets_state(USAGE, repo, now_dt=NOW)
    assert [(e["venue"], e.get("account")) for e in entries] == [
        ("colab", "primary"), ("colab", "backup"), ("ec2", "primary"), ("local", None)]

    by_key = {(e["venue"], e.get("account")): e for e in entries}
    # Home venue accounts keep the snapshot treatment: the
    # primary dials, the backup's balance is honest absence,
    # and each carries its own caps.
    assert by_key[("colab", "primary")]["budget"]["balance"] == 768.38
    assert by_key[("colab", "primary")]["budget"]["caps"]["daily"] == 15
    assert by_key[("colab", "backup")]["budget"]["balance"] is None
    assert by_key[("colab", "backup")]["budget"]["caps"]["daily"] == 40
    # Another venue's entry: its config-resolved caps, with
    # null figures — this repo holds no dial and no journal
    # for a venue it does not run.
    ec2 = by_key[("ec2", "primary")]
    assert ec2["label"] == "EC2 main"
    assert ec2["credential"] is None
    assert ec2["budget"]["caps"] == {"daily": 20, "monthly": 200, "standing_daily": None}
    assert ec2["budget"]["balance"] is None
    assert ec2["budget"]["day_spent"] is None
    assert ec2["budget"]["month_spent"] is None
    # The local venue's entry is exactly the venue and a null
    # budget: no account, no figures, no caps, nothing
    # budget-shaped — and never a zero.
    assert by_key[("local", None)] == {"venue": "local", "budget": None}


def test_caps_for_reads_only_the_budgets_block(repo):
    # Caps are tied per (venue, account): flat config keys are
    # not consulted for any venue or account, not even the home
    # venue's primary — a config carrying only flat keys serves
    # no caps at all.
    flat_only = {"daily_cu_budget": 99, "monthly_cu_budget": 999, "standing": {"daily_cu_cap": 9}}
    assert lease.accounts.caps_for(flat_only, "colab", "primary") == {"daily": None, "monthly": None, "standing_daily": None}
    cfg = {**flat_only, "budgets": {"colab": {"primary": {"daily": 15}}}}
    assert lease.accounts.caps_for(cfg, "colab", "primary") == {"daily": 15, "monthly": None, "standing_daily": None}
    # One venue's caps never leak into another's.
    assert lease.accounts.caps_for(cfg, "ec2", "primary") == {"daily": None, "monthly": None, "standing_daily": None}


def test_budget_check_budgetless_venue_never_dials(repo):
    def forbidden(*a, **k):
        raise AssertionError("a budget-less venue's check must not dial")

    out = lease.budget_check(forbidden, repo, {}, {"id": "local"}, hours=1, venue="local")
    assert out["ok"] is True and out["budgetless"] is True and out["balance"] is None and out["projected"] is None


def test_set_budget_caps_primary_writes_the_budgets_block(repo):
    out = lease.set_budget_caps(repo, daily=25)
    assert out["action"] == "caps-updated"
    cfg = _config(repo)
    assert cfg["budgets"]["colab"]["primary"]["daily"] == 25
    assert "daily_cu_budget" not in cfg and "monthly_cu_budget" not in cfg
    assert lease.accounts.caps_for(cfg, "colab", "primary")["daily"] == 25


def test_local_catalog_shapes_come_from_config(repo):
    cfg = _config(repo)
    cfg["venue_shapes"] = {"local": [{"id": "local", "label": "Local machine", "cores": 16, "memory_gb": 24}]}
    _write_config(repo, cfg)
    entries = lease.catalog.catalog_shapes(repo, venue="local")
    assert entries["local"]["label"] == "Local machine"
    assert entries["local"]["cores"] == 16 and entries["local"]["memory_gb"] == 24
    assert entries["local"]["rate_cu_per_hour"] is None


def test_specs_serve_every_venue_with_its_own_stamp(repo):
    cfg = _config(repo)
    cfg["venue_shapes"] = {"local": [{"id": "local", "label": "Local machine", "cores": 16, "memory_gb": 24}]}
    _write_config(repo, cfg)
    served = lease.specs(repo)
    venues = {entry["id"]: entry["venue"] for entry in served}
    assert venues["local"] == "local"
    assert all(v == "colab" for sid, v in venues.items() if sid != "local")
    local_entry = next(e for e in served if e["id"] == "local")
    assert local_entry["label"] == "Local machine" and local_entry["rate_cu_per_hour"] is None


def _local_record(repo):
    from datetime import timedelta

    rec = {"session": "local-main", "venue": "local", "shape": "local", "caller": "alpha",
           "rate_cu_per_hour": None, "acquired_at": NOW.isoformat(),
           "deadline": (NOW + timedelta(hours=5)).isoformat(), "last_used_at": NOW.isoformat(), "jobs": []}
    lease.save_record(repo, rec)
    return rec


def test_local_record_status_is_unverified_never_dead(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    _local_record(repo)
    # The home venue's listing does not contain the local
    # session; that list must not classify the record at all.
    out = lease.status(USAGE, repo, "local-main", snapshot="some-colab-session")
    assert out["action"] == "recorded-unverified"
    assert out["record"]["venue"] == "local"


def test_local_record_survives_a_reap_pass(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    _local_record(repo)

    def stub(*a, **k):
        if a and a[0] == "sessions":
            return cp(json.dumps(["some-colab-session"]))
        if a and a[0] == "usage":
            return cp("Current balance: 768.38 compute units")
        return cp("")

    out = lease.reap(stub, repo, now_dt=NOW)
    entry = next(r for r in out["records"] if r["session"] == "local-main")
    assert entry["action"] == "kept-unknown"
    assert lease.load_record(repo, "local-main") is not None


def test_reap_pass_stamps_the_local_pulse(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    _local_record(repo)
    monkeypatch.setattr(lease.local_venue, "probe_for_record", lambda repo_, rec, now_dt=None: True)

    def stub(*a, **k):
        if a and a[0] == "sessions":
            return cp(json.dumps(["some-colab-session"]))
        if a and a[0] == "usage":
            return cp("Current balance: 768.38 compute units")
        return cp("")

    lease.reap(stub, repo, now_dt=NOW)
    rec = lease.load_record(repo, "local-main")
    assert rec["last_pulse_result"] == "ok"
    assert rec["last_pulse_at"] == NOW.isoformat()
    # A failed probe stamps its own verdict, never silence.
    # (The on-disk stamp is aged directly: save_record's pulse
    # merge would keep the newer pair over an older saver.)
    rec_path = var / "lease-local-main.json"
    disk = json.loads(rec_path.read_text())
    disk["last_pulse_at"] = (NOW - timedelta(hours=2)).isoformat()
    rec_path.write_text(json.dumps(disk))
    monkeypatch.setattr(lease.local_venue, "probe_for_record", lambda repo_, rec, now_dt=None: False)
    lease.reap(stub, repo, now_dt=NOW)
    assert lease.load_record(repo, "local-main")["last_pulse_result"] == "unreachable"


def test_acquire_local_registers_adopts_and_releases(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    cfg = _config(repo)
    cfg["venue_shapes"] = {"local": [{"id": "local", "label": "Local machine"}]}
    _write_config(repo, cfg)
    out = lease.acquire_local(repo, "local", caller="alpha", hours=2, now_dt=NOW)
    assert out["action"] == "created"
    rec = out["record"]
    assert rec["venue"] == "local" and rec["session"] == "local-main" and rec["rate_cu_per_hour"] is None
    # A second acquire inside the window adopts the registration.
    out2 = lease.acquire_local(repo, "local", caller="beta", hours=2, now_dt=NOW)
    assert out2["action"] == "adopted"
    # A shape the venue does not serve refuses.
    assert lease.acquire_local(repo, "cpu-highram", caller="alpha", now_dt=NOW)["action"] == "refused-shape"
    # Release ends the registration; the venue itself stays up.
    assert lease.release_local(repo, "local-main")["action"] == "released"
    assert lease.load_record(repo, "local-main") is None
    assert lease.release_local(repo, "local-main")["action"] == "no-lease"


def test_local_targets_bind_per_shape(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    cfg = _config(repo)
    cfg["venue_shapes"] = {"local": [
        {"id": "local-a", "label": "Machine A", "target": "machine-a"},
        {"id": "local-b", "label": "Machine B", "target": "machine-b"},
        {"id": "local-unbound", "label": "Unbound"},
    ]}
    cfg["venue_targets"] = {"local": {
        "machine-a": {"host": "a.invalid", "user": "agent", "session": "local-a"},
        "machine-b": {"host": "b.invalid", "user": "agent", "session": "local-b"},
    }}
    _write_config(repo, cfg)
    lv = lease.local_venue
    # Several targets and no binding named: never a guess.
    assert lv.venue_target(repo) is None
    assert set(lv.local_targets(repo)) == {"machine-a", "machine-b"}
    # Each shape resolves its own machine and session, and the
    # lease record carries the target for status and dispatch.
    out_a = lease.acquire_local(repo, "local-a", caller="alpha", now_dt=NOW)
    assert out_a["action"] == "created"
    assert out_a["record"]["target"] == "machine-a" and out_a["record"]["session"] == "local-a"
    out_b = lease.acquire_local(repo, "local-b", caller="alpha", now_dt=NOW)
    assert out_b["record"]["target"] == "machine-b" and out_b["record"]["session"] == "local-b"
    # A shape binding no machine refuses rather than guessing.
    assert lease.acquire_local(repo, "local-unbound", caller="alpha", now_dt=NOW)["action"] == "refused-target"
    # Per-target probe caches are separate files.
    assert lv._probe_cache_name("machine-a") != lv._probe_cache_name("machine-b")
    # The single-target form still resolves with no binding.
    cfg["venue_targets"] = {"local": {"host": "one.invalid", "user": "agent", "session": "local-main"}}
    _write_config(repo, cfg)
    assert lv.venue_target(repo)["host"] == "one.invalid"
    _shape, tid, target = lv.shape_target(repo, "local-a")
    assert tid == "local" and target["host"] == "one.invalid"


def test_state_budget_portion_carries_the_set(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    _multi_venue(repo)
    portion = lease.state_budget(USAGE, repo)
    # The legacy snapshot rides unchanged beside the set.
    assert portion["venue"] == "colab"
    assert portion["budget"]["caps"]["daily"] == 15
    assert [a["account"] for a in portion["budget"]["accounts"]] == ["primary", "backup"]
    assert [(e["venue"], e.get("account")) for e in portion["budgets"]] == [
        ("colab", "primary"), ("colab", "backup"), ("ec2", "primary"), ("local", None)]


def test_ensure_transport_starts_a_down_managed_target(repo, monkeypatch):
    lv = lease.local_venue
    target = {"host": "127.0.0.1", "port": 2222, "user": "agent", "start": ["/bin/true"]}
    answers = iter([False, True])
    monkeypatch.setattr(lv, "_port_answers", lambda t: next(answers))
    launched = []
    monkeypatch.setattr(lv, "_launch_start", lambda t: launched.append(t) or True)
    assert lv.ensure_transport(target) is True
    assert launched == [target]


def test_ensure_transport_never_launches_unmanaged_targets(repo, monkeypatch):
    lv = lease.local_venue

    def no_launch(*a, **k):
        raise AssertionError("an unmanaged target was launched at")

    monkeypatch.setattr(lv.subprocess, "Popen", no_launch)
    monkeypatch.setattr(lv, "_port_answers", lambda t: False)
    # No start command configured: reported down, never launched.
    assert lv.ensure_transport({"host": "127.0.0.1", "port": 2222, "user": "agent"}) is False
    # A start command on a non-loopback target is not the runner's to run.
    assert lv.ensure_transport({"host": "a.invalid", "user": "agent", "start": ["/bin/true"]}) is False
    # An unusable start value never reaches a launch either.
    assert lv._launch_start({}) is False
    assert lv._launch_start({"start": []}) is False
    assert lv._launch_start({"start": "/bin/true"}) is False
    # A target already answering is left alone.
    monkeypatch.setattr(lv, "_port_answers", lambda t: True)
    assert lv.ensure_transport({"host": "127.0.0.1", "port": 2222, "user": "agent", "start": ["/bin/true"]}) is True


def test_probe_restarts_a_managed_transport_and_reprobes(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(var))
    cfg = _config(repo)
    cfg["venue_targets"] = {"local": {"host": "127.0.0.1", "port": 2222, "user": "agent", "start": ["/bin/true"]}}
    _write_config(repo, cfg)
    lv = lease.local_venue
    probes = iter([False, True])
    monkeypatch.setattr(lv, "_ssh_probe", lambda repo_, target: next(probes))
    ensured = []
    monkeypatch.setattr(lv, "ensure_transport", lambda target: ensured.append(target) or True)
    assert lv.probe(repo, now_dt=NOW) is True
    assert len(ensured) == 1
