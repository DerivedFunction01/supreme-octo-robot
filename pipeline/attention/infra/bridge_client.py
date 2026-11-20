"""The harness connector bridge client.

Enqueues a bridged chat_send and fetches its
fulfillment; the caller token is read from the
settings-named file on every call, never stored.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from attention.settings import Settings


class BridgeUnavailable(Exception):
    """The bridge could not be reached or refused."""


def _token(settings: Settings) -> str | None:
    try:
        text = settings.bridge_token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _call(settings: Settings, method: str, path: str, body: dict | None):
    token = _token(settings)
    if token is None:
        return None
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        settings.bridge_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.bridge_timeout_s
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BridgeUnavailable(f"http {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise BridgeUnavailable(str(exc)) from exc


def enqueue_chat_send(
    settings: Settings,
    chat_id: str,
    text: str,
    envelope_id: str,
    meta: dict | None = None,
) -> dict | None:
    """Queue one chat_send under an idempotent envelope;
    None when no bridge token is configured."""
    args = {"chat_id": chat_id, "text": text}
    if meta:
        args["meta"] = meta
    payload = _call(
        settings,
        "POST",
        "/tools/chat_send",
        {"args": args, "envelope_id": envelope_id},
    )
    if payload is None:
        return None
    return {"request_id": payload["request_id"], "status": payload["status"]}


def fetch_result(settings: Settings, request_id: str) -> dict | None:
    """The bridge record's state: queued, or done /
    failed with its result or error; None unconfigured."""
    try:
        payload = _call(settings, "GET", f"/tools/result/{request_id}", None)
    except BridgeUnavailable as exc:
        if "http 404" in str(exc):
            return {"status": "missing", "result": None, "error": None}
        raise
    if payload is None:
        return None
    return {
        "status": payload["status"],
        "result": payload.get("result"),
        "error": payload.get("error"),
    }
