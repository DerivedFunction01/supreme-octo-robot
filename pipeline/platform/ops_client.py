"""The /ops client for in-process callers: writes PERFORMED
by the scheduler server process (contract 04's endpoint,
contract 15's writer).

Why this module exists beside bin/sched's cli/ops_client:
the CLI client is the reporting form — it prints and
returns exit codes for a human at a shell. A programmatic
caller (the venue writer seam) needs the library form:
hand over the bytes, get the result back, and have every
failure raised as the platform writer's WriterError, so
the seam's error contract holds byte for byte. The wire
protocol, the endpoint resolution, and the token rules
are the CLI client's, unchanged — one protocol, two
faces, each in its own layer's home.

Resolution (mirrors the CLI client and the server's own
config fields):
- endpoint: $SCHEDULER_HOST / $SCHEDULER_PORT when set,
  else the scheduling live config's host/port, else the
  server's defaults (127.0.0.1:8796);
- token: $SCHED_OPS_TOKEN_DIR when set, else the
  scheduling package's ops token home; one <caller>.token
  file per caller, its content the raw token, presented
  as a bearer token. No token file → the request goes out
  unauthenticated and the server refuses it; no identity
  is ever invented here.

Failure semantics (the CLI client's exit-4 honesty, in
exception form): a transport failure provably before the
send (connection refused, name unresolvable) means
nothing was performed; a sent request whose response was
lost has an UNKNOWN outcome — the op may have performed,
verify before repeating. Both raise WriterError with the
face named in the detail ("io_error", the writer's table).
A server refusal or error raises WriterError under the
endpoint's own error name. This client never writes the
target itself: no local fallback exists to fall back to.
"""

import hashlib
import importlib.util as _ilu
import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

_paths_spec = _ilu.spec_from_file_location(
    "pipeline_platform_paths", Path(__file__).resolve().parent / "paths.py"
)
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

_writer_spec = _ilu.spec_from_file_location(
    "pipeline_platform_writer", Path(__file__).resolve().parent / "writer.py"
)
_writer = _ilu.module_from_spec(_writer_spec)
_writer_spec.loader.exec_module(_writer)

WriterError = _writer.WriterError

TOKEN_DIR_ENV = "SCHED_OPS_TOKEN_DIR"

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8796


def token_dir(env=None):
    env = os.environ if env is None else env
    return env.get(TOKEN_DIR_ENV) or _paths.OPS_TOKEN_DIR


def resolve_token(caller, env=None):
    """The acting caller's raw token, or None. The token
    file holds the token as its only content (one trailing
    newline tolerated); a missing, unreadable, or empty
    file resolves to None."""
    try:
        with open(
            os.path.join(token_dir(env), f"{caller}.token"), encoding="utf-8"
        ) as fh:
            token = fh.read().strip()
    except OSError:
        return None
    return token or None


def server_url(env=None):
    """The /ops endpoint URL. The server's own config
    fields, in the server's own precedence: the env vars,
    then the live config file, then the defaults."""
    env = os.environ if env is None else env
    host = env.get("SCHEDULER_HOST")
    port = env.get("SCHEDULER_PORT")
    if host is None or port is None:
        try:
            with open(_paths.SCHEDULING_CONFIG, encoding="utf-8") as fh:
                config = json.load(fh)
        except (OSError, ValueError):
            config = {}
        if host is None:
            host = config.get("host")
        if port is None:
            port = config.get("port")
    host = host or _DEFAULT_HOST
    try:
        port = int(port) if port is not None else _DEFAULT_PORT
    except (TypeError, ValueError):
        port = _DEFAULT_PORT
    return f"http://{host}:{port}/ops"


UNREACHABLE = "unreachable"
UNKNOWN = "unknown"


def _pre_send(reason) -> bool:
    """True when a transport failure provably happened
    before the request was sent: the connection was
    refused, or the host name did not resolve. Every other
    failure (a timeout at any stage, a reset, a dropped
    connection) may postdate the send."""
    return isinstance(reason, (ConnectionRefusedError, socket.gaierror))


def post(req, http_timeout, env=None):
    """POST one op to the server. Returns the payload dict
    when the server answered (any HTTP status); UNREACHABLE
    when the request provably never left (refused or
    unresolvable — nothing was performed); UNKNOWN when
    the request was sent but the response was lost (the
    outcome is unknown — the op may have performed)."""
    body = json.dumps(req).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = resolve_token(req.get("caller") or "", env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        server_url(env), data=body, method="POST", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=http_timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - shape below covers it
            return {
                "ok": False,
                "error": "bad_response",
                "detail": f"HTTP {exc.code} with no JSON body",
            }
    except urllib.error.URLError as exc:
        return UNREACHABLE if _pre_send(exc.reason) else UNKNOWN
    except (OSError, ValueError):
        return UNKNOWN


def perform(caller, req, http_timeout=30, env=None):
    """Perform one op under `caller` and return the result
    payload. Every failure raises WriterError: the
    endpoint's own error name for a server answer, or
    io_error with the transport face named for a request
    that never got one."""
    req = dict(req)
    req["caller"] = caller
    payload = post(req, http_timeout, env)
    if payload == UNREACHABLE:
        raise WriterError("io_error", "ops server unreachable — nothing was performed")
    if payload == UNKNOWN or not isinstance(payload, dict):
        raise WriterError(
            "io_error",
            "ops request sent but its response was lost — the "
            "outcome is unknown and the op may have performed; "
            "verify before repeating",
        )
    if not payload.get("ok"):
        raise WriterError(
            payload.get("error") or "io_error",
            payload.get("detail") or "ops request failed",
        )
    return payload


def staged_write(caller, path, data, mode=None, http_timeout=30, env=None):
    """Perform a full-replace write of `data` (bytes) to
    `path` through the /ops service: the server process
    runs the platform writer's staged protocol, so the
    write lands even while the write denial is denying
    this process. The protocol carries text (contract
    04's write form): non-UTF-8 content is refused here,
    before anything is sent, with the target untouched.
    An explicit `mode` rides the request and is stamped
    server-side — the credential-class discipline is
    never dropped at this seam. The server's result is
    verified against the bytes handed over (length +
    SHA-256) before success is reported."""
    if not isinstance(data, (bytes, bytearray)):
        raise WriterError("bad_request", "content must be bytes")
    data = bytes(data)
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WriterError(
            "bad_request",
            f"content is not UTF-8 text; the /ops write protocol carries text: {exc}",
        ) from exc
    req = {"op": "write", "path": path, "content": content}
    if mode is not None:
        req["mode"] = mode
    payload = perform(caller, req, http_timeout=http_timeout, env=env)
    if (
        payload.get("bytes") != len(data)
        or payload.get("sha256") != hashlib.sha256(data).hexdigest()
    ):
        raise WriterError(
            "verify_failed",
            f"ops result does not match the bytes handed over for {path}",
        )
    return payload
