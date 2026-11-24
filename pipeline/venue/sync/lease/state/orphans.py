import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ..core import foundation, catalog, callers, records
from ..access import access
from ..sessions import identity, sessions

# --- Orphaned sessions: evidence and adoption ----------------------------------
#
# Local why: a live session with no lease record is invisible to
# budget attribution and deadline enforcement; its history lives
# only in the journals and kit configs the lifecycle left behind.
# Mechanics: docs/lease-workflow.md.


def _jsonl_events(path: Path) -> list[dict]:
    """Every JSON object in a .jsonl journal, in file order. A
    missing file reads as no events; a torn line is skipped —
    journals are evidence, never a reason to fail a read."""
    events: list[dict] = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return events
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _orphan_contribution(source: str, **fields) -> dict:
    contribution = {"source": source, "deadline": None, "acquired_at": None, "shape": None, "spec": None, "caller": None, "at": None}
    contribution.update(fields)
    return contribution


def _dt_or_none(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return foundation.parse_dt(value)
    except ValueError:
        return None


def orphan_evidence(repo: Path, session: str) -> dict:
    """Every local source's contribution to one unrecorded
    session's history: {session, sources, kit_installed,
    handover_pending}, each source a {source, deadline,
    acquired_at, shape, spec, caller, at} contribution (None
    where the source carries nothing). Reads are local-only and
    tolerant: a missing or unparseable source contributes
    nothing, never an exception (the load_json pattern).
    Deadline evidence lives in three places — the renewal
    kit's config and the session-evidence file (both verbatim
    copies of the record: the kit's at install, the evidence
    file's at every record save) and the panel outbox's
    lease-extended chain — and nowhere else: claims, liveness
    state, and run records carry caller/shape/first-seen
    evidence only. Detached shell records (results/detached/,
    the shell channel's async path) carry job evidence the
    same way run records do."""
    var = foundation.var_dir(repo)
    sources: list[dict] = []
    kit = foundation.load_json(var / f"renewal-config-{session}.json", None)
    kit_installed = isinstance(kit, dict)
    if kit_installed:
        spec = {"gpu": kit.get("gpu"), "tpu": kit.get("tpu"), "high_mem": bool(kit.get("high_mem"))}
        sources.append(_orphan_contribution("renewal-config", deadline=kit.get("deadline"), acquired_at=kit.get("acquired_at"), shape=kit.get("shape"), spec=spec))
    evidence_file = foundation.load_json(records.session_evidence_path(repo, session), None)
    if isinstance(evidence_file, dict):
        sources.append(_orphan_contribution("session-evidence", deadline=evidence_file.get("deadline"), acquired_at=evidence_file.get("acquired_at"), shape=evidence_file.get("shape"), spec=evidence_file.get("spec"), caller=evidence_file.get("caller")))
    for event in _jsonl_events(var / "ui-outbox.jsonl"):
        detail = event.get("detail")
        if event.get("kind") != "lease-extended" or not isinstance(detail, dict) or detail.get("session") != session:
            continue
        sources.append(_orphan_contribution("ui-outbox", deadline=detail.get("new_deadline"), at=event.get("ts")))
    for event in _jsonl_events(foundation.reaper_events_path(repo)):
        if session not in (event.get("session"), event.get("new_session")):
            continue
        if event.get("caller"):
            sources.append(_orphan_contribution("reaper-events", caller=event.get("caller"), at=event.get("ts")))
    for claim in _jsonl_events(callers.caller_claims_path(repo)):
        if claim.get("session") == session and claim.get("caller"):
            sources.append(_orphan_contribution("caller-claims", caller=claim.get("caller"), at=claim.get("ts")))
            break
    liveness = foundation.load_json(var / f"liveness-{session}.json", None)
    if isinstance(liveness, dict):
        sources.append(_orphan_contribution("liveness", shape=liveness.get("shape"), caller=liveness.get("caller"), at=liveness.get("first_seen")))
    runs_dir = repo / "results" / "runs"
    if runs_dir.is_dir():
        for path in sorted(runs_dir.glob("*.json")):
            run = foundation.load_json(path, None)
            if not isinstance(run, dict) or run.get("session") != session:
                continue
            contribution = _orphan_contribution("run-record", caller=run.get("caller"), at=run.get("started_at"))
            contribution["run_id"] = run.get("run_id") or path.stem
            contribution["state"] = run.get("state")
            sources.append(contribution)
    detached_dir = repo / "results" / "detached"
    if detached_dir.is_dir():
        for path in sorted(detached_dir.glob("*.json")):
            det = foundation.load_json(path, None)
            if not isinstance(det, dict) or det.get("session") != session:
                continue
            contribution = _orphan_contribution("detached-record", caller=det.get("caller"), at=det.get("started_at"))
            contribution["run_id"] = f"detached:{det.get('id') or path.stem}"
            contribution["state"] = det.get("state")
            contribution["finished_at"] = det.get("finished_at")
            sources.append(contribution)
    handover = foundation.load_json(var / "lease-handover.json", None)
    handover_pending = isinstance(handover, dict) and handover.get("child_session") == session
    return {"session": session, "sources": sources, "kit_installed": kit_installed, "handover_pending": handover_pending}


def derive_orphan(repo: Path, live_entry: dict, evidence_session: str | None = None) -> dict:
    """One orphan census entry, composed from the session's
    evidence by the priority ruling: the renewal-config's
    deadline/acquired_at/shape first (a verbatim copy of the
    record at kit install), the session-evidence projection
    ranked with it (the same record's copy at every save;
    E2), any later lease-extended outbox event applied over
    the base, and nothing else carrying a deadline. The record's creator is the renewal-origin
    caller in the reaper events, never the earliest claim — a
    claim is a ride, and a rider may predate nothing but their
    own attach. Every conflicting value is served with its
    source; the operator can always override at adoption.
    Shape from evidence first, else the live entry's class
    cross-checked against the catalog: candidates are the
    entries consistent with the class evidence (a high-RAM
    endpoint names high memory, not an accelerator, so its
    candidates span the high-memory CPU and accelerator
    shapes); more than one candidate is ambiguity, never a
    guess. `evidence_session` overrides the name the evidence
    is read under (nameless adoption: the minted live name
    has no history; the endpoint's prior name does)."""
    session = live_entry.get("session")
    # The evidence is read under the live entry's own name,
    # except in the nameless-adoption flow: there the live
    # entry carries a freshly minted name with no history,
    # and the caller names the prior name the endpoint's
    # identity stamps recovered — the same evidence chain,
    # read under the name it was written for.
    evidence = orphan_evidence(repo, evidence_session or session)
    by_source: dict[str, list[dict]] = {}
    for contribution in evidence["sources"]:
        by_source.setdefault(contribution["source"], []).append(contribution)

    derived_deadline = None
    deadline_source = None
    deadline_stale_possible = False
    acquired_at = None
    shape = None
    shape_spec = None
    shape_evidenced = False
    # The base is a verbatim copy of the record: the renewal
    # kit's config first, the session-evidence projection
    # ranked with it (E2) — the two are copies of the same
    # record, so either serves when the other is gone, and a
    # disagreement between them is served as a conflict below.
    kit_cfg = (by_source.get("renewal-config") or [None])[0]
    base_cfg = kit_cfg
    base_source = "renewal-config"
    if base_cfg is None:
        base_cfg = (by_source.get("session-evidence") or [None])[0]
        base_source = "session-evidence"
    if base_cfg is not None:
        acquired_at = base_cfg.get("acquired_at")
        if base_cfg.get("deadline"):
            derived_deadline = base_cfg["deadline"]
            deadline_source = base_source
        if base_cfg.get("spec"):
            shape_spec = base_cfg["spec"]
            shape = catalog.shape_id_for(shape_spec.get("gpu"), shape_spec.get("tpu"), shape_spec.get("high_mem"))
            shape_evidenced = True
        elif base_cfg.get("shape"):
            shape = base_cfg["shape"]
            shape_evidenced = True
    extensions = by_source.get("ui-outbox") or []
    if extensions:
        last = extensions[-1]
        if _dt_or_none(last.get("deadline")) is not None:
            derived_deadline = last["deadline"]
            deadline_source = "ui-outbox"
        else:
            # An extension the config cannot reflect (extend does
            # not rewrite it once the kit is installed) whose
            # outbox event carries no usable new deadline: the
            # derived value may be stale, and says so.
            deadline_stale_possible = True

    conflicts: list[dict] = []
    deadline_values = []
    if kit_cfg is not None and kit_cfg.get("deadline"):
        deadline_values.append({"source": "renewal-config", "value": kit_cfg["deadline"]})
    evidence_cfg = (by_source.get("session-evidence") or [None])[0]
    if evidence_cfg is not None and evidence_cfg.get("deadline"):
        deadline_values.append({"source": "session-evidence", "value": evidence_cfg["deadline"]})
    for contribution in extensions:
        if contribution.get("deadline"):
            deadline_values.append({"source": "ui-outbox", "value": contribution["deadline"]})
    if len({v["value"] for v in deadline_values}) > 1:
        conflicts.append({"field": "deadline", "values": deadline_values})

    creator_caller = None
    creator_source = None
    for contribution in by_source.get("reaper-events") or []:
        if contribution.get("caller"):
            creator_caller = contribution["caller"]
            creator_source = "reaper-events"
            break
    if creator_caller is None and evidence_cfg is not None and evidence_cfg.get("caller"):
        # The session-evidence file is the record's own
        # projection, so its caller is the record's creator
        # stamp — not a claim. It ranks below the reaper
        # events' renewal-origin caller, which stays the
        # authority when both speak.
        creator_caller = evidence_cfg["caller"]
        creator_source = "session-evidence"
    first_claim = None
    claim = (by_source.get("caller-claims") or [None])[0]
    if claim is not None:
        first_claim = claim.get("caller")
    if creator_caller and first_claim and creator_caller != first_claim:
        conflicts.append({"field": "caller", "values": [{"source": creator_source, "value": creator_caller}, {"source": "caller-claims", "value": first_claim}]})

    shape_candidates: list[str] = []
    if not shape_evidenced:
        cls = live_entry.get("shape_class")
        entries = catalog.catalog_shapes(repo)
        if cls == "high_ram":
            shape_candidates = [sid for sid, entry in entries.items() if entry.get("high_mem")]
        elif cls == "standard":
            shape_candidates = [sid for sid, entry in entries.items() if not entry.get("high_mem")]
        if len(shape_candidates) == 1:
            shape = shape_candidates[0]

    # In-flight jobs: the pruned-jobs projection (records)
    # resolved over the census's own contributions — a run or
    # detached record counts only while it exists and is
    # non-terminal. The count is served as a count; the entries
    # ride under their own name, each kinded with its backing
    # record's state and start. Detached work (E8) enters under
    # its detached:<id> name, the name the shell lane registers
    # it by.
    jobs_entries: list[dict] = []
    seen_job_ids: set[str] = set()
    contributions = (by_source.get("run-record") or []) + (by_source.get("detached-record") or [])
    for contribution in contributions:
        run_id = contribution.get("run_id")
        if not run_id or run_id in seen_job_ids:
            continue
        entry = records.job_entry(repo, run_id)
        if entry is not None:
            jobs_entries.append(entry)
            seen_job_ids.add(run_id)
    seen = [c["at"] for c in evidence["sources"] if c.get("at")]
    stamp = access.load_unattributed(repo).get(evidence_session or session) or {}
    if stamp.get("first_seen"):
        seen.append(stamp["first_seen"])
    return {
        "session": session,
        "endpoint": live_entry.get("endpoint"),
        "shape_class": live_entry.get("shape_class"),
        "shape": shape,
        "shape_spec": shape_spec,
        "shape_evidenced": shape_evidenced,
        "shape_candidates": shape_candidates,
        "creator_caller": creator_caller,
        "first_claim": first_claim,
        "derived_deadline": derived_deadline,
        "deadline_source": deadline_source,
        "deadline_stale_possible": deadline_stale_possible,
        "conflicts": conflicts,
        "acquired_at": acquired_at,
        "jobs_in_flight": len(jobs_entries),
        "jobs_in_flight_entries": jobs_entries,
        "first_seen": min(seen) if seen else None,
        "kit_installed": evidence["kit_installed"],
        "handover_pending": evidence["handover_pending"],
    }


# --- Nameless assignments: the endpoint-keyed census ----------------------------
#
# Local why: an assignment whose name is lost server-side is
# invisible to the name-keyed census above — it bills on with
# no row anywhere (the first-rotation pair stood
# assigned for hours before a human read the assignments list
# by hand). The reap pass detects them (detect_nameless,
# beside unattributed detection) and the census serves them
# as rows the moment they are seen: adoptable by endpoint, or
# surfaced for release — never a standing idle-billing state.


def nameless_census_path(repo: Path) -> Path:
    return foundation.var_dir(repo) / "nameless-census.json"


def recorded_endpoints(repo: Path, recorded: set) -> set:
    """The endpoints the lease records already account for:
    each record's identity-stamp endpoint, plus its local
    binding endpoint — the two places a record's runtime
    address is written. Raw forms are kept (URL, host, bare);
    callers compare with sessions.endpoints_match."""
    out: set = set()
    for name in recorded:
        if not name:
            continue
        stamp = identity.read_stamp(repo, name)
        for key in ("endpoint", "host"):
            if stamp.get(key):
                out.add(stamp[key])
        bound = sessions.session_endpoint(name)
        if bound:
            out.add(bound)
    return out


def nameless_census(repo: Path, assignments: list, live: list | None, recorded: set) -> list[dict]:
    """One census row per assigned-but-unaccounted endpoint:
    an assignment is accounted when a live entry with a usable
    name carries its endpoint (a named orphan's row, or a
    recorded session) or a lease record's stamp/binding names
    it. Each row is the derive_orphan composition read under
    the endpoint's prior name when an identity stamp recovers
    one — the same evidence, the same priority — re-keyed to
    the endpoint: session None, nameless True, prior_session
    the recovered name or None, and the burn rate the resolved
    shape carries (None when no shape resolves: an unconfirmed
    rate projects nothing)."""
    accounted: set = set()
    for entry in live or []:
        name = entry.get("session")
        if name and name != "?" and entry.get("endpoint"):
            accounted.add(entry["endpoint"])
    accounted |= recorded_endpoints(repo, recorded)
    rows: list[dict] = []
    for assignment in assignments or []:
        ep = assignment.get("endpoint")
        if not ep or any(sessions.endpoints_match(ep, acc) for acc in accounted):
            continue
        priors = sessions.prior_names_for_endpoint(repo, ep)
        prior = priors[0] if priors else None
        entry = {"session": prior or "?", "endpoint": ep, "shape_class": assignment.get("shape_class")}
        row = derive_orphan(repo, entry, evidence_session=prior)
        row["session"] = None
        row["nameless"] = True
        row["prior_session"] = prior
        row["endpoint"] = ep
        row["shape_class"] = assignment.get("shape_class")
        row["rate_cu_per_hour"] = catalog.shape_rate(repo, row["shape"]) if row.get("shape") else None
        rows.append(row)
    return rows


def load_nameless_census(repo: Path) -> list[dict]:
    """The reap pass's stored nameless rows, [] when none are
    stored. A torn file reads as no rows — the next pass
    rewrites it, and a census never fails on its own store."""
    data = foundation.load_json(nameless_census_path(repo), None)
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        return []
    return [row for row in data["rows"] if isinstance(row, dict)]


def clear_nameless(repo: Path, endpoint: str) -> None:
    """Drop one endpoint's stored census row — the release
    verb's clear, the clear_unattributed pattern. The reap
    pass recomputes the census wholesale each pass, so the
    clear lasts exactly as long as the assignment stays
    gone; a row whose assignment survives reappears on the
    next pass rather than staying hidden by hand."""
    data = foundation.load_json(nameless_census_path(repo), None)
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        return
    rows = [row for row in data["rows"]
            if not (isinstance(row, dict)
                    and sessions.endpoints_match(row.get("endpoint"), endpoint))]
    if len(rows) == len(data["rows"]):
        return
    data["rows"] = rows
    foundation.staged_write(
        nameless_census_path(repo), json.dumps(data).encode())


def detect_nameless(repo: Path, live: list | None, now_dt: datetime) -> dict:
    """Nameless detection, run by reap() each pass beside
    unattributed detection: read the server's assignments (one
    bounded library read), compose the nameless census, store
    it for the served census, and spool a reaper event per
    endpoint as it appears (nameless-assignment) and clears
    (nameless-cleared) — the unattributed pattern, keyed by
    endpoint. An unreadable live list or assignments read
    detects nothing and keeps the stored census: detection
    never acts on a list it could not read."""
    if live is None:
        return {"detected": [], "cleared": [], "unreadable": True}
    assignments = sessions.assignments_list(timeout=45)
    if assignments is None:
        return {"detected": [], "cleared": [], "unreadable": True}
    recorded = {rec.get("session") for rec in records.all_records(repo)}
    rows = nameless_census(repo, assignments, live, recorded)
    previous = {row.get("endpoint") for row in load_nameless_census(repo)}
    current = {row.get("endpoint") for row in rows}
    detected: list[str] = []
    for row in rows:
        ep = row.get("endpoint")
        if ep and ep not in previous:
            foundation.append_reaper_event(repo, {"kind": "nameless-assignment", "endpoint": ep, "prior_session": row.get("prior_session"), "shape_class": row.get("shape_class"), "first_seen": now_dt.isoformat()})
            detected.append(ep)
    cleared: list[str] = []
    for ep in sorted(previous - current):
        if ep:
            foundation.append_reaper_event(repo, {"kind": "nameless-cleared", "endpoint": ep})
            cleared.append(ep)
    foundation.staged_write(nameless_census_path(repo), json.dumps({"written_at": now_dt.isoformat(), "rows": rows}).encode())
    return {"detected": detected, "cleared": cleared}
