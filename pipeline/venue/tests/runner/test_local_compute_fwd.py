"""Local forwarder credential agility (tunnel transport cure).

The defect class: the runtime proxy issues a fresh credential
per shell and issued credentials die at unpredictable times, so
a forwarder trusting one baked credential goes dark mid-service
while its process and port stay up; and a proxy response chunk
that coalesces the CONNECT headers with the first tunneled
bytes (the sshd banner) corrupts the banner if the leftover is
dropped. The specimens pin the forwarder's answers against a
scripted fake proxy: leftover bytes reach the caller, a refused
credential falls through to the next candidate inside the same
connection attempt, a refreshed pin is picked up with no module
reload, and all candidates dead closes cleanly (None), never a
half-open socket.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FWD = ROOT / "adapters" / "local" / "local_compute_fwd.py"

URL_A = "http://a:a@proxy.invalid"
URL_B = "http://b:b@proxy.invalid"
URL_C = "http://c:c@proxy.invalid"

OK = b"HTTP/1.1 200 OK\r\n\r\n"
REFUSED = b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n"


class FakeSocket:
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


def load_fwd(monkeypatch, tmp_path, launch_url, pin_url=None):
    pin = tmp_path / "pin.env"
    if pin_url is not None:
        pin.write_text(f"HTTPS_PROXY={pin_url}\n")
    monkeypatch.setattr(sys, "argv", ["local_compute_fwd.py", "10.0.0.9", "22", str(pin)])
    monkeypatch.setenv("HTTPS_PROXY", launch_url)
    spec = importlib.util.spec_from_file_location("local_compute_fwd_under_test", FWD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, pin


def script_proxy(monkeypatch, mod, sockets):
    queue = list(sockets)
    monkeypatch.setattr(mod.socket, "create_connection", lambda addr, timeout=0: queue.pop(0))


def test_leftover_bytes_past_connect_headers_reach_the_caller(monkeypatch, tmp_path):
    mod, _pin = load_fwd(monkeypatch, tmp_path, URL_A)
    script_proxy(monkeypatch, mod, [FakeSocket([OK + b"SSH-2.0-banner"])])
    sock, leftover = mod._try_connect(URL_A)
    assert leftover == b"SSH-2.0-banner"
    assert not sock.closed


def test_refused_credential_falls_through_to_the_pin(monkeypatch, tmp_path):
    mod, _pin = load_fwd(monkeypatch, tmp_path, URL_A, pin_url=URL_B)
    refused, good = FakeSocket([REFUSED]), FakeSocket([OK])
    script_proxy(monkeypatch, mod, [refused, good])
    sock, leftover = mod.connect_remote()
    assert sock is good
    assert refused.closed
    assert mod._last_good[0] == URL_B


def test_refreshed_pin_is_reread_without_reload(monkeypatch, tmp_path):
    mod, pin = load_fwd(monkeypatch, tmp_path, URL_A, pin_url=URL_B)
    script_proxy(monkeypatch, mod, [FakeSocket([REFUSED]), FakeSocket([REFUSED])])
    assert mod.connect_remote() is None
    pin.write_text(f"HTTPS_PROXY={URL_C}\n")
    good = FakeSocket([OK])
    script_proxy(monkeypatch, mod, [FakeSocket([REFUSED]), good])
    sock, _leftover = mod.connect_remote()
    assert sock is good
    assert mod._last_good[0] == URL_C


def test_all_candidates_dead_returns_none(monkeypatch, tmp_path):
    mod, _pin = load_fwd(monkeypatch, tmp_path, URL_A, pin_url=URL_B)
    script_proxy(monkeypatch, mod, [FakeSocket([REFUSED]), FakeSocket([REFUSED])])
    assert mod.connect_remote() is None


def test_pin_path_argv_wins_over_env(monkeypatch, tmp_path):
    other = tmp_path / "other.env"
    other.write_text(f"HTTPS_PROXY={URL_C}\n")
    monkeypatch.setenv("LOCAL_FWD_PIN", str(other))
    mod, pin = load_fwd(monkeypatch, tmp_path, URL_A, pin_url=URL_B)
    assert mod.PIN == pin
    assert mod._pin_url() == URL_B


# --- the declared argv surface (BT11) -------------------------------


def test_declaration_dummy_battery_matches(monkeypatch, tmp_path):
    mod, _pin = load_fwd(monkeypatch, tmp_path, URL_A)
    cases = mod._argv.dummy(mod.DECLARATION)
    assert cases and all(c["matched"] for c in cases)


def test_parse_only_launch_forms(monkeypatch, tmp_path):
    mod, _pin = load_fwd(monkeypatch, tmp_path, URL_A)
    full = mod._argv.parse_only(mod.DECLARATION, ["10.0.0.9", "22", "/pins/a.env", "2222"])
    assert full["ok"]
    assert full["result"]["positionals"] == {
        "target": "10.0.0.9",
        "port": "22",
        "pin": "/pins/a.env",
        "listen_port": "2222",
    }
    short = mod._argv.parse_only(mod.DECLARATION, ["10.0.0.9", "22", "/pins/a.env"])
    assert short["ok"]
    assert short["result"]["positionals"]["listen_port"] is None
    for bad in (
        [],
        ["10.0.0.9"],
        ["10.0.0.9", "22"],
        ["10.0.0.9", "22", "/pins/a.env", "2222", "extra"],
    ):
        out = mod._argv.parse_only(mod.DECLARATION, bad)
        assert not out["ok"] and out["exit_code"] == 2


def test_truncated_argv_is_a_loud_refusal(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["local_compute_fwd.py", "10.0.0.9"])
    monkeypatch.setenv("HTTPS_PROXY", URL_A)
    spec = importlib.util.spec_from_file_location("local_compute_fwd_truncated", FWD)
    mod = importlib.util.module_from_spec(spec)
    with pytest.raises(SystemExit) as caught:
        spec.loader.exec_module(mod)
    assert caught.value.code == 2


# --- the state surface -----------------------------------------------


def _state_path(pin):
    return Path(str(pin) + ".state.json")


def _read_state(pin):
    return json.loads(_state_path(pin).read_text())


def test_state_file_records_outcomes_per_source_without_credentials(monkeypatch, tmp_path):
    mod, pin = load_fwd(monkeypatch, tmp_path, URL_A, pin_url=URL_B)
    refused, good = FakeSocket([REFUSED]), FakeSocket([OK])
    script_proxy(monkeypatch, mod, [refused, good])
    sock, _leftover = mod.connect_remote()
    assert sock is good
    state = _read_state(pin)
    assert state["target"] == "10.0.0.9:22"
    assert state["started_at"]
    # last_good starts as the launch credential, so it owns
    # the first attempt; the pin owns the second.
    assert state["sources"]["last_good"]["last_outcome"] == "proxy-407"
    assert state["sources"]["last_good"]["attempts"] == 1
    assert state["sources"]["last_good"]["failures"] == 1
    assert state["sources"]["launch"]["attempts"] == 0
    assert state["sources"]["pin_file"]["last_outcome"] == "established"
    assert state["sources"]["pin_file"]["attempts"] == 1
    assert state["sources"]["pin_file"]["failures"] == 0
    assert state["last_outcome"] == "established"
    assert state["consecutive_failures"] == 0
    assert state["failing_since"] is None
    assert state["previous_instance"] is None
    raw = _state_path(pin).read_text()
    for secret in (URL_A, URL_B, "a:a", "b:b"):
        assert secret not in raw


def test_state_file_all_failing_opens_a_streak(monkeypatch, tmp_path):
    mod, pin = load_fwd(monkeypatch, tmp_path, URL_A, pin_url=URL_B)
    script_proxy(monkeypatch, mod, [FakeSocket([REFUSED]), FakeSocket([REFUSED])])
    assert mod.connect_remote() is None
    state = _read_state(pin)
    assert state["last_outcome"] == "failed"
    assert state["consecutive_failures"] == 1
    assert state["failing_since"] is not None
    script_proxy(monkeypatch, mod, [FakeSocket([REFUSED]), FakeSocket([REFUSED])])
    assert mod.connect_remote() is None
    state = _read_state(pin)
    assert state["consecutive_failures"] == 2
    # A later success closes the streak.
    script_proxy(monkeypatch, mod, [FakeSocket([OK])])
    assert mod.connect_remote() is not None
    state = _read_state(pin)
    assert state["last_outcome"] == "established"
    assert state["consecutive_failures"] == 0
    assert state["failing_since"] is None


def test_state_handover_preserves_the_previous_instance(monkeypatch, tmp_path):
    """An instance death reads as a started_at reset whose
    predecessor left clean outcomes: the successor's fresh
    state carries the predecessor's final summary, so the
    reset and its health are visible in one read."""
    mod, pin = load_fwd(monkeypatch, tmp_path, URL_A, pin_url=URL_B)
    script_proxy(monkeypatch, mod, [FakeSocket([REFUSED]), FakeSocket([OK])])
    assert mod.connect_remote() is not None
    before = _read_state(pin)
    # Stamp a fixed earlier start so the successor is
    # unambiguously a different instance.
    before["started_at"] = "2000-01-01T00:00:00+00:00"
    _state_path(pin).write_text(json.dumps(before))
    mod2, _pin2 = load_fwd(monkeypatch, tmp_path, URL_A, pin_url=URL_B)
    mod2._init_state()
    state = _read_state(pin)
    prev = state["previous_instance"]
    assert prev["previous_started_at"] == "2000-01-01T00:00:00+00:00"
    assert prev["last_outcome"] == "established"
    assert prev["attempts"] == 2
    assert prev["failures"] == 1
    assert state["started_at"] != "2000-01-01T00:00:00+00:00"
    assert state["sources"]["last_good"]["attempts"] == 0
    assert state["consecutive_failures"] == 0
