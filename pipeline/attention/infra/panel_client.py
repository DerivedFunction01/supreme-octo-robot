"""The lease panel client: portioned state reads only.

The panel stays the source for lease state; this client
fetches one portion at a time and never stores. A failure
raises PanelUnavailable with a plain-language reason.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class PanelUnavailable(Exception):
    """The lease panel portion could not be read."""


def _get(base_url: str, part: str, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + f"/api/state/{part}", timeout=timeout
        ) as res:
            payload = json.loads(res.read())
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise PanelUnavailable("Lease panel unreachable right now.") from err
    if not isinstance(payload, dict):
        raise PanelUnavailable("Lease panel sent an unreadable reply.")
    return payload


def fetch_records(base_url: str, timeout: float) -> dict:
    return _get(base_url, "records", timeout)


def fetch_specs(base_url: str, timeout: float) -> dict:
    return _get(base_url, "specs", timeout)
