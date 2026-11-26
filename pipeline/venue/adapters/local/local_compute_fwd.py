#!/usr/bin/env python3
"""Local TCP forwarder: localhost:2222 -> tailnet target via runtime proxy :3130 CONNECT.

Credential agility: the runtime proxy issues a fresh HTTPS_PROXY
credential per agent shell, issued credentials have variable
lifetimes, and a copied pin may be dead on arrival. So no single
baked credential is trusted: each CONNECT tries, in order, the
last credential that worked, the launch credential, and the
current pin file (re-read on every attempt — the runner's
refresh keeps it stocked with a CONNECT-verified credential).
A refreshed pin therefore takes effect on the next failed
CONNECT, with no forwarder restart and no lost connection: the
failover happens inside the connection that discovers the
death. Only credential hashes (12 hex) are ever logged.

The argv is a declared surface on the unified argument
contract (pipeline/platform/argv.py), in the lease config's
`start` argv order: target, port, pin file, listen port.
Target, port, and pin are required — a truncated or surplus
argv is a loud usage refusal (exit 2), never a silent
fallback to a default target, port, or pin. The listen port
alone keeps its documented default, 2222 — one forwarder per
target, so a second tunneled machine is a second instance on
its own port, never a code change.

State surface: the forwarder keeps a small JSON record beside
the pin file (`<pin>.state.json`) — per-credential-source and
overall CONNECT outcomes with counts and timestamps, nothing
else. The liveness checker reads it: a credential rotation
window reads as every source failing under one `started_at`,
an instance death as a `started_at` reset whose predecessor
left clean outcomes (the predecessor's final summary is
carried into the new state as `previous_instance`). Source
names and outcomes only: no credential value or fragment
ever lands in the state file.
"""
import base64
import hashlib
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


def _load_platform_argv():
    """The unified argument parser (pipeline/platform/argv.py),
    loaded by path: this file is launched standalone by the
    lease config's start argv, with no package context."""
    path = Path(__file__).resolve().parents[3] / "platform" / "argv.py"
    spec = importlib.util.spec_from_file_location("platform_argv", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_argv = _load_platform_argv()

# The declared surface (token BT11): the launch contract is
# the lease config's start argv — target, port, pin, listen
# port, in this order, with the same values when fully given.
DECLARATION = {
    "name": "local_compute_fwd",
    "summary": "Local TCP forwarder: a localhost listen port tunnelled to a tailnet target via the runtime proxy CONNECT.",
    "positionals": [
        {"name": "target", "required": True, "help": "tailnet host the CONNECT must reach"},
        {"name": "port", "required": True, "help": "port on the target"},
        {"name": "pin", "required": True, "help": "pin file, re-read on every CONNECT"},
        {"name": "listen_port", "help": "localhost listen port (default 2222)"},
    ],
}


def _usage_exit(message: str) -> SystemExit:
    print(f"local_compute_fwd: {message}", file=sys.stderr)
    print(_argv.help_text(DECLARATION), file=sys.stderr, end="")
    return SystemExit(_argv.USAGE_EXIT)


def _parse_argv(argv):
    """((target host, target port), pin path, listen port)
    from the declared surface. A refusal is a loud usage
    exit, never a fallback."""
    try:
        result = _argv.parse(DECLARATION, argv)
    except _argv.UsageError as exc:
        raise _usage_exit(str(exc)) from exc
    if "help" in result:
        print(result["help"], end="")
        raise SystemExit(0)
    pos = result["positionals"]
    try:
        port = int(pos["port"])
        listen = int(pos["listen_port"]) if pos["listen_port"] else 2222
    except ValueError:
        raise _usage_exit("port and listen_port must be integers") from None
    return (pos["target"], port), Path(pos["pin"]), listen


TARGET, PIN, _LAUNCH_LISTEN_PORT = _parse_argv(sys.argv[1:])
LAUNCH_URL = os.environ.get("HTTPS_PROXY", "")

_lock = threading.Lock()
_last_good = [LAUNCH_URL]

# --- state surface -------------------------------------------------
# Written atomically (stage + rename), throttled to one write
# per _STATE_WRITE_MIN_S unless an outcome changed. Every
# write is best-effort: a state failure is swallowed, because
# visibility must never break forwarding.
_STATE_PATH = Path(str(PIN) + ".state.json")
_STATE_WRITE_MIN_S = 5
_SOURCE_NAMES = ("last_good", "launch", "pin_file")
_STARTED_AT = datetime.now(timezone.utc).isoformat()
_LISTEN_PORT = [None]
_state_lock = threading.RLock()
_sources_state = {
    name: {"last_outcome": None, "last_at": None, "attempts": 0, "failures": 0}
    for name in _SOURCE_NAMES
}
_overall_state = {
    "last_outcome": None,
    "last_at": None,
    "consecutive_failures": 0,
    "failing_since": None,
}
_previous_instance = [None]
_state_sig = [None]
_state_written_at = [0.0]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_snapshot() -> dict:
    return {
        "target": f"{TARGET[0]}:{TARGET[1]}",
        "listen_port": _LISTEN_PORT[0],
        "started_at": _STARTED_AT,
        "sources": {name: dict(_sources_state[name]) for name in _SOURCE_NAMES},
        "last_outcome": _overall_state["last_outcome"],
        "last_at": _overall_state["last_at"],
        "consecutive_failures": _overall_state["consecutive_failures"],
        "failing_since": _overall_state["failing_since"],
        "previous_instance": _previous_instance[0],
    }


def _write_state(force: bool = False) -> None:
    try:
        with _state_lock:
            snap = _state_snapshot()
            # The signature carries the failure streak: a
            # failing window writes on every attempt (the
            # streak is the diagnostic payload), while a
            # steady established streak throttles.
            sig = (
                snap["last_outcome"],
                snap["consecutive_failures"],
                tuple(snap["sources"][n]["last_outcome"] for n in _SOURCE_NAMES),
            )
            now = time.monotonic()
            if (
                not force
                and sig == _state_sig[0]
                and now - _state_written_at[0] < _STATE_WRITE_MIN_S
            ):
                return
            tmp = Path(str(_STATE_PATH) + ".tmp")
            tmp.write_text(json.dumps(snap, indent=1))
            os.replace(tmp, _STATE_PATH)
            _state_sig[0] = sig
            _state_written_at[0] = now
    except Exception:
        pass


def _previous_summary(state: dict) -> dict:
    """A previous instance's final summary, in the shape the
    new state carries as `previous_instance`: its start, its
    last overall outcome, and its attempt/failure totals
    summed over its credential sources."""
    attempts = failures = 0
    sources = state.get("sources")
    if isinstance(sources, dict):
        for entry in sources.values():
            if isinstance(entry, dict):
                attempts += int(entry.get("attempts") or 0)
                failures += int(entry.get("failures") or 0)
    return {
        "previous_started_at": state.get("started_at"),
        "last_outcome": state.get("last_outcome"),
        "attempts": attempts,
        "failures": failures,
    }


def _init_state() -> None:
    """Startup: when the state file on disk belongs to an
    earlier instance (a different started_at), preserve its
    final summary as `previous_instance` before this
    instance's state overwrites it — the reset and the
    predecessor's health stay visible in one read."""
    try:
        prior = json.loads(_STATE_PATH.read_text())
    except (OSError, ValueError):
        prior = None
    if (
        isinstance(prior, dict)
        and prior.get("started_at")
        and prior.get("started_at") != _STARTED_AT
    ):
        _previous_instance[0] = _previous_summary(prior)
    _write_state(force=True)


def _record_attempt(source: str, outcome: str) -> None:
    with _state_lock:
        entry = _sources_state[source]
        entry["attempts"] += 1
        if outcome != "established":
            entry["failures"] += 1
        entry["last_outcome"] = outcome
        entry["last_at"] = _now_iso()
    _write_state()


def _record_overall(established: bool) -> None:
    with _state_lock:
        _overall_state["last_at"] = _now_iso()
        if established:
            _overall_state["last_outcome"] = "established"
            _overall_state["consecutive_failures"] = 0
            _overall_state["failing_since"] = None
        else:
            _overall_state["last_outcome"] = "failed"
            _overall_state["consecutive_failures"] += 1
            if _overall_state["failing_since"] is None:
                _overall_state["failing_since"] = _overall_state["last_at"]
    _write_state()


def _cred(url):
    u = urllib.parse.urlparse(url or "")
    if not u.username:
        return None
    return f"{u.username}:{u.password}"


def _tag(url):
    c = _cred(url)
    return hashlib.sha256(c.encode()).hexdigest()[:12] if c else "none"


def _pin_url():
    try:
        with open(PIN) as f:
            for line in f:
                line = line.strip()
                if line.startswith("HTTPS_PROXY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _candidate_sources():
    """(source name, url) per candidate credential, in the
    order attempts are made: the last credential that worked,
    the launch credential, the current pin file — deduped by
    credential, the first source owning it."""
    seen, out = set(), []
    for name, url in (
        ("last_good", _last_good[0]),
        ("launch", LAUNCH_URL),
        ("pin_file", _pin_url()),
    ):
        c = _cred(url)
        if c and c not in seen:
            seen.add(c)
            out.append((name, url))
    return out


def _candidates():
    return [url for _name, url in _candidate_sources()]


def _attempt(url):
    """One CONNECT attempt: ((socket, leftover), "established")
    on a 200, else (None, outcome) with outcome the attempt's
    class — "proxy-407" when the proxy rejected the credential
    itself, "connect-error" for everything else (no dial, a
    short read, a foreign refusal). Leftover bytes past the
    header terminator are already tunneled stream (the sshd
    banner's first bytes) and belong to the client."""
    u = urllib.parse.urlparse(url)
    cred = _cred(url)
    try:
        remote = socket.create_connection((u.hostname, 3130), timeout=30)
    except OSError as exc:
        print(f"CONNECT error for cred [{_tag(url)}]: {exc}", flush=True)
        return None, "connect-error"
    try:
        auth = base64.b64encode(cred.encode()).decode()
        remote.sendall(
            f"CONNECT {TARGET[0]}:{TARGET[1]} HTTP/1.1\r\nHost: {TARGET[0]}:{TARGET[1]}\r\n"
            f"Proxy-Authorization: Basic {auth}\r\n\r\n".encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = remote.recv(4096)
            if not chunk:
                remote.close()
                return None, "connect-error"
            resp += chunk
    except OSError as exc:
        print(f"CONNECT error for cred [{_tag(url)}]: {exc}", flush=True)
        remote.close()
        return None, "connect-error"
    head, _, leftover = resp.partition(b"\r\n\r\n")
    status = head.split(b"\r\n")[0]
    if b" 200 " not in status:
        print(f"CONNECT refused for cred [{_tag(url)}]:", head[:120], flush=True)
        remote.close()
        outcome = "proxy-407" if b" 407 " in status or status.endswith(b" 407") else "connect-error"
        return None, outcome
    return (remote, leftover), "established"


def _try_connect(url):
    """One CONNECT attempt. Returns (socket, leftover) on a 200,
    else None."""
    got, _outcome = _attempt(url)
    return got


def connect_remote():
    for name, url in _candidate_sources():
        got, outcome = _attempt(url)
        _record_attempt(name, outcome)
        if got is not None:
            with _lock:
                if _last_good[0] != url:
                    print(f"credential failover -> [{_tag(url)}]", flush=True)
                    _last_good[0] = url
            _record_overall(True)
            return got
    _record_overall(False)
    return None


def pipe(a, b):
    try:
        while True:
            import select

            r, _, _ = select.select([a], [], [], 60)
            if not r:
                break
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client):
    got = connect_remote()
    if got is None:
        print("CONNECT failed on all credentials", flush=True)
        client.close()
        return
    remote, leftover = got
    print("tunnel up", TARGET, flush=True)
    if leftover:
        client.sendall(leftover)
    threading.Thread(target=pipe, args=(client, remote), daemon=True).start()
    pipe(remote, client)
    client.close()
    remote.close()


def main():
    listen_port = _LAUNCH_LISTEN_PORT
    _LISTEN_PORT[0] = listen_port
    _init_state()
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", listen_port))
    srv.listen(128)
    print(f"listening 127.0.0.1:{listen_port} ->", TARGET, flush=True)
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
