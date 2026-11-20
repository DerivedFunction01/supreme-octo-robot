#!/usr/bin/env python3
"""Client for the harness connector (server/serving/connector.py),
shared by the scripted callers that speak its HTTP contract.

One behavior: speak the connector's HTTP contract for a scripted
caller — POST /tools/<name> with a bearer token, poll
GET /tools/result/<id> for bridged tools — and return enumerable
outcomes. No tool semantics live here; the callers own theirs.

Each caller authenticates as itself — the connector registry
(scopes per caller) is the identity of record; this module is
transport only and mints no identity. The token comes from the
environment (CONNECTOR_CLIENT_TOKEN), delivered through the
secure route and never stored in a file this repo tracks.
Without a token the client is in shadow: call() records the
would-call and returns a shadow outcome without touching the
network, so every caller can run its full code path under the
caller's shadow.

A poll timeout is not a failure: bridged requests fulfill on
the home bridge's drain cadence, which is slower than any one
caller's patience, so a request still queued at the deadline
reports "undrained" (call() returns {"undrained": True, ...})
instead of raising; the request stays queued under its envelope
dedupe and a later cycle collects its result. Genuine failures —
a refused scope, a failed fulfillment, an unreachable server —
still raise ConnectorError.

Stdlib only; no paths beyond the connector's own URL seam.
"""
import json
import os
import time
import urllib.error
import urllib.request

URL = (os.environ.get("CONNECTOR_CLIENT_URL")
       or "http://127.0.0.1:8796").rstrip("/")
ENV_TOKEN = "CONNECTOR_CLIENT_TOKEN"
POLL_SECONDS = 1200
POLL_STEP = 2


class ConnectorError(Exception):
    """An enumerable connector failure: name + human detail."""

    def __init__(self, name, detail=""):
        super().__init__(detail or name)
        self.name = name
        self.detail = detail or name


class Client:
    def __init__(self, token=None, url=None, opener=None,
                 poll_seconds=POLL_SECONDS, sleeper=time.sleep):
        self.token = (token if token is not None
                      else os.environ.get(ENV_TOKEN))
        self.url = (url or URL).rstrip("/")
        self._opener = opener or urllib.request.urlopen
        self.poll_seconds = poll_seconds
        self._sleep = sleeper
        self.would_calls = []

    @property
    def shadow(self):
        return not self.token

    def _request(self, method, path, payload=None):
        data = (json.dumps(payload).encode("utf-8")
                if payload is not None else None)
        req = urllib.request.Request(
            self.url + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self._opener(req, timeout=15) as resp:
                return resp.status, json.loads(
                    resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except ValueError:
                body = {"error": f"http {exc.code}"}
            return exc.code, body
        except (urllib.error.URLError, OSError) as exc:
            raise ConnectorError("unreachable", str(exc))

    def call(self, tool, args, envelope_id=None):
        """Call one tool; bridged tools poll to completion.

        Returns the tool's result dict, or {"undrained": True,
        "request_id": ..., "tool": ...} when the request is
        still queued at the poll deadline — the drain has not
        reached it yet, which is a wait, not a failure.
        Raises ConnectorError on an enumerable failure:
        unauthenticated, scope_refused, unknown_tool, bad_args,
        the server's error name, or a failed bridge
        fulfillment."""
        if self.shadow:
            self.would_calls.append(
                {"tool": tool, "args": args,
                 "envelope_id": envelope_id})
            return {"shadow": True, "tool": tool}
        payload = {"args": args}
        if envelope_id is not None:
            payload["envelope_id"] = envelope_id
        code, body = self._request("POST", f"/tools/{tool}", payload)
        if not body.get("ok"):
            raise ConnectorError(
                str(body.get("error") or f"http {code}"),
                str(body.get("detail") or body.get("error") or code))
        if body.get("status") == "done":
            # An envelope retry of an already-fulfilled call
            # dedupes onto the finished record: its result is
            # the performed call's result, not a new post.
            return body.get("result") or {}
        if body.get("status") == "failed":
            raise ConnectorError(
                "fulfillment_failed",
                str(body.get("error") or body.get("request_id")
                    or tool))
        if body.get("status") != "queued":
            return body.get("result") or {}
        request_id = body["request_id"]
        deadline = time.time() + self.poll_seconds
        while time.time() < deadline:
            code, body = self._request(
                "GET", f"/tools/result/{request_id}")
            if body.get("status") == "done":
                return body.get("result") or {}
            if body.get("status") == "failed":
                raise ConnectorError(
                    "fulfillment_failed",
                    str(body.get("error") or request_id))
            self._sleep(POLL_STEP)
        return {"undrained": True, "tool": tool,
                "request_id": request_id}
