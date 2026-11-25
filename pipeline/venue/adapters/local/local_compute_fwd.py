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

The pin file's path comes from argv[3] when given, else the
LOCAL_FWD_PIN env var, else a `.local-fwd.env` file in the
user's home directory; the deployment's lease config names the
real path in its `start` argv.
"""
import base64
import hashlib
import os
import socket
import sys
import threading
import urllib.parse
from pathlib import Path

TARGET = (sys.argv[1] if len(sys.argv) > 1 else "100.64.0.9", int(sys.argv[2]) if len(sys.argv) > 2 else 22)


def _pin_path() -> Path:
    if len(sys.argv) > 3 and sys.argv[3]:
        return Path(sys.argv[3])
    env = os.environ.get("LOCAL_FWD_PIN", "")
    if env:
        return Path(env)
    return Path.home() / ".local-fwd.env"


PIN = _pin_path()
LAUNCH_URL = os.environ.get("HTTPS_PROXY", "")

_lock = threading.Lock()
_last_good = [LAUNCH_URL]


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


def _candidates():
    seen, out = set(), []
    for url in (_last_good[0], LAUNCH_URL, _pin_url()):
        c = _cred(url)
        if c and c not in seen:
            seen.add(c)
            out.append(url)
    return out


def _try_connect(url):
    """One CONNECT attempt. Returns (socket, leftover) on a 200,
    else None. Leftover bytes past the header terminator are
    already tunneled stream (the sshd banner's first bytes) and
    belong to the client."""
    u = urllib.parse.urlparse(url)
    cred = _cred(url)
    remote = socket.create_connection((u.hostname, 3130), timeout=30)
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
            return None
        resp += chunk
    head, _, leftover = resp.partition(b"\r\n\r\n")
    if b" 200 " not in head.split(b"\r\n")[0]:
        print(f"CONNECT refused for cred [{_tag(url)}]:", head[:120], flush=True)
        remote.close()
        return None
    return remote, leftover


def connect_remote():
    for url in _candidates():
        try:
            got = _try_connect(url)
        except OSError as exc:
            print(f"CONNECT error for cred [{_tag(url)}]: {exc}", flush=True)
            got = None
        if got is not None:
            with _lock:
                if _last_good[0] != url:
                    print(f"credential failover -> [{_tag(url)}]", flush=True)
                    _last_good[0] = url
            return got
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
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 2222))
    srv.listen(128)
    print("listening 127.0.0.1:2222 ->", TARGET, flush=True)
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
