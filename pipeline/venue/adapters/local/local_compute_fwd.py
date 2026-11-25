#!/usr/bin/env python3
"""Local TCP forwarder: localhost:2222 -> tailnet target via runtime proxy :3130 CONNECT."""
import os, sys, socket, urllib.parse, base64, threading, select

TARGET = (sys.argv[1] if len(sys.argv) > 1 else "100.64.0.9", int(sys.argv[2]) if len(sys.argv) > 2 else 22)
u = urllib.parse.urlparse(os.environ["HTTPS_PROXY"])
AUTH = base64.b64encode(f"{u.username}:{u.password}".encode()).decode()

def pipe(a, b):
    try:
        while True:
            r, _, _ = select.select([a], [], [], 60)
            if not r: break
            data = a.recv(65536)
            if not data: break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass

def handle(client):
    # The proxy port selects the route: 3130 is the Tailscale
    # tunnel (the general egress port refuses tailnet targets).
    remote = socket.create_connection((u.hostname, 3130), timeout=30)
    remote.sendall(f"CONNECT {TARGET[0]}:{TARGET[1]} HTTP/1.1\r\nHost: {TARGET[0]}:{TARGET[1]}\r\nProxy-Authorization: Basic {AUTH}\r\n\r\n".encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = remote.recv(4096)
        if not chunk: raise ConnectionError("proxy closed during CONNECT")
        resp += chunk
    head, _, leftover = resp.partition(b"\r\n\r\n")
    if b" 200 " not in head.split(b"\r\n")[0]:
        print("CONNECT failed:", resp[:200], flush=True); client.close(); remote.close(); return
    # Bytes past the header terminator are already tunneled stream
    # (the sshd banner's first bytes, coalesced into the proxy's
    # response chunk). They belong to the client: dropping them
    # corrupts the banner and the client dies in banner/kex
    # exchange, intermittently under load. Forward them first.
    if leftover:
        client.sendall(leftover)
    print("tunnel up", TARGET, flush=True)
    threading.Thread(target=pipe, args=(client, remote), daemon=True).start()
    pipe(remote, client)
    client.close(); remote.close()

srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 2222)); srv.listen(128)
print("listening 127.0.0.1:2222 ->", TARGET, flush=True)
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
