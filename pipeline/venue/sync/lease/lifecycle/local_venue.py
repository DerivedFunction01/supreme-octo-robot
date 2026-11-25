"""The local venue's lease lifecycle (multi-venue plan, step 6).

The local venue is the operator's own machine: one workspace
container, always the same session, reached over SSH. Its
lease semantics are the generic ones, minus everything that
exists only because Colab meters and expires:

- No budget: the venue kind is budget-less (accounts.NO_BUDGET_
  VENUES) — acquire never prices, and budget_check's budget-less
  short-circuit is the same rule seen from the other side.
- No session creation: the container is the venue; acquire
  registers (or adopts) the caller's lease record against it.
- No keepalive, no renewal, no session gate: the record's
  window is the caller's reservation, and liveness is an SSH
  probe of the container, cached like every other dial.

The SSH targets are instance config, never tracked code:
config/lease.json's `venue_targets.local` is either one target
({"host", "port"?, "user", "identity_file"?, "session"?}) or a
map of target id -> target, one per local machine. A shape in
`venue_shapes.local` binds its machine with a `target` field;
lease and run records carry the target id, so every later
machine is an untracked config entry, never a code change.
Absent a target the venue still registers records; its
liveness serves as unverified (honest absence) until a target
is configured.

A target reached through a local transport (a loopback
forwarder, a tunnel process) names the command that brings
that transport up in its `start` field (an argv list). The
runner keeps its own transports up the way the home venue's
machinery relaunches a session's keepalive: when the target's
port does not answer, the probe and the dispatch path run the
start command once and check again — no external service,
watchdog, or operator step owns the transport's lifecycle.
Adding a machine is its target entry (its own port and start
command) plus its shape binding, never a code change.

A forwarder target whose credential can expire mid-service
(the runtime proxy issues a fresh credential per shell, with
a variable lifetime) declares it in two more fields: `fwd_pin`
(the pin file the forwarder re-reads on every CONNECT) and
`fwd_dest` ([host, port] the CONNECT must reach). For such a
target, revival is tunnel-shaped, not port-shaped: a port
that answers with no SSH banner behind it is a forwarder
holding a dead credential — it is killed and relaunched —
and every healthy ensure restocks the pin from the calling
process's own credential, but only with a value that has
just CONNECT-verified against `fwd_dest`: an empty or
unverified value never overwrites a live pin.
"""

import base64
import os
import re
import socket
import subprocess
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..core import catalog, foundation, records

VENUE = "local"
DEFAULT_SESSION = "local-main"
_PROBE_CACHE = "local-probe.json"


def _is_target(obj) -> bool:
    return isinstance(obj, dict) and bool(obj.get("host")) and bool(obj.get("user"))


def local_targets(repo: Path) -> dict:
    """Every configured local target, by id: the venue_targets
    block's local entry as a single target (id "local") or as a
    map of target id -> target, one entry per machine."""
    cfg = foundation.load_config(repo)
    targets = cfg.get("venue_targets")
    block = targets.get(VENUE) if isinstance(targets, dict) else None
    if _is_target(block):
        return {VENUE: block}
    if isinstance(block, dict):
        return {tid: t for tid, t in block.items() if isinstance(tid, str) and tid and _is_target(t)}
    return {}


def venue_target(repo: Path, target_id: str | None = None) -> dict | None:
    """One local target by id; with no id, the venue's only
    target — None when several are configured and the caller
    named none (an ambiguous target is never guessed)."""
    targets = local_targets(repo)
    if target_id is not None:
        return targets.get(target_id)
    if len(targets) == 1:
        return next(iter(targets.values()))
    return targets.get(VENUE)


def resolve_target(repo: Path, shape: dict | None = None, target_id: str | None = None):
    """(target id, target) for a dispatch: an explicit id wins,
    then the shape's `target` binding, then the venue's only
    target. Either element is None when unresolved."""
    targets = local_targets(repo)
    tid = target_id or (shape.get("target") if isinstance(shape, dict) else None)
    if isinstance(tid, str) and tid in targets:
        return tid, targets[tid]
    if len(targets) == 1:
        only = next(iter(targets))
        return only, targets[only]
    if VENUE in targets:
        return VENUE, targets[VENUE]
    return None, None


def shape_target(repo: Path, shape_id: str):
    """(shape, target id, target) for one catalog shape id:
    the shape entry plus the target it binds."""
    try:
        shape = catalog.catalog_shapes(repo, venue=VENUE).get(shape_id)
    except ValueError:
        shape = None
    if shape is None:
        return None, None, None
    tid, target = resolve_target(repo, shape)
    return shape, tid, target


def ssh_args(repo: Path, target: dict) -> list[str]:
    """The ssh argv for the venue target: key-only, batch mode
    (a prompt is a failure, never a hang), bounded connect."""
    args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "StrictHostKeyChecking=accept-new"]
    if target.get("port"):
        args += ["-p", str(target["port"])]
    if target.get("identity_file"):
        args += ["-i", str(target["identity_file"])]
    args.append(f"{target['user']}@{target['host']}")
    return args


def _probe_cache_name(target_id: str | None) -> str:
    if not target_id or target_id == VENUE:
        return _PROBE_CACHE
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in target_id)
    return f"local-probe-{safe}.json"


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_START_WAIT_S = 20


def _port_answers(target: dict) -> bool:
    """Whether the target's SSH port accepts a TCP connection
    (a bare connect — reachability of the transport, not an
    SSH handshake)."""
    try:
        with socket.create_connection((target["host"], int(target.get("port") or 22)), timeout=3):
            return True
    except OSError:
        return False


def _launch_start(target: dict) -> bool:
    """Launch the target's configured start command detached
    (its own session, no inherited stdio): the transport it
    brings up outlives this process. False when the target
    configures no usable command."""
    cmd = target.get("start")
    if not (isinstance(cmd, list) and cmd and all(isinstance(part, str) and part for part in cmd)):
        return False
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


# The runtime proxy's tailnet route port: the forwarder's
# CONNECTs go here, and a candidate credential verifies here.
_PROXY_TAILNET_PORT = 3130
_FORWARDER_MARK = "local_compute_fwd"


def _fwd_pin_path(target: dict) -> Path | None:
    pin = target.get("fwd_pin")
    return Path(pin) if isinstance(pin, str) and pin else None


def _fwd_dest(target: dict) -> tuple[str, int] | None:
    dest = target.get("fwd_dest")
    if isinstance(dest, list) and len(dest) == 2 and isinstance(dest[0], str) and dest[0]:
        try:
            return dest[0], int(dest[1])
        except (TypeError, ValueError):
            return None
    return None


def _pin_value(pin: Path) -> str:
    try:
        for line in pin.read_text().splitlines():
            line = line.strip()
            if line.startswith("HTTPS_PROXY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _connect_verifies(proxy_url: str, dest: tuple[str, int]) -> bool:
    """Whether one proxy credential CONNECTs to the forwarder's
    destination right now: a 200 from the proxy's tailnet route,
    nothing less. The credential itself is never logged."""
    u = urllib.parse.urlparse(proxy_url or "")
    if not u.username or not u.hostname:
        return False
    cred = f"{u.username}:{u.password or ''}"
    try:
        remote = socket.create_connection((u.hostname, _PROXY_TAILNET_PORT), timeout=10)
    except OSError:
        return False
    try:
        auth = base64.b64encode(cred.encode()).decode()
        remote.sendall(
            f"CONNECT {dest[0]}:{dest[1]} HTTP/1.1\r\nHost: {dest[0]}:{dest[1]}\r\n"
            f"Proxy-Authorization: Basic {auth}\r\n\r\n".encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = remote.recv(4096)
            if not chunk:
                return False
            resp += chunk
        return b" 200 " in resp.split(b"\r\n")[0]
    except OSError:
        return False
    finally:
        remote.close()


def refresh_pin(target: dict, env: dict | None = None) -> bool:
    """Restock a forwarder target's pin from the calling
    process's own HTTPS_PROXY — the refresh-on-dispatch writer.
    A value lands only after it CONNECT-verifies against the
    target's `fwd_dest`; an empty or unverified value leaves
    the pin untouched, so a shell whose environment carries no
    credential (the scheduler server's, for one) can never
    blank a live pin. True when the pin already holds or now
    holds the caller's verified credential."""
    pin = _fwd_pin_path(target)
    dest = _fwd_dest(target)
    if pin is None or dest is None:
        return False
    candidate = (os.environ if env is None else env).get("HTTPS_PROXY", "")
    if not candidate:
        return False
    if candidate == _pin_value(pin):
        return True
    if not _connect_verifies(candidate, dest):
        return False
    try:
        lines = [ln for ln in pin.read_text().splitlines() if not ln.strip().startswith("HTTPS_PROXY=")] if pin.exists() else []
    except OSError:
        lines = []
    lines.append(f"HTTPS_PROXY={candidate}")
    try:
        foundation.staged_write(pin, ("\n".join(lines) + "\n").encode(), mode=0o600)
    except Exception:
        return False
    return True


def _tunnel_banner_ok(target: dict) -> bool:
    """Whether the tunnel behind the target's port actually
    serves: an SSH banner read through it. A forwarder holding
    a dead credential accepts the TCP connection and then
    resets or hangs — the port answers, the banner never
    comes — so for a forwarder target this, not the bare port,
    is the liveness reading."""
    try:
        with socket.create_connection((target["host"], int(target.get("port") or 22)), timeout=5) as s:
            s.settimeout(5)
            return s.recv(64).startswith(b"SSH-")
    except OSError:
        return False


def _kill_forwarders() -> int:
    """SIGTERM every running forwarder process (matched by the
    adapter script's name in its cmdline; never this process).
    The stale half of a revival: a forwarder whose credential
    died cannot heal in place when every candidate it holds is
    dead, so it makes room for the relaunch."""
    killed = 0
    try:
        entries = list(Path("/proc").glob("[0-9]*/cmdline"))
    except OSError:
        return 0
    for entry in entries:
        try:
            pid = int(entry.parent.name)
            if pid == os.getpid():
                continue
            if _FORWARDER_MARK.encode() in entry.read_bytes():
                os.kill(pid, 15)
                killed += 1
        except (OSError, ValueError):
            continue
    return killed


def ensure_transport(target: dict | None) -> bool:
    """Whether the target's transport answers, starting it
    first when it is down. Only a loopback target carrying a
    `start` command is managed: its port not answering runs
    the command once and waits for the port. Any other target
    is the operator's own networking — reported as it answers,
    never launched at. Success is the port answering, not the
    launched process surviving (a second launcher losing the
    bind race still leaves the transport up).

    A forwarder target (one carrying `fwd_pin`/`fwd_dest`) is
    held to the tunnel-shaped bar instead: the port answering
    is not enough — the SSH banner must read through the
    tunnel. Port up and banner down is a stale forwarder
    holding a dead credential: it is killed and relaunched.
    Every healthy ensure restocks the pin via refresh_pin."""
    if not target:
        return False
    fwd = _fwd_pin_path(target) is not None and _fwd_dest(target) is not None
    managed = target.get("host") in _LOOPBACK_HOSTS
    if fwd:
        # Restock first, from this process's own credential:
        # the refresh verifies directly against the proxy, so
        # it can heal the pin even while the tunnel is down —
        # and a healed pin can heal the running forwarder on
        # its next CONNECT, no relaunch needed.
        refresh_pin(target)
    if _port_answers(target):
        if not fwd:
            return True
        if _tunnel_banner_ok(target) or _tunnel_banner_ok(target):
            return True
        if not managed:
            return False
        _kill_forwarders()
    elif not managed:
        return False
    if not _launch_start(target):
        return False
    deadline = time.monotonic() + _START_WAIT_S
    while time.monotonic() < deadline:
        if _port_answers(target):
            if not fwd or _tunnel_banner_ok(target):
                return True
        time.sleep(0.5)
    return False


def _ssh_probe(repo: Path, target: dict) -> bool:
    # The bound is generous on purpose: a managed transport's
    # tunnel can take tens of seconds to establish under load,
    # and a probe that gives up early reads a live venue dead.
    try:
        r = subprocess.run(ssh_args(repo, target) + ["true"], capture_output=True, timeout=45)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe(repo: Path, now_dt: datetime | None = None, target_id: str | None = None, shape: dict | None = None) -> bool | None:
    """Whether one local target answers over SSH: True/False
    from a real probe, None when no target resolves (liveness
    unverified). Probes ride the dial cache, one cache per
    target — a state read never dials more than once per TTL.
    A failed probe against a managed transport starts it and
    probes once more before the verdict is cached, so the
    reap pass's pulse cadence is the transport's keeper."""
    tid, target = resolve_target(repo, shape, target_id)
    if target is None:
        return None
    now = now_dt or datetime.now(timezone.utc)
    cache = _probe_cache_name(tid)
    cached = foundation.dial_cache_read(repo, cache, now)
    if cached is not None:
        return bool(cached)
    ok = _ssh_probe(repo, target)
    if not ok and ensure_transport(target):
        ok = _ssh_probe(repo, target)
    foundation.dial_cache_write(repo, cache, ok, now)
    return ok


def probe_for_record(repo: Path, rec: dict, now_dt: datetime | None = None) -> bool | None:
    """The probe for the machine a lease record belongs to:
    the record's own target when it carries one, else its
    shape's binding."""
    target_id = rec.get("target")
    if isinstance(target_id, str) and target_id:
        return probe(repo, now_dt=now_dt, target_id=target_id)
    _shape, tid, _target = shape_target(repo, rec.get("shape") or "")
    return probe(repo, now_dt=now_dt, target_id=tid)


def session_name(repo: Path, shape: dict) -> str:
    """The session name for a shape's machine: its target's
    configured session, else the shape's, else the default."""
    _tid, target = resolve_target(repo, shape)
    return (target or {}).get("session") or shape.get("session") or DEFAULT_SESSION


def acquire_local(repo: Path, shape_id: str, caller: str | None = None, hours: float | None = None, now_dt: datetime | None = None) -> dict:
    """Register (or adopt) a lease on the local venue for one
    caller and shape. Mirrors the home acquire's result shape:
    {"action": "created"|"adopted", "record"} on success, a
    refusal dict otherwise."""
    try:
        shapes = catalog.catalog_shapes(repo, venue=VENUE)
    except ValueError:
        return {"action": "refused-venue", "reason": f"venue {VENUE!r} serves no catalog"}
    shape = shapes.get(shape_id)
    if shape is None:
        return {"action": "refused-shape", "reason": f"shape {shape_id!r} is not in the {VENUE} catalog"}
    target_id, _target = resolve_target(repo, shape)
    if target_id is None and len(local_targets(repo)) > 1:
        # Several machines are configured and this shape binds
        # none of them: registering it would guess a machine.
        return {"action": "refused-target", "reason": f"shape {shape_id!r} binds no local target"}
    now = now_dt or datetime.now(timezone.utc)
    session = session_name(repo, shape)
    existing = records.load_record(repo, session)
    if existing and (existing.get("venue") or foundation.VENUE) == VENUE:
        try:
            if foundation.parse_dt(existing["deadline"]) > now:
                return {"action": "adopted", "record": existing}
        except (KeyError, ValueError):
            pass
    cfg = foundation.load_config(repo)
    window = float(hours) if hours is not None else float(cfg.get("max_hours", 8))
    rec = {
        "session": session,
        "venue": VENUE,
        **({"target": target_id} if target_id else {}),
        "shape": shape_id,
        "shape_spec": {"gpu": None, "tpu": None, "high_mem": False},
        "rate_cu_per_hour": None,
        "caller": caller,
        "account": "primary",
        "acquired_at": now.isoformat(),
        "deadline": (now + timedelta(hours=window)).isoformat(),
        "last_used_at": now.isoformat(),
        "jobs": [],
    }
    records.save_record(repo, rec)
    return {"action": "created", "record": rec}


def run_target(repo: Path, rec: dict) -> dict | None:
    """The SSH target a run record belongs to: the target the
    record itself carries, else its shape's binding, else the
    venue's only target."""
    target_id = rec.get("target")
    if isinstance(target_id, str) and target_id:
        return venue_target(repo, target_id)
    _shape, _tid, target = shape_target(repo, rec.get("shape") or "")
    return target or venue_target(repo)


_RUN_ID_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def read_run_state(repo: Path, rec: dict, target: dict | None = None) -> dict:
    """One tri-state read of a local run's container run dir
    (the remote account's runs/<run_id>, the dispatch's
    own layout):

    - "exit": the exit file is present — exit_code, the
      output tail, and finished_at from the exit file's own
      mtime (the run's completion time, not the reader's).
    - "running": the run dir is present with no exit file yet.
    - "absent": no run dir at all.
    - "unknown": no target resolves, the run id is not
      path-safe, or the read itself failed — a lost read is
      never a verdict (the session_state rule).

    A pure read: it never starts a transport."""
    run_id = rec.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID_SAFE.match(run_id):
        return {"reading": "unknown"}
    if target is None:
        target = run_target(repo, rec)
    if target is None:
        return {"reading": "unknown"}
    remote = (
        f'd="$HOME/runs/{run_id}"; '
        'if [ -f "$d/exit" ]; then echo KIND=exit; '
        'echo "CODE=$(cat "$d/exit")"; '
        'echo "MTIME=$(stat -c %Y "$d/exit" 2>/dev/null)"; '
        "echo TAIL; tail -n 200 \"$d/output.log\" 2>/dev/null; "
        'elif [ -d "$d" ]; then echo KIND=running; '
        "else echo KIND=absent; fi"
    )
    try:
        r = subprocess.run(ssh_args(repo, target) + [remote], capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return {"reading": "unknown"}
    if r.returncode != 0:
        return {"reading": "unknown"}
    lines = r.stdout.decode(errors="replace").splitlines()
    if not lines:
        return {"reading": "unknown"}
    if lines[0] == "KIND=running":
        return {"reading": "running"}
    if lines[0] == "KIND=absent":
        return {"reading": "absent"}
    if lines[0] != "KIND=exit" or len(lines) < 3:
        return {"reading": "unknown"}
    try:
        code = int(lines[1].split("=", 1)[1].strip())
    except (IndexError, ValueError):
        return {"reading": "unknown"}
    finished = None
    try:
        mtime = int(lines[2].split("=", 1)[1].strip())
        finished = datetime.fromtimestamp(mtime, timezone.utc).isoformat()
    except (IndexError, ValueError):
        pass
    tail = ""
    if len(lines) > 3 and lines[3] == "TAIL" and lines[4:]:
        tail = "\n".join(lines[4:]) + "\n"
    return {"reading": "exit", "exit_code": code, "finished_at": finished, "output_tail": tail}


def release_local(repo: Path, session: str | None = None) -> dict:
    """Release the local venue's lease record. The container
    itself is the venue and stays up; release ends the
    registration only."""
    name = session or DEFAULT_SESSION
    rec = records.load_record(repo, name)
    if not rec or (rec.get("venue") or foundation.VENUE) != VENUE:
        return {"action": "no-lease"}
    records.delete_record(repo, name)
    return {"action": "released", "session": name}
