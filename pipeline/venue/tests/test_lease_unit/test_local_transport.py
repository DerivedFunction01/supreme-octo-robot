"""Local forwarder transport revival (tunnel transport cure).

The defect class: the runtime proxy's credentials are issued
per shell and die at unpredictable times, so a forwarder can
hold only dead credentials while its process and port stay
up — the old port-shaped ensure read that as healthy forever,
and dispatches reset at the SSH handshake. The specimens pin
the cure's bounds against fakes: the pin restocks only from
the caller's own CONNECT-verified credential (an empty or
unverified value never overwrites a live pin), and ensure
treats port-up/banner-down as a stale forwarder — refresh
first, kill and relaunch only when the banner still does not
read — while a target without forwarder fields keeps the
plain port-shaped behaviour the older specimens pin.
"""

import os
import stat

from unit_harness import lease, repo  # noqa: F401

CAND = "http://new:new@proxy.invalid"
STALE = "http://old:old@proxy.invalid"


def _fwd_target(pin):
    return {
        "host": "127.0.0.1",
        "port": 2222,
        "user": "agent",
        "start": ["/bin/true"],
        "fwd_pin": str(pin),
        "fwd_dest": ["10.0.0.9", 22],
    }


def test_refresh_writes_a_verified_candidate_and_keeps_other_lines(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"OTHER=1\nHTTPS_PROXY={STALE}\n")
    monkeypatch.setattr(lv, "_connect_verifies", lambda url, dest: url == CAND)
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": CAND}) is True
    text = pin.read_text()
    assert f"HTTPS_PROXY={CAND}" in text
    assert "OTHER=1" in text
    assert STALE not in text
    assert stat.S_IMODE(os.stat(pin).st_mode) == 0o600


def test_refresh_never_overwrites_with_an_empty_value(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"HTTPS_PROXY={STALE}\n")
    monkeypatch.setattr(lv, "_connect_verifies", lambda url, dest: True)
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": ""}) is False
    assert lv.refresh_pin(_fwd_target(pin), env={}) is False
    assert pin.read_text() == f"HTTPS_PROXY={STALE}\n"


def test_refresh_never_overwrites_with_an_unverified_value(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"HTTPS_PROXY={STALE}\n")
    monkeypatch.setattr(lv, "_connect_verifies", lambda url, dest: False)
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": CAND}) is False
    assert pin.read_text() == f"HTTPS_PROXY={STALE}\n"


def test_refresh_noops_when_the_pin_already_holds_the_candidate(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"HTTPS_PROXY={CAND}\n")

    def no_verify(url, dest):
        raise AssertionError("a stocked pin was re-verified")

    monkeypatch.setattr(lv, "_connect_verifies", no_verify)
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": CAND}) is True


def test_refresh_is_inert_without_forwarder_fields(repo, tmp_path):
    lv = lease.local_venue
    target = {"host": "127.0.0.1", "port": 2222, "user": "agent"}
    assert lv.refresh_pin(target, env={"HTTPS_PROXY": CAND}) is False


def test_ensure_revives_a_stale_forwarder(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    target = _fwd_target(tmp_path / "pin.env")
    monkeypatch.setattr(lv, "refresh_pin", lambda t, env=None: True)
    monkeypatch.setattr(lv, "_port_answers", lambda t: True)
    banners = iter([False, False, True])
    monkeypatch.setattr(lv, "_tunnel_banner_ok", lambda t: next(banners))
    killed, launched = [], []
    monkeypatch.setattr(lv, "_kill_forwarders", lambda: killed.append(1) or 1)
    monkeypatch.setattr(lv, "_launch_start", lambda t: launched.append(t) or True)
    assert lv.ensure_transport(target) is True
    assert killed == [1]
    assert launched == [target]


def test_ensure_leaves_a_healthy_forwarder_alone(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    target = _fwd_target(tmp_path / "pin.env")
    monkeypatch.setattr(lv, "refresh_pin", lambda t, env=None: True)
    monkeypatch.setattr(lv, "_port_answers", lambda t: True)
    monkeypatch.setattr(lv, "_tunnel_banner_ok", lambda t: True)

    def no_kill():
        raise AssertionError("a healthy forwarder was killed")

    def no_launch(t):
        raise AssertionError("a healthy forwarder was relaunched")

    monkeypatch.setattr(lv, "_kill_forwarders", no_kill)
    monkeypatch.setattr(lv, "_launch_start", no_launch)
    assert lv.ensure_transport(target) is True
