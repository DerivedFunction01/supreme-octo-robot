"""Local forwarder transport revival (tunnel transport cure).

The defect class: the runtime proxy's credentials are issued
per shell and die at unpredictable times, so a forwarder can
hold only dead credentials while its process and port stay
up — the old port-shaped ensure read that as healthy forever,
and dispatches reset at the SSH handshake. The specimens pin
the cure's bounds against fakes: the pin restocks from the
caller's own credential under the stocking rule (an empty
value never lands, a CONNECT-refused 407 value never lands,
an established value lands, and an inconclusive verification
lands because an unreachable proxy is not proof of death),
and ensure
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


def _tailnet_target(pin):
    target = _fwd_target(pin)
    target["fwd_dest"] = ["100.64.0.9", 22]
    return target


def test_refresh_writes_a_verified_candidate_and_keeps_other_lines(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"OTHER=1\nHTTPS_PROXY={STALE}\n")
    monkeypatch.setattr(lv, "_connect_verdict", lambda url, dest: "established" if url == CAND else "refused")
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

    def no_verdict(url, dest):
        raise AssertionError("an empty candidate was verified")

    monkeypatch.setattr(lv, "_connect_verdict", no_verdict)
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": ""}) is False
    assert lv.refresh_pin(_fwd_target(pin), env={}) is False
    assert pin.read_text() == f"HTTPS_PROXY={STALE}\n"


def test_refresh_never_overwrites_with_a_refused_candidate(repo, tmp_path, monkeypatch):
    """A 407 is a definite dead credential: never stocked,
    however fresh the shell that carries it."""
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"HTTPS_PROXY={STALE}\n")
    monkeypatch.setattr(lv, "_connect_verdict", lambda url, dest: "refused")
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": CAND}) is False
    assert pin.read_text() == f"HTTPS_PROXY={STALE}\n"


def test_refresh_stocks_an_inconclusive_candidate(repo, tmp_path, monkeypatch):
    """A network error is not proof of death: when the
    verification cannot conclude, the caller's own fresh
    credential is stocked rather than stranding the pin on
    an older value the rotation may already have killed."""
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"HTTPS_PROXY={STALE}\n")
    monkeypatch.setattr(lv, "_connect_verdict", lambda url, dest: "inconclusive")
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": CAND}) is True
    assert pin.read_text() == f"HTTPS_PROXY={CAND}\n"


def test_refresh_transforms_a_tailnet_candidate_to_the_route_port(repo, tmp_path, monkeypatch):
    """A tailnet target offered the caller's verbatim
    general-egress value stocks the tailnet route port: the
    credential is the caller's, the port is the route's, and
    the verdict judges the transformed value."""
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"HTTPS_PROXY={STALE}\n")
    offered = "http://new:new@proxy.invalid:3128"
    routed = "http://new:new@proxy.invalid:3130"
    seen = []
    monkeypatch.setattr(lv, "_connect_verdict", lambda url, dest: seen.append(url) or "established")
    assert lv.refresh_pin(_tailnet_target(pin), env={"HTTPS_PROXY": offered}) is True
    assert seen == [routed]
    assert pin.read_text() == f"HTTPS_PROXY={routed}\n"


def test_refresh_stocks_a_public_route_candidate_verbatim(repo, tmp_path, monkeypatch):
    """A non-tailnet destination has no route transform: the
    caller's value, port included, stocks as offered."""
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"HTTPS_PROXY={STALE}\n")
    offered = "http://new:new@proxy.invalid:3128"
    monkeypatch.setattr(lv, "_connect_verdict", lambda url, dest: "established")
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": offered}) is True
    assert pin.read_text() == f"HTTPS_PROXY={offered}\n"


def test_refresh_noops_when_the_pin_already_holds_the_candidate(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    pin = tmp_path / "pin.env"
    pin.write_text(f"HTTPS_PROXY={CAND}\n")

    def no_verdict(url, dest):
        raise AssertionError("a stocked pin was re-verified")

    monkeypatch.setattr(lv, "_connect_verdict", no_verdict)
    assert lv.refresh_pin(_fwd_target(pin), env={"HTTPS_PROXY": CAND}) is True


class _FakeSock:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.sent = b""
        self.closed = False

    def sendall(self, data):
        self.sent += data

    def recv(self, _n):
        return self._chunks.pop(0) if self._chunks else b""

    def close(self):
        self.closed = True


def _script_proxy(monkeypatch, lv, chunks):
    monkeypatch.setattr(lv.socket, "create_connection", lambda addr, timeout=0: _FakeSock(chunks))


def test_connect_verdict_classifies_the_proxy_answers(repo, monkeypatch):
    lv = lease.local_venue
    dest = ("10.0.0.9", 22)
    _script_proxy(monkeypatch, lv, [b"HTTP/1.1 200 OK\r\n\r\n"])
    assert lv._connect_verdict(CAND, dest) == "established"
    assert lv._connect_verifies(CAND, dest) is True
    _script_proxy(monkeypatch, lv, [b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n"])
    assert lv._connect_verdict(CAND, dest) == "refused"
    assert lv._connect_verifies(CAND, dest) is False
    _script_proxy(monkeypatch, lv, [b"HTTP/1.1 502 Bad Gateway\r\n\r\n"])
    assert lv._connect_verdict(CAND, dest) == "inconclusive"
    _script_proxy(monkeypatch, lv, [])
    assert lv._connect_verdict(CAND, dest) == "inconclusive"


def test_connect_verdict_network_error_and_credentialless_are_inconclusive(repo, monkeypatch):
    lv = lease.local_venue
    dest = ("10.0.0.9", 22)

    def dead(addr, timeout=0):
        raise OSError("proxy unreachable")

    monkeypatch.setattr(lv.socket, "create_connection", dead)
    assert lv._connect_verdict(CAND, dest) == "inconclusive"

    def no_dial(addr, timeout=0):
        raise AssertionError("a credentialless value was dialed")

    monkeypatch.setattr(lv.socket, "create_connection", no_dial)
    assert lv._connect_verdict("http://proxy.invalid", dest) == "inconclusive"
    assert lv._connect_verdict("", dest) == "inconclusive"


def test_refresh_is_inert_without_forwarder_fields(repo, tmp_path):
    lv = lease.local_venue
    target = {"host": "127.0.0.1", "port": 2222, "user": "agent"}
    assert lv.refresh_pin(target, env={"HTTPS_PROXY": CAND}) is False


def test_listen_inodes_picks_only_the_listen_entry_on_the_port(repo):
    lv = lease.local_venue
    text = (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:08AE 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000   0 424242 1 0000000000000000 100 0 0 10 0\n"
        "   1: 0100007F:08AE 00000000:0000 01 00000000:00000000 00:00000000 00000000  1000   0 515151 1 0000000000000000 100 0 0 10 0\n"
        "   2: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000   0 636363 1 0000000000000000 100 0 0 10 0\n"
    )
    assert lv._listen_inodes(2222, text) == {"424242"}


def test_kill_forwarders_terms_only_the_marked_listener(repo, monkeypatch):
    lv = lease.local_venue
    target = {"host": "127.0.0.1", "port": 2222, "user": "agent"}
    killed = []
    monkeypatch.setattr(lv, "_listener_pid", lambda t: 777)
    monkeypatch.setattr(lv.os, "kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(lv, "_proc_cmdline", lambda pid: b"python3 local_compute_fwd.py 10.0.0.9 22")
    assert lv._kill_forwarders(target) == 1
    assert killed == [777]
    # A listener that is not the forwarder is never killed.
    monkeypatch.setattr(lv, "_proc_cmdline", lambda pid: b"sshd: listener")
    assert lv._kill_forwarders(target) == 0
    # No listener at all: nothing to kill.
    monkeypatch.setattr(lv, "_listener_pid", lambda t: None)
    monkeypatch.setattr(lv, "_proc_cmdline", lambda pid: b"python3 local_compute_fwd.py 10.0.0.9 22")
    assert lv._kill_forwarders(target) == 0
    assert killed == [777]


def test_ensure_revives_a_stale_forwarder(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    target = _fwd_target(tmp_path / "pin.env")
    monkeypatch.setattr(lv, "refresh_pin", lambda t, env=None: True)
    monkeypatch.setattr(lv, "_port_answers", lambda t: True)
    banners = iter([False, False, True])
    monkeypatch.setattr(lv, "_tunnel_banner_ok", lambda t: next(banners))
    killed, launched = [], []
    monkeypatch.setattr(lv, "_kill_forwarders", lambda t: killed.append(t) or 1)
    monkeypatch.setattr(lv, "_launch_start", lambda t: launched.append(t) or True)
    assert lv.ensure_transport(target) is True
    assert killed == [target]
    assert launched == [target]


def test_ensure_leaves_a_healthy_forwarder_alone(repo, tmp_path, monkeypatch):
    lv = lease.local_venue
    target = _fwd_target(tmp_path / "pin.env")
    monkeypatch.setattr(lv, "refresh_pin", lambda t, env=None: True)
    monkeypatch.setattr(lv, "_port_answers", lambda t: True)
    monkeypatch.setattr(lv, "_tunnel_banner_ok", lambda t: True)

    def no_kill(t):
        raise AssertionError("a healthy forwarder was killed")

    def no_launch(t):
        raise AssertionError("a healthy forwarder was relaunched")

    monkeypatch.setattr(lv, "_kill_forwarders", no_kill)
    monkeypatch.setattr(lv, "_launch_start", no_launch)
    assert lv.ensure_transport(target) is True
