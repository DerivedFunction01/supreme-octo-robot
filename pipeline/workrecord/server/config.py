#!/usr/bin/env python3
"""The one settings seam for the work-record server half.

Every machine- or deployment-specific value is read through
here. Precedence:  WB_VIEWER_* env var  >  config.json  >
built-in default.

Bootstrap (the only assumptions this module itself makes):
config.json lives at the service root (REPO_ROOT) unless
WB_VIEWER_CONFIG names another file. Callers import load()
from here and read nothing else directly — no literals in
the callers.

The traps this encodes (from the git repo viewer, the pattern
donor): under systemd HOME=/root, so the workspace is derived
from THIS FILE's location, never Path.home(); the port is
8792 because 8791 is the git viewer's.

Target-shape note (S8): REPO_ROOT is the work-record root
(pipeline/workrecord), so the workspace anchor is three
parents up — the same derivation the harness's `wb` uses
(its WORKSPACE_ROOT) — where the pinned repo, sitting one
level under the workspace, used one.
"""

import hashlib
import json
import os
from pathlib import Path

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "workrecord_server_paths",
    Path(__file__).resolve().parent / "paths.py")
_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paths)

HERE = Path(__file__).resolve().parent
REPO_ROOT = _paths.WORKRECORD_ROOT  # the work-record root: config.json, state/

DEFAULTS = {
    # null -> derive: the workspace is the work-record
    # root's third parent (pipeline/ -> repo root ->
    # workspace). NEVER Path.home() (systemd runs with
    # HOME=/root).
    "workspace_root": None,
    "host": "127.0.0.1",
    "port": 8792,  # 8791 is the git repo viewer's
    # null -> [workspace_root]
    "sweep_roots": None,
    "sweep_manifest": "workbench.yaml",
    "sweep_max_depth": 3,
    # "agents": the runtime's per-agent state forest under
    # the workspace root — never a project root, and its
    # thousands of UUID dirs dominated the sweep walk
    # (`wb progress` timeouts). Kept in step with
    # lib/discovery/sweep.py's DEFAULT_PRUNE.
    "sweep_prune": [".git", ".venv", ".venv311", "node_modules",
                    "__pycache__", "var", ".artifacts", "agents"],
    "sweep_ttl_s": 15,
    # Guarded file saves are OFF unless a deployment turns
    # them on: a fresh clone of this server cannot write.
    "file_editing_enabled": False,
    # Peek/save caps are enforced in lib/writes/files.py
    # (PEEK_MAX_BYTES / PEEK_MAX_LINES, same values); they are
    # listed here so /api/config reports the whole surface.
    "peek_max_bytes": 200 * 1024,
    "peek_max_lines": 2000,
    # Per-project feed lock budget: a locked project DB
    # degrades only its own payload. Enforcement is lib/'s
    # connect_readonly busy_timeout (250 ms); this key
    # records the value for the /api/config surface.
    "feed_lock_timeout_ms": 250,
    # Relative paths resolve against the repo root.
    "state_dir": "state",
    "lock_file": "server.lock",
    "health_file": "health.json",
    "link_file": "link.json",
    "repair_file": "repair.json",
    # Wedge stack dumps (stackdump-contract: v1): the
    # in-process watchdog (server/stackdump.py) checks the
    # health computation every cadence; a check unanswered
    # past the threshold dumps every thread's stack to the
    # dump file; repeats under a persisting lag are spaced
    # by the repeat interval and the file is capped in
    # aggregate. Defaults are the contract's.
    "stackdump_file": "stackdumps.log",
    "stackdump_cadence_s": 5,
    "stackdump_threshold_s": 15,
    "stackdump_repeat_s": 60,
    "stackdump_max_bytes": 16 * 1024 * 1024,
    # Auto-recovery (vm-restart bundle): the systemd unit
    # ops/install-unit.sh installs and ops/watchdog.sh keeps
    # the server under. The link probe verifies the running
    # server is this unit's MainPID — a stray process
    # answering the port is not recovery.
    "systemd_unit": "workhorse",
    "edit_backups_dir": "edit-backups",
    # Repo-home (spec §5/§6): the viewer-tied message store.
    # messages_db resolves against state_dir unless absolute.
    "messages_db": "messages.db",
    # Goal records (contract 11): the work-record
    # service's goal-record store — one JSON file of
    # records, written by lib/goals through the unified
    # writer. goals_file resolves against state_dir
    # unless absolute, like messages_db.
    "goals_file": "goals.json",
    # The assembled feeds document's persisted copy
    # (server/assemble): every successful assembly
    # writes it, and the next process primes its
    # document cache from it, so a restart serves the
    # last document stale-while-revalidate instead of
    # waiting on the cold assembly. Resolves against
    # state_dir unless absolute, like goals_file.
    "feeds_document_file": "feeds-document.json",
    # The assembled shapes' database store
    # (server/shapestore): the feeds document and the
    # repo census persist here across restarts, one
    # row per shape (payload bytes, the assembly
    # instant, a source fingerprint), so a restart
    # primes its caches from the last assembly instead
    # of paying the cold assembly / cold walk on its
    # first reads. Resolves against state_dir unless
    # absolute, like messages_db.
    "shapes_store_file": "shapes.db",
    # The assembled feeds document's freshness bound
    # (server/assemble, the lazy restore, 2026-11-16):
    # the document serves from its TTL store for this
    # long after the assembly that produced it; the
    # first read past the bound serves the stale
    # document and kicks one background reassembly.
    # The named trade: served state can be up to this
    # bound (plus one assembly's duration) old, and in
    # exchange an unread serve does zero discovery or
    # assembly work — the continuous freshness keeper
    # this replaces polled a content fingerprint every
    # minute and reassembled ~85% of the time at idle,
    # because the fingerprint's own inputs (the repos
    # registry's last_seen fold, the history appends)
    # are written by the assembly cycle itself, so the
    # signal could never read quiet. The bound is set
    # at the retired keeper's cooldown value, so the
    # worst-case freshness a reader sees does not
    # regress past what the burn cure delivered.
    # POST /api/refresh remains the manual escape.
    "feeds_document_ttl_s": 600,
    "messages_draft_ttl_days": 7,
    "messages_done_archive_days": 30,
    "messages_archive_ttl_days": 90,
    "messages_awaiting_badge_days": 14,
    "messages_per_project_cap": 1000,
    # Repo-home §15.1: optional generic notify targets for
    # new outbox rows, fired by the server maintenance loop.
    # null = not configured (the outbox table alone is the
    # interface). The command receives the event JSON on
    # stdin; the webhook receives it as a POST body.
    "messages_notify_webhook": None,
    "messages_notify_command": None,
    "messages_notify_poll_s": 30,
    # Repo-home §6: a worktree untouched this many days (or
    # merged into its base) derives the "likely done" flag.
    "worktree_stale_days": 14,
    # Stale work warnings: an OPEN plan/bundle/todo older
    # than this many days derives a stale flag on the
    # plans/todos feeds (lib/staleness work derivations;
    # age strictly greater than the threshold flags).
    "stale_warning_days": 3,
    # Repos (absorption plan, steps 2/5/7): the census
    # walks workspace_root at this depth; null prune ->
    # lib/repos DEFAULT_PRUNE. The registry + history
    # stores and the repo-save audit log live in state_dir.
    "repos_max_depth": 3,
    "repos_prune": None,
    "repos_registry_file": "repos-registry.json",
    "repos_history_file": "repos-history.jsonl",
    # The list feed serves its last computed payload for
    # this long; past it, requests keep serving that
    # payload while one background pass recomputes (the
    # derivation is a per-repo git fan-out, seconds even
    # warm). Writes invalidate the cache immediately.
    "repos_ttl_s": 30,
    # Feeds document detail scope (detail-scope
    # ruling, 2026-11-16): census repos under these
    # roots earn no repo document in the feeds
    # document — the roots name the gate's scratch
    # trees (pristine per-gate clones, reset and
    # discarded), which are working state, not
    # workspace repos; they ride the document as
    # census summaries like every unlinked repo.
    # Roots are workspace-relative unless absolute;
    # an empty list restores the full top-level scope.
    # The named roots are the scratch family as the
    # census carries it tonight: the gate's two
    # scratch trees, which the per-gate clones
    # populate, and the tmp-named scratch roots the
    # wider harness populates the same way (the
    # ruling as extended, 2026-11-16). Individual
    # scratch-shaped trees are not named — the list
    # names roots, not trees.
    "repos_detail_scratch_roots": ["tmp-gate",
                                   "tmp-gate2",
                                   ".tmp-parent-gate",
                                   "tmp-s7",
                                   ".tmp-test",
                                   ".tmp-serve-refresh"],
    # Board portions (heavy-feed batching): one portion
    # per project; the done lanes serve this many cards
    # per page (the lane totals always ride along, more
    # pages ride the same endpoint with done_offset).
    "board_done_page": 50,
    # Feed fan-out (threadpool plan): the subprocess-bound
    # derivations (per-repo git summaries, per-project
    # home rows) compute on a pool of this many workers;
    # 1 would restore the sequential derivations.
    "feed_pool_workers": 8,
    # Prime guard (poisoned-prime cure, 2026-11-16):
    # the largest persisted feeds document the prime
    # will parse at startup. The prime's parse
    # transient runs ~6x the file's size, so an
    # oversized persist makes every restart
    # un-survivable (a 752 MB document persisted by a
    # scope-uncured assembly primed at ~4.8 GB and
    # killed the service before it could assemble its
    # scoped successor). The bound is named from the
    # scoped corpus's expected size: the healthy
    # document ran ~60 MB carrying the full project
    # feeds with only a handful of repo documents,
    # and the ruled detail scope (34 repos) puts the
    # expectation at ~100 MB — the bound stands at
    # ~2.5x that, and an order below the poison
    # class. Above it the prime refuses, logs the
    # refusal and the size, and the cold assembly
    # stands (the next successful assembly's persist
    # replaces the file).
    "feeds_document_prime_max_bytes": 256 * 1024 * 1024,
    # Per-repo eager-payload budget (document-weight
    # cure, 2026-11-16): the most peek + dataset bytes
    # one repo's document carries eagerly. The per-file
    # caps (a 200 KB peek, a 1 MB dataset page) have no
    # aggregate, so a corpus-shaped repo — thousands of
    # capped files — produced a document of 170+ MB by
    # itself and the ruled 34-repo corpus persisted
    # 773 MB, whose two-generation refresh peak is what
    # the kernel OOM killer kept killing the service
    # for. The budget is named from the real corpus:
    # the largest real repo's payload is ~9 MB
    # (usmc-pay-monitor-v2), so 12 MB leaves every real
    # repo whole today and caps a corpus giant's eager
    # payload at 12 MB; past the budget, peeks take the
    # deferred form and datasets are omitted — the
    # listing stays whole and the pinned file/dataset
    # routes serve the real content on demand, the
    # same honest absence as an over-cap single file.
    "feeds_repo_document_payload_max_bytes":
        12 * 1024 * 1024,
    "edit_audit_log": "edit-log.jsonl",
    # Datasets (datasets plan, step 3): the caps are
    # enforced in lib/datasets (derivations + console);
    # the timeout is passed through, the rest are listed
    # so /api/config reports the whole surface (the peek
    # caps precedent).
    "datasets_page_max_bytes": 1024 * 1024,
    "datasets_sql_max_rows": 10000,
    "datasets_sql_max_payload_bytes": 8 * 1024 * 1024,
    "datasets_sql_timeout_s": 10,
}


def _coerce(raw: str, default):
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    if isinstance(default, list):
        return [p.strip() for p in raw.split(",") if p.strip()]
    return raw


def config_path() -> Path:
    raw = os.environ.get("WB_VIEWER_CONFIG")
    return Path(raw) if raw else REPO_ROOT / "config.json"


def load() -> dict:
    cfg = dict(DEFAULTS)
    path = config_path()
    if path.is_file():
        file_cfg = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(file_cfg, dict):
            raise ValueError(f"{path}: config must be an object")
        for key, value in file_cfg.items():
            if key.startswith("_"):
                continue  # comments in config.example.json
            if key not in DEFAULTS:
                raise ValueError(f"{path}: unknown config key "
                                 f"{key!r}")
            cfg[key] = value
    for key, default in DEFAULTS.items():
        env = os.environ.get("WB_VIEWER_" + key.upper())
        if env is not None:
            cfg[key] = _coerce(env, default)
    # Derived values, resolved once here so callers never
    # re-derive them (the systemd HOME trap lives here).
    if not cfg["workspace_root"]:
        cfg["workspace_root"] = str(
            REPO_ROOT.parent.parent.parent)
    if not cfg["sweep_roots"]:
        cfg["sweep_roots"] = [cfg["workspace_root"]]
    return cfg


def config_hash(cfg: dict) -> str:
    blob = json.dumps(cfg, sort_keys=True,
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def state_dir(cfg: dict) -> Path:
    p = Path(cfg["state_dir"])
    return p if p.is_absolute() else REPO_ROOT / p


def state_file(cfg: dict, key: str) -> Path:
    return state_dir(cfg) / cfg[key]


def sweep_roots(cfg: dict) -> list:
    return [Path(r) for r in cfg["sweep_roots"]]


def stackdump_path(cfg: dict) -> Path:
    """The stack-dump file (stackdump-contract: v1):
    state_dir/stackdump_file unless the key is absolute."""
    p = Path(cfg["stackdump_file"])
    return p if p.is_absolute() else state_dir(cfg) / p


def messages_db_path(cfg: dict) -> Path:
    """The viewer-tied message store (repo-home spec D9):
    state_dir/messages_db unless the key is absolute."""
    p = Path(cfg["messages_db"])
    return p if p.is_absolute() else state_dir(cfg) / p


def goals_path(cfg: dict) -> Path:
    """The goal-record store (contract 11): state_dir/
    goals_file unless the key is absolute."""
    p = Path(cfg["goals_file"])
    return p if p.is_absolute() else state_dir(cfg) / p


def feeds_document_path(cfg: dict) -> Path:
    """The persisted feeds document (server/assemble's
    cross-restart cache prime): state_dir/
    feeds_document_file unless the key is absolute."""
    p = Path(cfg["feeds_document_file"])
    return p if p.is_absolute() else state_dir(cfg) / p


def shapes_store_path(cfg: dict) -> Path:
    """The assembled shapes' database store
    (server/shapestore): state_dir/shapes_store_file
    unless the key is absolute."""
    p = Path(cfg["shapes_store_file"])
    return p if p.is_absolute() else state_dir(cfg) / p


def notify_targets(cfg: dict) -> dict:
    """Watcher notify targets (repo-home spec §15.1),
    assembled from the seam for lib/notify.fire_targets."""
    return {"webhook": cfg["messages_notify_webhook"],
            "command": cfg["messages_notify_command"]}


def messages_policy(cfg: dict) -> dict:
    """Cleanup policy for lib/messages.cleanup, assembled
    from the seam so lib/ never reads config itself."""
    return {
        "draft_ttl_days": cfg["messages_draft_ttl_days"],
        "done_archive_days": cfg["messages_done_archive_days"],
        "archive_ttl_days": cfg["messages_archive_ttl_days"],
        "awaiting_badge_days":
            cfg["messages_awaiting_badge_days"],
        "per_project_cap": cfg["messages_per_project_cap"],
    }
