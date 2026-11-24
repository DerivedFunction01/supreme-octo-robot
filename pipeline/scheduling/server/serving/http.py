"""HTTP surface: GET /health, GET /pings, GET /pings/wakeable,
POST /pings/<id>/ack, POST /pings/<id>/woken, POST /ops (the
delegated write/patch/exec operations — see server/serving/ops.py), and
the /api/v1 viewer API (see server/serving/api.py — all derivations live
there; this module only routes). The one write on /api/v1 is
the entry config save (contract 09's amendment: the guarded
save behind the served config blocks, in server/entries/configblocks.py).
A caller of the engine — the engine never imports this module.

The routes ride the platform serving core
(pipeline/platform/serving.py) — the one serving
implementation for the whole mega app (owner ruling).
This module owns the routes and their
payloads; the wire, the reply framing, and the containment
are the core's — a fault in any route is contained in its
request and can never reach the engine's tick.
"""
import importlib.util
import json
from datetime import datetime, timezone

from . import api, connector, ops
from .. import paths as _paths
from ..entries import configblocks

UTC = timezone.utc

MAX_OPS_BODY_BYTES = 4 * 1024 * 1024


def _load_core():
    spec = importlib.util.spec_from_file_location(
        "platform_serving", _paths.PLATFORM_SERVING)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


serving = _load_core()


def build_health(engine, values, sources):
    data = engine.health_data()
    shown = dict(values)
    if "connector" in shown:
        # Caller hashes never ride /health: names and scopes only.
        shown["connector"] = connector.health_summary(values)
    data["config"] = {
        key: {"value": shown[key], "source": sources[key]} for key in sorted(shown)
    }
    return data


def _dumps(payload):
    return json.dumps(payload, sort_keys=True)


def build_mount(engine, values, sources):
    r = serving.Router()
    mount = serving.Mount(
        "scheduling", r, dumps=_dumps, unquote_path=False,
        not_found=lambda request: serving.Reply.json(
            404, {"error": "not found"}, _dumps))

    def reply(status, payload):
        # The (status, payload) tuple form: the mount
        # serializes with this dialect's dumps.
        return status, payload

    def connector_auth(request):
        header = request.headers.get("Authorization") or ""
        token = header[7:] if header.startswith("Bearer ") else None
        return connector.authenticate(values, token)

    def connector_ledger(caller, tool, status, detail=""):
        if engine.ledger is not None:
            engine.ledger.record(
                "connector", caller=caller, tool=tool,
                status=status, detail=detail)

    def no_outbox():
        return reply(503, {
            "error": "outbox unavailable (state_error)"})

    def clamped_limit(request, default, ceiling):
        raw = request.query.get("limit", str(default))
        try:
            return max(1, min(ceiling, int(raw)))
        except ValueError:
            return default

    # -- plain GETs ---------------------------------------
    def health(request):
        return reply(200, build_health(engine, values, sources))

    def pings(request):
        if engine.outbox is None:
            return no_outbox()
        return reply(200, {"pings": engine.outbox.pending()})

    def wakeable(request):
        if engine.outbox is None:
            return no_outbox()
        wake = engine.outbox.wake_set(
            datetime.now(UTC), values["outbox_ack_timeout_secs"])
        return reply(200, {"pings": wake})

    # -- viewer API ---------------------------------------
    def api_overview(request):
        return reply(200, api.overview(engine, datetime.now(UTC)))

    def api_jobs(request):
        return reply(200, api.jobs_list(engine, datetime.now(UTC)))

    def api_job(request):
        detail = api.job_detail(engine, request.params["job_id"],
                                datetime.now(UTC))
        if detail is None:
            return reply(404, {"error": "no such job"})
        return reply(200, detail)

    def api_pings(request):
        if engine.outbox is None:
            return no_outbox()
        return reply(200, api.pings_list(engine, datetime.now(UTC)))

    def api_pings_recent(request):
        if engine.outbox is None:
            return no_outbox()
        limit = clamped_limit(request, 20, 100)
        return reply(200, api.pings_recent(
            engine, datetime.now(UTC), limit=limit))

    def api_ledger(request):
        limit = clamped_limit(request, 50, 500)
        return reply(200, api.ledger_feed(
            engine, datetime.now(UTC), limit=limit))

    def api_job_config(request):
        try:
            req = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            req = None
        if not isinstance(req, dict):
            return reply(400, {
                "ok": False, "error": "bad_request",
                "detail": "body must be {\"version\": N, "
                          "\"values\": {...}}"})
        caller = req.get("caller")
        code, payload = configblocks.save_config(
            engine, request.params["job_id"], req.get("version"),
            req.get("values"),
            caller if isinstance(caller, str) and caller
            else "scheduler-app")
        return reply(code, payload)

    # -- tools surface ------------------------------------
    def tools_home(request):
        auth = connector_auth(request)
        if auth is None:
            connector_ledger("unknown", "tools", "refused",
                             "unauthenticated")
            return reply(401, {"ok": False,
                               "error": "unauthenticated"})
        caller, _scopes = auth
        connector_ledger(caller, "tools", "ok")
        return reply(200, {"ok": True,
                           "tools": connector.tool_scopes()})

    def tool_result(request):
        auth = connector_auth(request)
        if auth is None:
            connector_ledger("unknown", "tools", "refused",
                             "unauthenticated")
            return reply(401, {"ok": False,
                               "error": "unauthenticated"})
        caller, scopes = auth
        try:
            code, payload = connector.fetch_result(
                engine, values, caller, scopes,
                request.params["result_id"])
        except connector.ToolError as exc:
            connector_ledger(caller, "result", "error", exc.name)
            return reply(exc.status, {"ok": False, "error": exc.name,
                                      "detail": exc.detail})
        connector_ledger(caller, "result",
                         payload.get("status", "ok"))
        return reply(code, payload)

    def tool_post(request):
        tool = request.params["tool"]
        auth = connector_auth(request)
        if auth is None:
            connector_ledger("unknown", tool, "refused",
                             "unauthenticated")
            return reply(401, {"ok": False,
                               "error": "unauthenticated"})
        caller, scopes = auth
        try:
            req = json.loads(request.body.decode("utf-8"))
            args = req.get("args") if isinstance(req, dict) else None
            envelope_id = req.get("envelope_id") \
                if isinstance(req, dict) else None
        except (ValueError, UnicodeDecodeError):
            args = None
            envelope_id = None
        if not isinstance(args, dict):
            connector_ledger(caller, tool, "error", "bad_args")
            return reply(400, {
                "ok": False, "error": "bad_args",
                "detail": "body must be {\"args\": {...}}"})
        try:
            code, payload = connector.call_tool(
                engine, values, caller, scopes, tool, args,
                envelope_id=envelope_id)
        except connector.ToolError as exc:
            connector_ledger(
                caller, tool,
                "refused" if exc.name == "scope_refused" else "error",
                exc.name)
            return reply(exc.status, {"ok": False, "error": exc.name,
                                      "detail": exc.detail})
        connector_ledger(
            caller, tool,
            "deduped" if payload.get("deduped")
            else payload.get("status", "ok"))
        return reply(code, payload)

    # -- ops ----------------------------------------------
    def ops_post(request):
        body = request.body
        if len(body) <= 0:
            return reply(400, {"ok": False, "error": "bad_request",
                               "detail": "missing request body"})
        if len(body) > MAX_OPS_BODY_BYTES:
            return reply(413, {"ok": False, "error": "bad_request",
                               "detail": "request body too large"})
        try:
            req = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return reply(400, {"ok": False, "error": "bad_request",
                               "detail": "body is not JSON"})
        # /ops rides the /tools token model (§10.1): the
        # bearer token authenticates here; ops.perform
        # enforces the identity and the per-op scope.
        code, payload = ops.perform(
            engine.ledger, values, req,
            auth=connector_auth(request))
        return reply(code, payload)

    # -- pings writes --------------------------------------
    def ping_ack(request):
        if engine.outbox is None:
            return no_outbox()
        ping = engine.outbox.ack(request.params["ping_id"])
        if ping is None:
            return reply(404, {"error": "no such ping"})
        return reply(200, {"ping": ping})

    def ping_woken(request):
        if engine.outbox is None:
            return no_outbox()
        ping_id = request.params["ping_id"]
        if engine.outbox.get(ping_id) is None:
            return reply(404, {"error": "no such ping"})
        engine.outbox.mark_woken([ping_id])
        return reply(200, {"ping": engine.outbox.get(ping_id)})

    r.add("GET", "/health", health)
    r.add("GET", "/pings", pings)
    r.add("GET", "/pings/wakeable", wakeable)
    r.add("POST", "/pings/{ping_id}/ack", ping_ack)
    r.add("POST", "/pings/{ping_id}/woken", ping_woken)
    r.add("POST", "/ops", ops_post)
    r.add("GET", "/api/v1/overview", api_overview)
    r.add("GET", "/api/v1/jobs", api_jobs)
    r.add("GET", "/api/v1/jobs/{job_id}", api_job)
    r.add("GET", "/api/v1/pings", api_pings)
    r.add("GET", "/api/v1/pings/recent", api_pings_recent)
    r.add("GET", "/api/v1/ledger", api_ledger)
    r.add("POST", "/api/v1/jobs/{job_id}/config", api_job_config)
    r.add("GET", "/tools", tools_home)
    r.add("GET", "/tools/result/{result_id}", tool_result)
    r.add("POST", "/tools/{tool}", tool_post)
    return mount


def make_server(engine, values, sources, host=None, port=None):
    """The standalone listener for this surface on the core
    (server/main.py's entry, and the suites' fixture)."""
    host = host if host is not None else values["host"]
    port = port if port is not None else values["port"]
    return serving.Listener(build_mount(engine, values, sources),
                            host, port)
