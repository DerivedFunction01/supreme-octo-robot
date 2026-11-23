"""Delegated operations: write, patch, and exec performed by the
server process on behalf of a caller whose own process cannot be
trusted to land a write (the write-denial flap denies agent-class
processes in waves; the server's class is never denied — flap
plan Step 1 findings, 2026-11-08).

`perform()` is the whole surface: it validates the request shape,
enforces the workspace scope server-side, performs the operation,
and records every attempt — success, refusal, or error — in the
ledger with its caller. The HTTP layer (server/serving/http.py) only
routes; bin/sched carries the client verbs.

Contract (POST /ops, JSON body):
  {"caller": str, "op": "write", "path": p, "content": text, "mode": int?}
  {"caller": str, "op": "patch", "path": p, "old": text, "new": text}
  {"caller": str, "op": "exec", "argv": [..], "cwd": p?, "timeout": secs?}
The write form's optional `mode` (an int in 0..0o7777) carries
contract 15's mode discipline through the endpoint: a
credential-class target is stamped with it server-side, so a
caller performing through the service never loses the stamp
its in-process write would have applied.
Paths are absolute or relative to the workspace root; the
resolved real path must stay inside it. Responses are
{"ok": true, ...result} or {"ok": false, "error": name,
"detail": text} with enumerable error names: bad_request,
outside_scope, not_found, no_match, multi_match, verify_failed,
io_error, unauthenticated, scope_refused, caller_mismatch.

Authentication (§10.1, ruled; contract 04's frozen mapping):
the request rides the /tools token model — the HTTP layer
authenticates the bearer token through the connector's
registry (read fresh per call) and passes the identity here.
`write`/`patch` require the `write-state` scope; `exec`
requires the `exec` scope (contract 01). The body's `caller`
must equal the authenticated caller — the self-asserted
string is an audit label, never an authentication input.
Unauthenticated and under-scoped calls are refused before
anything is performed and ledgered as refusals.

Consolidation (step S3, plan §4.15): this service's mutation
half is the unified state writer's base implementation. The
staged-write protocol core lives in the pipeline platform
home (`pipeline/platform/writer.py`, contract 15) and this
endpoint delegates to it; the writer's wider operation set
(cas-update, delete) is pipeline-internal there — this
endpoint's set stays contract 04's write/patch/exec, and the
per-repo standalone form of the service does not survive.
"""

import hashlib
import os
import shlex
import signal
import subprocess
import threading

from .. import paths as _paths
from ..firing.executor import TailBuffer, _pump

DEFAULT_TIMEOUT_SECS = 120
MAX_TIMEOUT_SECS = 600

# HTTP status per error name (perform returns these).
_STATUS = {
    "bad_request": 400,
    "unauthenticated": 401,
    "outside_scope": 403,
    "scope_refused": 403,
    "caller_mismatch": 403,
    "not_found": 404,
    "no_match": 409,
    "multi_match": 409,
    "verify_failed": 500,
    "io_error": 500,
}

# The scope each op requires (contract 04, §10.1 mapping —
# frozen): state writes ride write-state; delegated execution
# rides the exec-denoting scope alone.
_OP_SCOPES = {"write": "write-state", "patch": "write-state", "exec": "exec"}

# Refusals ledger as refusals, not errors.
_REFUSAL_NAMES = frozenset(
    {"outside_scope", "unauthenticated", "scope_refused", "caller_mismatch"}
)


class OpError(Exception):
    def __init__(self, name, detail=""):
        super().__init__(detail or name)
        self.name = name
        self.detail = detail or name


def _root(values):
    return os.path.realpath(values["workspace_root"])


def _resolve(root, raw):
    """Resolve a caller-supplied path against the workspace root
    and refuse anything that lands outside it."""
    if not isinstance(raw, str) or not raw:
        raise OpError("bad_request", "path must be a non-empty string")
    candidate = raw if os.path.isabs(raw) else os.path.join(root, raw)
    resolved = os.path.realpath(candidate)
    if resolved != root and not resolved.startswith(root + os.sep):
        raise OpError("outside_scope", f"{raw} resolves outside the workspace")
    return resolved


def _load_platform_writer():
    """The staged-write protocol core lives in the pipeline
    platform home (contract 15); loaded by path, derived from
    this file's own location — the ops scripts' standing
    pattern — so the protocol has exactly one implementation
    and this endpoint is its first caller."""
    import importlib.util

    path = _paths.PLATFORM_WRITER
    spec = importlib.util.spec_from_file_location("pipeline_platform_writer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_writer = _load_platform_writer()


def _staged_write(path, data, mode=None):
    """Write via a sibling temp file, read back, rename over.
    Even a crash mid-write cannot tear the target. The
    implementation is the platform writer's (contract 15);
    its WriterError names are this endpoint's error names."""
    try:
        _writer.staged_write(path, data, mode=mode)
    except _writer.WriterError as exc:
        raise OpError(exc.name, exc.detail) from exc


def _result_for(path, root, data):
    return {
        "path": os.path.relpath(path, root),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _op_write(root, req):
    content = req.get("content")
    if not isinstance(content, str):
        raise OpError("bad_request", "content must be a string")
    mode = req.get("mode")
    if mode is not None and (
        isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0o7777
    ):
        raise OpError("bad_request", "mode must be an int in 0..0o7777")
    path = _resolve(root, req.get("path"))
    data = content.encode("utf-8")
    _staged_write(path, data, mode=mode)
    return _result_for(path, root, data)


def _op_patch(root, req):
    old, new = req.get("old"), req.get("new")
    if not isinstance(old, str) or not old:
        raise OpError("bad_request", "old must be a non-empty string")
    if not isinstance(new, str):
        raise OpError("bad_request", "new must be a string")
    path = _resolve(root, req.get("path"))
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        raise OpError("not_found", f"no such file: {req.get('path')}") from None
    except UnicodeDecodeError as exc:
        raise OpError("bad_request", f"not a text file: {exc}") from exc
    except OSError as exc:
        raise OpError("io_error", str(exc)) from exc
    count = text.count(old)
    if count == 0:
        raise OpError("no_match", "target text not found")
    if count > 1:
        raise OpError("multi_match", f"target text found {count} times")
    data = text.replace(old, new, 1).encode("utf-8")
    _staged_write(path, data)
    return _result_for(path, root, data)


def _exec_env(values):
    """The environment an exec child runs with: the server's
    own, plus the scheduler-owned GitHub SSH identity when the
    config seam provides one. Both configured paths (identity
    file and known-hosts file) are required — a half-configured
    identity would weaken host-key verification, so it pins
    nothing. Strict checking stays on; no trust-on-first-use.
    Callers pass nothing: the machine assumption lives here,
    in the untracked live config, never in tracked code."""
    env = dict(os.environ)
    identity = values.get("git_ssh_identity_file")
    known_hosts = values.get("git_ssh_known_hosts_file")
    if identity and known_hosts:
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {shlex.quote(identity)} "
            f"-o UserKnownHostsFile={shlex.quote(known_hosts)} "
            "-o StrictHostKeyChecking=yes"
        )
    return env


def _op_exec(root, values, req):
    argv = req.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(a, str) for a in argv)
    ):
        raise OpError("bad_request", "argv must be a non-empty list of strings")
    cwd_raw = req.get("cwd")
    cwd = _resolve(root, cwd_raw) if cwd_raw else root
    if not os.path.isdir(cwd):
        raise OpError("not_found", f"no such directory: {cwd_raw or '.'}")
    timeout = req.get("timeout", DEFAULT_TIMEOUT_SECS)
    if not isinstance(timeout, int) or not 1 <= timeout <= MAX_TIMEOUT_SECS:
        raise OpError("bad_request", f"timeout must be an int in 1..{MAX_TIMEOUT_SECS}")
    cap = values["capture_cap_bytes"]
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=_exec_env(values),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        raise OpError("io_error", f"spawn failed: {exc}") from exc
    out_tail, err_tail = TailBuffer(cap), TailBuffer(cap)
    threads = [
        threading.Thread(target=_pump, args=(proc.stdout, out_tail), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, err_tail), daemon=True),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
    return {
        "exit_code": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "stdout_tail": out_tail.text(),
        "stderr_tail": err_tail.text(),
    }


def _target_text(root, op, req):
    """The audit target: the path (workspace-relative when it
    resolves) or the argv, truncated for the ledger record."""
    if op in ("write", "patch"):
        raw = req.get("path")
        try:
            return os.path.relpath(_resolve(root, raw), root)
        except OpError:
            return str(raw)
    if op == "exec":
        argv = req.get("argv")
        if isinstance(argv, list):
            return " ".join(str(a) for a in argv)[:300]
    return ""


def perform(ledger, values, req, auth=None):
    """Validate, authenticate, perform, audit. Returns
    (http_status, payload). `auth` is the HTTP layer's
    connector.authenticate() result — (caller, scopes) for the
    presented bearer token, or None. Authentication is checked
    before any op runs: no identity, a caller label that does
    not match the identity, or a missing scope is a ledgered
    refusal and nothing is performed."""
    if not isinstance(req, dict):
        return 400, {
            "ok": False,
            "error": "bad_request",
            "detail": "request must be a JSON object",
        }
    caller = req.get("caller")
    op = req.get("op")
    root = _root(values)
    target = _target_text(root, op, req) if isinstance(op, str) else ""
    try:
        if not isinstance(caller, str) or not caller:
            raise OpError("bad_request", "caller must be a non-empty string")
        if auth is None:
            raise OpError(
                "unauthenticated", "a bearer token is required (contract 04, §10.1)"
            )
        auth_caller, scopes = auth
        if caller != auth_caller:
            raise OpError(
                "caller_mismatch",
                f"caller label {caller!r} does not match the "
                f"authenticated caller {auth_caller!r}",
            )
        required = _OP_SCOPES.get(op)
        if required is not None and required not in scopes:
            raise OpError("scope_refused", f"{op} needs scope {required}")
        if op == "write":
            result = _op_write(root, req)
        elif op == "patch":
            result = _op_patch(root, req)
        elif op == "exec":
            result = _op_exec(root, values, req)
        else:
            raise OpError("bad_request", f"unknown op: {op!r}")
    except OpError as exc:
        status = "refused" if exc.name in _REFUSAL_NAMES else "error"
        # An unauthenticated attempt ledgers as caller `unknown`
        # (the connector's convention): the label it presented
        # is unproven and never enters the record as a caller.
        audit_caller = "unknown" if exc.name == "unauthenticated" else caller
        _audit(ledger, audit_caller, op, target, status, error=exc.name)
        return _STATUS[exc.name], {"ok": False, "error": exc.name, "detail": exc.detail}
    except Exception as exc:  # noqa: BLE001 - the surface stays up
        _audit(ledger, caller, op, target, "error", error="io_error")
        return 500, {"ok": False, "error": "io_error", "detail": str(exc)}
    _audit(ledger, caller, op, target, "ok", exit_code=result.get("exit_code"))
    payload = {"ok": True, "op": op}
    payload.update(result)
    return 200, payload


def _audit(ledger, caller, op, target, status, error=None, exit_code=None):
    if ledger is None:
        return
    try:
        ledger.record(
            "op",
            caller=caller if isinstance(caller, str) else None,
            op=op if isinstance(op, str) else None,
            target=target,
            status=status,
            error=error,
            exit_code=exit_code,
        )
    except Exception:  # noqa: BLE001 - audit failure never fails the op
        pass
