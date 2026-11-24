"""Denial-tolerant text writes for the platform ops tools.

The agent/keeper process class on this host sits under an
intermittent write-denial wave: a plain open(path, "w") from
Python raises PermissionError at random — most writes in a
run pass, one in N is denied, and a single denial used to
kill install-units.sh's generation step outright, which the
watchdog ladder then read as an unclassifiable unit and
failed loud on a healthy service (three false "server down"
wakes in one day alone; the same shape as the earlier
outage's empty --check classifications).

The write itself is the platform's unified writer
(pipeline/platform/writer.py — the one home of the staged
protocol: sibling temp, flush + fsync, read back and
compare, rename over). This module adds only the tolerance
the ops context needs: retry the writer's act on
PermissionError with a short backoff — the denial is
per-operation and intermittent, so a retry a moment later
lands. The result is byte-identical to the writer's own
output; only the tolerance differs. Attempts and base
delay are env seams (DURABLE_WRITE_ATTEMPTS /
DURABLE_WRITE_BASE_DELAY_S) so tests can exercise the
give-up path without real waits.

This writer shrinks the denial surface; it does not carry
the classification verdict alone — a wave at its peak
denies every write from the class for minutes at a time.
The watchdog ladder's cure for the verdict itself is its
scheduler-route fallback (ops/watchdog.sh): a check that
dies without classifying is re-run through the scheduler
ops route, whose server process is never denied.
"""

import importlib.util
import os
import time

_ATTEMPTS = max(1, int(os.environ.get("DURABLE_WRITE_ATTEMPTS", "4")))
_BASE_DELAY_S = float(os.environ.get("DURABLE_WRITE_BASE_DELAY_S", "0.3"))
_MAX_DELAY_S = 5.0


def _load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_writer():
    """The platform writer, reached through the platform's
    paths spine: the ops tools run with only their own
    directory importable, so this module bootstraps the
    spine by path (ops/cutover -> platform/paths.py) and
    takes the writer's location from it — derivation lives
    in the spine, never here."""
    here = os.path.dirname(os.path.abspath(__file__))
    paths = _load_by_path(
        "platform_paths", os.path.join(here, "..", "..", "paths.py"))
    return _load_by_path("platform_writer", paths.WRITER)


_WRITER = _load_writer()


def _is_denial(exc):
    """A denial reaches this seam in two forms: a bare
    PermissionError, or the writer's WriterError wrapping
    one (staged_write re-raises every OSError as
    WriterError('io_error') with the original as cause).
    Only denials retry; every other failure is the
    caller's to hear about, unretried."""
    if isinstance(exc, PermissionError):
        return True
    cause = getattr(exc, "__cause__", None)
    return isinstance(cause, PermissionError)


def write_text(path, text, encoding="utf-8"):
    """Write text to path through the unified writer,
    retrying denials with backoff. Raises the last denial
    when the attempts run out; any other error propagates
    immediately."""
    data = text.encode(encoding)
    delay = _BASE_DELAY_S
    for attempt in range(_ATTEMPTS):
        try:
            _WRITER.staged_write(path, data)
            return
        except Exception as exc:
            if not _is_denial(exc) or attempt == _ATTEMPTS - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, _MAX_DELAY_S)
