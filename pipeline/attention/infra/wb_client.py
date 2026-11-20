"""The workbench surface client: read-time pulls, plus
the one actuation the supervision plan assigns the
tick — the drain pass (Step 4), a POST that hands the
workbench this tick's programme declarations and lets
its own detector run (the minting and archiving happen
workbench-side, through the writer path; this client
still stores nothing itself).

The workbench stays the source for todo and plan state.
A failure raises WbUnavailable with a plain-language
reason.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class WbUnavailable(Exception):
    """The workbench surface could not be read."""


def _get(base_url: str, path: str, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + path, timeout=timeout
        ) as res:
            return json.loads(res.read())
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise WbUnavailable("Workbench unreachable right now.") from err


def _project_payload(base_url: str, project: str, part: str, timeout: float) -> dict:
    path = "/api/projects/" + urllib.parse.quote(project, safe="") + "/" + part
    payload = _get(base_url, path, timeout)
    if not payload.get("available", False):
        reason = "; ".join(payload.get("errors") or []) or "no reason given"
        raise WbUnavailable(f"One workbench project could not be read ({reason}).")
    return payload


def _post(base_url: str, path: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as res:
            return json.loads(res.read())
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise WbUnavailable("Workbench unreachable right now.") from err


def run_drain(base_url: str, project: str, programmes: list, timeout: float) -> dict:
    """One drain pass for a project: the response carries
    one outcome per programme (drained bundles, raised
    tail todos, archived trees)."""
    path = "/api/projects/" + urllib.parse.quote(project, safe="") + "/drain"
    return _post(base_url, path, {"programmes": programmes}, timeout)


def fetch_todos(base_url: str, project: str, timeout: float) -> dict:
    return _project_payload(base_url, project, "todos", timeout)


def fetch_plans(base_url: str, project: str, timeout: float) -> dict:
    return _project_payload(base_url, project, "plans", timeout)


def fetch_projects(base_url: str, timeout: float) -> list:
    payload = _get(base_url, "/api/projects", timeout)
    return [p["slug"] for p in payload.get("projects", []) if p.get("slug")]
