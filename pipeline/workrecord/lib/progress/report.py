"""Derived progress: computed at read time, never stored.

For every todo armed with a progress schedule (the
`progress_check` / `progress_armed` front-matter fields,
written only through lib/writes/bundles.py), this module derives
the driver's view: the cadence interval, the last
checkpoint, the last activity (arming or checkpoint,
whichever is newer), how many whole check intervals have
passed with no activity, and the stall verdict — stalled
when the missed-check count reaches STALL_MISSED_CHECKS
(the progress-schedules plan's ruled threshold: 2). The
verdict reads status before it derives on age: a todo
at a stop status (bundles.TODO_STOP_STATUSES — done,
the terminal status, or blocked, a declared pause) or
in an archived bundle is finished or paused work, and
its checkpoint age is its history, never a stall (the
refresh-step-6-verdict-v2 zombie stall: a
done todo pinged STALLED in two watch passes because
its last checkpoint was its done flip).

A checkpoint is a todo-body line of the form

    progress-checkpoint: <ISO-8601 timestamp> — <text>

appended through `wb todo set --note` by whoever does
the work or runs a driver cycle; this module only reads
them. The todo file stays the progress record.

This module is pure: same inputs → same report. Acting
on a verdict (checkpointing, nudging, surfacing a
blocker) is the driver's business. The schedule that
runs the checks is the harness's own mechanism since
the owner's auto-create commission:
lib/progress/schedule.py writes a scheduler-registry
entry when a todo arms and deletes it when the todo
disarms, and each entry runs `wb progress-check` at
the todo's cadence (the older scheduling-is-a-platform-
concern doctrine survives only for the staleness
check's `print-schedule`).

Freshness (the stale-measure cure): a
served measure is a snapshot, and a consumer holding
one must never mistake it for the records' current
state — the Edgar Step 6 lane was steered three times
off a snapshot hours old whose cited records had long
since advanced. Every measure this module serves
therefore carries a `freshness` block — its as-of
(the measure's computed_at), the newest activity
among the records it cites, and the cadence bound —
and `measure_freshness` re-reads the cited todo files
and re-rules the measure at consumption time: VOID
when the cited records have advanced more than one
checkpoint cadence past the as-of (the consumer must
re-measure from the files), CURRENT otherwise. A
cited record that is gone, and a measure that cannot
state its as-of, are void: stale is never presented
as current.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from ..plans import bundles as bundle_parser
from ..util import parse_iso

CHECKPOINT_PREFIX = "progress-checkpoint:"
_CHECKPOINT_RE = re.compile(r"^progress-checkpoint:\s*(\S+)")

# The ruled stall threshold: this many consecutive
# missed checks (a full cadence interval each with no
# checkpoint and no status move) declares the work
# stalled.
STALL_MISSED_CHECKS = 2


def _stalled(todo: dict, missed) -> bool:
    """The stall verdict over one todo: the missed-check
    count at threshold AND the work still able to stall.
    A todo at a stop status (bundles.TODO_STOP_STATUSES)
    or in an archived bundle is finished or paused — its
    age derives (missed_checks stays the factual count)
    but the verdict never fires. Every derivation in
    this module rules through here, so no surface can
    emit a stall the others would refuse."""
    if missed is None or missed < STALL_MISSED_CHECKS:
        return False
    if todo.get("status") in bundle_parser.TODO_STOP_STATUSES:
        return False
    if todo.get("archived"):
        return False
    return True


def _instant(value):
    """An ISO-8601 string → an aware datetime, or None.
    Malformed values are honest unknowns, never guesses;
    a naive value reads as UTC (the system's timestamps
    are UTC ISO-8601)."""
    if not value:
        return None
    try:
        parsed = parse_iso(str(value).strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def last_checkpoint(todo: dict):
    """The newest checkpoint timestamp in a todo's body,
    as an ISO string, or None when it has none. A line
    whose timestamp does not parse does not count as
    activity — body prose is not validated, so an
    unreadable checkpoint is simply not activity."""
    best = None
    for line in (todo.get("body") or "").splitlines():
        m = _CHECKPOINT_RE.match(line.strip())
        if not m:
            continue
        instant = _instant(m.group(1))
        if instant is not None \
                and (best is None or instant > best):
            best = instant
    return best.isoformat() if best is not None else None


def todo_progress(todo: dict, *, now=None):
    """The progress block for one todo, or None when the
    todo is not armed. Not armed means: no
    `progress_check` field, the opt-out value, or a
    cadence that does not parse — an unparseable cadence
    is not arming (the same predicate
    lib/progress/schedule.py's is_armed uses). A block
    with no interval could only ever report a vacuous
    verdict — the opt-out once leaked through this way,
    printing "on track (None missed checks)" at any
    time, forever, while the todo's file showed a
    three-cadence gap (the refresh-repo-finalization
    divergence)."""
    cadence = todo.get("progress_check")
    if not cadence:
        return None
    interval = bundle_parser.parse_cadence(cadence)
    if interval is None:
        return None
    now = now or datetime.now(timezone.utc)
    checkpoint = last_checkpoint(todo)
    activity = _instant(todo.get("progress_armed"))
    ck = _instant(checkpoint)
    if ck is not None \
            and (activity is None or ck > activity):
        activity = ck
    missed = None
    if interval is not None and activity is not None:
        elapsed = (now - activity).total_seconds()
        missed = max(
            0, int(elapsed // interval.total_seconds()))
    return {
        "id": todo.get("id"),
        "title": todo.get("title"),
        "status": todo.get("status"),
        "bundle": todo.get("bundle"),
        "archived": bool(todo.get("archived")),
        "path": todo.get("path"),
        "cadence": cadence,
        "interval_seconds": interval.total_seconds()
        if interval is not None else None,
        "armed_at": todo.get("progress_armed"),
        "last_checkpoint": checkpoint,
        "last_activity": activity.isoformat()
        if activity is not None else None,
        "missed_checks": missed,
        "stalled": _stalled(todo, missed),
    }


# The standing checkpoint cadence (AGENTS.md's named
# value): the freshness bound for a measure whose cited
# blocks carry no interval of their own.
DEFAULT_CADENCE_SECONDS = 900


def _record_activity(todo, plans_dir=None):
    """One cited record's newest activity instant: the
    newest of its checkpoints, its arming stamp, and —
    when the todo's file resolves under plans_dir — the
    file's own mtime (any write to the record counts:
    the measure claims to describe the record, so a
    record rewritten past the bound no longer provably
    matches it). None when nothing dates the record."""
    instants = []
    ck = _instant(last_checkpoint(todo))
    if ck is not None:
        instants.append(ck)
    armed = _instant(todo.get("progress_armed"))
    if armed is not None:
        instants.append(armed)
    if plans_dir is not None and todo.get("path"):
        try:
            mtime = (Path(plans_dir) / todo["path"]).stat().st_mtime
        except OSError:
            mtime = None
        if mtime is not None:
            instants.append(
                datetime.fromtimestamp(mtime, tz=timezone.utc))
    return max(instants) if instants else None


def _bound_seconds(blocks):
    """The freshness bound for a measure: the tightest
    cadence among the blocks it cites (a steer must not
    issue on a snapshot older than the cadence it claims
    to measure), or the standing 15-minute cadence when
    no cited block carries an interval."""
    intervals = [b.get("interval_seconds") for b in blocks
                 if b.get("interval_seconds")]
    return min(intervals) if intervals else DEFAULT_CADENCE_SECONDS


def _freshness_block(*, as_of, cited_newest, bound_seconds,
                     checked_at, gone=False):
    """The verdict over one as-of / cited-newest pair.
    Void when a cited record is gone, when the as-of
    cannot be stated, or when the cited records have
    advanced more than the bound past the as-of."""
    advanced = None
    if as_of is not None and cited_newest is not None:
        advanced = (cited_newest - as_of).total_seconds()
    if gone:
        verdict = "void"
        reason = ("a record this measure cites is gone — "
                  "the measure no longer describes the files")
    elif as_of is None:
        verdict = "void"
        reason = ("the measure states no as-of — its "
                  "freshness cannot be told, so it is void")
    elif advanced is not None and advanced > bound_seconds:
        verdict = "void"
        reason = (
            f"the cited records advanced {advanced:.0f}s "
            f"past the measure's as-of, beyond one cadence "
            f"({bound_seconds:.0f}s) — re-measure from the files")
    else:
        verdict = "current"
        reason = ("the cited records stand within one "
                  "cadence of the measure's as-of")
    return {
        "verdict": verdict,
        "as_of": as_of.isoformat() if as_of is not None else None,
        "cited_newest_activity": (
            cited_newest.isoformat()
            if cited_newest is not None else None),
        "bound_seconds": bound_seconds,
        "advanced_seconds": advanced,
        "checked_at": checked_at.isoformat(),
        "reason": reason,
    }


def measure_freshness(measure, plans_dir, *, now=None):
    """Re-rule a served measure's freshness at
    consumption time, against the records it cites.

    `measure` is a project_progress report (its
    computed_at is the as-of; its armed blocks cite the
    todo files by their plans-relative paths);
    `plans_dir` is the project the measure was drawn
    from. Each cited todo file is re-read and its
    current newest activity derived (checkpoints,
    arming stamp, file mtime); the measure is VOID when
    the newest cited activity stands more than one
    cadence past the as-of, when a cited record is
    gone, or when the measure states no as-of. The
    returned block has the served freshness block's
    shape, with checked_at set to this ruling."""
    now = now or datetime.now(timezone.utc)
    blocks = measure.get("armed") or []
    as_of = _instant(measure.get("computed_at"))
    bound = _bound_seconds(blocks)
    cited_newest = None
    gone = False
    for block in blocks:
        rel = block.get("path")
        if not rel:
            continue
        path = Path(plans_dir) / rel
        if not path.is_file():
            gone = True
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            gone = True
            continue
        todo = bundle_parser.parse_todo(text, path=rel)
        activity = _record_activity(todo, plans_dir)
        if activity is not None and (
                cited_newest is None or activity > cited_newest):
            cited_newest = activity
    return _freshness_block(
        as_of=as_of, cited_newest=cited_newest,
        bound_seconds=bound, checked_at=now, gone=gone)


def project_progress(plans_dir, *, now=None) -> dict:
    """The `wb progress` report for one project: every
    armed todo across its bundles (active and finished)
    with its derived block, plus a summary. Unarmed
    todos are not the driver's business and never
    appear. The report carries its freshness block
    (see the module note): at serve time the verdict is
    ruled over the records just read, and the block's
    as-of / cited-newest / bound are what a later
    consumer re-rules with measure_freshness."""
    now = now or datetime.now(timezone.utc)
    armed = []
    cited = []
    for todo in bundle_parser.list_todos(plans_dir):
        block = todo_progress(todo, now=now)
        if block is not None:
            armed.append(block)
            cited.append(todo)
    cited_newest = None
    for todo in cited:
        activity = _record_activity(todo, plans_dir)
        if activity is not None and (
                cited_newest is None or activity > cited_newest):
            cited_newest = activity
    return {
        "computed_at": now.isoformat(),
        "armed": armed,
        "summary": {
            "armed": len(armed),
            "stalled": sum(1 for b in armed if b["stalled"]),
        },
        "freshness": _freshness_block(
            as_of=now, cited_newest=cited_newest,
            bound_seconds=_bound_seconds(armed),
            checked_at=now),
    }
