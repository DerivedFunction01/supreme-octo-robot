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
import sys
from pathlib import Path

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
