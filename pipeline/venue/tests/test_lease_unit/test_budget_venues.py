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
from datetime import datetime, timezone

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
        "colab": {"backup": {"daily": 40}},
        "ec2": {"primary": {"daily": 20, "monthly": 200}},
    }
    _write_config(repo, cfg)
    return cfg


def test_configured_venues_union_in_config_order(repo):
    assert lease.accounts.configured_venues(_config(repo)) == []
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
    monkeypatch.setenv("COLAB_RUNNER_VAR", str(var))
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
    monkeypatch.setenv("COLAB_RUNNER_VAR", str(var))
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


def test_state_budget_portion_carries_the_set(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COLAB_RUNNER_VAR", str(var))
    _multi_venue(repo)
    portion = lease.state_budget(USAGE, repo)
    # The legacy snapshot rides unchanged beside the set.
    assert portion["venue"] == "colab"
    assert portion["budget"]["caps"]["daily"] == 15
    assert [a["account"] for a in portion["budget"]["accounts"]] == ["primary", "backup"]
    assert [(e["venue"], e.get("account")) for e in portion["budgets"]] == [
        ("colab", "primary"), ("colab", "backup"), ("ec2", "primary"), ("local", None)]
