"""Denial-tolerant text writes for the platform ops tools.

The agent/keeper process class on this host sits under an
intermittent write-denial wave: a plain open(path, "w") from
Python raises PermissionError at random — most writes in a
run pass, one in N is denied, and a single denial used to
kill install-units.sh's generation step outright, which the
watchdog ladder then read as an unclassifiable unit and
failed loud on a healthy service (three false "server down"
wakes on 2026-11-21 alone; the same shape as the 2026-11-20
outage's empty --check classifications).

The write method that survives the wave is the platform's
own staged discipline: write a sibling temp file, then
rename it over the target (rename-over was never denied in
any probe), retrying the whole act on PermissionError with
a short backoff — the denial is per-operation and
intermittent, so a retry a moment later lands. The result
is byte-identical to a plain write; only the tolerance
differs. Attempts and base delay are env seams
(DURABLE_WRITE_ATTEMPTS / DURABLE_WRITE_BASE_DELAY_S) so
tests can exercise the give-up path without real waits.

This writer shrinks the denial surface; it does not carry
the classification verdict alone — a wave at its peak
denies every write from the class for minutes at a time.
The watchdog ladder's cure for the verdict itself is its
scheduler-route fallback (ops/watchdog.sh): a check that
dies without classifying is re-run through the scheduler
ops route, whose server process is never denied.
"""

import os
import time

_ATTEMPTS = max(1, int(os.environ.get("DURABLE_WRITE_ATTEMPTS", "4")))
_BASE_DELAY_S = float(os.environ.get("DURABLE_WRITE_BASE_DELAY_S", "0.3"))
_MAX_DELAY_S = 5.0


def write_text(path, text, encoding="utf-8"):
    """Write text to path via a staged sibling + rename-over,
    retrying PermissionError with backoff. Raises the last
    PermissionError when the attempts run out; any other
    OSError propagates immediately."""
    tmp = f"{path}.tmp-{os.getpid()}"
    delay = _BASE_DELAY_S
    for attempt in range(_ATTEMPTS):
        try:
            with open(tmp, "w", encoding=encoding) as fh:
                fh.write(text)
            os.replace(tmp, path)
            return
        except PermissionError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, _MAX_DELAY_S)
