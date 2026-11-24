"""Venue measure (superapp supervision plan, Step 2):
the family-concurrency facts and the plan-frontier
comparison, computed from the venue's own records.

Families come from the runner's runs store
(pipeline/venue/results/runs, read-only): a run's
family is its job's workstream stem — the job name
minus the programme's shared job prefix and minus
trailing run-kind segments (the venue's job grammar:
every job is named <workstream>-<kind>). A family
counts at an instant on a run in flight or on
evidence advancing within the contract's window —
the registry's staffing contract supplies the window
and the bands; nothing here hardcodes a programme.
Runs attribute to a programme by caller: a caller
base (the part before an optional :lane suffix)
belongs to the active programme whose slug it names
or whose slug stem it carries — edgar-specimen and
its lanes belong to the edgar programme. A todo
staffed only by a research delegate fires no venue
runs, so it never enters the family count — the
contract's delegate rule holds by construction.

The frontier comparison reads each armed bundle's
plan step blocks (the wb-step comments the plan
grammar declares: todos, requires, fanout|serial)
against the workbench's todo statuses: a step is
frontier-eligible when every required todo is done
and its own todos are not all done; the expected
in-flight set is the eligible fanout steps' open
todos — serial-declared steps are the named
exceptions and never enter the expected set. The
actual set is the bundle's doing todos.

Both facts collect on the slow loop into snapshots
the staffing measure reads, in the same discipline
as records/stamps: a failed read keeps the prior
snapshot and clears nothing.
"""

from __future__ import annotations

import glob as glob_mod
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from attention.infra import run_records as detached_records
from attention.infra import wb_client
from attention.services import programmes
from attention.services.measure import registry
from attention.settings import REPO_ROOT, Settings

WINDOW_HOURS = 24
NONTERMINAL_STATES = {"starting", "launching", "polling", "running", "active"}
DONE_STATUSES = {"done"}
# The standing evidence window for a programme with
# no ruled staffing contract (the sweep's window);
# a contract's own window always wins.
DEFAULT_EVIDENCE_WINDOW_MINUTES = 30

# The venue's job grammar: the trailing segments of a
# job name that say what a run does, as opposed to the
# workstream it works on. A segment also counts as a
# run kind when it is a single character, all digits,
# or a kind carrying a variant suffix — one uppercase
# letter (gateC, reproE) or digits (diag2, price2).
RUN_KINDS = {
    "adjud",
    "anchor",
    "arod",
    "assembly",
    "basegate",
    "build",
    "cell",
    "cells",
    "census",
    "cure",
    "cureproof",
    "derive",
    "determination",
    "diag",
    "draw",
    "enum",
    "explore",
    "extract",
    "fidelity",
    "fmt",
    "format",
    "fresh",
    "gate",
    "genre",
    "heldout",
    "logread",
    "payments",
    "plain",
    "post",
    "price",
    "pricing",
    "probe",
    "pytest",
    "readback",
    "recall",
    "rederive",
    "redet",
    "repro",
    "routed",
    "scancheck",
    "seggeom",
    "solve",
    "specimens",
    "subkinds",
    "subprice",
    "subseq",
    "survey",
    "surv",
    "sweep",
    "trace",
    "union",
    "variants",
}

_VARIANT_RE = re.compile(r"^([a-z]+)([A-Z]|\d+)$")


def _is_run_kind(segment: str) -> bool:
    if not segment:
        return True
    if segment in RUN_KINDS or len(segment) == 1 or segment.isdigit():
        return True
    match = _VARIANT_RE.match(segment)
    return bool(match and match.group(1) in RUN_KINDS)


def job_prefix(jobs: list) -> str:
    """The shared job prefix of a programme's jobs,
    cut at a hyphen boundary (greenfield-ci- for the
    edgar fleet's jobs)."""
    names = sorted({j for j in jobs if j})
    if not names:
        return ""
    prefix = names[0]
    for name in names[1:]:
        while not name.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    cut = prefix.rfind("-")
    return prefix[: cut + 1] if cut >= 0 else ""


def family_of(job: str, prefix: str) -> str:
    """A run's family: its job's workstream stem."""
    stem = job[len(prefix) :] if prefix and job.startswith(prefix) else job
    parts = stem.split("-")
    while parts and _is_run_kind(parts[-1]):
        parts.pop()
    return "-".join(parts) or stem


def caller_base(caller: str) -> str:
    return (caller or "").split(":", 1)[0].strip()


def attribute_slug(caller: str, declarations: list) -> str | None:
    """The active programme a caller belongs to: the
    caller base names the programme's slug outright,
    or carries its slug stem (edgar-specimen →
    edgar-greenfield), or carries one of the stems
    the programme declares in caller_stems for callers
    that do not ride the slug (steampower-cust →
    steampowernj, workhorse → supreme-octo-robot).
    Longest match wins; an ambiguous stem attributes
    to no one."""
    base = caller_base(caller)
    if not base:
        return None
    best: tuple[int, str] | None = None
    tied = False
    for row in declarations:
        slug = row["slug"]
        stems = [slug.split("-", 1)[0]] + list(row.get("caller_stems") or [])
        matched = 0
        if base == slug:
            matched = len(slug) + 1
        else:
            for stem in stems:
                if base == stem or base.startswith(stem + "-"):
                    matched = max(matched, len(stem))
        if not matched:
            continue
        if best is None or matched > best[0]:
            best = (matched, slug)
            tied = False
        elif matched == best[0] and slug != best[1]:
            tied = True
    return None if tied or best is None else best[1]


def read_run_store(runs_dir: Path, now: datetime) -> list:
    """The runs store's records inside the window,
    normalized: a run's end is its payload finish. A
    terminal event is the runner's declaration, not
    an end — a launch-lost record's terminal event
    lands long after the launch died, so it must
    never stand in for a finish; a record with no
    finish counts only while its evidence is fresh.
    Its evidence stamp is the last evidence the
    collector saw, else its end, else its start. The
    store is read-only here — records are historical
    and immutable."""
    if not runs_dir.is_dir():
        return []
    cutoff = now - timedelta(hours=WINDOW_HOURS)
    out = []
    for path in sorted(runs_dir.glob("*.json")):
        stamp = detached_records._filename_time(path)
        if stamp is None:
            try:
                stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=now.tzinfo)
            except OSError:
                stamp = None
        if stamp is not None and stamp < cutoff:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        started = detached_records._parse_time(record.get("started_at")) or stamp
        if started is None or started < cutoff:
            continue
        finished = detached_records._parse_time(record.get("finished_at"))
        evidence = (
            detached_records._parse_time(record.get("last_evidence_at"))
            or finished
            or started
        )
        out.append(
            {
                "id": record.get("run_id") or path.stem,
                "job": record.get("job") or "",
                "caller": record.get("caller") or "",
                "session": record.get("session") or "",
                "state": record.get("state") or "",
                "started_at": started,
                "finished_at": finished,
                "evidence_at": evidence,
                # The terminal-unconsumed class's own
                # fields: when the record entered its
                # terminal state by event (the orphaned
                # shape carries no payload finish), and
                # the declared outputs the collector
                # never recovered (the unpulled shape).
                "terminal_event_at": detached_records._parse_time(
                    record.get("terminal_event_at")
                ),
                "missing_outputs": list(record.get("missing_outputs") or []),
            }
        )
    return out


def _in_flight(record: dict, now: datetime, window: timedelta) -> bool:
    """A run counts at `now` when it is in flight —
    started, not yet ended, and (for a record whose
    end was never written) still advancing evidence —
    or when its evidence advanced within the window."""
    started = record["started_at"]
    if started is None or started > now:
        return False
    end = record["finished_at"]
    if end is None and record["state"] not in NONTERMINAL_STATES:
        end = record["evidence_at"]
    if end is None:
        if record["evidence_at"] >= now - window:
            return True
    elif started <= now < end:
        return True
    evidence = record["evidence_at"]
    return evidence is not None and now - window <= evidence <= now


def orphans_at(records: list, now: datetime, window_minutes: float) -> list:
    """Records claiming work the records do not support:
    no payload finish and no longer in flight — the
    launch-lost shape (a launch that died while the
    runner still holds the record) and the stuck shape
    (a non-terminal record whose evidence stopped
    advancing). A record in flight on fresh evidence
    is not an orphan; a finished record is not one
    either. A terminal record with no pulled outputs
    is deliberately NOT an orphan here: a job that
    declares no outputs pulls nothing, so the record
    alone cannot tell 'nothing to pull' from 'never
    pulled' — that class stays a coordinator act until
    the record carries the job's outputs declaration."""
    window = timedelta(minutes=window_minutes)
    out = []
    for record in records:
        if record.get("finished_at") is not None:
            continue
        if _in_flight(record, now, window):
            continue
        started = record["started_at"]
        if started is None or started > now:
            continue
        evidence = record["evidence_at"]
        out.append(
            {
                "id": record["id"],
                "job": record["job"],
                "caller": record["caller"],
                "session": record["session"],
                "state": record["state"],
                "started_at": started.isoformat(),
                "evidence_at": evidence.isoformat() if evidence else None,
            }
        )
    return out


def terminal_unconsumed_at(records: list, now: datetime) -> list:
    """A programme's terminal runs in the shapes the
    terminal-unconsumed class covers — the three
    specimens of the commission:

    failed — a payload finish in state failed (the
    clean specimen: prompt terminal record, zero
    consumption). orphaned — a record closed into
    state orphaned by its terminal event, carrying no
    payload finish; its terminal instant is the
    event, the hours before it being the orphan
    class's ground. unpulled — a record in state
    complete whose declared outputs were never
    recovered (missing_outputs non-empty): the
    deceptive specimen, a terminal state that reads
    complete while the substance is absent — and the
    derivable face of the orphan class's named
    residual, since this record carries the outputs
    declaration the residual waits on.

    A clean complete run never enters; a non-terminal
    record is the orphan class's ground. Whether the
    owning programme has consumed one is the records
    measure's evidence, not the record's — the
    collector's stamp on the record is the recording,
    and recording is not consumption."""
    out = []
    for record in records:
        state = record.get("state")
        finished = record.get("finished_at")
        missing = record.get("missing_outputs") or []
        if state == "failed" and finished is not None and finished <= now:
            shape, terminal_at = "failed", finished
        elif state == "orphaned":
            terminal_at = record.get("terminal_event_at") or record.get("evidence_at")
            if terminal_at is None or terminal_at > now:
                continue
            shape = "orphaned"
        elif (
            state == "complete" and finished is not None and finished <= now and missing
        ):
            shape, terminal_at = "unpulled", finished
        else:
            continue
        started = record["started_at"]
        out.append(
            {
                "id": record["id"],
                "job": record["job"],
                "caller": record["caller"],
                "session": record["session"],
                "state": state,
                "shape": shape,
                "started_at": started.isoformat() if started else None,
                "finished_at": terminal_at.isoformat(),
                "missing_outputs": list(missing),
            }
        )
    return out


def families_at(records: list, now: datetime, window_minutes: float) -> dict:
    """One programme's family facts at an instant:
    the distinct families in flight with their
    sessions and run counts, the per-session
    distribution, and the coordinator/child split
    (the coordinator base is the programme's modal
    caller base over the read window; runs under a
    lane suffix or another base are child work)."""
    window = timedelta(minutes=window_minutes)
    prefix = job_prefix([r["job"] for r in records])
    bases: dict[str, int] = {}
    for record in records:
        base = caller_base(record["caller"])
        if base:
            bases[base] = bases.get(base, 0) + 1
    coordinator = max(bases, key=lambda b: (bases[b], b)) if bases else ""
    families: dict[str, dict] = {}
    sessions: dict[str, list] = {}
    workers = 0
    child_workers = 0
    for record in records:
        if not _in_flight(record, now, window):
            continue
        family = family_of(record["job"], prefix)
        entry = families.setdefault(
            family, {"sessions": set(), "runs": 0, "child_runs": 0}
        )
        entry["runs"] += 1
        workers += 1
        if record["session"]:
            entry["sessions"].add(record["session"])
            sessions.setdefault(record["session"], set()).add(family)
        if caller_base(record["caller"]) != coordinator or ":" in (
            record["caller"] or ""
        ):
            entry["child_runs"] += 1
            child_workers += 1
    return {
        "families": {
            name: {
                "sessions": sorted(entry["sessions"]),
                "runs": entry["runs"],
                "child_runs": entry["child_runs"],
            }
            for name, entry in sorted(families.items())
        },
        "sessions": {name: sorted(fams) for name, fams in sorted(sessions.items())},
        "workers": workers,
        "child_workers": child_workers,
        "coordinator_caller": coordinator,
    }


def collect(state: dict, settings: Settings, now: datetime) -> bool:
    """Snapshot each active colab programme's family
    facts from the runs store; True when changed. A
    programme with no contract reads the standing
    30-minute evidence window."""
    runs_dir = settings.run_records_dir.parent / "runs"
    records = read_run_store(runs_dir, now)
    active = registry.active_declarations()
    # The terminal-unconsumed class measures any
    # programme that declares it, including one whose
    # declaration names no venue while its runs ride
    # the venue under a declared caller stem
    # (steampowernj) — attribution is by caller either
    # way, so those programmes join the snapshot with
    # terminal facts only.
    terminal_slugs = {
        row["slug"]
        for row in active
        if "terminal" in registry.measure_classes_for(row["slug"])
    }
    measured = [
        row
        for row in active
        if row.get("venue") == "colab" or row["slug"] in terminal_slugs
    ]
    snapshot: dict = {}
    for row in measured:
        slug = row["slug"]
        attributed = [r for r in records if attribute_slug(r["caller"], active) == slug]
        facts: dict = {}
        if row.get("venue") == "colab":
            contract = registry.staffing_contract_for(slug)
            window = (
                contract["evidence_window_minutes"]
                if contract
                else DEFAULT_EVIDENCE_WINDOW_MINUTES
            )
            facts = families_at(attributed, now, window)
            facts["orphans"] = orphans_at(attributed, now, window)
        facts["jobs"] = len(attributed)
        if slug in terminal_slugs:
            facts["terminal_unconsumed"] = terminal_unconsumed_at(attributed, now)
        snapshot[slug] = {"at": now, **facts}
    before = {
        slug: {k: v for k, v in entry.items() if k != "at"}
        for slug, entry in (state.get("venue_snapshot") or {}).items()
    }
    after = {
        slug: {k: v for k, v in entry.items() if k != "at"}
        for slug, entry in snapshot.items()
    }
    if after == before:
        return False
    state["venue_snapshot"] = snapshot
    return True


_STEP_BLOCK_RE = re.compile(r"<!--\s*wb-step\b(.*?)-->", re.DOTALL)


def parse_step_blocks(text: str) -> list:
    """A plan's declared step blocks: the wb-step
    comments, one field per line — step, todos
    (|-separated), requires (|-separated prerequisite
    todos, all of which must be done), and exactly one
    of fanout / serial."""
    steps = []
    for match in _STEP_BLOCK_RE.finditer(text or ""):
        fields: dict[str, str] = {}
        for line in match.group(1).splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key.strip()] = value.strip()
        todos = [t.strip() for t in fields.get("todos", "").split("|") if t.strip()]
        requires = [
            t.strip() for t in fields.get("requires", "").split("|") if t.strip()
        ]
        try:
            number = int(fields.get("step", "0"))
        except ValueError:
            number = 0
        steps.append(
            {
                "step": number,
                "todos": todos,
                "requires": requires,
                "fanout": fields.get("fanout"),
                "serial": fields.get("serial"),
            }
        )
    return steps


def frontier_for(steps: list, statuses: dict, bundle_todos: set) -> dict:
    """The frontier comparison for one bundle: the
    expected in-flight set (eligible fanout steps'
    open todos), the actual set (the bundle's doing
    todos), the shortfall, and the serial exceptions
    the declaration names. `statuses` reads across
    the served project — a step may require a todo
    a sibling bundle minted — while the actual set
    counts only this bundle's todos."""
    expected: list[str] = []
    serial_excluded: list[str] = []
    for step in steps:
        todos = step["todos"]
        if not todos:
            continue
        if all(statuses.get(t) in DONE_STATUSES for t in todos):
            continue
        if not all(statuses.get(t) in DONE_STATUSES for t in step["requires"]):
            continue
        open_todos = [t for t in todos if statuses.get(t) not in DONE_STATUSES]
        if step.get("serial") is not None:
            serial_excluded.extend(open_todos)
        else:
            expected.extend(open_todos)
    actual = sorted(t for t in bundle_todos if statuses.get(t) == "doing")
    expected_set = sorted(set(expected))
    missing = [t for t in expected_set if t not in actual]
    return {
        "expected": expected_set,
        "actual": actual,
        "missing": missing,
        "serial_excluded": sorted(set(serial_excluded)),
    }


def _plan_roots(state: dict, programme: dict | None) -> list:
    roots = [REPO_ROOT]
    if programme:
        for root in programme.get("worktree_roots") or []:
            if any(ch in str(root) for ch in "*?["):
                roots.extend(
                    Path(p)
                    for p in sorted(glob_mod.glob(str(root)))
                    if Path(p).is_dir()
                )
            else:
                roots.append(Path(str(root)))
    return roots


def _read_plan(state: dict, programme: dict | None, rel: str) -> str | None:
    for root in _plan_roots(state, programme):
        try:
            return (root / rel).read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def collect_frontier(state: dict, settings: Settings, now: datetime) -> bool:
    """Snapshot the frontier comparison for every
    armed bundle: the bundle's todos and statuses
    from the workbench surface (whichever served
    project carries the bundle), its plan's step
    blocks read from the owning repo, compared.
    Bundles whose plan cannot be read carry the
    error, never an invented frontier."""
    armed = state.get("armed_rows") or []
    bundles: dict[str, list] = {}
    for entry in armed:
        row = entry.get("row") or {}
        bundle = row.get("bundle")
        if bundle:
            bundles.setdefault(bundle, []).append(entry)
    if not bundles:
        if state.get("frontier_snapshot"):
            state["frontier_snapshot"] = {}
            return True
        return False
    try:
        projects = wb_client.fetch_projects(
            settings.wb_url, settings.wb_collect_timeout_s
        )
    except wb_client.WbUnavailable:
        return False
    todos_by_project: dict[str, dict] = {}
    for project in projects:
        try:
            payload = wb_client.fetch_todos(
                settings.wb_url, project, settings.wb_collect_timeout_s
            )
        except wb_client.WbUnavailable:
            continue
        todos_by_project[project] = {
            t.get("id"): t for t in payload.get("todos") or [] if t.get("id")
        }
    state_programmes = {p["slug"]: p for p in programmes.declarations(state)}
    snapshot: dict = {}
    for bundle, entries in sorted(bundles.items()):
        todo_ids = [e["todo"] for e in entries]
        served = None
        for project, todos in todos_by_project.items():
            if any(t in todos for t in todo_ids):
                served = (project, todos)
                break
        if served is None:
            continue
        project, todos = served
        bundle_todos = {tid: t for tid, t in todos.items() if t.get("bundle") == bundle}
        if not bundle_todos:
            bundle_todos = {tid: todos[tid] for tid in todo_ids if tid in todos}
        statuses = {tid: t.get("status") for tid, t in todos.items()}
        plan_rel = next(
            (t.get("plan") for t in bundle_todos.values() if t.get("plan")), None
        )
        named = {project} | {e.get("project") for e in entries}
        slug = None
        for row in registry.active_declarations():
            if named & set(registry.wb_projects_for(row)):
                slug = row["slug"]
                break
        entry_snapshot: dict = {
            "bundle": bundle,
            "project": project,
            "slug": slug,
            "at": now,
            "statuses": {tid: statuses.get(tid) for tid in bundle_todos},
        }
        text = None
        if plan_rel:
            text = _read_plan(state, state_programmes.get(slug or ""), plan_rel)
        if text is None:
            entry_snapshot["plan_error"] = f"plan not readable: {plan_rel}"
        else:
            entry_snapshot.update(
                frontier_for(parse_step_blocks(text), statuses, set(bundle_todos))
            )
        snapshot[bundle] = entry_snapshot
    before = {
        b: {k: v for k, v in e.items() if k != "at"}
        for b, e in (state.get("frontier_snapshot") or {}).items()
    }
    after = {b: {k: v for k, v in e.items() if k != "at"} for b, e in snapshot.items()}
    if after == before:
        return False
    state["frontier_snapshot"] = snapshot
    return True
