"""The funnel-side writer route: one home for the venue sync
package's non-lease state writes (contract 15).

The writers homed here are the short-lived funnel-class
processes: the Colab CLI funnel's own state (the credential
token, the session binding, the auth-required marker) and the
liveness entries the lease core arms through
sync/liveness_entry.py. Both used to carry a private copy of
the same seam — load the platform writer by path, call it
in-process, else the staged protocol inline. In-process is
the denied class under the write-denial flap (the flap
denies Python open('w') and fsync in waves; stage, rename
and unlink are never denied), so a private in-process copy
is a write that dies in the wave that caused the damage it
was healing.

The route, in order:

1. The /ops service, through the platform /ops client under
   caller "workhorse": the long-lived scheduler server
   process performs the staged protocol server-side — the
   shared file writer, used as much as possible. A
   well-formed server answer is final: a refusal (scope,
   auth, a malformed payload) raises and is never routed
   around.
2. On a transport failure — the server unreachable, or a
   sent request whose response was lost — the platform
   writer's staged_write in-process, under a bounded retry
   on the denial signature (an OSError with errno EPERM or
   EDQUOT anywhere in the error's cause chain). The write
   is a full replace of identical bytes through the same
   atomic protocol on either leg, so the composed operation
   is correct whichever leg lands it; retry exhaustion
   raises with the target byte-identical, as the protocol
   guarantees at every stage.
3. Where no platform tree exists (the pinned source repo's
   own layout, where no /ops service exists either), the
   staged protocol inline — the same protocol the deleted
   per-seam copies carried — under the same retry.

Attempts and backoff are env-tunable at call time
(VENUE_WRITER_ATTEMPTS, VENUE_WRITER_BACKOFF_S — the
run-dir cure's VENUE_RUN_DIR_* precedent). The defaults
match the /ops client's own retry discipline deliberately
(TRANSIENT_ATTEMPTS = 4, TRANSIENT_BACKOFF_S = (3, 8, 20)
in the claim-retry cure): the same denial wave should meet
the same schedule on either surface. They are stated here,
not imported — the client's constants are its own surface's,
and this module must load where only the writer exists.
"""

from __future__ import annotations

import errno
import importlib.util as _ilu
import os
import time
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

# The route's /ops caller: the workhorse machinery caller,
# registered in the scheduler's connector registry with the
# write-state scope (contract 04, §10.1); its raw token
# lives in the ops token home like every caller's.
CALLER = "workhorse"

# The denial signature: the flap denies the write syscalls
# with EPERM (the sandbox's fsync/open denial) or EDQUOT
# (the wave's quota face). Any other failure — a read-back
# mismatch, a malformed payload — is not a denial and is
# never retried.
DENIAL_ERRNOS = frozenset({errno.EPERM, errno.EDQUOT})

DEFAULT_ATTEMPTS = 4
DEFAULT_BACKOFF_S = (3.0, 8.0, 20.0)

# The /ops client's two transport faces, as its perform()
# publishes them in the WriterError detail: the request
# provably never left, or it was sent and its response was
# lost. A server-side io_error answer carries an OS error
# string instead and matches neither mark — it is a
# well-formed answer and stays final.
_UNREACHABLE_MARK = "ops server unreachable"
_LOST_MARK = "response was lost"


class _InlineWriterError(Exception):
    """The WriterError shape for the no-platform-tree world:
    the platform writer's error contract (a name from its
    closed table, a detail), carried by this module when
    there is no platform module instance to borrow it from."""

    def __init__(self, name, detail=""):
        super().__init__(detail or name)
        self.name = name
        self.detail = detail or name


def _load_module(name, cand):
    if cand.exists():
        spec = _ilu.spec_from_file_location(name, cand)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    return None


WRITER = _load_module("pipeline_platform_writer", _paths.PLATFORM_WRITER)
OPS_CLIENT = _load_module("pipeline_platform_ops_client", _paths.PLATFORM_OPS_CLIENT)

WriterError = WRITER.WriterError if WRITER is not None else _InlineWriterError


def _attempts(env) -> int:
    try:
        n = int(env.get("VENUE_WRITER_ATTEMPTS", env.get("COLAB_WRITER_ATTEMPTS", "")))  # step6-retire: COLAB_ dual-read fallback
    except ValueError:
        return DEFAULT_ATTEMPTS
    return n if n >= 1 else DEFAULT_ATTEMPTS


def _backoff(env) -> tuple:
    raw = env.get("VENUE_WRITER_BACKOFF_S", env.get("COLAB_WRITER_BACKOFF_S", ""))  # step6-retire: COLAB_ dual-read fallback
    try:
        parts = tuple(float(p) for p in raw.split(",") if p.strip())
    except ValueError:
        return DEFAULT_BACKOFF_S
    if not parts or any(p < 0 for p in parts):
        return DEFAULT_BACKOFF_S
    return parts


def _is_denial(exc) -> bool:
    """True when the failure is a write denial: an OSError
    carrying EPERM/EDQUOT anywhere in the cause chain (the
    platform writer wraps the denied syscall into its
    io_error WriterError `from` the OSError, so the errno
    rides the chain, not the surface)."""
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, OSError) and cur.errno in DENIAL_ERRNOS:
            return True
        cur = cur.__cause__ if cur.__cause__ is not None else cur.__context__
    return False


def _is_transport_failure(exc) -> bool:
    return (
        getattr(exc, "name", None) == "io_error"
        and (_UNREACHABLE_MARK in exc.detail or _LOST_MARK in exc.detail)
    )


def _inline_write(path: Path, data: bytes, mode) -> None:
    """The staged protocol inline (contract 15): stage to a
    fresh sibling, fsync, read back and compare, stamp the
    mode, rename over. The last-resort form for a tree with
    no platform writer; a failure at any stage unlinks the
    staging file and leaves the target byte-identical."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.sched-tmp-{os.getpid()}")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp, "rb") as fh:
            if fh.read() != data:
                raise WriterError("verify_failed", f"read-back mismatch for {path}")
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except WriterError:
        tmp.unlink(missing_ok=True)
        raise
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise WriterError("io_error", str(exc)) from exc


def _local_write(path: Path, data: bytes, mode) -> None:
    """One local attempt: the platform writer where the tree
    provides it, else the protocol inline."""
    if WRITER is not None:
        WRITER.staged_write(str(path), data, mode=mode)
        return
    _inline_write(path, data, mode)


def _local_write_with_retry(path: Path, data: bytes, mode) -> None:
    """The local leg under denial retry: a denial is a wave,
    and the wave passes; a non-denial failure raises at
    once. Exhaustion raises the last denial with the target
    byte-identical — the protocol never lands a partial
    write, on any attempt."""
    attempts = _attempts(os.environ)
    backoff = _backoff(os.environ)
    for attempt in range(attempts):
        try:
            _local_write(path, data, mode)
            return
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _is_denial(exc) or attempt == attempts - 1:
                raise
            time.sleep(backoff[min(attempt, len(backoff) - 1)])


def staged_write(path, data: bytes, mode: int | None = None) -> None:
    """Write bytes to path through the writer route: the
    /ops service performs it where the service answers; a
    transport failure falls back to the local staged
    protocol under denial retry; a well-formed refusal
    raises the writer's WriterError, normalized onto the
    platform writer's class so a caller catching it sees
    one class whichever module instance raised it. An
    explicit `mode` (credential-class targets are 0600 by
    rule) rides every leg and is stamped by whichever
    performs the write."""
    target = Path(path)
    if OPS_CLIENT is not None:
        try:
            OPS_CLIENT.staged_write(CALLER, str(target), data, mode=mode)
            return
        except OPS_CLIENT.WriterError as exc:
            if not _is_transport_failure(exc):
                if WRITER is not None and not isinstance(exc, WRITER.WriterError):
                    raise WRITER.WriterError(exc.name, exc.detail) from exc
                raise
            # Transport failure: the service did not answer
            # (or its answer was lost). Fall through to the
            # local leg — the same bytes, the same protocol.
    _local_write_with_retry(target, data, mode)
