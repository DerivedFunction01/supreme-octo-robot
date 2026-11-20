#!/usr/bin/env python3
"""Stale-mockup census — the scripted leg of the stale-mockup-cleanup job.

Censuses every workbench project registry (a workspace directory holding
both workbench.yaml and workbench/registry.db), classifies each mockup
mechanically from the registry's own recorded fields, and speaks only
when there is something to say:

- Only kind=mockup entries are candidates. Everything else — including
  deployed/live artifacts — is excluded deterministically, no judgment.
- STALE-SUPERSEDED: superseded_by names an entry that exists in the
  same registry (the successor is the evidence).
- STALE-IMPLEMENTED: status=implemented with a spec_ref or ruling on
  record (the owning project's recorded landing is the evidence).
- KEEP: unexplored / canonical / deferred / hard-gate with no
  superseded_by — live or undecided, never touched.
- UNRESOLVED: abandoned (a terminal ruling outside the stale classes),
  an unknown status, a dangling superseded_by, or an implemented claim
  with no landing reference on record. Unresolved items are never
  removed.
- CANDIDATE (proposed, never confirmed by status alone): a KEEP entry
  tied to a plan whose lifecycle status is complete proposes
  candidate-implemented; tied to a superseded plan proposes
  candidate-superseded. The tie is the entry's plan_ref resolving to a
  plan under the project's .plans/ with a parseable Status line (the
  plan is the attribution anchor — thread/repo derive through it —
  commissioned in the workbench thread; refs that do not resolve to a
  lifecycle plan, such as inventory handoffs, are not ties). Status
  alone proposes: candidates are escalated to the agent, who confirms
  with landing/successor evidence and records the outcome in the
  registry — only then does an item enter the stale path. Candidates
  are never removed by this leg.

The same-state skip keys on the disposition-relevant inputs, not on
the census alone (owner's edge-case ruling, 2026-11-08): a mockup goes
stale because of state outside the census — a landing in its owning
repo, a successor appearing, its attribution record arriving. So each
project carries a digest over its census rows, its per-entry
attribution data, and its owning repo's git HEAD. When a project's
digest moves, that project's KEEP mockups are escalated as RECHECK
items for the agent to re-judge against the repo's current state.
And unresolved residue defeats the skip outright: while any unresolved
item exists, every run escalates it — sameness never suppresses the
agent. (The scheduler's outbox coalesces to one pending ping per job,
so a standing residue cannot pile up duplicate pings.)

Removals: registry entries are archived through the harness's one
mutation path (wb archive), and only once workbench attribution is
live — detected mechanically: a candidate entry carrying attribution
(an attribution column on entries, or attribution keys in state_json).
Until then the leg runs census-and-report: stale items are printed as
report lines and nothing is removed.

State (state/mockup-census/last.json, under this repo's gitignored
state/) records the buckets, the per-project digests, the stale,
unresolved, and candidate sets each run. A run with no removals, no
new stale items, no unresolved residue, no new candidates, no changed
project digest, and no errors prints nothing and exits 0 — no report,
no agent.

Exit codes: 0 = resolved or quiet; 3 = unresolved residue or RECHECK
items (agent escalation); 1 = census error (agent escalation).
Stdlib only; every path derives from this script's own location.
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

ROOT = paths.REPO_ROOT
WS = paths.WORKSPACE_ROOT
STATE_DIR = os.path.join(paths.STATE_DIR, "mockup-census")
STATE_FILE = os.path.join(STATE_DIR, "last.json")
WB = os.path.join(WS, "workbench-viewer", "wb")

KEEP_STATUSES = {"unexplored", "canonical", "deferred", "hard-gate"}
ATTRIBUTION_COLUMNS = {"owner_thread", "thread_id", "owner_repo", "repo", "attribution"}
ATTRIBUTION_STATE_KEYS = {"attribution", "owner_thread", "owner_repo", "thread"}


def discover_projects():
    projects = []
    for name in sorted(os.listdir(WS)):
        proj = os.path.join(WS, name)
        db = os.path.join(proj, "workbench", "registry.db")
        if os.path.isfile(os.path.join(proj, "workbench.yaml")) and os.path.isfile(db):
            projects.append((name, proj, db))
    return projects


def repo_head(proj):
    """The owning repo's landing state, mechanically: its git HEAD."""
    try:
        proc = subprocess.run(
            ["git", "-C", proj, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "nogit"


_STATUS_LINE = re.compile(r"^Status:\s*(.+)$", re.IGNORECASE)


def _plan_status_from_file(path):
    """A plan's lifecycle status from its Status header line; a plan
    resting under .plans/finished/ with no Status line is complete."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 60:
                    break
                m = _STATUS_LINE.match(line.strip())
                if m:
                    value = m.group(1).strip().lower()
                    for known in ("complete", "superseded", "in progress",
                                  "in-progress", "draft", "parked"):
                        if value.startswith(known):
                            return known.replace(" ", "-")
                    return value.split()[0] if value else ""
    except OSError:
        return ""
    if f"{os.sep}.plans{os.sep}finished{os.sep}" in path:
        return "complete"
    return ""


def resolve_plan_status(proj, plan_ref):
    """The lifecycle status of the plan an entry is tied to, or '' when
    the ref is not a tie: no ref, an anchor-only ref, a path that does
    not resolve under the project's .plans/, or a document with no
    lifecycle Status (e.g. an inventory handoff)."""
    if not plan_ref:
        return ""
    rel = plan_ref.split("#", 1)[0].strip()
    if not rel:
        return ""
    path = os.path.normpath(os.path.join(proj, rel))
    plans_root = os.path.normpath(os.path.join(proj, ".plans"))
    if not path.startswith(plans_root + os.sep):
        return ""
    if os.path.isfile(path):
        return _plan_status_from_file(path)
    if os.path.isdir(path):
        names = sorted(f for f in os.listdir(path) if f.endswith(".md"))
        own = os.path.basename(path) + ".md"
        if own in names:
            names.remove(own)
            names.insert(0, own)
        for name in names:
            status = _plan_status_from_file(os.path.join(path, name))
            if status:
                return status
    return ""


def entry_attribution(row, columns):
    """The attribution data one entry carries, as a stable string."""
    parts = {}
    for col in sorted(ATTRIBUTION_COLUMNS & columns):
        if row[col]:
            parts[col] = row[col]
    if row["state_json"]:
        try:
            state = json.loads(row["state_json"])
        except ValueError:
            state = {}
        if isinstance(state, dict):
            for key in ATTRIBUTION_STATE_KEYS:
                if state.get(key):
                    parts[key] = state[key]
    return json.dumps(parts, sort_keys=True) if parts else ""


def census_project(name, proj, db_path):
    """Returns (items, attribution_live) or raises on a broken registry.

    Each item is (project, row dict, registry id set, attribution blob,
    plan status) — the plan status of the entry's tied plan, '' when
    the entry has no lifecycle-plan tie.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        columns = {r[1] for r in con.execute("PRAGMA table_info(entries)")}
        wanted = ["id", "kind", "status", "superseded_by", "archived",
                  "spec_ref", "ruling_date", "source_kind", "source_ref",
                  "plan_ref", "state_json"] + sorted(ATTRIBUTION_COLUMNS & columns)
        rows = con.execute(
            f"SELECT {', '.join(wanted)} FROM entries"
        ).fetchall()
        ids = {r["id"] for r in rows}
        items = []
        attribution_live = False
        plan_cache = {}
        for r in rows:
            row = dict(r)
            blob = entry_attribution(row, columns)
            if blob and row["kind"] == "mockup" and not row["archived"]:
                attribution_live = True
            ref = row.get("plan_ref") or ""
            if ref not in plan_cache:
                plan_cache[ref] = resolve_plan_status(proj, ref)
            items.append((name, row, ids, blob, plan_cache[ref]))
        return items, attribution_live
    finally:
        con.close()


def classify(row, ids, plan_status=""):
    """One entry -> (bucket, evidence). Buckets: excluded, done, keep,
    stale-superseded, stale-implemented, unresolved, and the proposed
    candidate-implemented / candidate-superseded (a tied plan's
    lifecycle status proposing over a keep — evidence must confirm)."""
    if row["kind"] != "mockup":
        return "excluded", "not a mockup"
    if row["archived"]:
        return "done", "already archived"
    sup = (row["superseded_by"] or "").strip()
    if sup:
        if sup in ids:
            return "stale-superseded", f"superseded_by={sup}"
        return "unresolved", f"superseded_by={sup} names no entry in this registry"
    status = (row["status"] or "").strip()
    if status == "implemented":
        if row["spec_ref"] or row["ruling_date"]:
            ev = row["spec_ref"] or f"ruling {row['ruling_date']}"
            return "stale-implemented", f"status=implemented, {ev}"
        return "unresolved", "status=implemented with no spec_ref or ruling on record"
    if status in KEEP_STATUSES:
        if plan_status == "complete":
            return ("candidate-implemented",
                    f"tied plan {row.get('plan_ref')} status=complete — proposes"
                    " implemented; landing evidence must confirm")
        if plan_status == "superseded":
            return ("candidate-superseded",
                    f"tied plan {row.get('plan_ref')} status=superseded — proposes"
                    " superseded; successor evidence must confirm")
        return "keep", f"status={status}"
    if status == "abandoned":
        return "unresolved", "status=abandoned — terminal ruling outside the stale classes"
    return "unresolved", f"unknown status {status!r}"


def project_digest(items, head):
    """Digest over one project's disposition-relevant inputs: its census
    rows, per-entry attribution data, and the owning repo's HEAD."""
    tuples = sorted(
        (row["id"], row["kind"], row["status"] or "", row["superseded_by"] or "",
         bool(row["archived"]), blob, row.get("plan_ref") or "", plan_status)
        for _name, row, _ids, blob, plan_status in items
    )
    blob = json.dumps({"head": head, "rows": tuples}, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def main():
    lines = []
    errors = []
    buckets = {}
    stale = []       # (project, id, bucket, evidence)
    unresolved = []  # (project, id, reason)
    candidates = []  # (project, id, bucket, evidence) — proposed only
    digests = {}
    keeps_by_project = {}
    attribution_live = False
    total = 0

    for name, proj, db in discover_projects():
        try:
            items, proj_attribution = census_project(name, proj, db)
        except Exception as exc:  # noqa: BLE001 - a broken registry is a census error
            errors.append(f"{name}: registry unreadable: {exc}")
            continue
        attribution_live = attribution_live or proj_attribution
        digests[name] = project_digest(items, repo_head(proj))
        for _name, row, ids, _blob, plan_status in items:
            total += 1
            bucket, evidence = classify(row, ids, plan_status)
            buckets[f"{name}/{row['id']}"] = bucket
            if bucket.startswith("stale"):
                stale.append((name, row["id"], bucket, evidence))
            elif bucket == "unresolved":
                unresolved.append((name, row["id"], evidence))
            elif bucket.startswith("candidate"):
                candidates.append((name, row["id"], bucket, evidence))
            elif bucket == "keep":
                keeps_by_project.setdefault(name, []).append(row["id"])

    last = load_state()
    last_stale = {tuple(s) for s in last.get("stale", [])}
    stale_set = set(stale)
    stale_changed = stale_set != last_stale
    last_digests = last.get("project_digests", {})
    last_candidates = {tuple(c) for c in last.get("candidates", [])}
    candidates_changed = set(candidates) != last_candidates

    # RECHECK: a project whose disposition-relevant inputs moved since
    # the last run re-opens its KEEP mockups for agent re-judgment. A
    # project with no recorded digest is baselining, not changing.
    recheck = []
    for proj_name, digest in digests.items():
        if proj_name in last_digests and last_digests[proj_name] != digest:
            for entry_id in keeps_by_project.get(proj_name, []):
                recheck.append((proj_name, entry_id))

    removed = []
    if attribution_live and stale:
        still_stale = []
        for proj_name, entry_id, bucket, evidence in stale:
            proj_dir = os.path.join(WS, proj_name)
            proc = subprocess.run(
                [WB, "--root", proj_dir, "archive", entry_id],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0:
                removed.append((proj_name, entry_id, bucket, evidence))
            else:
                unresolved.append(
                    (proj_name, entry_id,
                     f"wb archive failed: {(proc.stderr or proc.stdout).strip()[:200]}")
                )
                still_stale.append((proj_name, entry_id, bucket, evidence))
        stale = still_stale

    if removed:
        for proj_name, entry_id, bucket, evidence in removed:
            lines.append(f"REMOVED {proj_name}/{entry_id} ({bucket}) — evidence: {evidence}")
    elif stale and stale_changed and not attribution_live:
        for proj_name, entry_id, bucket, evidence in stale:
            lines.append(
                f"STALE {proj_name}/{entry_id} ({bucket}) — evidence: {evidence}"
                " — report-only (attribution not live), not removed"
            )

    # Unresolved residue defeats the skip outright: it is printed and
    # escalated on every run while it exists, changed or not.
    for proj_name, entry_id, reason in unresolved:
        lines.append(f"UNRESOLVED {proj_name}/{entry_id} — {reason}")
    # Candidates are proposals: surfaced when the candidate set moves,
    # never acted on by this leg — the agent confirms or rejects them
    # against landing/successor evidence.
    if candidates_changed:
        for proj_name, entry_id, bucket, evidence in candidates:
            lines.append(f"CANDIDATE {proj_name}/{entry_id} ({bucket}) — {evidence}")
    for proj_name, entry_id in recheck:
        lines.append(
            f"RECHECK {proj_name}/{entry_id} — disposition inputs changed in"
            f" {proj_name} (registry, attribution, or repo landing state);"
            " re-judge for staleness"
        )
    for err in errors:
        lines.append(f"CENSUS-ERROR {err}")
    if lines:
        counts = {}
        for b in buckets.values():
            counts[b] = counts.get(b, 0) + 1
        summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        lines.append(f"census: {total} entries across registries — {summary}")

    save_state({
        "project_digests": digests,
        "buckets": buckets,
        "stale": [list(s) for s in sorted(stale_set)],
        "unresolved": [list(u) for u in unresolved],
        "candidates": [list(c) for c in candidates],
        "attribution_live": attribution_live,
        "last_run": datetime.now(timezone.utc).isoformat(),
    })

    for line in lines:
        print(line)
    if errors:
        return 1
    if unresolved or recheck or (candidates_changed and candidates):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
