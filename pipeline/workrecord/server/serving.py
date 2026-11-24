"""The workbench viewer's serving shell, on the platform
serving core (pipeline/platform/serving.py) — the one
serving implementation for the whole mega app (owner
ruling).

This module is the shell the OI-3 unit template's run.py
shape always pointed at: the single-instance lock, the
stack-dump watchdog, bind-before-warm, the route table,
and the message-maintenance loops. The feed and mutation
logic lives in the sibling modules (feeds, repos_feed,
messages_api, actions); the wire, the reply framing, and
the containment are the core's.

Startup order is the pinned server's (wedge fix):
lock, watchdog, maintenance, bind — and only
then the warm-up, on its own thread, so a storage stall
during warm-up can never park the process before it
answers. In the one-process form (the repo-root run.py),
the maintenance loops ride as supervised workers beside
the listeners: the core's supervisor owns their threads,
and a loop fault surfaces instead of dying silently on a
daemon thread. The passes themselves keep their own
containment (they never raise), exactly as the pinned
server ran them.
"""

import fcntl
import importlib.util
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from dispatch import messages as msg_mod  # noqa: E402
from evaluation import datasets as datasets_mod  # noqa: E402
from evaluation import repos as repos_mod  # noqa: E402
from lib.registry import export as export_mod  # noqa: E402
from lib.writes import files as files_mod  # noqa: E402
from lib import registry as reg  # noqa: E402
from lib.plans import parser as plan_parser  # noqa: E402

from . import config as cfgmod  # noqa: E402
from . import feedcache, task_manager as _task_manager  # noqa: E402
from . import paths as _paths  # noqa: E402
from . import stackdump as stackdump_mod  # noqa: E402
from .actions import (_require_registry, drain_action,  # noqa: E402
                      entry_action, plan_resolve, todo_action)
from .assemble import (build_feeds,  # noqa: E402
                       feeds_payload_bytes,
                       invalidate_payload,
                       kick_document_refresh,
                       prime_document_cache)
from .common import (CFG, COMMIT, MAX_BODY, STARTED_AT,  # noqa: E402
                     VERSION, ApiError, find_project, get_sweep,
                     peek_sweep)
from .goals import goal_ping, goal_status  # noqa: E402
from .feeds import (_home_invalidate_cache, board_project_feed,  # noqa: E402
                    classification_feed, diff_feed, entries_feed,
                    entry_detail, entry_segments, home_feed,
                    plans_feed, todos_feed,
                    worktrees_feed)
from .messages_api import (effective_settings, fire_pending_notifications,  # noqa: E402
                           message_archive, message_cleanup,
                           message_create, message_done, message_send,
                           message_update_body, messages_list,
                           outbox_feed, run_message_cleanup)
from .projects_feed import (code_history_feed,  # noqa: E402
                            code_status_feed,
                            projects_index_feed,
                            projects_registry_feed,
                            projects_registry_save, resolve_checkout)
from .repos_feed import (_repos_invalidate_cache,  # noqa: E402
                         dataset_rows_feed, dataset_schema_feed,
                         dataset_stats_feed, prime_census_cache,
                         repos_feed)


def _load_core():
    spec = importlib.util.spec_from_file_location(
        "platform_serving",
        Path(_paths.PIPELINE_ROOT) / "platform" / "serving.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


serving = _load_core()

_lock_fd = None


def _dumps(payload):
    return json.dumps(payload, ensure_ascii=False, indent=1)


# ----------------------------------------------------------------
# Startup pieces (the pinned server's, in its order)
# ----------------------------------------------------------------

def acquire_lock():
    global _lock_fd
    state = cfgmod.state_dir(CFG)
    state.mkdir(parents=True, exist_ok=True)
    lock_path = state / CFG["lock_file"]
    fd = open(lock_path, "a+")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"workbench-viewer: another instance holds "
              f"{lock_path}", file=sys.stderr)
        raise SystemExit(2)
    fd.seek(0)
    fd.truncate()
    fd.write(json.dumps({
        "pid": os.getpid(),
        "port": CFG["port"],
        "started_at": STARTED_AT.isoformat(),
        "version": VERSION,
    }) + "\n")
    fd.flush()
    _lock_fd = fd  # held for the process's life


def _warm_feeds() -> None:
    """Fill the cached derivations (the sweep, the
    repos census, home, and the assembled feeds
    document) once at startup, off the request path
    (the pinned server's docstring stands: binding
    first costs a cold first request only — the feeds
    document's assembly is the expensive one, so its
    cold compute belongs here, not on the first
    GET /api/feeds). When build_mount primed the
    document cache from the persisted document, this
    pass's build_feeds() serves the prime and the
    reassembly runs on the cache's refresh thread
    instead."""
    get_sweep()
    repos_feed()
    projects_index_feed()
    home_feed()
    build_feeds()


def _cleanup_worker(stop):
    # Spec §5.3: the cleanup pass runs at server start and
    # daily inside the server process. No cron.
    run_message_cleanup("startup")
    while not stop.wait(24 * 3600):
        run_message_cleanup("daily")


def _notify_worker(stop):
    # Spec §15.1: the notify poll loop, on the core's
    # supervised thread instead of a daemon thread.
    while not stop.is_set():
        fire_pending_notifications()
        stop.wait(max(5, CFG["messages_notify_poll_s"]))


# ----------------------------------------------------------------
# The mount
# ----------------------------------------------------------------

def build_mount():
    """Build this surface's mount and its supervised
    workers; returns (mount, workers, host, port). Takes
    the single-instance lock and starts the watchdog —
    call once per process."""
    acquire_lock()
    # stackdump-contract: v1 — the in-process watchdog
    # supervises the sweep computation (get_sweep, the
    # fill the health route reports on by peek), started
    # before the bind so even a stall during warm-up is
    # captured.
    stackdump_mod.start_stackdump(
        lambda: get_sweep(), cfgmod.stackdump_path(CFG),
        server_name="workbench-viewer", cfg=CFG)

    r = serving.Router()

    def not_found(request):
        raise_mounted = ApiError(
            404, f"no route: {'/' + '/'.join(request.parts)}")
        return mount.json_reply(
            raise_mounted.status, raise_mounted.payload,
            content_type="application/json; charset=utf-8")

    def error_mapper(exc):
        if isinstance(exc, ApiError):
            return mount.json_reply(
                exc.status, exc.payload,
                content_type="application/json; charset=utf-8")
        if isinstance(exc, files_mod.FileError_):
            return mount.json_reply(
                exc.status, dict(exc.payload),
                content_type="application/json; charset=utf-8")
        if isinstance(exc, msg_mod.MessageError):
            return mount.json_reply(
                400, {"error": str(exc)},
                content_type="application/json; charset=utf-8")
        return None

    mount = serving.Mount("workbench", r, dumps=_dumps,
                          error_mapper=error_mapper,
                          not_found=not_found)

    def reply(status, payload):
        return mount.json_reply(
            status, payload,
            content_type="application/json; charset=utf-8")

    def body(request) -> dict:
        if len(request.body) > MAX_BODY:
            raise ApiError(413, "body too large")
        if not request.body:
            return {}
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            raise ApiError(400, "body must be JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "body must be a JSON object")
        return data

    def project_or_404(slug):
        project = find_project(slug)
        if project is None:
            raise ApiError(404, f"no such project: {slug}")
        return project

    # -- the byte route -----------------------------------
    def raw(request):
        # GET /raw/<slug>/entries/<id>/<path...> — an
        # entry's file bytes served as a document (SPEC
        # §7): the one route outside /api, answered in
        # bytes, with plain-text errors.
        parts = request.parts
        if len(parts) < 5:
            raise ApiError(
                404, f"no route: {'/' + '/'.join(parts)}")
        try:
            project = find_project(parts[1])
            if project is None:
                raise ApiError(404,
                               f"no such project: {parts[1]}")
            db = _require_registry(project)
            try:
                entry = reg.get_entry(db, parts[3])
            except reg.RegistryError as e:
                raise ApiError(404, str(e))
            raw_bytes, content_type = files_mod.entry_bytes(
                entry, "/".join(parts[4:]))
        except ApiError as e:
            return serving.Reply(e.status,
                                 (e.payload["error"] + "\n"),
                                 "text/plain; charset=utf-8")
        except files_mod.FileError_ as e:
            return serving.Reply(e.status, (str(e) + "\n"),
                                 "text/plain; charset=utf-8")
        return serving.Reply(200, raw_bytes, content_type,
                             headers={"Cache-Control": "no-store"})

    # -- plain reads ---------------------------------------
    def health(request):
        # The sweep serves by peek, never by compute:
        # health is the route that must answer while
        # everything else is still filling (a cold
        # start's first sweep can take a minute, and
        # get_sweep computes that fill on the caller's
        # thread), so it reports the cache's warmth as
        # data — sweep_warm, with zero counts while
        # cold — and never queues behind the fill
        # (the coupling ruling's health
        # discipline, carried inside this process).
        result = peek_sweep()
        projects = len(result.projects) \
            if result is not None else 0
        errors = len(result.errors) \
            if result is not None else 0
        uptime = (datetime.now(timezone.utc)
                  - STARTED_AT).total_seconds()
        return reply(200, {
            "ok": True, "version": VERSION, "commit": COMMIT,
            "started_at": STARTED_AT.isoformat(),
            "uptime_s": round(uptime, 1),
            "host": CFG["host"], "port": CFG["port"],
            "projects_count": projects,
            "stackdump_last_at": stackdump_mod.last_dump_at(),
            "config_hash": cfgmod.config_hash(CFG),
            "sweep": {"projects": projects,
                      "errors": errors},
            "sweep_warm": result is not None,
        })

    def config_route(request):
        return reply(200, {
            "config": CFG,
            "config_hash": cfgmod.config_hash(CFG),
            "config_file": str(cfgmod.config_path()),
        })

    def feeds_document(request):
        # GET /api/feeds — the whole feeds document over
        # HTTP: exactly what assemble.build_feeds builds
        # (every route family's payload, from the same
        # builders the routes serve). The serving shell's
        # original topology injected this document as
        # __WORKBENCH_FEEDS__; the published app's
        # integration entry fetches it here and injects
        # the same global before the app mounts, so both
        # forms run the live adapter over the one shape.
        # The body serves from assemble's document
        # store: the serialized bytes the last assembly
        # (or the startup prime) stored, returned
        # verbatim through the core's Reply — the same
        # raw-bytes seam the /raw route uses — with no
        # serialization and no recompute on the request
        # path. The read's one freshness act is the
        # lazy kick: past the document's TTL it spawns
        # the one background reassembly and still
        # serves the stored bytes (assemble's
        # kick_document_refresh). Only an empty store
        # (a cold start whose warm-up has not landed
        # yet) falls back to building on the request
        # path, as the route always did.
        payload = feeds_payload_bytes()
        if payload is not None:
            kick_document_refresh()
            return serving.Reply(
                200, payload,
                "application/json; charset=utf-8")
        return reply(200, build_feeds())

    def code_dispatch(request):
        # The Code facet routes (SPEC §21): the project
        # id itself may contain slashes (a repository-only
        # project's census id), so the tail dispatches on
        # its final segment, as the retired repos dispatch
        # did. ?checkout=<census id> selects a linked
        # worktree checkout; the default is the main
        # checkout.
        parts = request.parts
        last = parts[-1]
        checkout = request.query.get("checkout") or None
        if last in ("status", "files", "file", "history"):
            project_id = "/".join(parts[3:-1])
            if last == "status":
                return reply(200, code_status_feed(
                    project_id, checkout))
            if last == "history":
                return reply(200, code_history_feed(project_id))
            record, _main, _checkouts = resolve_checkout(
                project_id, checkout)
            if last == "files":
                query = request.query
                # The dir parameter's presence is read from
                # the raw query pairs: ?dir= (the root) is a
                # real request, distinct from no dir at all.
                if any(k == "dir" for k, _v in
                       request.query_pairs):
                    try:
                        listing = repos_mod.repo_dir(
                            record, query.get("dir") or "")
                    except ValueError as e:
                        raise ApiError(400, str(e))
                    except FileNotFoundError:
                        raise ApiError(404, "no such directory")
                    return reply(200, listing)
                include_all = query.get("all") in ("1", "true")
                return reply(200, repos_mod.repo_files(
                    record, include_all=include_all))
            rel = request.query.get("path")
            if not rel:
                raise ApiError(400, "file needs ?path=")
            try:
                peek = files_mod.repo_peek(
                    record["root"], rel,
                    reveal=request.query.get("reveal")
                    in ("1", "true"),
                    editing_enabled=CFG["file_editing_enabled"])
            except files_mod.FileError_ as e:
                raise ApiError(e.status, str(e))
            return reply(200, peek)
        if last == "dataset":
            record, _main, _checkouts = resolve_checkout(
                "/".join(parts[3:-1]), checkout)
            return reply(200, dataset_schema_feed(
                record, request.query))
        if len(parts) >= 6 and parts[-2] == "dataset" \
                and last in ("rows", "stats"):
            record, _main, _checkouts = resolve_checkout(
                "/".join(parts[3:-2]), checkout)
            if last == "rows":
                return reply(200, dataset_rows_feed(
                    record, request.query))
            return reply(200, dataset_stats_feed(
                record, request.query))
        raise ApiError(
            404, f"no route: {'/' + '/'.join(parts)}")

    def messages(request):
        try:
            return reply(200, messages_list(request.query))
        except msg_mod.MessageError as e:
            raise ApiError(400, str(e))

    def projects(request):
        return reply(200, get_sweep().summary())

    def project_entries(request):
        project = project_or_404(request.params["slug"])
        archived = request.query.get("archived") == "1"
        return reply(200, entries_feed(project,
                                       archived=archived))

    def project_plan(request):
        project = project_or_404(request.params["slug"])
        rel = request.query.get("path")
        if not rel:
            raise ApiError(400, "plan needs ?path=")
        if project.manifest.plans is None:
            raise ApiError(409, "project declares no plans dir")
        try:
            doc = plan_parser.load_plan(project.manifest.plans,
                                        rel)
        except (ValueError, FileNotFoundError) as e:
            raise ApiError(404, str(e))
        return reply(200, doc)

    def entry_detail_route(request):
        project = project_or_404(request.params["slug"])
        db = _require_registry(project)
        try:
            detail = entry_detail(db,
                                  request.params["entry_id"])
        except reg.RegistryError as e:
            raise ApiError(404, str(e))
        return reply(200, detail)

    def entry_segments_route(request):
        project = project_or_404(request.params["slug"])
        db = _require_registry(project)
        try:
            segments = entry_segments(
                db, request.params["entry_id"])
        except reg.RegistryError as e:
            raise ApiError(404, str(e))
        except files_mod.FileError_ as e:
            raise ApiError(e.status, str(e))
        return reply(200, segments)

    def entry_file(request):
        project = project_or_404(request.params["slug"])
        db = _require_registry(project)
        try:
            entry = reg.get_entry(db,
                                  request.params["entry_id"])
        except reg.RegistryError as e:
            raise ApiError(404, str(e))
        rel = request.query.get("path")
        if not rel:
            raise ApiError(400, "file needs ?path=")
        try:
            peek = files_mod.peek_file(
                entry, rel,
                editing_enabled=CFG["file_editing_enabled"])
        except files_mod.FileError_ as e:
            raise ApiError(e.status, str(e))
        return reply(200, peek)

    # -- writes --------------------------------------------
    def message_verb(request):
        verb = request.params["verb"]
        if verb not in ("done", "send", "archive", "body"):
            raise ApiError(
                404, f"no route: {'/' + '/'.join(request.parts)}")
        try:
            message_id = int(request.params["message_id"])
        except ValueError:
            raise ApiError(404, "no such message: "
                                f"{request.params['message_id']}")
        if verb == "body":
            return reply(200, message_update_body(
                message_id, body(request)))
        fn = {"done": message_done, "send": message_send,
              "archive": message_archive}[verb]
        return reply(200, fn(message_id))

    def refresh(request):
        # The manual escape hatch (cache-refresh plan):
        # force the sweep and bust every feed
        # cache, so the next read re-derives from disk.
        result = get_sweep(force=True)
        _repos_invalidate_cache()
        _home_invalidate_cache()
        feedcache.invalidate_all()
        invalidate_payload()
        return reply(200, {
            "ok": True, "projects": len(result.projects),
            "invalidated": ["sweep", "home", "projects", "feeds"]})

    def projects_registry_save_route(request):
        data_body = body(request)
        result = projects_registry_save(
            data_body.get("id"), data_body.get("patch"))
        _home_invalidate_cache()
        return reply(200, result)

    def code_save(request):
        record, _main, _checkouts = resolve_checkout(
            "/".join(request.parts[3:-1]),
            request.query.get("checkout") or None)
        data_body = body(request)
        state = cfgmod.state_dir(CFG)
        result = files_mod.repo_save(
            record["root"], data_body.get("path"),
            data_body.get("content"),
            data_body.get("base_sha256"),
            editing_enabled=CFG["file_editing_enabled"],
            confirm_secret=data_body.get("confirm_secret")
            is True,
            backup_dir=state / CFG["edit_backups_dir"]
            / "repos" / record["id"],
            audit_log=state / CFG["edit_audit_log"])
        _repos_invalidate_cache()
        _home_invalidate_cache()
        return reply(200, result)

    def code_dataset_sql(request):
        record, _main, _checkouts = resolve_checkout(
            "/".join(request.parts[3:-2]),
            request.query.get("checkout") or None)
        data_body = body(request)
        if not data_body.get("path") or not data_body.get("sql"):
            raise ApiError(400, "sql needs {path, sql}")
        try:
            result = datasets_mod.run_dataset_sql(
                record["root"], data_body["path"],
                data_body["sql"],
                table=data_body.get("table") or None,
                timeout_s=CFG["datasets_sql_timeout_s"])
        except datasets_mod.DatasetError as e:
            raise ApiError(400, str(e))
        return reply(200, result)

    def code_post_dispatch(request):
        # POST under /api/projects/code/<id...>: only the
        # file save and the dataset sql tails exist.
        parts = request.parts
        if parts[-1] == "file":
            return code_save(request)
        if len(parts) >= 6 and parts[-2] == "dataset" \
                and parts[-1] == "sql":
            return code_dataset_sql(request)
        raise ApiError(
            404, f"no route: {'/' + '/'.join(parts)}")

    def project_todos_post(request):
        project = project_or_404(request.params["slug"])
        result = todo_action(project, body(request))
        # The server's own .plans writes invalidate the
        # keyed feed caches immediately (the registry-
        # curation precedent).
        feedcache.invalidate_all()
        return reply(200, result)

    def project_plan_resolve(request):
        project = project_or_404(request.params["slug"])
        result = plan_resolve(project, body(request))
        feedcache.invalidate_all()
        return reply(200, result)

    def project_drain_post(request):
        project = project_or_404(request.params["slug"])
        result = drain_action(project, body(request))
        feedcache.invalidate_all()
        return reply(200, result)

    def entry_action_route(request):
        project = project_or_404(request.params["slug"])
        return reply(200, entry_action(
            project, request.params["entry_id"], body(request)))

    def entry_file_save(request):
        project = project_or_404(request.params["slug"])
        db = _require_registry(project)
        data_body = body(request)
        try:
            entry = reg.get_entry(db,
                                  request.params["entry_id"])
        except reg.RegistryError as e:
            raise ApiError(404, str(e))
        backup_root = cfgmod.state_dir(CFG) \
            / CFG["edit_backups_dir"]
        result = files_mod.save_file(
            db, entry, data_body.get("path"),
            data_body.get("content"),
            data_body.get("base_sha256"),
            editing_enabled=CFG["file_editing_enabled"],
            backup_root=backup_root, actor="viewer")
        try:
            export_mod.regenerate(db, project=project.slug)
        except Exception as e:
            raise ApiError(500, f"save landed but export "
                                f"regeneration failed: {e}",
                           mutated=True)
        return reply(200, result)

    r.add("GET", "/raw/{slug}/entries/{entry_id}/{rest...}", raw)
    r.add("GET", "/api/health", health)
    r.add("GET", "/api/config", config_route)
    r.add("GET", "/api/feeds", feeds_document)
    r.add("GET", "/api/home", lambda request: reply(200, home_feed()))
    r.add("GET", "/api/projects-index", lambda request: reply(200, projects_index_feed()))
    r.add("GET", "/api/task-manager",
          lambda request: reply(200, _task_manager.task_manager_feed()))
    r.add("GET", "/api/projects/registry",
          lambda request: reply(200, projects_registry_feed()))
    r.add("GET", "/api/projects/code/{tail...}", code_dispatch)
    r.add("GET", "/api/messages", messages)
    r.add("GET", "/api/outbox",
          lambda request: reply(200, outbox_feed(request.query)))
    r.add("GET", "/api/settings/effective",
          lambda request: reply(200, effective_settings()))
    r.add("GET", "/api/projects", projects)
    r.add("GET", "/api/projects/{slug}/worktrees",
          lambda request: reply(200, worktrees_feed(
              project_or_404(request.params["slug"]))))
    r.add("GET", "/api/projects/{slug}/diff",
          lambda request: reply(200, diff_feed(
              project_or_404(request.params["slug"]),
              request.query)))
    r.add("GET", "/api/projects/{slug}/entries", project_entries)
    r.add("GET", "/api/projects/{slug}/plans",
          lambda request: reply(200, plans_feed(
              project_or_404(request.params["slug"]))))
    r.add("GET", "/api/projects/{slug}/plan", project_plan)
    r.add("GET", "/api/projects/{slug}/todos",
          lambda request: reply(200, todos_feed(
              project_or_404(request.params["slug"]))))
    r.add("GET", "/api/projects/{slug}/classification",
          lambda request: reply(200, classification_feed(
              project_or_404(request.params["slug"]))))
    r.add("GET", "/api/projects/{slug}/board",
          lambda request: reply(200, board_project_feed(
              project_or_404(request.params["slug"]),
              request.query)))
    r.add("GET", "/api/projects/{slug}/entries/{entry_id}",
          entry_detail_route)
    r.add("GET",
          "/api/projects/{slug}/entries/{entry_id}/segments",
          entry_segments_route)
    r.add("GET", "/api/projects/{slug}/entries/{entry_id}/file",
          entry_file)
    r.add("POST", "/api/messages",
          lambda request: reply(200, message_create(body(request))))
    r.add("POST", "/api/messages/cleanup",
          lambda request: reply(200,
                                message_cleanup(body(request))))
    r.add("POST", "/api/messages/{message_id}/{verb}",
          message_verb)
    r.add("POST", "/api/projects/rescan",
          lambda request: reply(200,
                                get_sweep(force=True).summary()))
    r.add("POST", "/api/refresh", refresh)
    r.add("POST", "/api/projects/registry",
          projects_registry_save_route)
    r.add("POST", "/api/projects/code/{tail...}",
          code_post_dispatch)
    r.add("POST", "/api/projects/{slug}/todos",
          project_todos_post)
    r.add("POST", "/api/projects/{slug}/plan/resolve",
          project_plan_resolve)
    r.add("POST", "/api/projects/{slug}/drain",
          project_drain_post)
    r.add("POST", "/api/projects/{slug}/entries/{entry_id}/action",
          entry_action_route)
    r.add("POST", "/api/projects/{slug}/entries/{entry_id}/file",
          entry_file_save)
    r.add("POST", "/api/goals/{slug}/ping",
          lambda request: reply(200, goal_ping(
              request.params["slug"], body(request))))
    r.add("POST", "/api/goals/{slug}/status",
          lambda request: reply(200, goal_status(
              request.params["slug"], body(request))))

    # Prime the feeds document cache from the last
    # persisted assembly BEFORE any warm-up: the first
    # /api/feeds read then serves the persisted document
    # through the cache's stale path, with a reassembly
    # running behind it, instead of waiting on the cold
    # assembly. No persisted document (or a corrupt one)
    # primes nothing; the warm-up's cold compute stands.
    prime_document_cache()
    # The census primes beside it, from the same
    # shapes database: the warm-up's repos pass and
    # the first per-repo resolve serve the persisted
    # census through its stale path instead of paying
    # the cold walk, and the refresh behind them may
    # confirm it by the stat probe without re-walking
    # (repos_feed's persistence note).
    prime_census_cache()

    # Bind BEFORE any warm-up: the cached derivations fill
    # on this thread, off the request path. No freshness
    # keeper starts here (the lazy restore):
    # the document and census refresh on reads past
    # their TTLs, kicked from the read paths themselves,
    # so an unread serve does no discovery or assembly
    # work at all.
    threading.Thread(target=_warm_feeds, name="workbench-warm",
                     daemon=True).start()
    workers = {"workbench-cleanup": _cleanup_worker}
    targets = cfgmod.notify_targets(CFG)
    if targets["webhook"] or targets["command"]:
        workers["workbench-notify"] = _notify_worker
    return mount, workers, CFG["host"], CFG["port"]


def main() -> int:
    """The standalone entry (the package's own run.py shape,
    for a single-surface run); the mega app's one process
    is the repo-root run.py, which builds this same mount."""
    mount, workers, host, port = build_mount()
    listener = serving.Listener(mount, host, port)
    print(f"workbench-viewer server v{VERSION} on "
          f"{host}:{port} "
          f"(workspace {CFG['workspace_root']})",
          file=sys.stderr)
    return serving.serve([listener], workers=workers,
                         log=lambda line: print(line,
                                                file=sys.stderr))
