"""The venue panel's route surface — the HTTP routes
ui/server.py mounts, extracted 2026-11-16 ahead of
server.py's file-size cap on the state_surface
precedent.

Behaviour-preserving by construction: the handlers are
server.py's own, moved whole. Their dependencies arrive
as one env namespace of callables the server supplies,
and every dependency resolves AT CALL TIME through it —
run_core, the outbox, and the state-read cache are the
server module's globals, so the test suites'
monkeypatched run_core (and a reset OUTBOX / STATE_READS)
is exactly what a dispatched request calls, as before
the extraction. The route table, the reply shapes, and
the outbox event vocabulary are unchanged.
"""

import json
import math
import mimetypes
import subprocess
from datetime import datetime

FAILURE_ACTIONS = {"refused-budget", "create-failed", "lease-disabled", "error", "extend-no-lease", "extend-unknown", "extend-standing-managed", "grant-inactive", "caps-invalid", "unknown-shape", "caller-start-refused"}
# The panel's budget-cap editor fields, in body-name → core-flag order.
BUDGET_CAP_FIELDS = {"daily_cu_budget": "--daily", "monthly_cu_budget": "--monthly", "standing_daily_cu_cap": "--standing-daily"}
STATE_PARTS = ("records", "specs", "budget", "grant", "meta", "orphans", "listeners")


def is_success(rc: int, result) -> bool:
    if rc != 0 or not isinstance(result, dict):
        return False
    action = result.get("action")
    if not action or action in FAILURE_ACTIONS or str(action).endswith("-failed"):
        return False
    return True


def fmt_hours(hours) -> str:
    value = float(hours)
    return str(int(value)) if value == int(value) else str(value)


def register_routes(r, env) -> None:
    """Register the panel's route table on the serving
    core's router. `env` carries the server's call-time
    dependencies: run_core, outbox() and state_reads()
    (the server's current globals), drain_reaper_events,
    repo_config, stackdump_last_at, ui_sh, static_dir,
    and the serving module itself."""

    def reply(status, payload):
        return status, payload

    def body(request) -> dict:
        # The pinned shell's lenient read: an absent or
        # unparseable body is an empty object.
        if not request.body:
            return {}
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    # -- reads -------------------------------------------------
    def api_state(request):
        env.drain_reaper_events()
        rc, result, err = env.state_reads().read(("state",))
        if not isinstance(result, dict):
            return reply(502, {"error": "lease core state unavailable", "detail": err, "rc": rc})
        payload = dict(result)
        payload["caps"] = env.repo_config()
        payload["stackdump_last_at"] = env.stackdump_last_at()
        return reply(200, payload)

    def api_state_part(request):
        """One portion of the state read. Portions fail alone: a
        502 here names only its own portion, and no other portion's
        endpoint is affected."""
        part = request.params["part"]
        if part not in STATE_PARTS:
            return reply(404, {"error": f"unknown state part {part!r}"})
        env.drain_reaper_events()
        rc, result, err = env.state_reads().read(
            ("state", "--part", part))
        if not isinstance(result, dict):
            return reply(502, {"error": f"lease core state {part} unavailable", "detail": err, "rc": rc})
        payload = dict(result)
        if part in ("specs", "budget"):
            # The repo-file caps ride the portions whose sections
            # render them — an instant local read.
            payload["caps"] = env.repo_config()
        payload["stackdump_last_at"] = env.stackdump_last_at()
        return reply(200, payload)

    def api_outbox(request):
        env.drain_reaper_events()
        try:
            after = int(request.query.get("after", "0"))
        except ValueError:
            after = 0
        events, last = env.outbox().after(after)
        return reply(200, {"events": events, "last_seq": last})

    def serve_static(request):
        path = request.path
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/"):]
        target = (env.static_dir / rel).resolve()
        if env.static_dir.resolve() not in target.parents and target != env.static_dir.resolve():
            return reply(404, {"error": "not found"})
        if not target.is_file():
            return reply(404, {"error": "not found"})
        raw = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return env.serving.Reply(200, raw, ctype)

    # -- mutations ----------------------------------------------
    def api_server_restart(request):
        """Ask ui.sh to restart this server (the panel's degraded-state
        recovery). The restart is spawned detached — it stops this very
        process — and the answer goes out immediately; ui.sh's restart
        pauses briefly so this response lands before the stop does."""
        try:
            subprocess.Popen(
                [env.ui_sh(), "restart"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            return reply(502, {"error": "restart spawn failed", "detail": str(exc)})
        return reply(200, {"action": "restart-requested"})

    def api_lease_start(request):
        data = body(request)
        shape = data.get("shape")
        if not shape or not isinstance(shape, str):
            return reply(400, {"error": "shape is required"})
        args = ["acquire", "--shape", shape, "--create"]
        hours = data.get("hours")
        if hours is not None:
            try:
                if float(hours) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return reply(400, {"error": "hours must be a positive number"})
            args += ["--hours", fmt_hours(hours)]
        # Panel-started leases carry the panel's requester tag, so a
        # lease record shows who started it (envelope attribution),
        # and its caller claim — the machinery caller "panel", which
        # is also the creation authority the gate's bypass rides.
        # Start is a creation, never a ride (--create): clicking
        # start mints a parallel lease; using the current lease at
        # the shape is the extend endpoint's job.
        args += ["--via", "panel", "--caller", "panel"]
        rc, result, err = env.run_core(*args)
        if result is None:
            env.outbox().append("lease-start-failed", {"shape": shape, "hours": hours, "error": err, "rc": rc})
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        kind = "lease-started" if is_success(rc, result) else "lease-start-failed"
        env.outbox().append(kind, {"shape": shape, "hours": hours, "result": result})
        return reply(200, result)

    def api_access_release(request):
        """One-tap release of an unattributed session from the access
        list: the core's release-session verb (a record-backed
        session is refused there — it releases per session). The
        body names the session — or, for a nameless census row,
        the endpoint (the core's --endpoint form, the adopt
        endpoint's discipline beside it). The outcome is appended
        to the outbox under a server-side kind the notify hook
        counts like any lease event; the UI log's kind vocabulary
        is untouched."""
        data = body(request)
        session = data.get("session")
        endpoint = data.get("endpoint")
        if endpoint is not None and (not isinstance(endpoint, str) or not endpoint):
            return reply(400, {"error": "endpoint must be an endpoint token"})
        if session and endpoint:
            return reply(400, {"error": "session and endpoint are alternatives — give one"})
        if not session and not endpoint:
            return reply(400, {"error": "session is required"})
        if session and not isinstance(session, str):
            return reply(400, {"error": "session is required"})
        args = ["release-session", "--endpoint", endpoint] if endpoint else ["release-session", session]
        rc, result, err = env.run_core(*args)
        subject = session or endpoint
        if result is None:
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        if result.get("action") == "session-released":
            env.outbox().append("session-released", {"session": subject, "result": result})
            return reply(200, result)
        return reply(409, result)

    def api_lease_stop(request):
        session = body(request).get("session")
        if not session or not isinstance(session, str):
            return reply(400, {"error": "session is required"})
        rc, result, err = env.run_core("release", session)
        if result is None:
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        # Only a real release is announced: the core's release guard
        # can abort a stop whose deadline an extension just moved
        # (release-aborted), and that is not a stop.
        if is_success(rc, result) and result.get("action") == "released":
            env.outbox().append("lease-stopped", {"session": session, "result": result})
        return reply(200, result)

    def api_lease_extend(request):
        data = body(request)
        session = data.get("session")
        if not session or not isinstance(session, str):
            return reply(400, {"error": "session is required"})
        hours = data.get("hours")
        if hours is None:
            return reply(400, {"error": "hours is required"})
        try:
            if float(hours) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return reply(400, {"error": "hours must be a positive number"})
        rc, result, err = env.run_core("extend", session, "--hours", fmt_hours(hours))
        if result is None:
            env.outbox().append("lease-extend-failed", {"session": session, "hours": hours, "error": err, "rc": rc})
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        if is_success(rc, result):
            env.outbox().append("lease-extended", {"session": session, "hours": hours, "old_deadline": result.get("old_deadline"), "new_deadline": result.get("new_deadline")})
        else:
            env.outbox().append("lease-extend-failed", {"session": session, "hours": hours, "result": result})
        return reply(200, result)

    def api_lease_adopt(request):
        """Adopt one orphaned session from the census: the core
        adopt verb with the panel caller. The body names the
        session — or, for a nameless census row, the endpoint
        (the core's --endpoint form: a fresh name is minted and
        bound, and the record restores under it) — and
        optionally plants a deadline (an ISO
        timestamp, or a positive hours count — with neither, the
        derived evidence plants itself) and a shape for a
        class-ambiguous orphan. A core refusal is a 409 with the
        verdict (the access-release mapping); an unreachable
        core is a 502. The outcome is appended to the outbox
        under server-side kinds, as the other one-tap actions
        do; the UI log vocabulary is untouched."""
        data = body(request)
        session = data.get("session")
        endpoint = data.get("endpoint")
        if endpoint is not None and (not isinstance(endpoint, str) or not endpoint):
            return reply(400, {"error": "endpoint must be an endpoint token"})
        if session and endpoint:
            return reply(400, {"error": "session and endpoint are alternatives — give one"})
        if not session and not endpoint:
            return reply(400, {"error": "session is required"})
        if session and not isinstance(session, str):
            return reply(400, {"error": "session is required"})
        deadline = data.get("deadline")
        hours = data.get("hours")
        if deadline is not None and hours is not None:
            return reply(400, {"error": "deadline and hours are alternatives — give one"})
        args = ["adopt", "--endpoint", endpoint] if endpoint else ["adopt", session]
        if deadline is not None:
            if not isinstance(deadline, str):
                return reply(400, {"error": "deadline must be an ISO timestamp"})
            try:
                datetime.fromisoformat(deadline)
            except ValueError:
                return reply(400, {"error": "deadline must be an ISO timestamp"})
            args += ["--deadline", deadline]
        elif hours is not None:
            try:
                if float(hours) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return reply(400, {"error": "hours must be a positive number"})
            args += ["--hours", fmt_hours(hours)]
        shape = data.get("shape")
        if shape is not None:
            if not isinstance(shape, str) or not shape:
                return reply(400, {"error": "shape must be a shape id"})
            args += ["--shape", shape]
        args += ["--caller", "panel"]
        rc, result, err = env.run_core(*args)
        subject = session or endpoint
        if result is None:
            env.outbox().append("lease-adopt-failed", {"session": subject, "error": err, "rc": rc})
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        if result.get("action") == "adopted":
            # An endpoint-keyed adoption mints the session's
            # name in the core; the event's subject is that
            # minted name (the result's own stamps), never
            # the request's endpoint token — the resolved
            # views title-case the subject as a display name.
            minted = (result.get("adopted_nameless") or {}).get("session") \
                or (result.get("record") or {}).get("session")
            env.outbox().append("lease-adopted", {"session": minted or subject, "result": result})
            return reply(200, result)
        env.outbox().append("lease-adopt-failed", {"session": subject, "result": result})
        return reply(409, result)

    def api_lease_shorten(request):
        """Shorten one lease from the panel: the core shorten
        verb with the panel caller. The body names the session
        and exactly one target — an ISO deadline or a positive
        hours count to pull in by. The outcome mapping mirrors
        the adopt endpoint beside it: 200 shortened, 409 core
        refusal, 502 core unreachable, with exactly one outbox
        event per call (lease-shortened / lease-shorten-failed)."""
        data = body(request)
        session = data.get("session")
        if not session or not isinstance(session, str):
            return reply(400, {"error": "session is required"})
        deadline = data.get("deadline")
        hours = data.get("hours")
        if (deadline is None) == (hours is None):
            return reply(400, {"error": "deadline or hours is required — give one"})
        args = ["shorten", session]
        if deadline is not None:
            if not isinstance(deadline, str):
                return reply(400, {"error": "deadline must be an ISO timestamp"})
            try:
                datetime.fromisoformat(deadline)
            except ValueError:
                return reply(400, {"error": "deadline must be an ISO timestamp"})
            args += ["--deadline", deadline]
        else:
            try:
                if float(hours) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return reply(400, {"error": "hours must be a positive number"})
            args += ["--hours", fmt_hours(hours)]
        args += ["--caller", "panel"]
        rc, result, err = env.run_core(*args)
        if result is None:
            env.outbox().append("lease-shorten-failed", {"session": session, "error": err, "rc": rc})
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        if result.get("action") == "shortened":
            env.outbox().append("lease-shortened", {"session": session, "result": result})
            return reply(200, result)
        env.outbox().append("lease-shorten-failed", {"session": session, "result": result})
        return reply(409, result)

    def api_grant_extend(request):
        hours = body(request).get("hours")
        if hours is None:
            return reply(400, {"error": "hours is required"})
        try:
            if float(hours) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return reply(400, {"error": "hours must be a positive number"})
        rc, result, err = env.run_core("extend-grant", "--hours", fmt_hours(hours))
        if result is None:
            env.outbox().append("grant-extend-failed", {"hours": hours, "error": err, "rc": rc})
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        if is_success(rc, result):
            env.outbox().append("grant-extended", {"hours": hours, "old_until": result.get("old_until"), "new_until": result.get("new_until")})
        else:
            env.outbox().append("grant-extend-failed", {"hours": hours, "result": result})
        return reply(200, result)

    def api_grant(request):
        data = body(request)
        hours = data.get("hours")
        if hours is None:
            return reply(400, {"error": "hours is required"})
        try:
            if float(hours) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return reply(400, {"error": "hours must be a positive number"})
        args = ["grant", "--hours", fmt_hours(hours)]
        burst = data.get("burst")
        if burst:
            if not isinstance(burst, str):
                return reply(400, {"error": "burst must be a shape id"})
            args += ["--burst", burst]
        rc, result, err = env.run_core(*args)
        if result is None:
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        if is_success(rc, result):
            env.outbox().append("grant-started", {"hours": hours, "burst": burst, "result": result})
        return reply(200, result)

    def api_ungrant(request):
        # Ungrant actuates on no target field, so an empty body
        # would end the standing grant on a bare POST (the R-2
        # class, 2026-11-15): the call must carry an explicit
        # confirmation, as the panel's confirm dialog sends.
        if body(request).get("confirm") is not True:
            return reply(400, {"error": "confirm is required"})
        rc, result, err = env.run_core("ungrant")
        if result is None:
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        if is_success(rc, result):
            env.outbox().append("grant-ended", {"result": result})
        return reply(200, result)

    def api_config_budget(request):
        """Update the budget caps (the operator's throttle, editable
        from the panel): the core validates and persists them to
        config/lease.json. Only the caps present in the body change;
        a null clears its cap (no cap)."""
        data = body(request)
        args = ["budget-caps"]
        # Addressing (venue rework): an optional venue/account
        # pair targets one adapter's one account; absent, the
        # core's default target (this venue's primary account)
        # is addressed, exactly as before accounts existed.
        for field in ("venue", "account"):
            if field in data:
                if not isinstance(data[field], str) or not data[field]:
                    return reply(400, {"error": f"{field} must be a non-empty string"})
                args += [f"--{field}", data[field]]
        provided = False
        for field, flag in BUDGET_CAP_FIELDS.items():
            if field not in data:
                continue
            provided = True
            value = data[field]
            if value is None:
                args += [flag, "none"]
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                return reply(400, {"error": f"{field} must be a non-negative number or null"})
            else:
                args += [flag, fmt_hours(value)]
        if not provided:
            return reply(400, {"error": "no budget caps provided"})
        rc, result, err = env.run_core(*args)
        if result is None:
            return reply(502, {"error": "lease core failed", "detail": err, "rc": rc})
        if is_success(rc, result):
            env.outbox().append("budget-caps-changed", {"caps": result.get("caps"), "previous": result.get("previous")})
            return reply(200, result)
        return reply(400, result)

    r.add("GET", "/api/state", api_state)
    r.add("GET", "/api/state/{part}", api_state_part)
    r.add("GET", "/api/outbox", api_outbox)
    r.add("POST", "/api/lease/start", api_lease_start)
    r.add("POST", "/api/lease/stop", api_lease_stop)
    r.add("POST", "/api/lease/extend", api_lease_extend)
    r.add("POST", "/api/lease/adopt", api_lease_adopt)
    r.add("POST", "/api/lease/shorten", api_lease_shorten)
    r.add("POST", "/api/access/release", api_access_release)
    r.add("POST", "/api/grant", api_grant)
    r.add("POST", "/api/grant/extend", api_grant_extend)
    r.add("POST", "/api/ungrant", api_ungrant)
    r.add("POST", "/api/config/budget", api_config_budget)
    r.add("POST", "/api/server/restart", api_server_restart)
    r.add("GET", "/{path...}", serve_static)
