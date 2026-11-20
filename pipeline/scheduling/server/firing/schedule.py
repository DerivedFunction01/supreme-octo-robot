"""Due calculation. All durable state is UTC instants (spec
Rulings); timezones exist only here, where a wall-clock cadence is
parsed into grid instants.

Grids:
- interval: the grid is anchored at the entry's first persisted
  next_due; advancing adds whole intervals, so a long run cannot
  drift the schedule.
- daily / weekly: grid points are local dates at HH:MM in the
  entry's timezone. A wall time inside the spring-forward gap fires
  at the first valid instant after the gap (EC-2); the fall-back
  repeated hour yields one date, one fire, at its first occurrence
  (EC-3).
"""
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
EVERY_RE = re.compile(r"^(\d+)([smh])$")
UNIT = {"s": "seconds", "m": "minutes", "h": "hours"}
DOW_INDEX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def parse_every(text):
    match = EVERY_RE.match(str(text))
    if not match:
        raise ValueError(f"bad interval duration: {text!r}")
    return timedelta(**{UNIT[match.group(2)]: int(match.group(1))})


def parse_at(text):
    hh, mm = str(text).split(":")
    return time(int(hh), int(mm))


def _valid_wall(day, at, tz):
    """The instant for wall time `at` on local date `day` in `tz`,
    or the first valid instant after it when `at` falls in a DST
    gap. fold=0 picks the first occurrence of a repeated hour."""
    naive = datetime.combine(day, at)
    candidate = naive.replace(tzinfo=tz, fold=0)
    back = candidate.astimezone(UTC).astimezone(tz)
    if (back.hour, back.minute, back.date()) == (at.hour, at.minute, day):
        return candidate.astimezone(UTC)
    probe = naive
    for _ in range(180):
        probe += timedelta(minutes=1)
        candidate = probe.replace(tzinfo=tz, fold=0)
        back = candidate.astimezone(UTC).astimezone(tz)
        if (back.hour, back.minute, back.date()) == (probe.hour, probe.minute, probe.date()):
            return candidate.astimezone(UTC)
    raise ValueError(f"no valid wall time within 3h after {day} {at} in {tz}")


def _wall_points(cadence, tz, start_day, days):
    at = parse_at(cadence["at"])
    dows = None
    if cadence["type"] == "weekly":
        dows = {DOW_INDEX[d] for d in cadence["dow"]}
    points = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        if dows is not None and day.weekday() not in dows:
            continue
        points.append(_valid_wall(day, at, tz))
    return points


def first_point_after(cadence, tz_name, after):
    """The first grid instant strictly after `after` (a UTC datetime),
    for an entry with no persisted next_due yet."""
    tz = ZoneInfo(tz_name)
    if cadence["type"] == "interval":
        return after + parse_every(cadence["every"])
    start_day = after.astimezone(tz).date() - timedelta(days=1)
    for point in _wall_points(cadence, tz, start_day, 10):
        if point > after:
            return point
    raise ValueError("no grid point within 10 days")


def first_point_at_or_after(cadence, tz_name, instant):
    tz = ZoneInfo(tz_name)
    if cadence["type"] == "interval":
        return instant
    start_day = instant.astimezone(tz).date() - timedelta(days=1)
    for point in _wall_points(cadence, tz, start_day, 10):
        if point >= instant:
            return point
    raise ValueError("no grid point within 10 days")


def advance(cadence, tz_name, next_due, now):
    """Given a persisted next_due <= now, return
    (latest_missed_point, collapsed_count, new_next_due) where
    new_next_due is the first grid point strictly after `now`.
    collapsed_count counts every missed point including the one
    that will fire."""
    tz = ZoneInfo(tz_name)
    if cadence["type"] == "interval":
        step = parse_every(cadence["every"])
        missed = int((now - next_due) / step) + 1
        latest = next_due + step * (missed - 1)
        return latest, missed, next_due + step * missed
    start_day = next_due.astimezone(tz).date() - timedelta(days=1)
    span_days = (now.astimezone(tz).date() - start_day).days + 3
    points = [p for p in _wall_points(cadence, tz, start_day, span_days) if p >= next_due]
    missed_points = [p for p in points if p <= now]
    future = [p for p in points if p > now]
    if not missed_points or not future:
        raise ValueError("grid computation failed to bracket now")
    return missed_points[-1], len(missed_points), future[0]
