"""Lane records (lane-records plan, Steps 1 and 3):
a programme's lanes declared as records in the
existing record form — the same files the record
collector already reads for checkpoints, carrying a
lane-record block per lane — snapshotted for the
measure on the slow loop beside the record snapshot.

The record's lifecycle is the plan's: Declare (the
coordinator posts an expected count and one block
per lane, with its estimate and termination
condition), Ping (the declaration stays live only
while the lane's own checkpoint/state writes move —
a conforming progress-checkpoint line in the lane's
record, or a write to the lane's own record file;
never a manual act), Renew (at estimate end the
lane renews with a new estimate or terminates; the
record carries estimate against actual and the
renewal count), Terminate (only on an explicit
checkable condition — a landed SHA, a delivered
record path, a queue item pruned as landed in the
evidence; never by silence, expiry, or say-so — an
expired, unrenewed, unterminated declaration is an
escalated row, not a closed lane).

The venue field is always present: a session name,
or the declared value "none" for an authoring-side
lane. A block without one is refused — dropped and
counted in the snapshot, never silently read. A
lane may declare gap-wait: it names what is planted
and waited on, and does not end for want of a
session.

Seeding: a programme's registry declaration may
carry lane declarations in the registry-contract
form (the migration form — one programme's declaration is
seeded so); the collector merges them with record
blocks by key, the record block winning. The
measure reads lane records as its primary staffing
source: expected reconciles the contract's
staffable queue with the declared records, actual
is the open, non-stale lane records, and the
cross-checks run both ways against venue run
records and worktree activity.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from attention.paths import WORKSPACE_ROOT
from attention.services import programmes
from attention.services.measure import records, registry, stamps
from attention.services.measure.staffing_common import _row

LANE_BLOCK_START = re.compile(r"<!--\s*lane-record\s*$")
DECLARATION_HEADER = re.compile(
    r"<!--\s*lane-declaration:\s*expected_count=(\d+)\s*-->"
)
# The worktree witness bound: activity older than
# this is a dead tree for cross-check purposes. The
# findings it feeds are hours-scale (a lane's state
# fresh over a tree dead for hours), so the probe
# stays coarse and bounded: the tree's HEAD commit
# time and its top-level mtimes.
WITNESS_DEAD_MINUTES = 120


def _stamp(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        return records._parse_stamp(value)
    return None


def _resolve_record(record) -> Path:
    """A declared record location as a path: an
    absolute location stands as written; a
    workspace-relative one (the seeded form)
    resolves against the workspace anchor."""
    path = Path(str(record)).expanduser()
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    return path


def parse_record_text(text: str) -> tuple:
    """One record file's lane grammar: a
    lane-declaration header (the coordinator's
    posted expected count) and one lane-record
    block per lane declaration or renewal, in the
    wb-step block form — one key: value field per
    line. A progress-checkpoint line attributes to
    the lane whose block stands most recently above
    it. Returns (declared_count, blocks, refused):
    blocks carry their attributed checkpoint stamps
    under "_checkpoints"; refused names each dropped
    block and why — a block with no lane key, or no
    venue, is not a lane record."""
    declared = None
    header = DECLARATION_HEADER.search(text or "")
    if header:
        declared = int(header.group(1))
    blocks: list[dict] = []
    refused: list[str] = []
    current: dict | None = None
    last_key: str | None = None
    by_key: dict[str, dict] = {}
    for line in (text or "").splitlines():
        if current is not None:
            if line.strip() == "-->":
                key = current.get("lane")
                if not key:
                    refused.append("lane-record block with no lane key")
                elif not current.get("venue"):
                    refused.append(
                        f"lane {key}: no venue declared — a lane record "
                        "always carries its venue (a session name, or none)"
                    )
                else:
                    blocks.append(current)
                    by_key[key] = current
                    last_key = key
                current = None
                continue
            if ":" in line:
                field, _, value = line.partition(":")
                field = field.strip()
                if field:
                    current[field] = value.strip()
            continue
        if LANE_BLOCK_START.search(line):
            current = {"_checkpoints": []}
            continue
        match = records.CHECKPOINT.search(line)
        if match and last_key is not None:
            stamp = records._parse_stamp(match.group(1))
            if stamp is not None:
                by_key[last_key]["_checkpoints"].append(stamp)
    if current is not None:
        refused.append("unterminated lane-record block")
    return declared, blocks, refused


def _merge_blocks(blocks: list[dict]) -> dict:
    """One lane's blocks merged: the block with the
    latest renewal (else declaration) stamp is the
    current declaration; declared-at is the earliest
    across blocks; the renewal count is the greatest
    the blocks carry or the count of renewing blocks,
    whichever stands higher."""
    merged: dict = {}
    declared_stamps = []
    renewals = 0
    current = None
    current_stamp = None
    for block in blocks:
        stamp = _stamp(block.get("renewed_at")) or _stamp(block.get("declared_at"))
        first = _stamp(block.get("declared_at"))
        if first is not None:
            declared_stamps.append(first)
        if block.get("renewed_at"):
            renewals += 1
        try:
            renewals = max(renewals, int(block.get("renewals") or 0))
        except (TypeError, ValueError):
            pass
        if current is None or (
            stamp is not None and (current_stamp is None or stamp >= current_stamp)
        ):
            current, current_stamp = block, stamp
    for block in blocks:
        if block is not current:
            for field, value in block.items():
                if value not in (None, "") and field not in merged:
                    merged[field] = value
    if current is not None:
        for field, value in current.items():
            if value not in (None, ""):
                merged[field] = value
    if declared_stamps:
        merged["declared_at"] = stamps.iso(min(declared_stamps))
    merged["renewals"] = renewals
    checkpoints: list[datetime] = []
    for block in blocks:
        checkpoints.extend(block.get("_checkpoints") or [])
    merged["_checkpoints"] = checkpoints
    return merged


def _evidence_verified(evidence: str, record_path, contract) -> bool:
    """Termination is checkable or it is not
    termination: the evidence verifies when it names
    a commit the record's own repo carries on main,
    a path that exists, or a queue item the contract
    no longer holds unlanded (a landed marker, or an
    item pruned from the queue)."""
    if not evidence:
        return False
    repo = records._repo_for(Path(record_path)) if record_path else None
    if repo:
        for sha in records.SHA_TOKEN.findall(evidence):
            if records._is_landed(repo, sha) is True:
                return True
    queue = {}
    if contract:
        queue = {
            entry.get("key"): entry for entry in contract.get("staffable_queue") or []
        }
    for token in re.split(r"[\s,;]+", evidence):
        token = token.strip("'\"()[]<>`.")
        if not token:
            continue
        if token.startswith(("/", "~/")):
            if Path(token).expanduser().exists():
                return True
        entry = queue.get(token)
        if entry is not None and entry.get("marker") is True and entry.get("landed"):
            return True
    return False


def _evaluate_lane(raw: dict, now: datetime, bound: float, contract) -> dict:
    """One lane's served record: the declaration as
    posted, its lifecycle read against now — ping
    freshness at the programme's cadence bound,
    estimate against actual, termination only where
    its evidence verifies."""
    declared_at = _stamp(raw.get("declared_at"))
    renewed_at = _stamp(raw.get("renewed_at"))
    estimate = raw.get("estimate_minutes")
    try:
        estimate = int(estimate) if estimate is not None else None
    except (TypeError, ValueError):
        estimate = None
    estimate_end = None
    base = renewed_at or declared_at
    if base is not None and estimate is not None:
        estimate_end = base + timedelta(minutes=estimate)
    pings = [s for s in raw.get("_checkpoints") or [] if s is not None]
    file_stamp = _stamp(raw.get("_file_stamp"))
    if file_stamp is not None:
        pings.append(file_stamp)
    last_ping = max(pings) if pings else None
    gap = (
        int((now - last_ping).total_seconds() // 60) if last_ping is not None else None
    )
    stale = gap is None or gap > bound
    state = raw.get("state") or "declared"
    evidence = raw.get("termination_evidence")
    terminated = state == "terminated" and _evidence_verified(
        evidence or "", raw.get("_record_path"), contract
    )
    overrun = not terminated and estimate_end is not None and now > estimate_end
    return {
        "key": raw.get("lane") or raw.get("key"),
        "label": raw.get("label"),
        "family": raw.get("family"),
        "queue_item": raw.get("queue_item"),
        "seat": raw.get("seat"),
        "venue": raw.get("venue"),
        "state": state,
        "declared_at": stamps.iso(declared_at),
        "renewed_at": stamps.iso(renewed_at),
        "estimate_minutes": estimate,
        "estimate_end": stamps.iso(estimate_end),
        "elapsed_minutes": (
            int((now - declared_at).total_seconds() // 60)
            if declared_at is not None
            else None
        ),
        "renewals": raw.get("renewals") or 0,
        "last_ping_at": stamps.iso(last_ping),
        "ping_gap_minutes": gap,
        "stale": stale,
        "overrun": overrun,
        "terminated": terminated,
        "termination_condition": raw.get("termination_condition"),
        "termination_evidence": evidence,
        "gap_waits_on": raw.get("gap_waits_on"),
        "worktree": raw.get("worktree"),
        "record": raw.get("record") or raw.get("_record_path"),
        "source": raw.get("_source") or "record",
    }


def _worktree_activity(path: Path) -> datetime | None:
    """A tree's latest witnessed activity, bounded:
    its HEAD commit time, its root mtime, and its
    top-level entries' mtimes."""
    stamps: list[datetime] = []
    try:
        stamps.append(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
        for child in path.iterdir():
            try:
                stamps.append(datetime.fromtimestamp(child.stat().st_mtime, tz=UTC))
            except OSError:
                continue
    except OSError:
        return None
    import subprocess

    try:
        done = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%ct", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if done.returncode == 0 and done.stdout.strip():
            stamps.append(datetime.fromtimestamp(int(done.stdout.strip()), tz=UTC))
    except Exception:
        pass
    return max(stamps) if stamps else None


def _read_file(path: Path) -> tuple:
    """One record file read for the lane grammar:
    (declared header, blocks, refused, mtime). An
    unreadable file reads as empty with its mtime
    unknown — the lanes it carried read stale, which
    is the honest direction."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None, [], [], None
    declared, blocks, refused = parse_record_text(text)
    return declared, blocks, refused, stamp


def _seed_raw(entry: dict) -> dict:
    raw = {
        "lane": entry.get("key"),
        "label": entry.get("label"),
        "family": entry.get("family"),
        "queue_item": entry.get("queue_item"),
        "seat": entry.get("seat"),
        "venue": entry.get("venue"),
        "state": entry.get("state"),
        "declared_at": entry.get("declared_at"),
        "renewed_at": entry.get("renewed_at"),
        "estimate_minutes": entry.get("estimate_minutes"),
        "renewals": entry.get("renewals") or 0,
        "termination_condition": entry.get("termination_condition"),
        "termination_evidence": entry.get("termination_evidence"),
        "gap_waits_on": entry.get("gap_waits_on"),
        "worktree": entry.get("worktree"),
        "record": (
            str(_resolve_record(entry["record"])) if entry.get("record") else None
        ),
        "_blocks": [],
        "_checkpoints": [],
        "_source": "registry-seed",
    }
    return raw


def _absorb(raws: dict, order: list, blocks, path, stamp) -> None:
    """Merge one record file's lane blocks into the
    raw lanes by key, in first-seen order: a block
    for a seeded lane appends to the seed's raw (the
    record block wins at merge time); the file's
    stamp is the lane's latest file ping."""
    for block in blocks:
        key = block.get("lane")
        if key not in raws:
            raws[key] = {"_blocks": [], "_checkpoints": []}
            order.append(key)
        raws[key]["_blocks"].append(block)
        if stamp is not None:
            prior = raws[key].get("_file_stamp")
            if prior is None or stamp > _stamp(prior):
                raws[key]["_file_stamp"] = stamps.iso(stamp)
        raws[key]["_record_path"] = str(path)


def collect(state: dict, now: datetime) -> bool:
    """Refresh the lane snapshot for every declared
    programme: the registry-seeded declarations
    merged with the lane-record blocks in the
    programme's record files (and in each seeded
    lane's own record file), each lane evaluated
    against now. True when the snapshot changed."""
    snapshot: dict = {}
    for programme in programmes.declarations(state):
        slug = programme["slug"]
        declared_count, seed_entries = registry.lane_declarations_for(slug)
        locations = programme.get("record_locations") or []
        if not seed_entries and not locations:
            continue
        contract = registry.staffing_contract_for(slug)
        bound = programme.get("cadence_minutes") or 15
        raws: dict[str, dict] = {}
        order: list[str] = []
        refused: list[dict] = []
        header_count = None

        for entry in seed_entries:
            raw = _seed_raw(entry)
            raws[raw["lane"]] = raw
            order.append(raw["lane"])
        files = records._files(locations)
        seen = {str(p) for p in files}
        for entry in seed_entries:
            record = entry.get("record")
            if record:
                path = _resolve_record(record)
                if str(path) not in seen and path.is_file():
                    files.append(path)
                    seen.add(str(path))
        for path in files:
            header, blocks, file_refused, stamp = _read_file(path)
            if header is not None:
                header_count = header
            for reason in file_refused:
                refused.append({"file": str(path), "reason": reason})
            _absorb(raws, order, blocks, path, stamp)
            # A seeded lane whose own record file this
            # is still pings on the file's writes even
            # where the file carries no block yet: the
            # STATE write is the ping act.
            for entry in seed_entries:
                if entry.get("record") and str(_resolve_record(entry["record"])) == str(
                    path
                ):
                    key = entry.get("key")
                    if key in raws and stamp is not None:
                        prior = raws[key].get("_file_stamp")
                        if prior is None or stamp > _stamp(prior):
                            raws[key]["_file_stamp"] = stamps.iso(stamp)
        lanes = []
        for key in order:
            raw = raws[key]
            blocks = raw.pop("_blocks", [])
            if blocks:
                merged = _merge_blocks(blocks)
                merged["_checkpoints"] = (merged.get("_checkpoints") or []) + (
                    raw.get("_checkpoints") or []
                )
                for field in ("_file_stamp", "_record_path"):
                    if raw.get(field) is not None:
                        merged[field] = raw[field]
                merged["_source"] = "record"
                if not merged.get("record"):
                    merged["record"] = raw.get("record")
                raw = merged
            raw.setdefault("lane", key)
            lanes.append(_evaluate_lane(raw, now, bound, contract))
        declared = header_count
        if declared is None:
            declared = declared_count
        trees = {}
        for tree in (state.get("worktree_snapshot") or {}).get(slug, {}).get(
            "trees"
        ) or []:
            path = Path(tree["path"])
            trees[tree["path"]] = stamps.iso(_worktree_activity(path))
        snapshot[slug] = {
            "at": now,
            "declared": declared,
            "lanes": lanes,
            "refused": refused,
            "worktrees": trees,
        }
    before = {
        slug: {k: v for k, v in entry.items() if k != "at"}
        for slug, entry in (state.get("lane_snapshot") or {}).items()
    }
    after = {
        slug: {k: v for k, v in entry.items() if k != "at"}
        for slug, entry in snapshot.items()
    }
    if after == before:
        return False
    state["lane_snapshot"] = snapshot
    return True


def record_facts(state: dict, slug: str) -> dict | None:
    """The record-derived staffing facts for one
    programme, or None where it carries no lane
    records: the declared count, the counted actual
    (open, non-stale lanes), and the queue items and
    families those counted lanes cover. The serial
    measure reconciles its queue derivation against
    this; a programme with no lane snapshot keeps
    the venue-only derivation untouched."""
    entry = (state.get("lane_snapshot") or {}).get(slug)
    if entry is None:
        return None
    lanes = entry.get("lanes") or []
    counted = [lane for lane in lanes if not lane["terminated"] and not lane["stale"]]
    return {
        "declared": entry.get("declared"),
        "actual": len(counted),
        "covered_queue_items": sorted(
            {lane["queue_item"] for lane in counted if lane.get("queue_item")}
        ),
        "covered_families": sorted(
            {lane["family"] for lane in counted if lane.get("family")}
        ),
        "lanes": lanes,
    }


def _programme_row(state: dict, slug: str) -> dict | None:
    for programme in programmes.declarations(state):
        if programme["slug"] == slug:
            return programme
    return registry.for_slug(slug)


def _lane_row(topic, handle, label, kind, detail, **evidence) -> dict:
    """A lane row: the shared staffing row, carrying
    its evidence mapping under "extra" as the lane
    rows' consumers read it, beside the flattened
    fields every staffing row carries."""
    row = _row(topic, handle, label, kind, detail, **evidence)
    row["extra"] = evidence.get("extra") or {}
    return row


def _lane_rows(state: dict, now: datetime) -> list:
    """The lane-record rows, beside the shortfall
    row: a declared lane past its ping bound
    (staleness), a lane past its estimate unrenewed
    (overrun), an expired unrenewed unterminated
    declaration gone silent (escalation), activity
    with no lane record (unposted work), and a lane
    claim no witness carries (unwitnessed). Built
    from the lane snapshot alone — a programme with
    no lane records raises none of these."""
    snapshot = state.get("lane_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    venue_snapshot = state.get("venue_snapshot") or {}
    for slug, entry in sorted(snapshot.items()):
        programme = _programme_row(state, slug)
        if programme is None:
            continue
        handle = (programme.get("handles") or [slug])[0]
        label = programme.get("label") or slug
        bound = programme.get("cadence_minutes") or 15
        lanes = entry.get("lanes") or []
        open_lanes = [lane for lane in lanes if not lane["terminated"]]
        families = (venue_snapshot.get(slug) or {}).get("families") or {}
        activity = entry.get("worktrees") or {}
        for lane in open_lanes:
            key = lane["key"]
            name = lane.get("label") or key
            if lane["overrun"] and lane["stale"]:
                row = _lane_row(
                    slug,
                    handle,
                    label,
                    "lane_escalated",
                    f"Lane {name}: declared "
                    f"{lane.get('declared_at') or 'at an unrecorded time'}, "
                    f"estimate {lane.get('estimate_minutes')}m ended "
                    f"{lane.get('estimate_end') or 'unrecorded'}, unrenewed "
                    f"and unterminated, and silent for "
                    f"{lane.get('ping_gap_minutes')}m against the "
                    f"{bound}-minute ping bound. An expired declaration "
                    "is an escalated row, not a closed lane — it closes "
                    "only on its termination condition, evidenced.",
                    checkpoint_gap_minutes=lane.get("ping_gap_minutes"),
                    key=f"lane_escalated:{slug}:{key}",
                    extra={"lane": key, "venue": lane.get("venue")},
                )
                row["escalation"] = "main"
                rows.append(row)
            elif lane["stale"]:
                rows.append(
                    _lane_row(
                        slug,
                        handle,
                        label,
                        "lane_stale",
                        f"Lane {name}: no ping for "
                        f"{lane.get('ping_gap_minutes')}m against the "
                        f"{bound}-minute bound — the declaration stays "
                        "live only while the lane's own checkpoint and "
                        "state writes move it, and a stale record is "
                        "not counted as staffed.",
                        checkpoint_gap_minutes=lane.get("ping_gap_minutes"),
                        key=f"lane_stale:{slug}:{key}",
                        extra={"lane": key, "venue": lane.get("venue")},
                    )
                )
            elif lane["overrun"]:
                rows.append(
                    _lane_row(
                        slug,
                        handle,
                        label,
                        "lane_overrun",
                        f"Lane {name}: estimate "
                        f"{lane.get('estimate_minutes')}m ended "
                        f"{lane.get('estimate_end')} with no renewal and "
                        "no termination — at estimate end a lane renews "
                        "with a new estimate or terminates on evidence.",
                        key=f"lane_overrun:{slug}:{key}",
                        extra={
                            "lane": key,
                            "venue": lane.get("venue"),
                            "estimate_end": lane.get("estimate_end"),
                            "renewals": lane.get("renewals"),
                        },
                    )
                )
            rows.extend(
                _unwitnessed_row(slug, handle, label, lane, families, activity, now)
            )
        covered_families = {
            lane.get("family") for lane in open_lanes if lane.get("family")
        }
        for family in sorted(families):
            if family not in covered_families:
                rows.append(
                    _lane_row(
                        slug,
                        handle,
                        label,
                        "lane_unposted",
                        f"Family {family} is in flight on venue run "
                        "records with no open lane record naming it — "
                        "work with no lane record is unposted work.",
                        key=f"lane_unposted:{slug}:venue:{family}",
                        extra={"family": family, "via": "venue_run_records"},
                    )
                )
        covered_trees = {
            lane.get("worktree") for lane in open_lanes if lane.get("worktree")
        }
        for tree_path, active_at in sorted(activity.items()):
            stamp = _stamp(active_at)
            if stamp is None or (now - stamp) > timedelta(minutes=WITNESS_DEAD_MINUTES):
                continue
            if tree_path not in covered_trees:
                rows.append(
                    _lane_row(
                        slug,
                        handle,
                        label,
                        "lane_unposted",
                        f"Worktree {tree_path} shows activity at "
                        f"{active_at} with no open lane record naming "
                        "it — work with no lane record is unposted work.",
                        key=f"lane_unposted:{slug}:worktree:{tree_path}",
                        extra={"worktree": tree_path, "via": "worktree_activity"},
                    )
                )
    return rows


def _unwitnessed_row(slug, handle, label, lane, families, activity, now) -> list:
    """A lane claim no witness carries: fresh lane
    state over a worktree dead for hours, or a lane
    in the running state whose family no run record
    flies and whose tree stands dead. A gap-wait
    lane is exempt — waiting is its declared state —
    and a merely declared lane claims no flight."""
    if lane["state"] == "gap-wait":
        return []
    tree_path = lane.get("worktree")
    tree_stamp = _stamp(activity.get(tree_path)) if tree_path else None
    tree_dead = tree_path is not None and (
        tree_stamp is None
        or (now - tree_stamp) > timedelta(minutes=WITNESS_DEAD_MINUTES)
    )
    fresh = not lane["stale"]
    if tree_path and tree_dead and fresh:
        return [
            _lane_row(
                slug,
                handle,
                label,
                "lane_unwitnessed",
                f"Lane {lane.get('label') or lane['key']}: its state "
                f"moved at {lane.get('last_ping_at')} while its "
                f"worktree {tree_path} shows no activity inside "
                f"{WITNESS_DEAD_MINUTES} minutes — fresh lane state "
                "over a dead worktree is a finding.",
                key=f"lane_unwitnessed:{slug}:{lane['key']}",
                extra={"lane": lane["key"], "worktree": tree_path},
            )
        ]
    if (
        lane["state"] == "running"
        and lane.get("venue") not in (None, "none")
        and lane.get("family")
        and lane["family"] not in families
        and (tree_path is None or tree_dead)
    ):
        return [
            _lane_row(
                slug,
                handle,
                label,
                "lane_unwitnessed",
                f"Lane {lane.get('label') or lane['key']}: in the "
                f"running state on venue {lane.get('venue')} for "
                f"family {lane['family']}, but no venue run record "
                "flies that family and no worktree activity carries "
                "the claim.",
                key=f"lane_unwitnessed:{slug}:{lane['key']}",
                extra={"lane": lane["key"], "family": lane["family"]},
            )
        ]
    return []
