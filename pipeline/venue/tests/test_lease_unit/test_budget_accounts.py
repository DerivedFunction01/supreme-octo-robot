"""Lease unit tests: per-account budgets (venue rework).

Accounts carry the caps model: a venue's accounts are named
in config's `accounts` block and their caps live only in the
`budgets` block, keyed per (venue, account) — the legacy flat
cap keys are dropped, and an account with no budgets entry is
uncapped. These tests pin the resolution matrix, the addressed
caps write, the per-account spend split, the per-account
guard, and the served accounts portions, all against the
scratch fixture repo (no subprocess, no live config).
"""

import json
from datetime import datetime, timezone

from unit_harness import NOW, cp, lease, repo  # noqa: F401


def _config(repo):
    return json.loads((repo / "config" / "lease.json").read_text())


def _write_config(repo, cfg):
    (repo / "config" / "lease.json").write_text(json.dumps(cfg, sort_keys=True, separators=(",", ":")))


def _with_accounts(repo, budgets=None):
    cfg = _config(repo)
    cfg["accounts"] = {"colab": [
        {"id": "primary", "label": "Primary"},
        {"id": "backup", "label": "Backup", "token_file": "accounts/backup.token.json"},
    ]}
    if budgets is not None:
        # Merge per (venue, account): naming one account's caps
        # never wipes another account's entry.
        merged = dict(cfg.get("budgets") or {})
        for venue, accounts in budgets.items():
            merged[venue] = {**(merged.get(venue) or {}), **accounts}
        cfg["budgets"] = merged
    _write_config(repo, cfg)
    return cfg


def test_caps_resolution_matrix(repo):
    cfg = _config(repo)
    # The primary account resolves its budgets entry (fixture
    # caps: daily 15, monthly 150, standing 4).
    assert lease.accounts.caps_for(cfg, "colab", "primary") == {
        "daily": 15, "monthly": 150, "standing_daily": 4}
    # No accounts configured: one account, the primary.
    assert [a["id"] for a in lease.accounts.venue_accounts(cfg, "colab")] == ["primary"]
    assert lease.accounts.default_account(cfg, "colab") == "primary"

    cfg = _with_accounts(repo, budgets={"colab": {"backup": {"daily": 40}}})
    # An account's entry is its whole caps set: unlisted keys
    # stay uncapped — no account inherits another's caps.
    assert lease.accounts.caps_for(cfg, "colab", "backup") == {
        "daily": 40, "monthly": None, "standing_daily": None}
    # The primary account is untouched by another account's entry.
    assert lease.accounts.caps_for(cfg, "colab", "primary")["daily"] == 15
    # Replacing the primary entry replaces its whole set.
    cfg["budgets"]["colab"]["primary"] = {"monthly": 90}
    assert lease.accounts.caps_for(cfg, "colab", "primary") == {
        "daily": None, "monthly": 90, "standing_daily": None}
    # The compat projection serves the primary account's caps.
    assert lease.grants._served_caps(cfg)["monthly"] == 90


def test_set_budget_caps_default_target_writes_budgets_block(repo):
    out = lease.set_budget_caps(repo, daily=20)
    assert out["action"] == "caps-updated"
    assert out["account"] == "primary"
    assert out["caps"]["daily"] == 20
    assert out["previous"]["daily"] == 15
    cfg = _config(repo)
    assert cfg["budgets"]["colab"]["primary"]["daily"] == 20
    # The legacy flat keys are never written.
    assert "daily_cu_budget" not in cfg


def test_set_budget_caps_addressed_account_writes_budgets_block(repo):
    _with_accounts(repo)
    out = lease.set_budget_caps(repo, daily=40, monthly=None, account="backup")
    assert out["action"] == "caps-updated"
    assert out["account"] == "backup"
    assert out["caps"] == {"daily": 40, "monthly": None, "standing_daily": None}
    assert out["previous"] == {"daily": None, "monthly": None, "standing_daily": None}
    cfg = _config(repo)
    assert cfg["budgets"]["colab"]["backup"] == {"daily": 40, "monthly": None}
    # The primary account's entry is untouched.
    assert cfg["budgets"]["colab"]["primary"]["daily"] == 15
    # A second addressed write preserves the first entry's keys.
    out2 = lease.set_budget_caps(repo, standing_daily=5, account="backup")
    assert out2["caps"] == {"daily": 40, "monthly": None, "standing_daily": 5}
    # Validation applies to addressed writes identically.
    bad = lease.set_budget_caps(repo, daily=-1, account="backup")
    assert bad["action"] == "caps-invalid"


def test_attributed_spend_splits_by_account(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COLAB_RUNNER_VAR", str(var))
    now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    hours = (now - day_start).total_seconds() / 3600.0
    segs = [
        # Unstamped: predates accounts -> the primary account.
        {"caller": "a", "session": "s-old", "start": day_start.isoformat(), "end": now.isoformat(), "rate": 1.0 / hours},
        {"caller": "a", "session": "s-pri", "account": "primary", "start": day_start.isoformat(), "end": now.isoformat(), "rate": 2.0 / hours},
        {"caller": "b", "session": "s-bak", "account": "backup", "start": day_start.isoformat(), "end": now.isoformat(), "rate": 4.0 / hours},
    ]
    (var / "lease-spend-journal.jsonl").write_text("".join(json.dumps(s) + "\n" for s in segs))
    out = lease.attributed_spend(repo, now)
    assert out["day_spent"] == 7.0
    assert out["accounts"]["primary"]["day_spent"] == 3.0
    assert out["accounts"]["backup"]["day_spent"] == 4.0


def test_budget_check_prices_the_addressed_account(repo):
    cfg = _with_accounts(repo, budgets={"colab": {"backup": {"daily": 0.5}}})
    colab = lambda *a, **k: cp("Current balance: 768.38 compute units")  # noqa: E731
    shape = {"rate_cu_per_hour": 0.08}
    # A 1h window at 0.08 CU/h projects 0.08: fine for the
    # primary account (its budgets entry caps daily at 15)...
    out = lease.budget_check(colab, repo, cfg, shape, hours=1, now_dt=NOW)
    assert out["ok"] is True
    # ...and refused for the backup account, whose own daily
    # cap is 0.5 but whose committed sum is priced against it
    # once its spend + projection exceed it: an 8h window
    # projects 0.64 > 0.5.
    out = lease.budget_check(colab, repo, cfg, shape, hours=8, now_dt=NOW, account="backup")
    assert out["ok"] is False
    assert out["reason"] == "daily-budget"
    assert out["cap"] == 0.5
    # The same 8h window under the primary account's cap passes.
    out = lease.budget_check(colab, repo, cfg, shape, hours=8, now_dt=NOW, account="primary")
    assert out["ok"] is True


def test_record_save_stamps_account_and_segment_carries_it(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COLAB_RUNNER_VAR", str(var))
    _with_accounts(repo)
    rec = {
        "session": "acct-stamp", "shape": "cpu",
        "shape_spec": {"gpu": None, "tpu": None, "high_mem": False},
        "rate_cu_per_hour": 0.08,
        "acquired_at": "2026-10-29T17:00:00+00:00",
        "deadline": "2026-10-30T01:00:00+00:00", "jobs": [],
    }
    lease.save_record(repo, rec)
    assert rec["account"] == "primary"
    assert rec["venue"] == "colab"
    end = datetime(2026, 10, 29, 18, 0, tzinfo=timezone.utc)
    assert lease.append_spend_segment(repo, rec, end) is True
    line = json.loads((var / "lease-spend-journal.jsonl").read_text().strip())
    assert line["account"] == "primary"
    assert line["venue"] == "colab"


def test_snapshot_and_census_serve_accounts(repo, tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COLAB_RUNNER_VAR", str(var))
    _with_accounts(repo, budgets={"colab": {"backup": {"daily": 40}}})

    census = lease.accounts_state(repo, NOW)
    assert census["venue"] == "colab"
    by_id = {a["account"]: a for a in census["accounts"]}
    assert by_id["primary"]["credential"] == "live"
    assert by_id["primary"]["caps"]["daily"] == 15
    assert by_id["backup"]["credential"] == "not-brought-in"
    assert by_id["backup"]["caps"]["daily"] == 40

    # Placing the credential file is the brought-in fact; its
    # contents are never read by this layer.
    token = var / "accounts" / "backup.token.json"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text("{}")
    census = lease.accounts_state(repo, NOW)
    by_id = {a["account"]: a for a in census["accounts"]}
    assert by_id["backup"]["credential"] == "credential-present"

    snap = lease.budget_snapshot(lambda *a, **k: cp("Current balance: 768.38 compute units"), repo, now_dt=NOW)
    by_id = {a["account"]: a for a in snap["accounts"]}
    assert by_id["primary"]["balance"] == 768.38
    # A non-primary account's balance is honest absence until
    # the funnel can dial under its credential.
    assert by_id["backup"]["balance"] is None
    assert by_id["backup"]["caps"]["daily"] == 40
    # The top level still serves the primary account's figures.
    assert snap["caps"]["daily"] == 15
