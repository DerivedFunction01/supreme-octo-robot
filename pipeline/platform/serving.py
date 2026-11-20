"""The platform serving core — the ONE HTTP serving
implementation for the whole mega app (owner ruling,
2026-11-14: multiple processes collapse to one process,
and the serving implementations collapse to one core).

Before this module the tree carried a hand-rolled
`BaseHTTPRequestHandler` dialect per surface (the
scheduling server's `server/serving/http.py`, the venue panel's
`ui/server.py`, and — in the pinned originals — the
workbench viewer's `server/server.py` and the attention
server's `backend/apps/server.py`), each re-implementing
routing, JSON replies, body reads, and error containment.
That is a duplicate-intent defect: the HTTP plumbing now
lives exactly here, in the platform layer beside the
unified writer (contract 15). Every surface mounts its
own routes, shapes, and error forms on this core; no
surface re-implements the plumbing.

What the core owns:
- route registration and matching (segment patterns with
  `{name}` parameters and one trailing `{name...}`
  wildcard), per mount;
- the request object (path parts, query, headers, body
  with an optional per-mount size cap, JSON body parsing
  that raises `HttpError` in the mount's own terms);
- reply normalization: a handler returns a `Reply`, a
  `(status, payload)` pair, or a bare payload (200); the
  core serializes JSON payloads through the mount's
  prepare/dumps hooks and always sends Content-Length
  under HTTP/1.1;
- error containment: a handler exception becomes the
  mount's mapped reply (domain errors) or its unhandled
  reply (500) — a route fault never escapes the request,
  never stops a listener, never touches a worker thread;
- listeners and supervision: one `ThreadingHTTPServer`
  per mount, each on its own thread, plus supervised
  worker threads (engine ticks, maintenance loops). A
  worker fault SURFACES: it is recorded, every listener
  shuts down, and `serve` returns non-zero — a dead tick
  never leaves a happily-serving process behind.

Stdlib only, like every platform module.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, parse_qsl, unquote, urlparse

__all__ = [
    "HttpError",
    "Reply",
    "Request",
    "Router",
    "Mount",
    "Listener",
    "serve",
]


class HttpError(Exception):
    """An error that IS a reply: a status, a JSON payload
    (or a message string, wrapped as {"error": ...}), and
    an optional content type. Mounts raise their own
    domain errors instead and map them via error_mapper;
    HttpError is the core's native form (bad JSON body,
    oversize body, no route)."""

    def __init__(self, status, payload, content_type=None):
        if isinstance(payload, str):
            payload = {"error": payload}
        super().__init__(status, payload)
        self.status = status
        self.payload = payload
        self.content_type = content_type


class Reply:
    """One complete response: status, body bytes, content
    type, extra headers."""

    def __init__(self, status, body, content_type, headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.status = status
        self.body = body
        self.content_type = content_type
        self.headers = dict(headers or {})

    @classmethod
    def json(cls, status, payload, dumps, prepare=None,
             content_type="application/json", headers=None):
        if prepare is not None:
            payload = prepare(payload)
        body = dumps(payload).encode("utf-8")
        return cls(status, body, content_type, headers)


def _default_dumps(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class Request:
    """One request, surface-neutral. `parts` are the path
    segments (empty segments dropped — every surface's own
    dialect split this way); `params` are the matched
    route's path parameters; `query` maps each key to its
    first value, `query_pairs` keeps the raw pairs (blank
    values included) for the routes that distinguish a
    present-but-blank parameter from an absent one."""

    def __init__(self, method, raw_path, headers, body):
        parsed = urlparse(raw_path)
        self.method = method
        self.path = parsed.path
        self.parts = [p for p in parsed.path.split("/") if p]
        self.query_pairs = parse_qsl(parsed.query,
                                     keep_blank_values=True)
        self.query = {k: v[0] for k, v in
                      parse_qs(parsed.query).items()}
        self.headers = headers
        self.body = body
        self.params = {}

    def json(self):
        """The body parsed as JSON; a body that is not JSON
        is a 400 in the core's terms."""
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise HttpError(400, "body must be JSON")

    def json_object(self):
        """The body parsed as a JSON object; an absent body
        is an empty object (the surfaces' own convention)."""
        if not self.body:
            return {}
        data = self.json()
        if not isinstance(data, dict):
            raise HttpError(400, "body must be a JSON object")
        return data


class Router:
    """An ordered route table for one mount. Patterns are
    slash-joined segments; `{name}` matches one segment,
    a final `{name...}` matches the remaining segments
    joined with '/'. First match wins."""

    def __init__(self):
        self._routes = []

    def add(self, method, pattern, handler):
        segments = tuple(p for p in pattern.split("/") if p)
        self._routes.append((method, segments, handler))
        return handler

    def route(self, method, pattern):
        def decorator(handler):
            self.add(method, pattern, handler)
            return handler
        return decorator

    def match(self, method, parts):
        for route_method, segments, handler in self._routes:
            if route_method != method:
                continue
            params = _match_segments(segments, parts)
            if params is not None:
                return handler, params
        return None, None


def _match_segments(segments, parts):
    params = {}
    for i, segment in enumerate(segments):
        if segment.startswith("{") and segment.endswith("...}"):
            params[segment[1:-4]] = "/".join(parts[i:])
            return params
        if i >= len(parts):
            return None
        if segment.startswith("{") and segment.endswith("}"):
            params[segment[1:-1]] = parts[i]
        elif segment != parts[i]:
            return None
    if len(parts) != len(segments):
        return None
    return params


class Mount:
    """One surface's binding to the core: its router plus
    the hooks that keep its served forms its own.

    - prepare_payload: transform a payload before JSON
      serialization (the attention surface's datetime
      folding rides here);
    - dumps: the JSON serializer (default: sorted,
      ensure_ascii=False);
    - error_mapper(exc) -> Reply | None: domain errors
      (the workbench ApiError family, the attention
      AppError family) become their own replies here;
    - on_unhandled(exc, request) -> Reply: the 500 form
      (default {"error": "internal: ..."} truncated);
    - decorate(reply, request) -> Reply: headers every
      reply carries (the attention security baseline);
    - pre_route(request) -> Reply | None: a reply that
      short-circuits routing (the attention OPTIONS
      answer);
    - body_cap: maximum request body bytes, or None;
    - unquote_path: decode percent-escapes in the path
      before routing (the scheduling dialect routed on
      the raw path; the other surfaces unquote);
    - not_found(request) -> Reply: the no-route form.
    """

    def __init__(self, name, router, *, prepare_payload=None,
                 dumps=None, error_mapper=None, on_unhandled=None,
                 decorate=None, pre_route=None, body_cap=None,
                 unquote_path=True, not_found=None):
        self.name = name
        self.router = router
        self.prepare_payload = prepare_payload
        self.dumps = dumps or _default_dumps
        self.error_mapper = error_mapper
        self.on_unhandled = on_unhandled or _default_unhandled
        self.decorate = decorate
        self.pre_route = pre_route
        self.body_cap = body_cap
        self.unquote_path = unquote_path
        self.not_found = not_found or _default_not_found

    def json_reply(self, status, payload, headers=None,
                   content_type="application/json"):
        return Reply.json(status, payload, self.dumps,
                          prepare=self.prepare_payload,
                          content_type=content_type,
                          headers=headers)

    def dispatch(self, request):
        """Route one request to its reply. Every exception
        is contained here: HttpError is a reply in the
        core's terms; a domain error goes through the
        mount's mapper; anything else is the mount's
        unhandled form. Nothing propagates to the server
        thread."""
        try:
            if self.pre_route is not None:
                reply = self.pre_route(request)
                if reply is not None:
                    return self._finish(reply, request)
            handler, params = self.router.match(
                request.method, request.parts)
            if handler is None:
                return self._finish(self.not_found(request),
                                    request)
            request.params = params
            result = handler(request)
            return self._finish(self._normalize(result), request)
        except HttpError as exc:
            reply = Reply.json(exc.status, exc.payload, self.dumps,
                               prepare=self.prepare_payload,
                               content_type=exc.content_type
                               or "application/json")
            return self._finish(reply, request)
        except Exception as exc:  # containment is the contract
            if self.error_mapper is not None:
                reply = self.error_mapper(exc)
                if reply is not None:
                    return self._finish(reply, request)
            return self._finish(self.on_unhandled(exc, request),
                                request)

    def _normalize(self, result):
        if isinstance(result, Reply):
            return result
        if isinstance(result, tuple):
            status, payload = result
            return self.json_reply(status, payload)
        return self.json_reply(200, result)

    def _finish(self, reply, request):
        if self.decorate is not None:
            reply = self.decorate(reply, request)
        return reply


def _default_not_found(request):
    return Reply.json(404, {"error": "not found"}, _default_dumps)


def _default_unhandled(exc, request):
    return Reply.json(500, {"error": f"internal: {exc}"[:300]},
                      _default_dumps)


class Listener:
    """One mount on one address: a ThreadingHTTPServer
    whose handler class is generated from the mount. The
    object itself carries serve_forever / shutdown /
    server_address, so existing callers that hold a server
    object keep their shape."""

    def __init__(self, mount, host, port):
        self.mount = mount
        self._closed = False
        handler_class = _make_handler_class(mount)
        self.httpd = ThreadingHTTPServer((host, port),
                                         handler_class)
        self.server_address = self.httpd.server_address

    def serve_forever(self, poll_interval=0.1):
        self.httpd.serve_forever(poll_interval=poll_interval)

    def shutdown(self):
        self.httpd.shutdown()

    def server_close(self):
        if not self._closed:
            self._closed = True
            self.httpd.server_close()

    def start(self, name=None):
        thread = threading.Thread(
            target=self.serve_forever,
            name=name or f"serve-{self.mount.name}",
            daemon=True)
        thread.start()
        return thread


def _make_handler_class(mount):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "Workhorse/1.0"

        def log_message(self, format, *args):  # quiet by default
            pass

        def _handle(self, method):
            try:
                length = int(self.headers.get("Content-Length")
                             or 0)
            except ValueError:
                length = 0
            if mount.body_cap is not None and length > mount.body_cap:
                reply = mount.json_reply(413, {"error": "body too large"})
            else:
                body = self.rfile.read(length) if length > 0 else b""
                path = unquote(self.path) if mount.unquote_path \
                    else self.path
                request = Request(method, path, self.headers, body)
                reply = mount.dispatch(request)
            self._write(reply)

        def _write(self, reply):
            try:
                self.send_response(reply.status)
                self.send_header("Content-Type", reply.content_type)
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length",
                                 str(len(reply.body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(reply.body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the caller hung up; nothing to surface

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def do_PUT(self):
            self._handle("PUT")

        def do_DELETE(self):
            self._handle("DELETE")

        def do_OPTIONS(self):
            self._handle("OPTIONS")

        def do_HEAD(self):
            self._handle("HEAD")

    return Handler


class Faults:
    """The supervision record: worker faults, by name, in
    arrival order. `serve` reads it to decide the exit."""

    def __init__(self):
        self._lock = threading.Lock()
        self._faults = []

    def record(self, name, exc):
        with self._lock:
            self._faults.append((name, exc))

    def first(self):
        with self._lock:
            return self._faults[0] if self._faults else None


def serve(listeners, workers=None, stop=None, log=print):
    """Serve every listener in this process, with the
    workers (name -> callable) as supervised threads.

    The separation this pins: a route fault is contained
    inside its request (see Mount.dispatch) and can never
    reach a worker; a worker fault is never silent — it is
    recorded, the listeners shut down, and this returns 3
    so the supervisor (systemd Restart) brings the process
    back loudly. A clean stop (the stop event set, or
    KeyboardInterrupt) returns 0.
    """
    faults = Faults()
    stop = stop if stop is not None else threading.Event()
    threads = []
    for listener in listeners:
        threads.append(listener.start())

    def supervise(name, work):
        def run():
            try:
                work(stop)
            except Exception as exc:  # a worker fault surfaces
                faults.record(name, exc)
                stop.set()
        thread = threading.Thread(target=run, name=name,
                                  daemon=True)
        thread.start()
        return thread

    for name, work in (workers or {}).items():
        supervise(name, work)

    try:
        while not stop.wait(0.2):
            fault = faults.first()
            if fault is not None:
                break
    except KeyboardInterrupt:
        stop.set()
    fault = faults.first()
    for listener in listeners:
        try:
            listener.shutdown()
            listener.server_close()
        except Exception:
            pass
    if fault is not None:
        name, exc = fault
        log(f"serving: worker {name} faulted: {exc!r}")
        return 3
    return 0
