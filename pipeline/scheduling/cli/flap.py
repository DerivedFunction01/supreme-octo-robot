"""The flap command: the write-denial flap verdict from the
state file the write-denial-watch job keeps. flap_line is
the pure (line, exit_code) core — tests/test_sched_flap.py
loads it off bin/sched, which re-exports it from here."""
import json
import os

from server import config as config_mod
from server.firing import schedule

from cli.common import _load


def flap_line(state, now, stale_after):
    """(line, exit_code) for the flap state surface. Pure: the
    caller supplies the parsed state (or None), the current time
    as a datetime, and the staleness budget in seconds."""
    from datetime import datetime, timezone

    if not state or not state.get("verdict"):
        return ("flap: unknown (no samples recorded)", 4)
    verdict = state["verdict"]
    last = state.get("last_sample_at")
    age = None
    if last:
        try:
            when = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            age = max(0, int((now - when).total_seconds()))
        except ValueError:
            age = None
    if age is None:
        return (f"flap: {verdict} (sample time unreadable)", 4)
    stale = age > stale_after
    parts = [f"flap: {verdict}", f"since {state.get('since', '?')}",
             f"sample {age}s old"]
    if verdict in ("up", "mixed"):
        denied = [name for name, m in (state.get("mechanisms") or {}).items()
                  if m.get("status") == "denied"]
        if denied:
            parts.append("denied: " + ", ".join(denied))
    if stale:
        parts.append("STALE")
    if stale or verdict == "inconclusive":
        code = 4
    elif verdict == "down":
        code = 0
    else:
        code = 3
    return ("  ".join(parts), code)


def cmd_flap():
    from datetime import datetime, timezone

    values, _sources = config_mod.resolve()
    state_dir = os.path.join(values["home"], "state")
    path = os.path.join(state_dir, "flap-state.json")
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = None
    # Staleness budget: two cadences of the registered watch job
    # when it exists, else two of the plan's 3-minute default.
    stale_after = 360
    try:
        entries, _errors = _load()
        entry = entries.get("write-denial-watch")
        if entry is not None and entry.cadence.get("type") == "interval":
            every = entry.cadence.get("every", "")
            stale_after = 2 * int(schedule.parse_every(every).total_seconds())
    except Exception:  # noqa: BLE001 - a read stays readable
        pass
    line, code = flap_line(state, datetime.now(timezone.utc), stale_after)
    print(line)
    return code
