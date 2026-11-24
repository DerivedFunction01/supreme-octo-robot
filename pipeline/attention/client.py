#!/usr/bin/env python3
"""The api/1 posting client: the one transport the `attn`
CLI uses. Caller-attributed; refuses unconfigured or
unattributed calls before any request is made."""

import importlib.util
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "attention_paths", Path(__file__).resolve().parent / "paths.py"
)
_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paths)

ROOT = _paths.ATTENTION_HOME
CALLER_RECORD = ROOT / "var" / "connector" / "caller.json"
DEFAULT_URL = "http://127.0.0.1:8797"

# Calls go direct, never through an ambient proxy: the
# surface is private by default (loopback / tailnet).
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class AttentionError(Exception):
    """The base for every connector-side failure."""


class Refusal(AttentionError):
    """A named refusal: unconfigured or unattributed call."""


class ApiError(AttentionError):
    """The server answered with a problem document."""

    def __init__(self, status: int, problem: dict):
        self.status = status
        self.problem = problem
        detail = problem.get("detail") or problem.get("title") or "API error"
        super().__init__(f"{status}: {detail}")


class EmptyAnswer(AttentionError):
    """The surface answered 2xx without a JSON body
    (diagnosis of record: the serving
    process dying mid-response leaves exactly this
    shape — a status line and no body). The call's
    landing is UNKNOWN: it may or may not have been
    recorded, and the caller decides what is safe to
    repeat."""


def caller_name() -> str:
    """The governed caller: env first, then the record."""
    env = os.environ.get("ATTN_CALLER", "").strip()
    if env:
        return env
    if CALLER_RECORD.is_file():
        record = json.loads(CALLER_RECORD.read_text(encoding="utf-8"))
        name = str(record.get("caller") or "").strip()
        if name:
            return name
    raise Refusal(
        "unattributed call refused: set ATTN_CALLER or register "
        "the caller first (connector/register_caller.py)"
    )


def base_url() -> str:
    return os.environ.get("ATTN_URL", DEFAULT_URL).rstrip("/")


def request(method: str, path: str, payload: dict | None = None) -> dict:
    """One api/1 call; a problem answer raises ApiError."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base_url() + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with OPENER.open(req, timeout=10) as res:
            raw = res.read()
    except urllib.error.HTTPError as err:
        try:
            problem = json.loads(err.read())
        except ValueError:
            problem = {"title": err.reason}
        raise ApiError(err.code, problem) from err
    try:
        return json.loads(raw)
    except ValueError as err:
        raise EmptyAnswer(
            f"the surface answered {method} {path} without a JSON body "
            f"({len(raw)} bytes) — the call's landing is unknown; "
            "it may or may not have been recorded"
        ) from err


def get_registries() -> dict:
    return request("GET", "/api/v1/registries")


def post_item(payload: dict) -> dict:
    return request("POST", "/api/v1/agent/items", payload)


def post_wait(payload: dict) -> dict:
    return request("POST", "/api/v1/agent/waits", payload)


def get_wait(wait_id: str) -> dict:
    return request("GET", f"/api/v1/agent/waits/{wait_id}")


def resolve_item(item_id: str, payload: dict) -> dict:
    return request("POST", f"/api/v1/agent/items/{item_id}/resolve", payload)


def get_undispatched() -> dict:
    return request("GET", "/api/v1/sends/undispatched")


def claim_send(send_id: str, consumer: str) -> dict:
    return request("POST", f"/api/v1/sends/{send_id}/claim", {"consumer": consumer})


def ack_send(send_id: str, consumer: str, delivery_ref: str) -> dict:
    return request(
        "POST",
        f"/api/v1/sends/{send_id}/ack",
        {"consumer": consumer, "delivery_ref": delivery_ref},
    )


def suppress_send(send_id: str, reason: str) -> dict:
    return request(
        "POST",
        f"/api/v1/sends/{send_id}/suppress",
        {"reason": reason},
    )


def report_dispatch_failure(send_id: str, consumer: str, reason: str) -> dict:
    return request(
        "POST",
        "/api/v1/agent/dispatch-failures",
        {"send_id": send_id, "consumer": consumer, "reason": reason},
    )


def verify_status(handle: str, verdict: str, note: str, posted_by: str) -> dict:
    return request(
        "POST",
        "/api/v1/agent/verifications",
        {
            "handle": handle,
            "verdict": verdict,
            "note": note,
            "posted_by": posted_by,
        },
    )
