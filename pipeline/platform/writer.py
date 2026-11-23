"""The unified state writer — base implementation (contract 15).

Every state mutation in the pipeline is performed through this
module's protocol: content stages to a fresh sibling, is flushed
and fsync'd here (the long-lived server class is never the
denied one), read back and compared, then renamed over the
target, with a directory fsync for the rename's durability. No
caller ever opens a target for truncate-write, and a denial or
failure at any stage leaves the target byte-identical to its
pre-state.

This module is the scheduler `/ops` service's mutation half,
moved at the consolidation's step S3 (plan §4.15): the ops
endpoint (`pipeline/scheduling/server/serving/ops.py`) delegates its
staged write here, and the remaining stores re-point at their
own steps (work record S4, venue records S5, attention state
S7); step S9 closes the service over the re-pointed set with
the flap-simulation drill. `exec` is NOT a writer operation —
delegated execution stays the ops service's clause of
contract 04; the two halves share the platform service and
the ledger, not an operation set.

Operation set (request forms carry {caller, op, path, ...}):

  write       {path, content, mode?}                full replace
  patch       {path, old, new}                      single-match
  cas-update  {path, expected_stamp, content}  or
              {path, expected_stamp, old, new}      stamp-guarded
  delete      {path}                                unlink

The stamp is the target's identity as served by its owning
contract: for file targets, the SHA-256 of the file's bytes.
Failure semantics are contract 04's closed error table reused
whole, plus the one addition cas-update requires:
version_conflict (409) — the expected stamp no longer
matches; nothing was written.
"""

import hashlib
import os
import threading

# HTTP status per error name (perform returns these).
_STATUS = {
    "bad_request": 400,
    "outside_scope": 403,
    "not_found": 404,
    "no_match": 409,
    "multi_match": 409,
    "version_conflict": 409,
    "verify_failed": 500,
    "io_error": 500,
}


class WriterError(Exception):
    def __init__(self, name, detail=""):
        super().__init__(detail or name)
        self.name = name
        self.detail = detail or name


def _unlink_quiet(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def staged_write(path, data, mode=None):
    """Write via a sibling temp file, read back, rename over.
    Even a crash mid-write cannot tear the target.

    Mode discipline: an explicit `mode` is stamped on the
    staged file before the rename (the credential-class
    targets — the venue funnel's token and session binding —
    are 0600 by rule, including the write that recreates a
    clobbered file, where there is no mode to carry). With
    no explicit mode, the target's existing mode is carried
    onto the staged file, as below."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(
        directory,
        f".{os.path.basename(path)}.sched-tmp-{os.getpid()}-{threading.get_ident()}",
    )
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp, "rb") as fh:
            if fh.read() != data:
                raise WriterError("verify_failed", f"read-back mismatch for {path}")
        # Carry the target's existing mode onto the staged
        # file before the rename: rename-over would
        # otherwise reset it to the umask default. (The
        # original workbench seam's pin, ported at the
        # S11 resync; a new target keeps the default.)
        if mode is None:
            try:
                mode = os.stat(path).st_mode & 0o7777
            except FileNotFoundError:
                mode = None
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except WriterError:
        _unlink_quiet(tmp)
        raise
    except OSError as exc:
        _unlink_quiet(tmp)
        raise WriterError("io_error", str(exc)) from exc
    try:  # directory fsync: durability of the rename itself
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def resolve(root, raw):
    """Resolve a caller-supplied path against the workspace root
    and refuse anything that lands outside it."""
    if not isinstance(raw, str) or not raw:
        raise WriterError("bad_request", "path must be a non-empty string")
    candidate = raw if os.path.isabs(raw) else os.path.join(root, raw)
    resolved = os.path.realpath(candidate)
    if resolved != root and not resolved.startswith(root + os.sep):
        raise WriterError("outside_scope", f"{raw} resolves outside the workspace")
    return resolved


def stamp_of(path):
    """The file target's CAS stamp: SHA-256 of its bytes."""
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except FileNotFoundError:
        raise WriterError("not_found", f"no such file: {path}") from None
    except OSError as exc:
        raise WriterError("io_error", str(exc)) from exc


def _result_for(path, root, data):
    return {
        "path": os.path.relpath(path, root),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def op_write(root, req):
    content = req.get("content")
    if not isinstance(content, str):
        raise WriterError("bad_request", "content must be a string")
    mode = req.get("mode")
    if mode is not None and (
        isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0o7777
    ):
        raise WriterError("bad_request", "mode must be an int in 0..0o7777")
    path = resolve(root, req.get("path"))
    data = content.encode("utf-8")
    staged_write(path, data, mode=mode)
    return _result_for(path, root, data)


def _read_text(path, raw):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        raise WriterError("not_found", f"no such file: {raw}") from None
    except UnicodeDecodeError as exc:
        raise WriterError("bad_request", f"not a text file: {exc}") from exc
    except OSError as exc:
        raise WriterError("io_error", str(exc)) from exc


def _patched(text, req):
    old, new = req.get("old"), req.get("new")
    if not isinstance(old, str) or not old:
        raise WriterError("bad_request", "old must be a non-empty string")
    if not isinstance(new, str):
        raise WriterError("bad_request", "new must be a string")
    count = text.count(old)
    if count == 0:
        raise WriterError("no_match", "target text not found")
    if count > 1:
        raise WriterError("multi_match", f"target text found {count} times")
    return text.replace(old, new, 1)


def op_patch(root, req):
    path = resolve(root, req.get("path"))
    text = _read_text(path, req.get("path"))
    data = _patched(text, req).encode("utf-8")
    staged_write(path, data)
    return _result_for(path, root, data)


def op_cas_update(root, req):
    path = resolve(root, req.get("path"))
    expected = req.get("expected_stamp")
    if not isinstance(expected, str) or not expected:
        raise WriterError("bad_request", "expected_stamp must be a non-empty string")
    found = stamp_of(path)
    if found != expected:
        # Nothing is written: the target changed under the
        # edit; the caller re-reads for the fresh stamp and
        # re-presents — never forces.
        raise WriterError(
            "version_conflict",
            f"stamp mismatch for {req.get('path')}: expected {expected}, found {found}",
        )
    if isinstance(req.get("content"), str):
        data = req["content"].encode("utf-8")
    elif "old" in req or "new" in req:
        text = _read_text(path, req.get("path"))
        data = _patched(text, req).encode("utf-8")
    else:
        raise WriterError("bad_request", "cas-update needs content, or old + new")
    staged_write(path, data)
    return _result_for(path, root, data)


def op_delete(root, req):
    path = resolve(root, req.get("path"))
    try:
        os.unlink(path)
    except FileNotFoundError:
        raise WriterError("not_found", f"no such file: {req.get('path')}") from None
    except OSError as exc:
        raise WriterError("io_error", str(exc)) from exc
    return {"path": os.path.relpath(path, root), "deleted": True}


_OPS = {
    "write": op_write,
    "patch": op_patch,
    "cas-update": op_cas_update,
    "delete": op_delete,
}


def perform(ledger, values, req):
    """Validate, perform, audit. Returns (http_status, payload),
    the ops service's convention: every attempt — success,
    refusal, or error — is ledgered as an `op` event with its
    caller (contract 05's kind vocabulary, unchanged)."""
    if not isinstance(req, dict):
        return 400, {
            "ok": False,
            "error": "bad_request",
            "detail": "request must be a JSON object",
        }
    caller = req.get("caller")
    op = req.get("op")
    root = os.path.realpath(values["workspace_root"])
    raw_path = req.get("path")
    target = ""
    if isinstance(raw_path, str):
        try:
            target = os.path.relpath(resolve(root, raw_path), root)
        except WriterError:
            target = raw_path
    try:
        if not isinstance(caller, str) or not caller:
            raise WriterError("bad_request", "caller must be a non-empty string")
        fn = _OPS.get(op) if isinstance(op, str) else None
        if fn is None:
            raise WriterError("bad_request", f"unknown op: {op!r}")
        result = fn(root, req)
    except WriterError as exc:
        status = "refused" if exc.name == "outside_scope" else "error"
        _audit(ledger, caller, op, target, status, error=exc.name)
        return _STATUS[exc.name], {"ok": False, "error": exc.name, "detail": exc.detail}
    except Exception as exc:  # noqa: BLE001 - the surface stays up
        _audit(ledger, caller, op, target, "error", error="io_error")
        return 500, {"ok": False, "error": "io_error", "detail": str(exc)}
    _audit(ledger, caller, op, target, "ok")
    payload = {"ok": True, "op": op}
    payload.update(result)
    return 200, payload


def _audit(ledger, caller, op, target, status, error=None):
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
        )
    except Exception:  # noqa: BLE001 - audit failure never fails the op
        pass
