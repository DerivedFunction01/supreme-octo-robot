"""Push-item fact re-verification: a push wait's load-bearing
facts — the repo's HEAD and its distance from origin — are
measured from the repo itself, never trusted from a title."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from attention.settings import REPO_ROOT

_SHA = re.compile(r"[0-9a-f]{7,40}")
CLEARED_STATES = ("pushed", "gone")


def _git(repo: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _named_shas(item: dict) -> list:
    text = f"{item.get('title', '')} {item.get('source_ref', '')}"
    return _SHA.findall(text)


def measure(item: dict, workspace: Path, now: datetime) -> dict:
    """One push item's facts, measured now: current,
    superseded, pushed, gone, or unverifiable — the
    five states the module docstring names."""
    repo = item["repo"]
    base = {
        "repo": repo,
        "verified_at": now,
        "head": None,
        "ahead": None,
        "behind": None,
        "dirty": None,
    }
    path = workspace / repo
    if not path.exists():
        return {**base, "state": "gone"}
    head = _git(path, "rev-parse", "HEAD")
    if head is None:
        return {**base, "state": "unverifiable"}
    ahead_raw = _git(path, "rev-list", "--count", "origin/main..HEAD")
    ahead = int(ahead_raw) if ahead_raw and ahead_raw.isdigit() else None
    behind_raw = _git(path, "rev-list", "--count", "HEAD..origin/main")
    behind = int(behind_raw) if behind_raw and behind_raw.isdigit() else None
    status = _git(path, "status", "--porcelain")
    dirty = None if status is None else bool(status)
    measured = {**base, "head": head, "ahead": ahead, "behind": behind, "dirty": dirty}
    if ahead == 0:
        return {**measured, "state": "pushed"}
    named = _named_shas(item)
    current = any(head.startswith(sha) or sha.startswith(head[:7]) for sha in named)
    return {**measured, "state": "current" if current else "superseded"}


def _push_candidates(state: dict) -> list:
    return [
        i
        for i in state["items"]
        if i["kind"] == "push_needed"
        and i["triage"] not in ("done", "muted")
        and i.get("repo")
        and "/" not in i["repo"]
        and not i["repo"].startswith(".")
    ]


def derive_push_facts(
    state: dict, now: datetime, workspace: Path | None = None
) -> dict:
    """{item_id: fact} for every open push item naming a
    repo — the serve-time derivation the builders read."""
    root = workspace if workspace is not None else REPO_ROOT.parent
    return {i["id"]: measure(i, root, now) for i in _push_candidates(state)}


def served_title(item: dict, fact: dict | None) -> str:
    """The title the surface may present: the poster's,
    unless measurement superseded its facts — then the
    measured statement, which is the current truth."""
    if not fact or fact["state"] != "superseded" or not fact.get("head"):
        return item["title"]
    title = f"Push {fact['repo']} — {fact['head'][:7]}"
    if fact.get("ahead") is not None:
        noun = "commit" if fact["ahead"] == 1 else "commits"
        title += f", {fact['ahead']} {noun} ahead of origin"
    return title


def clear_resolved(state: dict, now: datetime, workspace: Path | None = None) -> bool:
    """The tick's self-clearing pass: a push item whose
    subject resolved (pushed) or retired (repo gone)
    leaves the queue as a stored fact, not a render mask."""
    root = workspace if workspace is not None else REPO_ROOT.parent
    changed = False
    for item in _push_candidates(state):
        fact = measure(item, root, now)
        if fact["state"] in CLEARED_STATES:
            item["triage"] = "done"
            item["fact_state"] = fact["state"]
            changed = True
    return changed


# --- staleness basis probes (the decision-staleness plan,
# Step 2): pure readers over injected roots and record
# sets, consumed by services/waits/basis.py. Each returns
# None when it cannot decide — never a guess.

_SENTINEL_BLOCK = re.compile(r"<!--\s*wb-question\b(.*?)-->", re.DOTALL)
_SENTINEL_FIELD = re.compile(r"^\s*([a-z_]+)=(.*)$")


def _sentinel_fields(block: str) -> dict:
    fields = {}
    for line in block.splitlines():
        matched = _SENTINEL_FIELD.match(line)
        if matched:
            fields[matched.group(1)] = matched.group(2).strip()
    return fields


def plan_sentinel(source_ref: str, plans_root: Path) -> dict | None:
    """Resolve a plan-sentinel source ref — the form
    "<plan path>#<question id>" — under an injected plans
    root. Returns {plan, question, finished, answered,
    answer}, or None when the ref is not a plan sentinel
    or cannot be resolved there (no such plan, no such
    question): the caller treats None as cannot-decide.
    A copy under finished/ settles the question by the
    landing itself, answered or not."""
    path_part, sep, question = source_ref.rpartition("#")
    if not sep or not question or not path_part.endswith(".md"):
        return None
    rel = Path(path_part)
    if rel.is_absolute():
        return None
    finished_copy = plans_root / "finished" / rel.name
    active_copy = plans_root / rel
    finished = finished_copy.exists() or (
        rel.parts[:1] == ("finished",) and active_copy.exists()
    )
    target = finished_copy if finished_copy.exists() else active_copy
    if not target.exists():
        return None
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for block in _SENTINEL_BLOCK.findall(text):
        fields = _sentinel_fields(block)
        if fields.get("id") == question:
            answer = fields.get("answer") or None
            return {
                "plan": path_part,
                "question": question,
                "finished": finished,
                "answered": answer is not None,
                "answer": answer,
            }
    return None


def source_standing(
    source_ref: str, records: dict | None, terminal_codes=()
) -> bool | None:
    """Whether the record a clears_at_source item points
    at still stands, over an injected {id: record} set:
    gone from the set, resolved (triage done, a decision
    past pending), or at a terminal status all read as no
    longer standing. None when no record set was injected
    — the probe cannot decide."""
    if records is None:
        return None
    record = records.get(source_ref)
    if record is None:
        return False
    if record.get("triage") == "done":
        return False
    decision = record.get("decision")
    if decision is not None and decision != "pending":
        return False
    if record.get("status_code") in terminal_codes:
        return False
    return True


def load_records(state_path: Path) -> dict | None:
    """The {id: record} set over a state file's items and
    waits — the provider-side loader for source_standing.
    None when the file cannot be read as state."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict):
        return None
    records = {}
    for section in ("items", "waits"):
        for record in state.get(section) or []:
            if isinstance(record, dict) and record.get("id"):
                records[record["id"]] = record
    return records
