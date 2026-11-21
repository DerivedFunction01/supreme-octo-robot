"""The /ops client core shared by every command that rides
the server endpoint (adopt, write, patch, exec,
connector-token): caller resolution, token resolution, the
POST, the report, and flag taking. Exit 4 means the server
was unreachable and nothing was performed — the client
never falls back to a direct write.

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


def _ops_post(req, http_timeout):
    """POST one op to the server. Returns the payload dict, or
    None when the server could not be reached (nothing was
    performed — the client never falls back to a direct write)."""
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
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _ops_report(op, payload):
    if payload is None:
        print(f"sched {op}: server unreachable — nothing was performed",
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
