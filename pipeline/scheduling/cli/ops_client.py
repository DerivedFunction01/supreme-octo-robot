"""The /ops client core shared by every command that rides
the server endpoint (adopt, write, patch, exec,
connector-token): caller resolution, token resolution, the
POST, the report, and flag taking. Exit 4 means no
CONFIRMED performance, in two named faces: the server was
unreachable before the request was sent (connection
refused or unresolvable — nothing was performed), or the
request was sent but its response was lost (a timeout, a
reset, a truncated body — the outcome is UNKNOWN and the
op may have performed; verify before repeating). The
earlier form collapsed both into "nothing was performed",
which was unsound for the second face and was attested
three times in one night (2026-11-21/22) by callers who
repeated work that had in fact run. The client never
falls back to a direct write in either face.

Authentication (§10.1; contract 04): /ops rides the /tools
token model. The raw token lives client-side only, in the
ops token home — one untracked file per caller,
`<caller>.token` in the token directory (default:
`cli.paths.OPS_TOKEN_DIR`; the SCHED_OPS_TOKEN_DIR env var
re-points it for staged installs and tests). Resolution is
per caller name: a token file present for the acting caller
is presented as a bearer token; none present means the call
goes out unauthenticated and the server refuses it — the
client never invents an identity."""
import importlib.util
import json
import os
import sys

from cli import paths as _paths
from server import config as config_mod

TOKEN_DIR_ENV = "SCHED_OPS_TOKEN_DIR"


def _ops_caller(argv):
    if "--caller" in argv:
        return argv[argv.index("--caller") + 1]
    return os.environ.get("SCHED_CALLER") or "sched-cli"


def token_dir(env=None):
    env = os.environ if env is None else env
    return env.get(TOKEN_DIR_ENV) or _paths.OPS_TOKEN_DIR


def token_file_path(caller, env=None):
    return os.path.join(token_dir(env), f"{caller}.token")


def resolve_ops_token(caller, env=None):
    """The acting caller's raw token, or None. The token file
    holds the token as its only content (one trailing newline
    tolerated); a missing, unreadable, or empty file resolves
    to None."""
    try:
        with open(token_file_path(caller, env), encoding="utf-8") as fh:
            token = fh.read().strip()
    except OSError:
        return None
    return token or None


def store_ops_token(caller, token, env=None):
    """Write the acting caller's token file (0600, created in
    the token home) through the platform writer's staged
    protocol — a denied or torn write leaves the standing
    token byte-identical, where the direct truncate-write
    this replaced destroyed it (the 2026-11-21 mint failure
    the writer census named). The delivery half of a mint:
    the token prints once at mint and is saved here by its
    receiver."""
    path = token_file_path(caller, env)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", _paths.PLATFORM_WRITER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.staged_write(
        path, (token + "\n").encode("utf-8"), mode=0o600)
    return path


UNREACHABLE = "unreachable"
UNKNOWN = "unknown"


def _pre_send(reason) -> bool:
    """True when a transport failure provably happened
    before the request was sent: the connection was
    refused, or the host name did not resolve. Every other
    failure (a timeout at any stage, a reset, a dropped
    connection) may postdate the send."""
    import socket

    return isinstance(reason, (ConnectionRefusedError, socket.gaierror))


def _ops_post(req, http_timeout):
    """POST one op to the server. Returns the payload dict
    when the server answered (any HTTP status); UNREACHABLE
    when the request provably never left (refused or
    unresolvable — nothing was performed); UNKNOWN when
    the request was sent but the response was lost (the
    outcome is unknown — the op may have performed)."""
    import urllib.error
    import urllib.request

    values, _sources = config_mod.resolve()
    url = f"http://{values['host']}:{values['port']}/ops"
    body = json.dumps(req).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = resolve_ops_token(req.get("caller") or "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=http_timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - shape below covers it
            return {"ok": False, "error": "bad_response",
                    "detail": f"HTTP {exc.code} with no JSON body"}
    except urllib.error.URLError as exc:
        return UNREACHABLE if _pre_send(exc.reason) else UNKNOWN
    except (OSError, ValueError):
        return UNKNOWN


def _ops_report(op, payload):
    if payload == UNREACHABLE:
        print(f"sched {op}: server unreachable — nothing was performed",
              file=sys.stderr)
        return 4
    if not isinstance(payload, dict):
        # A response that parsed to a non-object (a JSON
        # null body is the reachable case) is a lost
        # outcome, reported as UNKNOWN — never a crash.
        payload = UNKNOWN
    if payload == UNKNOWN:
        print(f"sched {op}: the request was sent but the response "
              "was lost — the outcome is UNKNOWN and the op may "
              "have performed; verify before repeating",
              file=sys.stderr)
        return 4
    if not payload.get("ok"):
        print(f"sched {op}: {payload.get('error')}: {payload.get('detail')}",
              file=sys.stderr)
        return 1
    return 0


def _ops_do(req, op, http_timeout=30):
    payload = _ops_post(req, http_timeout)
    return _ops_report(op, payload), payload


def _take_flag(argv, name):
    if name in argv:
        idx = argv.index(name)
        value = argv[idx + 1]
        return value, argv[:idx] + argv[idx + 2:]
    return None, argv
