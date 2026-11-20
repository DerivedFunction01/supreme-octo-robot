"""Staffing row builders (spec §1.11): the fleet-
independent defect classes — phantom stops, blocked
states, unrouted defects, serial plans, owner-waiting —
and, from Step 2 of the supervision plan, the venue
family-concurrency rows and the plan-frontier
shortfall rows the registry contracts declare.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from attention.services import programmes
from attention.services.measure import registry, venue
from attention.services.reads import digest as digest_mod
from attention.services.reads import model


def _as_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            stamp = datetime.fromisoformat(value)
        except ValueError:
            return None
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    return None


KIND_LABELS = {
    "understaffed": "Understaffed",
    "fleet_idle": "Idle session",
    "idle_unlanded": "Idle — work complete",
    "no_successor": "No successor staffed",
    "record_gap": "Record not moving",
    "phantom_stop": "Unverified owner stop",
    "unrouted_defect": "Unrouted defect",
    "blocked_uncited": "Blocked — no basis",
    "blocked_unverified": "Blocked — unverified",
    "steer_undeliverable": "Steer undeliverable",
    "owner_waiting": "Owner waiting",
    "owner_waiting_unanswered": "Owner waiting — ask unanswered",
    "armed_unreported": "Armed — no checkpoint yet",
    "unlanded_claim": "Done claimed — worktree unlanded",
    "unarmed_work": "Worktree standing — unarmed",
    "orphan_record": "Orphaned run record",
    "serial_staffing": "Serial staffing",
    "frontier_shortfall": "Frontier shortfall",
}
WORKHORSE_TERMS = {
    "scheduler": ("scheduler",),
    "workbench": ("workbench", "harness"),
    "colab": ("colab", "lease runner", "lease panel"),
}
OWNER_THREADS = {
    "scheduler": "the scheduler thread",
    "workbench": "the workbench viewer thread",
    "colab": "the Colab panel thread",
}


def _names_workhorse(text) -> str | None:
    low = (text or "").lower()
    for name, terms in WORKHORSE_TERMS.items():
        if any(term in low for term in terms):
            return name
    return None


def _unrouted_rows(state: dict) -> list:
    """§1.11 (j): a workhorse defect in a lane's queue item
    with no routing, addressed to the lane; it clears
    when the item carries routing, not on ack."""
    handlers = model.handler_map(state)
    rows = []

    def add(handle, text, key):
        workhorse = _names_workhorse(text)
        if not workhorse:
            return
        rows.append(
            _row(
                digest_mod.topic_of(handle),
                handle,
                handlers.get(handle, {}).get("label", handle),
                "unrouted_defect",
                f"A defect naming the {workhorse} workhorse "
                f"carries no routing: {OWNER_THREADS[workhorse]} "
                f"has not been notified. It clears when the "
                f"item carries its routing.",
                key=key,
            )
        )

    for item in state.get("items", []):
        if (
            item.get("kind") == "defect"
            and item.get("triage") == "open"
            and not item.get("routing")
        ):
            add(item["handle"], item.get("title"), f"unrouted_defect:{item['id']}")
    return rows


_CLAIM_RE = re.compile(
    r"owner.{0,40}(order|instruct|direct|said|asked|told|stop|halt|"
    r"stood|stand[ -]down|pause)|(order|stop|halt|instruction|direction)"
    r".{0,30}owner",
    re.IGNORECASE,
)


def _claims_owner_order(text: str) -> bool:
    return bool(text) and bool(_CLAIM_RE.search(text))


_CITATION_RE = re.compile(
    r"thread[:\s]+\S+.{0,120}?\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",
    re.IGNORECASE,
)


def _find_citation(body: str) -> str | None:
    """A blocked todo's citation: a body line naming the
    owner's message thread and the time — the basis a
    blocked claim stands on. None when no line carries
    both."""
    for line in (body or "").splitlines():
        if _CITATION_RE.search(line):
            return line.strip()
    return None


def _blocked_todos(state: dict) -> list:
    """Every blocked todo in the snapshot, with its
    programme: (programme, entry) pairs."""
    out = []
    for programme in programmes.active_declarations(state):
        entry = (state.get("blocked_snapshot") or {}).get(programme["slug"]) or {}
        for todo in entry.get("blocked") or []:
            out.append((programme, todo))
    return out


def _phantom_rows(state: dict, now: datetime) -> list:
    """§1.11 (i): an uncited owner-instruction claim in a
    blocked todo's body is a defect addressed to main,
    priced with its frozen duration; a cited claim is a
    state. The frozen clock runs from the body's latest
    checkpoint — the lane's last act."""
    rows = []
    for programme, todo in _blocked_todos(state):
        body = todo.get("body") or ""
        if _find_citation(body):
            continue
        if not _claims_owner_order(body):
            continue
        stamp = _as_dt(todo.get("checkpoint_at"))
        frozen = int((now - stamp).total_seconds() // 60) if stamp is not None else None
        detail = (
            f"Frozen {frozen} minutes on a claimed owner "
            f"instruction that cites no owner message. The "
            f"claim is unverified; it is addressed to main "
            f"for verification, never held as a state."
            if frozen is not None
            else "A claimed owner instruction cites no owner "
            "message, and the record carries no checkpoint "
            "to date the claim. The claim is unverified; "
            "it is addressed to main for verification, "
            "never held as a state."
        )
        handle = (programme.get("handles") or [programme["slug"]])[0]
        row = _row(
            programme["slug"],
            handle,
            programme["label"],
            "phantom_stop",
            detail,
            idle_minutes=frozen,
            key=f"phantom_stop:{programme['slug']}:{todo.get('todo')}",
        )
        row["escalation"] = "main"
        rows.append(row)
    return rows


def _blocked_rows(state: dict, now: datetime, cadence_of, skip: set) -> list:
    """Blocked is a supervised state (§1.11 (i)
    addenda): no stated basis, or a cited basis main
    has not stamped past one check cycle, is a row.
    `skip` holds the phantom rows' keys — a claim the
    phantom row already carries is not reported twice."""
    stamped = {v["handle"] for v in state.get("verifications", [])}
    rows = []
    for programme, todo in _blocked_todos(state):
        phantom_key = f"phantom_stop:{programme['slug']}:{todo.get('todo')}"
        if phantom_key in skip:
            continue
        handle = (programme.get("handles") or [programme["slug"]])[0]
        topic = programme["slug"]
        label = programme["label"]
        body = (todo.get("body") or "").strip()
        if not body:
            row = _row(
                topic,
                handle,
                label,
                "blocked_uncited",
                "Blocked with no stated basis: the todo "
                "body carries no blocker note, so nothing "
                "cites what it waits on.",
                key=f"blocked_uncited:{programme['slug']}:{todo.get('todo')}",
            )
            row["escalation"] = "main"
            rows.append(row)
            continue
        citation = _find_citation(body)
        if citation and handle not in stamped:
            stamp = _as_dt(todo.get("checkpoint_at"))
            if stamp is None:
                continue
            age = int((now - stamp).total_seconds() // 60)
            if age > cadence_of(handle):
                row = _row(
                    topic,
                    handle,
                    label,
                    "blocked_unverified",
                    f"Blocked on a cited basis main has not "
                    f"stamped for {age} minutes — past one "
                    f"check cycle. The verification is main's.",
                    idle_minutes=age,
                    key=f"blocked_unverified:{programme['slug']}:{todo.get('todo')}",
                )
                row["escalation"] = "main"
                rows.append(row)
    return rows


def _latest_lane_stamp(state: dict, programme: dict) -> datetime | None:
    """The programme's newest lane record: the latest
    checkpoint stamp across its armed todos, or the
    latest checkpoint in its declared lane record files
    — whichever moved last. None when nothing moved."""
    latest = None
    stamps = (state.get("stamp_snapshot") or {}).get(programme["slug"]) or {}
    for value in (stamps.get("stamps") or {}).values():
        stamp = _as_dt(value)
        if stamp is not None and (latest is None or stamp > latest):
            latest = stamp
    records = (state.get("record_snapshot") or {}).get(programme["slug"]) or {}
    for record in (records.get("records") or {}).values():
        stamp = _as_dt(record.get("checkpoint_at"))
        if stamp is not None and (latest is None or stamp > latest):
            latest = stamp
    return latest


def _owner_waiting_rows(state, now, cadence_of, counts=None) -> list:
    """§1.11 (l): past one check cycle with no staffing
    measure and no record newer than the declaration, an
    owner-waiting declaration from the goal store is a row
    to main at once."""
    pings = state.get("pings") or {}
    rows = []
    for programme in programmes.active_declarations(state):
        entry = (state.get("goal_snapshot") or {}).get(programme["slug"]) or {}
        decls = entry.get("owner_waiting") or []
        if not decls:
            continue
        handles = programme.get("handles") or [programme["slug"]]
        handle = handles[0]
        label = programme["label"]
        topic = programme["slug"]
        latest = _latest_lane_stamp(state, programme)
        for decl in decls:
            commissioned = _as_dt(decl.get("commissioned_at"))
            declared_at = _as_dt(decl.get("declared_at")) or commissioned
            if commissioned is None:
                continue
            waiting = int((now - commissioned).total_seconds() // 60)
            staffed = False
            if counts is not None:
                entry_counts = counts.get(topic) or {}
                evidence = entry_counts.get("evidence")
                staffed = entry_counts.get("workers", 0) > 0 or (
                    evidence is not None and evidence > commissioned
                )
            if (
                (now - commissioned).total_seconds() > cadence_of(handle) * 60
                and (latest is None or latest <= declared_at)
                and not staffed
            ):
                row = _row(
                    topic,
                    handle,
                    label,
                    "owner_waiting",
                    f"The owner has waited {waiting} minutes on "
                    f"{decl['label']}: no workers measured for "
                    f"its topic and no lane record since the "
                    f"commission — past one check cycle. "
                    f"Owner-waiting outranks queue position.",
                    idle_minutes=waiting,
                    key=f"owner_waiting:{programme['slug']}:{decl.get('goal')}",
                )
                row["escalation"] = "main"
                rows.append(row)
            ping = pings.get(handle) or {}
            last_ask = _as_dt(ping.get("last_at"))
            if (
                last_ask is not None
                and (latest is None or latest <= last_ask)
                and (now - last_ask).total_seconds() > cadence_of(handle) * 60
            ):
                ask_age = int((now - last_ask).total_seconds() // 60)
                row = _row(
                    topic,
                    handle,
                    label,
                    "owner_waiting_unanswered",
                    f"An ask about {decl['label']} has "
                    f"gone unanswered for {ask_age} minutes — "
                    f"past one check cycle; the owner has "
                    f"waited {waiting} minutes since the "
                    f"commission. The answer precedes lane work.",
                    idle_minutes=waiting,
                    key=f"owner_waiting_unanswered:{programme['slug']}:{decl.get('goal')}",
                )
                row["escalation"] = "main"
                rows.append(row)
    return rows


def _armed_rows(state, now) -> list:
    """Armed work no checkpoint has picked up: a harness
    row older than two of its cadence intervals with no
    checkpoint stamp for its todo is unsupervised work —
    the lane has not started reporting, or has stopped."""
    stamps = state.get("stamp_snapshot") or {}
    stamped: set = set()
    for _slug, entry in stamps.items():
        for todo in entry.get("stamps") or {}:
            stamped.add(todo)
    rows = []
    for entry in state.get("armed_rows") or []:
        row = entry.get("row") or {}
        todo = entry.get("todo")
        if not todo or todo in stamped:
            continue
        armed_at = _as_dt(row.get("armed_at")) or _as_dt(entry.get("ingested_at"))
        if armed_at is None:
            continue
        cadence = row.get("cadence_minutes") or 15.0
        age = int((now - armed_at).total_seconds() // 60)
        if age <= 2 * cadence:
            continue
        rows.append(
            _row(
                entry.get("project"),
                todo,
                row.get("title") or todo,
                "armed_unreported",
                f"Armed {age} minutes ago; no checkpoint "
                f"names this todo after two cadence "
                f"intervals — the lane is unsupervised, "
                f"or the work has not started.",
                idle_minutes=age,
                key=f"armed_unreported:{entry.get('project')}:{todo}",
            )
        )
    return rows


def _worktree_rows(state, now, wb_topics=None) -> list:
    """The two derived checks on worktree presence: work
    that reads done in the workbench while trees stand
    unlanded, and a standing tree with no arm and no
    done work — unarmed. A standing tree is unfinished
    work whatever any earlier claim said."""
    snapshot = state.get("worktree_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for programme in programmes.active_declarations(state):
        entry = snapshot.get(programme["slug"])
        if not entry:
            continue
        trees = entry.get("trees") or []
        if not trees:
            continue
        handles = programme.get("handles") or []
        handle = handles[0] if handles else programme["slug"]
        armed = programmes.armed_entries(state, programme)
        info = (wb_topics or {}).get(programme["slug"]) or {}
        done = bool(
            info.get("todos_total") and info.get("todos_done", 0) >= info["todos_total"]
        )
        unlanded = [t for t in trees if t.get("landed") is False]
        if done and unlanded:
            names = ", ".join(t["name"] for t in unlanded[:3])
            rows.append(
                _row(
                    programme["slug"],
                    handle,
                    programme["label"],
                    "unlanded_claim",
                    f"The work reads done for this programme "
                    f"while {len(unlanded)} worktree(s) stand "
                    f"unlanded ({names}) — the claim is "
                    f"reported against the tree, not taken.",
                    key=f"unlanded_claim:{programme['slug']}",
                )
            )
        if not done and not armed:
            rows.append(
                _row(
                    programme["slug"],
                    handle,
                    programme["label"],
                    "unarmed_work",
                    f"{len(trees)} worktree(s) stand for this "
                    f"programme with no armed registry row and "
                    f"no done work — work standing "
                    f"unsupervised.",
                    key=f"unarmed_work:{programme['slug']}",
                )
            )
    return rows


def _record_rows(state, now, cadence_of) -> list:
    """A declared lane record whose latest conforming
    checkpoint is older than two cadence intervals is a
    record gap — the lane owes a checkpoint or a blocker."""
    snapshot = state.get("record_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for programme in programmes.declarations(state):
        entry = snapshot.get(programme["slug"])
        if not entry:
            continue
        cadence = programme.get("cadence_minutes") or cadence_of(
            (programme.get("handles") or [programme["slug"]])[0]
        )
        handles = programme.get("handles") or [programme["slug"]]
        for record in (entry.get("records") or {}).values():
            stamp = record.get("checkpoint_at")
            stamp = _as_dt(stamp) if stamp else None
            gap = None if stamp is None else (now - stamp).total_seconds() / 60
            if gap is not None and gap <= 2 * cadence:
                continue
            detail = (
                "No conforming progress-checkpoint in this "
                "lane's record yet — the lane owes its first "
                "checkpoint or its exact blocker."
                if gap is None
                else f"Latest conforming checkpoint in this "
                f"lane's record is {round(gap)}m old against a "
                f"{cadence:g}m cadence — a record gap: the lane "
                f"owes a checkpoint or its exact blocker."
            )
            rows.append(
                _row(
                    programme["slug"],
                    handles[0],
                    f"{programme['label']} — {record['lane']}",
                    "record_gap",
                    detail,
                    key=f"record_gap:{programme['slug']}:{record['lane']}",
                )
            )
    return rows


def _orphan_rows(state: dict, now: datetime) -> list:
    """The sweep's orphan class, from the venue
    snapshot: a run record claiming work the records
    do not support — no payload finish, evidence
    stale past the programme's window. The row names
    the record, its session, and the evidence age;
    it clears when the record is disposed (abandoned
    and re-fired) or its finish lands. Gated on the
    programme declaring the orphan class."""
    snapshot = state.get("venue_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for declaration in registry.active_declarations():
        slug = declaration["slug"]
        if "orphan" not in registry.measure_classes_for(slug):
            continue
        facts = snapshot.get(slug)
        if not facts:
            continue
        contract = registry.staffing_contract_for(slug)
        window = (
            contract["evidence_window_minutes"]
            if contract
            else venue.DEFAULT_EVIDENCE_WINDOW_MINUTES
        )
        handle = (declaration.get("handles") or [slug])[0]
        for entry in facts.get("orphans") or []:
            evidence = _as_dt(entry.get("evidence_at"))
            age = int((now - evidence).total_seconds() // 60) if evidence else None
            age_text = f"{age} minutes ago" if age is not None else "never"
            rows.append(
                _row(
                    slug,
                    handle,
                    declaration["label"],
                    "orphan_record",
                    f"Run {entry['id']} ({entry.get('job') or 'unnamed job'}) "
                    f"on {entry.get('session') or 'no session'} claims "
                    f"state {entry.get('state') or 'unknown'} with no "
                    f"payload finish; its last evidence advanced "
                    f"{age_text} against a {window:g}-minute window — "
                    f"the launch died or the record stuck, and no lane "
                    f"is advancing it. Next act: dispose the record — "
                    f"abandon the launch and re-fire the work — and "
                    f"verify the collecting lane.",
                    idle_minutes=age,
                    key=f"orphan_record:{slug}:{entry['id']}",
                    extra={
                        "run_id": entry["id"],
                        "job": entry.get("job"),
                        "session": entry.get("session"),
                    },
                )
            )
    return rows


def _programme_armed(state: dict, row: dict) -> list:
    """The armed rows a registry declaration owns,
    matched through its declared wb projects (the
    same linkage the frontier keys bundles by)."""
    projects = set(registry.wb_projects_for(row))
    return [
        entry
        for entry in state.get("armed_rows") or []
        if entry.get("project") in projects
        or (entry.get("row") or {}).get("programme") == row["slug"]
    ]


def _family_rows(state: dict, now: datetime, live: list, idle_since: dict) -> list:
    """The family-concurrency measure (owner
    enforcement ruling, 2026-11-19, carried as the
    registry's staffing contract): fewer families in
    flight than the contract's minimum, or all
    compute on one session while another live session
    carries none, is a serial staffing defect while
    open family work stands. Facts come from the
    venue snapshot; the bands come from the registry
    — no evaluator constants, no programme names."""
    snapshot = state.get("venue_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for declaration in registry.active_declarations():
        slug = declaration["slug"]
        contract = registry.staffing_contract_for(slug)
        if contract is None:
            continue
        if "serial" not in registry.measure_classes_for(slug):
            continue
        facts = snapshot.get(slug)
        if not facts:
            continue
        if len(live) < contract["min_live_sessions"]:
            continue
        if not _programme_armed(state, declaration):
            continue
        families = facts.get("families") or {}
        carrying_sessions = {
            session
            for entry in families.values()
            for session in entry.get("sessions") or []
            if session in live
        }
        idle_sessions = []
        for name in live:
            if name in carrying_sessions:
                continue
            since = _as_dt(idle_since.get(name))
            minutes = int((now - since).total_seconds() // 60) if since else 0
            idle_sessions.append({"name": name, "idle_minutes": minutes})
        conditions = []
        if len(families) < contract["min_families_in_flight"]:
            conditions.append("fewer_than_min_families_in_flight")
        if (
            len(carrying_sessions) < contract["min_sessions_carrying_work"]
            and idle_sessions
            and families
        ):
            conditions.append(
                "all_compute_on_one_session_while_another_live_session_carries_none"
            )
        if not conditions:
            continue
        handle = (declaration.get("handles") or [slug])[0]
        fam_text = ", ".join(
            f"{name} on {', '.join(entry.get('sessions') or []) or 'no session'}"
            for name, entry in sorted(families.items())
        )
        parts = [
            f"{len(families)} famil{'y' if len(families) == 1 else 'ies'} "
            f"in flight ({fam_text or 'none'}) against a minimum of "
            f"{contract['min_families_in_flight']}, measured from venue "
            f"run records over a {contract['evidence_window_minutes']}-"
            f"minute evidence window."
        ]
        if idle_sessions:
            idle_text = ", ".join(
                f"{s['name']} idle {s['idle_minutes']}m" for s in idle_sessions
            )
            parts.append(
                f"Live sessions carrying no work: {idle_text} — while "
                f"open family work stands, that idleness is priced here."
            )
        parts.append(
            "The defect clears only on a later measure at or above the "
            "contract's bands — never on an acknowledgement."
        )
        rows.append(
            _row(
                slug,
                handle,
                declaration["label"],
                "serial_staffing",
                " ".join(parts),
                workers=facts.get("workers"),
                child_workers=facts.get("child_workers"),
                sessions_used=len(carrying_sessions),
                sessions_live=len(live),
                idle_minutes=max((s["idle_minutes"] for s in idle_sessions), default=0),
                jobs_run=facts.get("jobs"),
                key=f"serial_staffing:{slug}",
                extra={
                    "families": [
                        {
                            "name": name,
                            "sessions": entry.get("sessions") or [],
                            "runs": entry.get("runs"),
                            "child_runs": entry.get("child_runs"),
                        }
                        for name, entry in sorted(families.items())
                    ],
                    "idle_sessions": idle_sessions,
                    "conditions": conditions,
                    "coordinator_caller": facts.get("coordinator_caller"),
                },
            )
        )
    return rows


def _frontier_rows(state: dict) -> list:
    """The plan-frontier comparison (supervision
    plan, Step 2 as amended): an armed bundle whose
    declared fan-out — its plan's eligible fanout
    steps, serial exceptions excluded — exceeds its
    actual in-flight set stands short; the shortfall
    is a staffing defect of the same class, and this
    row is the form the reminder's ping takes."""
    snapshot = state.get("frontier_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for bundle, entry in sorted(snapshot.items()):
        missing = entry.get("missing") or []
        if not missing or entry.get("plan_error"):
            continue
        slug = entry.get("slug")
        declaration = registry.for_slug(slug) if slug else None
        if declaration and "serial" not in registry.measure_classes_for(slug):
            continue
        handle = (declaration.get("handles") or [None])[0] if declaration else None
        label = declaration["label"] if declaration else bundle
        expected = entry.get("expected") or []
        actual = entry.get("actual") or []
        serial = entry.get("serial_excluded") or []
        detail = (
            f"Bundle {bundle}: the plan's declared frontier expects "
            f"{', '.join(expected)} in flight — fanout steps whose "
            f"prerequisites have landed — but the actual in-flight "
            f"set is {', '.join(actual) or 'empty'}; "
            f"{', '.join(missing)} stand unstaffed."
        )
        if serial:
            detail += (
                f" Serial exceptions excluded by the plan's own "
                f"declaration: {', '.join(serial)}."
            )
        rows.append(
            _row(
                slug or entry.get("project"),
                handle,
                label,
                "frontier_shortfall",
                detail,
                key=f"frontier_shortfall:{bundle}",
                extra={
                    "bundle": bundle,
                    "expected": expected,
                    "actual": actual,
                    "missing": missing,
                    "serial_excluded": serial,
                },
            )
        )
    return rows


def _row(topic, handle, label, kind, detail, **evidence) -> dict:
    row = {
        "topic": topic,
        "handle": handle,
        "handler_label": label,
        "kind": kind,
        "kind_label": KIND_LABELS[kind],
        "workers": evidence.get("workers"),
        "child_workers": evidence.get("child_workers"),
        "sessions_used": evidence.get("sessions_used", 0),
        "sessions_live": evidence.get("sessions_live", 0),
        "idle_minutes": evidence.get("idle_minutes"),
        "checkpoint_gap_minutes": evidence.get("checkpoint_gap_minutes"),
        "stall_minutes": None,
        "jobs_run": evidence.get("jobs_run"),
        "expected_minutes": None,
        "owner_directed": False,
        "escalation": "lane",
        "detail": detail,
    }
    row.update(evidence.get("extra") or {})
    row["_key"] = evidence.get("key") or f"{kind}:{topic or handle or ''}"
    return row
