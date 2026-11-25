"""Lane record locations: a programme declares where
its lanes keep their run-log records; their conforming
progress-checkpoint lines are lane evidence alongside
the posts, snapshotted for the measure on the slow loop.
The goal store is collected beside them: its
owner-waiting declarations are the record source for
owner-waiting rows once the status-code transport is
gone."""

from __future__ import annotations

import glob as glob_mod
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from attention.infra import wb_client
from attention.paths import WORKRECORD_GOALS
from attention.services import programmes
from attention.settings import Settings

CHECKPOINT = re.compile(r"progress-checkpoint:\s*(\S+)")
# A run id as the runner mints it: a job stem and a
# UTC stamp, with an optional collision suffix.
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*?-\d{8}T\d{6}Z(?:-\d+)?")
# The words that make a citation a citation of the
# run's terminal state rather than of its launch:
# a programme record naming a run beside one of
# these has registered how the run ended.
TERMINAL_TOKENS = re.compile(
    r"fail|terminal|exit|verdict|dispos|abandon|collect|orphan", re.IGNORECASE
)
# The words that make a checkpoint line a completion
# claim about a build: the unlanded class measures the
# claim against main's ancestry, never against the
# claim's own word — a line claiming "landed" for a
# commit main does not carry is the sharpest specimen.
# A gate FIRE claims nothing; a gate verdict (pass /
# complete / green) claims the build it gated.
COMPLETION_TOKENS = re.compile(
    r"complet|built|landed|gate[ -](pass|complete|green)|\bPASS\b", re.IGNORECASE
)
# A commit token in a claim line: hex, 7-40 chars,
# carrying at least one a-f letter (a bare digit run
# is a date or a count, not a commit).
SHA_TOKEN = re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
TAIL_BYTES = 65536


def _parse_stamp(text) -> datetime | None:
    """Parse one stamp in either of the state's two
    shapes: the text a record file carries, and the
    datetime the store's decoder restores a persisted
    stamp to on load. A prior snapshot's entries
    arrive in the second shape; a parser that only
    takes text dies on them (the capacity-freeze
    specimen: this parser, fed a decoded prior
    claim, raised TypeError inside the pass)."""
    if isinstance(text, datetime):
        return text if text.tzinfo else text.replace(tzinfo=UTC)
    if not isinstance(text, str):
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _latest_checkpoint(path: Path) -> datetime | None:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > TAIL_BYTES:
                handle.seek(size - TAIL_BYTES)
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    latest = None
    for match in CHECKPOINT.finditer(text):
        stamp = _parse_stamp(match.group(1))
        if stamp is not None and (latest is None or stamp > latest):
            latest = stamp
    return latest


def _files(locations: list) -> list[Path]:
    found: list[Path] = []
    for entry in locations or []:
        if any(ch in str(entry) for ch in "*?["):
            found.extend(
                Path(p) for p in sorted(glob_mod.glob(str(entry))) if Path(p).is_file()
            )
        elif Path(str(entry)).is_file():
            found.append(Path(str(entry)))
    return found


def collect(state: dict, now: datetime) -> bool:
    """Refresh the record snapshot for every declared
    programme; True when the snapshot changed."""
    snapshot: dict = {}
    for programme in programmes.declarations(state):
        locations = programme.get("record_locations") or []
        if not locations:
            continue
        entries = {}
        for path in _files(locations):
            stamp = _latest_checkpoint(path)
            entries[str(path)] = {
                "lane": path.stem,
                "checkpoint_at": stamp,
            }
        snapshot[programme["slug"]] = {"at": now, "records": entries}
    before = {
        slug: entry.get("records")
        for slug, entry in (state.get("record_snapshot") or {}).items()
    }
    if {s: e["records"] for s, e in snapshot.items()} == before:
        return False
    state["record_snapshot"] = snapshot
    return True


def cited_terminal_runs(text: str) -> set:
    """The run ids one programme record cites in
    their terminal state: a run id on a line that
    also carries a terminal token. A citation of a
    launch (the id alone, or beside start/fire words)
    is not consumption — the gap this class answers
    is a terminal state recorded by the runner and
    never registered by the owning programme."""
    found = set()
    for line in (text or "").splitlines():
        if not TERMINAL_TOKENS.search(line):
            continue
        found.update(RUN_ID.findall(line))
    return found


def _tail_text(path: Path) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > TAIL_BYTES:
                handle.seek(size - TAIL_BYTES)
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def collect_consumption(state: dict, settings: Settings, now: datetime) -> bool:
    """Snapshot, per declared programme, the terminal
    runs its own records have consumed: run ids cited
    in a terminal state across the programme's
    workbench todo titles and bodies and its declared
    record-location files. The runner's own records
    are never a source here — the collector's stamp
    is the recording, and recording is not
    consumption. A project the workbench cannot
    serve keeps its prior citations (the fresh set is
    unioned over the prior, never shrunk by a failed
    read); the same discipline as the stamp snapshot."""
    snapshot = state.setdefault("consumption_snapshot", {})
    changed = False
    for programme in programmes.active_declarations(state):
        slug = programme["slug"]
        prior = set((snapshot.get(slug) or {}).get("consumed") or [])
        found: set = set()
        failed = False
        for project in programmes.wb_projects(programme):
            try:
                payload = wb_client.fetch_todos(
                    settings.wb_url, project, settings.wb_collect_timeout_s
                )
            except wb_client.WbUnavailable:
                failed = True
                continue
            for todo in payload.get("todos") or []:
                text = f"{todo.get('title') or ''}\n{todo.get('body') or ''}"
                found |= cited_terminal_runs(text)
        for path in _files(programme.get("record_locations") or []):
            found |= cited_terminal_runs(_tail_text(path))
        consumed = (prior | found) if failed else found
        if consumed != prior:
            snapshot[slug] = {"at": now, "consumed": sorted(consumed)}
            changed = True
    return changed


def claimed_builds(text: str) -> list:
    """The completion claims one programme record
    makes: a progress-checkpoint line carrying a
    completion token and naming a commit. The claim's
    instant is the line's own checkpoint stamp — the
    interval runs from the claim, not from the build.
    A checkpoint line with no completion token, or a
    completion word with no commit named, claims
    nothing this class can measure."""
    found = []
    for line in (text or "").splitlines():
        match = CHECKPOINT.search(line)
        if match is None or not COMPLETION_TOKENS.search(line):
            continue
        stamp = _parse_stamp(match.group(1))
        if stamp is None:
            continue
        for sha in SHA_TOKEN.findall(line):
            found.append({"sha": sha, "claimed_at": stamp})
    return found


def _repo_for(path: Path):
    """The git repo enclosing a record file, or None:
    the ancestry a claim is measured against is its
    own repo's main, derived from where the record
    lives — attribution stays filesystem truth, never
    a measure-side table."""
    import subprocess

    try:
        done = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def _is_landed(repo: str, sha: str):
    """True when main carries the commit, False when
    the commit exists and main does not, None when the
    object is unknown locally — unmeasurable is honest
    absence, never a row."""
    import subprocess

    try:
        exists = subprocess.run(
            ["git", "-C", repo, "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            timeout=10,
        )
        if exists.returncode != 0:
            return None
        done = subprocess.run(
            ["git", "-C", repo, "merge-base", "--is-ancestor", sha, "main"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return None
    if done.returncode == 0:
        return True
    if done.returncode == 1:
        return False
    return None


def _note_claim(claims: dict, claim) -> None:
    # The earliest claim of a commit starts its
    # clock; a re-claim never resets it.
    sha = claim["sha"]
    if sha not in claims or claim["claimed_at"] < claims[sha]:
        claims[sha] = claim["claimed_at"]


def collect_unlanded(state: dict, settings: Settings, now: datetime) -> bool:
    """Snapshot, per declared programme, the builds
    its own records claim complete, each measured
    against main: the unlanded class's facts. The
    claim is the programme's checkpoint word; the
    landed flag is git ancestry at collect time, so
    a row clears on the landing itself, never on a
    later checkpoint's say-so. The earliest claim of
    a commit starts its clock. A programme whose
    workbench read fails keeps its prior claims (the
    consumption collector's discipline); a claim
    whose repo cannot be derived stays unmeasured."""
    snapshot = state.setdefault("unlanded_snapshot", {})
    changed = False
    for programme in programmes.active_declarations(state):
        slug = programme["slug"]
        prior = (snapshot.get(slug) or {}).get("claims") or []
        claims: dict = {}
        repos: dict = {}
        failed = False
        for project in programmes.wb_projects(programme):
            try:
                payload = wb_client.fetch_todos(
                    settings.wb_url, project, settings.wb_collect_timeout_s
                )
            except wb_client.WbUnavailable:
                failed = True
                continue
            for todo in payload.get("todos") or []:
                text = f"{todo.get('title') or ''}\n{todo.get('body') or ''}"
                for claim in claimed_builds(text):
                    _note_claim(claims, claim)
        for path in _files(programme.get("record_locations") or []):
            repo = _repo_for(path)
            for claim in claimed_builds(_tail_text(path)):
                _note_claim(claims, claim)
                if repo is not None:
                    repos[claim["sha"]] = repo
        if failed and not claims:
            continue
        if failed:
            for entry in prior:
                _note_claim(
                    claims,
                    {
                        "sha": entry["sha"],
                        "claimed_at": _parse_stamp(entry["claimed_at"]),
                    },
                )
                if entry.get("repo"):
                    repos[entry["sha"]] = entry["repo"]
        # wb-only claims measure against the repo of
        # any record file the programme declares.
        fallback_repo = next(iter(repos.values()), None)
        entries = []
        for sha, claimed_at in sorted(claims.items(), key=lambda kv: kv[1]):
            repo = repos.get(sha) or fallback_repo
            entries.append(
                {
                    "sha": sha,
                    "claimed_at": claimed_at.isoformat(),
                    "repo": repo,
                    "landed": _is_landed(repo, sha) if repo else None,
                }
            )

        # The prior entries arrive store-decoded (their
        # stamps are datetimes); the fresh entries carry
        # text. Project both through the one parser, so
        # the comparison measures the claims, not the
        # shapes they arrived in.
        def _projection(entry: dict) -> dict:
            stamp = _parse_stamp(entry.get("claimed_at"))
            return {
                "sha": entry.get("sha"),
                "claimed_at": stamp.isoformat() if stamp else None,
                "landed": entry.get("landed"),
            }

        before = [_projection(e) for e in prior]
        after = [_projection(e) for e in entries]
        if after != before:
            snapshot[slug] = {"at": now, "claims": entries}
            changed = True
    return changed


def _goals_file() -> Path:
    override = os.environ.get("WB_GOALS_FILE")
    if override:
        return Path(override)
    return WORKRECORD_GOALS


def collect_goals(state: dict, now: datetime) -> bool:
    """Snapshot the goal store's owner-waiting
    declarations per programme, from each goal record's
    latest post — the declaration is sticky in the store
    until an explicit null clears it. A missing store
    file is honest absence: no declarations, not an
    error."""
    snapshot: dict = {}
    try:
        store = json.loads(_goals_file().read_text())
    except (OSError, ValueError):
        store = {}
    records = store.get("goals") if isinstance(store, dict) else None
    by_slug: dict = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        by_slug.setdefault(record.get("slug"), []).append(record)
    for programme in programmes.active_declarations(state):
        waiting = []
        for record in by_slug.get(programme["slug"]) or []:
            posts = record.get("posts") or []
            decl = (posts[-1] or {}).get("owner_waiting") if posts else None
            if decl:
                waiting.append(
                    {
                        "goal": record.get("slug"),
                        "label": decl.get("label"),
                        "commissioned_at": decl.get("commissioned_at"),
                        "declared_at": decl.get("declared_at"),
                    }
                )
        snapshot[programme["slug"]] = {"at": now, "owner_waiting": waiting}
    before = {
        slug: entry.get("owner_waiting")
        for slug, entry in (state.get("goal_snapshot") or {}).items()
    }
    if {s: e["owner_waiting"] for s, e in snapshot.items()} == before:
        return False
    state["goal_snapshot"] = snapshot
    return True
