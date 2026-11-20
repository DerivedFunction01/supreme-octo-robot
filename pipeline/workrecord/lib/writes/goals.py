"""Goal records — contract 11's store, writer, and ping.

A goal is a record plus its ping: this module is the
record's one home in the pipeline. The work-record service
owns the store (a single JSON file of goal records, every
save riding the unified writer through lib.util's write
seam — contract 15's stage-verify-rename protocol, so a
denied or torn write leaves the prior store byte-identical).
The workspace a goal shows the world (its GOAL.md, files/,
hidden_files/) is a projection of the record, never its
source; the binding migration of live goal state into this
store is the cutover's business, not this module's.

The record (stored form, one per goal):

    slug             the goal's identity (kebab-case)
    project          the swept project the goal belongs to
    title            display title
    short_objective  optional one-clause objective for
                     condensed rows; absent, never invented
    contract         the contract block, a FIELD of the
                     record: objective / complete_when /
                     blocked_only_when / continuation —
                     all four non-empty at the writer (the
                     bundle-contract gate's rule: an
                     incomplete contract does not arm)
    ping             {cadence_minutes, armed} — the record's
                     own reminder; its scheduler entry is a
                     projection of this block (see below)
    posts            status posts in contract 03's wire
                     form, oldest first, each stamped
                     posted_at by this writer
    created_at / updated_at

Linkage is by reference only: the record names its project,
and its posts carry contract 03 refs (plan + todo_ids) —
bundles and todos themselves stay in their own stores
(WR4: two stores stay two).

The writer rules (contract 11 + its 2026-11-13 amendment):

- A post asserting a blocked state (BLOCKED-OWNER /
  BLOCKED-HARD) must carry its basis_citation (the owner's
  message reference: thread + time); without it the post
  is refused here, at the writer — it is not a renderable
  state anywhere downstream. The verifying party's stamp
  (verification: by + at) is applied by this writer when
  the poster did not supply one, exactly as the amendment
  places it: the citation is the poster's, the stamp is
  the verifier's.
- A terminal post (DONE / CLOSED — contract 06's terminal
  flags) clears the sticky owner_waiting declaration and
  retires the ping for good: the entry is deleted in the
  same writer call, and a retired ping refuses re-arm.
- Status codes are contract 06's closed set; anything
  outside it is refused, never stored.

The ping: on create (armed) and on every arm/disarm or
cadence change, the record arms its own scheduler entry
through the same writer path the progress schedules use
(lib/progress/schedule.py's jobs-dir seam): one YAML file
in the pipeline scheduling registry, contract 14's form,
owner: goal:<slug>, running `wb goal-check <slug>` — a
fixed command whose exit code is the whole verdict (0 on
track / retired / gone, 3 stalled, the stall line as
output). The entry carries no machine source stamp: that
form names a todo, and a goal record has none to name —
the goal-owned entries the registry already carries are
the precedent (owner names the goal; the record is the
truth; the entry is its projection, deleted by the same
writer call that retires the ping). A sync failure never
fails the record write it rides: the outcome rides the
mutation's result, and reconciliation is a re-sync.

The verdict mirrors the todo derivation (lib/progress):
activity is the record's latest post (or its creation);
two missed intervals at the record's cadence is a stall.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .. import paths as _paths
from .. import util as util_mod
from ..progress import schedule as schedule_mod

REPO_ROOT = _paths.PACKAGE_DIR

STORE_VERSION = 1
ENTRY_PREFIX = "goal-ping-"
CHECK_TIMEOUT_SECS = 120
STALL_MISSED_CHECKS = 2
DEFAULT_CADENCE_MINUTES = 15
# The deployment's verifying party (the supervision
# bindings name it): a blocked post's verification stamp
# is applied by main unless a caller names another.
DEFAULT_VERIFIER = "main"

# Contract 06's closed status vocabulary (code, terminal).
STATUS_CODES = {
    "WORKING": False,
    "CONTINUE": False,
    "DONE": True,
    "CLOSED": True,
    "PARKED": False,
    "BLOCKED-OWNER": False,
    "BLOCKED-HARD": False,
    "REVIEW": False,
}
BLOCKED_CODES = ("BLOCKED-OWNER", "BLOCKED-HARD")
CONTRACT_FIELDS = ("objective", "complete_when",
                   "blocked_only_when", "continuation")

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_POST_FIELDS = {"handle", "status_code", "summary", "refs",
                "done", "ongoing", "owner_waiting",
                "basis_citation", "verification"}


class GoalError(Exception):
    """A goal-record refusal: invalid input, an uncited
    blocked post, a retired ping's re-arm, a store that
    does not parse. The write it rode on did not happen."""


def default_store_path() -> Path:
    """The store's home: WB_GOALS_FILE when set, else the
    service state dir (the server config's state_dir
    default, resolved the same way)."""
    override = os.environ.get("WB_GOALS_FILE")
    if override:
        return Path(override)
    return REPO_ROOT / "state" / "goals.json"


# ----------------------------------------------------------------
# Validation
# ----------------------------------------------------------------

def _require_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise GoalError(f"goal {field} must be a non-empty "
                        f"string")
    return value


def _validate_contract(contract):
    if not isinstance(contract, dict):
        raise GoalError("goal contract must be an object "
                        "with the four contract fields")
    out = {}
    for field in CONTRACT_FIELDS:
        out[field] = _require_text(contract.get(field),
                                   f"contract {field}")
    return out


def _validate_post(post, *, verified_by, now):
    """Normalize one status post to its stored form, or
    refuse it. The writer owns posted_at and (for blocked
    posts) the verification stamp."""
    if not isinstance(post, dict):
        raise GoalError("status post must be an object")
    unknown = set(post) - _POST_FIELDS - {"posted_at"}
    if unknown:
        raise GoalError(
            f"status post carries unknown fields: "
            f"{sorted(unknown)}")
    code = post.get("status_code")
    if code not in STATUS_CODES:
        raise GoalError(
            f"status_code {code!r} is outside contract "
            f"06's closed set")
    out = {
        "handle": _require_text(post.get("handle"),
                                "post handle"),
        "status_code": code,
        "summary": _require_text(post.get("summary"),
                                 "post summary"),
    }
    for field in ("refs", "done", "ongoing"):
        if post.get(field) is not None:
            out[field] = post[field]
    if post.get("owner_waiting") is not None:
        waiting = post["owner_waiting"]
        if not isinstance(waiting, dict) \
                or not waiting.get("label") \
                or not waiting.get("commissioned_at"):
            raise GoalError(
                "owner_waiting names a label and its "
                "commissioned_at")
        out["owner_waiting"] = {
            "label": waiting["label"],
            "commissioned_at": waiting["commissioned_at"],
        }
    if code in BLOCKED_CODES:
        # Contract 11 amendment: the pair or the refusal.
        citation = post.get("basis_citation")
        if not isinstance(citation, dict) \
                or not str(citation.get("thread") or
                           "").strip() \
                or not str(citation.get("at") or "").strip():
            raise GoalError(
                "a blocked post must carry its basis "
                "citation — the owner's message reference "
                "(thread + time); uncited blocked posts "
                "are refused at the writer")
        out["basis_citation"] = {
            "thread": citation["thread"],
            "at": citation["at"],
        }
        verification = post.get("verification")
        if verification is None:
            verification = {"by": verified_by, "at": now}
        if not isinstance(verification, dict) \
                or not verification.get("by") \
                or not verification.get("at"):
            raise GoalError(
                "verification names the verifying party "
                "and its time")
        out["verification"] = {
            "by": verification["by"],
            "at": verification["at"],
        }
    if STATUS_CODES[code]:
        # A terminal post clears the sticky owner-waiting
        # declaration (contract 03): the stored post
        # carries it as null, never as the stale claim.
        if out.get("owner_waiting") is not None:
            out["owner_waiting"] = None
    out["posted_at"] = now
    return out


# ----------------------------------------------------------------
# The store
# ----------------------------------------------------------------

class GoalStore:
    """The goal-record store over one JSON file. Reads
    are fail-closed: a file that does not parse, or parses
    to the wrong shape, raises GoalError rather than
    serving a partial truth (the registry store's rule).
    A missing file is an empty store — the honest absence
    every fresh deployment starts from."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None \
            else default_store_path()

    # -- reads --------------------------------------------

    def _load(self) -> list:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as e:
            raise GoalError(
                f"goal store unreadable: {e}") from e
        try:
            data = json.loads(raw)
        except ValueError as e:
            raise GoalError(
                f"goal store at {self.path} does not "
                f"parse: {e}") from e
        if not isinstance(data, dict) \
                or not isinstance(data.get("goals"), list):
            raise GoalError(
                f"goal store at {self.path} has the "
                f"wrong shape")
        return data["goals"]

    def records(self) -> list:
        return self._load()

    def get(self, slug):
        for record in self._load():
            if record.get("slug") == slug:
                return record
        return None

    def _require(self, slug):
        record = self.get(slug)
        if record is None:
            raise GoalError(f"unknown goal {slug}")
        return record

    # -- writes --------------------------------------------

    def _save(self, records) -> None:
        payload = {"version": STORE_VERSION,
                   "goals": records}
        text = json.dumps(payload, indent=2,
                          sort_keys=True) + "\n"
        util_mod.write_text(self.path, text)

    def _mutate(self, slug, change, *, sync=True):
        """Load, apply `change(record)` to the named
        record, save, then bring the record's ping entry
        in line with its post-write state. The entry sync
        mirrors the progress schedules' posture: it never
        fails the record write — its outcome rides the
        returned dict as `ping_sync`."""
        records = self._load()
        for record in records:
            if record.get("slug") == slug:
                change(record)
                record["updated_at"] = util_mod.now_iso()
                self._save(records)
                outcome = {"record": record}
                if sync:
                    outcome["ping_sync"] = \
                        sync_goal_entry(self, record)
                return outcome
        raise GoalError(f"unknown goal {slug}")

    def create(self, slug, project, title, contract, *,
               cadence_minutes=DEFAULT_CADENCE_MINUTES,
               armed=True, short_objective=None, now=None):
        """Create a goal record and (when armed) arm its
        ping in the same call: the record arms its own
        schedule, as contract 11 places it. Returns the
        mutation outcome ({record, ping_sync})."""
        if not isinstance(slug, str) \
                or not _SLUG_RE.match(slug):
            raise GoalError(
                f"goal slug {slug!r} must be kebab-case")
        _require_text(project, "project")
        _require_text(title, "title")
        contract = _validate_contract(contract)
        if not isinstance(cadence_minutes, int) \
                or isinstance(cadence_minutes, bool) \
                or cadence_minutes <= 0:
            raise GoalError(
                "cadence_minutes must be a positive "
                "integer")
        if short_objective is not None:
            _require_text(short_objective,
                          "short_objective")
        records = self._load()
        if any(r.get("slug") == slug for r in records):
            raise GoalError(f"goal {slug} already exists")
        stamp = now or util_mod.now_iso()
        record = {
            "slug": slug,
            "project": project,
            "title": title,
            "short_objective": short_objective,
            "contract": contract,
            "ping": {"cadence_minutes": cadence_minutes,
                     "armed": bool(armed)},
            "posts": [],
            "created_at": stamp,
            "updated_at": stamp,
        }
        records.append(record)
        self._save(records)
        return {"record": record,
                "ping_sync": sync_goal_entry(self, record)}

    def update_record(self, slug, *, title=None,
                      short_objective=None, contract=None):
        """Field updates to the record itself (the ping
        and posts have their own verbs). A contract given
        here is validated whole — the four fields land
        together or not at all."""
        def change(record):
            if title is not None:
                record["title"] = _require_text(
                    title, "title")
            if short_objective is not None:
                record["short_objective"] = \
                    _require_text(short_objective,
                                  "short_objective")
            if contract is not None:
                record["contract"] = \
                    _validate_contract(contract)
        return self._mutate(slug, change, sync=False)

    def post_status(self, slug, post, *,
                    verified_by=DEFAULT_VERIFIER, now=None):
        """Append a status post under the writer rules.
        A terminal post retires the ping in the same call
        (the entry sync below deletes it): the record's
        lifecycle and its schedule never diverge."""
        stamp = now or util_mod.now_iso()
        normalized = _validate_post(
            post, verified_by=verified_by, now=stamp)

        def change(record):
            record.setdefault("posts", []).append(
                normalized)
            if STATUS_CODES[normalized["status_code"]]:
                record["ping"]["armed"] = False
        return self._mutate(slug, change)

    def set_ping(self, slug, armed, *,
                 cadence_minutes=None):
        """Arm or disarm the record's ping. Arming a
        record whose latest post is terminal is refused:
        a closed goal's ping is retired for good, never
        re-armed by a toggle."""
        def change(record):
            if armed:
                posts = record.get("posts") or []
                if posts and STATUS_CODES.get(
                        posts[-1]["status_code"]):
                    raise GoalError(
                        "this goal is closed — its ping "
                        "is retired and cannot be "
                        "re-armed")
                record["ping"]["armed"] = True
            else:
                record["ping"]["armed"] = False
            if cadence_minutes is not None:
                if not isinstance(cadence_minutes, int) \
                        or cadence_minutes <= 0:
                    raise GoalError(
                        "cadence_minutes must be a "
                        "positive integer")
                record["ping"]["cadence_minutes"] = \
                    cadence_minutes
        return self._mutate(slug, change)


# ----------------------------------------------------------------
# The ping entry (contract 14 form, owner: goal:<slug>)
# ----------------------------------------------------------------

def entry_id(slug: str) -> str:
    return f"{ENTRY_PREFIX}{slug}"


_CLASSIFICATION = (
    "fixed command (wb goal-check <slug>); exit 0 on "
    "track, retired, or gone, exit 3 stalled with the "
    "stall line as output; when it speaks is fully "
    "determined by that exit code, no content judgment")
_SELF_REMOVAL = (
    "the goal writer deletes this entry in the same "
    "writer call that retires the ping (a terminal "
    "status post or a disarm); the goal record is the "
    "record of truth and this entry is its derived "
    "schedule")


def _workspace_root():
    override = os.environ.get("WB_WORKSPACE_ROOT")
    if override:
        return Path(override)
    return REPO_ROOT.parent.parent


def _harness_root():
    override = os.environ.get("WB_VIEWER_ROOT")
    if override:
        return Path(override)
    return REPO_ROOT


def _ws_relative(path):
    try:
        return Path(path).resolve().relative_to(
            _workspace_root().resolve()).as_posix()
    except ValueError:
        return None


def _live_jobs_dir():
    """The live registry dir on THIS machine, from this
    module's own location (the progress schedules' rule):
    a seam-redirected workspace's jobs dir never compares
    equal to it."""
    return (REPO_ROOT.parent / "scheduling"
            / "jobs").resolve()


def _quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _title_text(raw: str) -> str:
    import re as _re
    text = _re.sub(r"[^A-Za-z0-9 .,;:()\-]", " ",
                   (raw or "").strip())
    return _re.sub(r"\s+", " ", text).strip()[:80]


def render_entry(record, repo_rel: str) -> str:
    """One registry entry in the scheduler's strict YAML
    subset (contract 14), rendered from the record. The
    owner field names the goal; there is no machine
    source stamp — that form names a todo, and the
    record's writer and lifecycle are stated in the
    classification and self-removal text instead."""
    slug = record["slug"]
    eid = entry_id(slug)
    title = (f"Goal ping - "
             f"{_title_text(record.get('title') or slug)} "
             f"({slug})")
    cadence = record["ping"]["cadence_minutes"]
    lines = [
        f"id: {eid}",
        f"title: {_quoted(title)}",
        "kind: scripted",
        "status: active",
        "cadence:",
        "  type: interval",
        f"  every: {cadence}m",
        f"owner: goal:{slug}",
        "run:",
        "  argv:",
        f"    - ${{WS}}/{repo_rel}/.venv/bin/python",
        f"    - ${{WS}}/{repo_rel}/wb",
        "    - goal-check",
        f"    - {slug}",
        f"timeout_secs: {CHECK_TIMEOUT_SECS}",
        "report:",
        "  when: on_failure",
        "  ok_exit_codes:",
        "    - 0",
        f"classification: {_quoted(_CLASSIFICATION)}",
        "lifetime: until_complete",
        f"self_removal: {_quoted(_SELF_REMOVAL)}",
    ]
    return "\n".join(lines) + "\n"


def sync_goal_entry(store, record) -> dict:
    """Bring one record's scheduler entry in line with
    its ping state, through the progress schedules' jobs
    dir seam. Never raises: the record is the truth and
    the entry is derived state, so a sync failure rides
    the result (the progress schedules' posture)."""
    try:
        return _sync_goal_entry(store, record)
    except Exception as e:  # noqa: BLE001 - rides the result
        return {"action": "error", "error": str(e)}


def _sync_goal_entry(store, record) -> dict:
    directory = schedule_mod.jobs_dir()
    if directory is None:
        return {"action": "skipped",
                "reason": "no scheduler jobs dir"}
    slug = record["slug"]
    eid = entry_id(slug)
    path = directory / f"{eid}.yaml"
    live = Path(directory).resolve() == _live_jobs_dir()
    if live and util_mod.under_temp_root(store.path):
        # The leak this guards (the progress schedules'
        # own): a fixture store arming into the LIVE
        # registry leaves an entry whose store dies with
        # the fixture. Fixture registries take fixture
        # pings; the live registry takes only live-store
        # records.
        return {"action": "skipped",
                "reason": "scratch store, live jobs dir"}
    if record["ping"].get("armed"):
        repo_rel = _ws_relative(_harness_root())
        if repo_rel is None:
            return {"action": "skipped",
                    "reason": "service outside the "
                              "workspace root"}
        text = render_entry(record, repo_rel)
        if path.is_file() and \
                path.read_text(encoding="utf-8") == text:
            return {"action": "unchanged", "entry": eid}
        util_mod.write_text(path, text)
        return {"action": "written", "entry": eid}
    if path.is_file():
        path.unlink()
        return {"action": "removed", "entry": eid}
    return {"action": "unchanged", "entry": eid}


# ----------------------------------------------------------------
# The verdict — `wb goal-check <slug>`
# ----------------------------------------------------------------

def last_activity(record):
    """The record's activity instant: its latest post,
    else its creation. (The deeper measure — the record's
    bundles' checkpoint activity — is the evaluator's
    business over contract 03's feeds; the ping's own
    verdict reads the record, as the todo's reads its
    file.)"""
    posts = record.get("posts") or []
    if posts:
        return util_mod.parse_instant(posts[-1].get("posted_at"))
    return util_mod.parse_instant(record.get("created_at"))


def check_goal(store, slug, *, now=None):
    """The goal ping's verdict: (exit_code, line). Exit 0
    — on track, retired, or not found (a missing record
    means an orphaned entry; pinging about it every
    cadence would only spam). Exit 3 — stalled, with the
    stall line the scheduler's failure report carries."""
    record = store.get(slug)
    if record is None:
        return 0, (f"{slug}: not found — entry orphaned "
                   f"(reconcile the registry)")
    posts = record.get("posts") or []
    if posts and STATUS_CODES.get(
            posts[-1]["status_code"]):
        return 0, (f"{slug}: "
                   f"{posts[-1]['status_code']} — "
                   f"ping retired")
    now = now or datetime.now(timezone.utc)
    activity = last_activity(record)
    cadence = record["ping"]["cadence_minutes"]
    missed = None
    if activity is not None:
        elapsed = (now - activity).total_seconds()
        missed = max(0, int(elapsed // (cadence * 60)))
    if missed is not None and missed >= STALL_MISSED_CHECKS:
        return 3, (
            f"STALLED goal {slug} "
            f"({record.get('title') or ''}): "
            f"{missed} missed checks at {cadence}m "
            f"cadence, last activity "
            f"{activity.isoformat()}")
    return 0, (f"{slug}: on track "
               f"({missed} missed checks)")


# ----------------------------------------------------------------
# The served projection (the feeds document's shape)
# ----------------------------------------------------------------

def serve_record(record) -> dict:
    """One record in the shape the workbench app's
    adapter consumes: the contract block camel-cased,
    the ping carrying its entry id, the latest post in
    contract 03's wire form with its postedAt stamp.
    Served derivations are consumed as served — nothing
    here re-derives what the record states."""
    posts = record.get("posts") or []
    last = None
    if posts:
        last = dict(posts[-1])
        last["postedAt"] = last.pop("posted_at", None)
    contract = record["contract"]
    out = {
        "slug": record["slug"],
        "project": record["project"],
        "title": record["title"],
        "contract": {
            "objective": contract["objective"],
            "completeWhen": contract["complete_when"],
            "blockedOnlyWhen":
                contract["blocked_only_when"],
            "continuation": contract["continuation"],
        },
        "ping": {
            "entryId": entry_id(record["slug"]),
            "cadenceMinutes":
                record["ping"]["cadence_minutes"],
            "armed": bool(record["ping"]["armed"]),
        },
        "lastPost": last,
    }
    if record.get("short_objective"):
        out["shortObjective"] = record["short_objective"]
    return out
