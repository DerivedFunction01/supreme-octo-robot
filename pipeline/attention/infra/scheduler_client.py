"""The scheduler surface client (S-5 ingest leg).

Reads the scheduler's served pending pings — the one
read the report-ping ingest consumes. Unauthenticated:
the scheduler's /api/v1 reads are open on the loopback
surface (the bearer token guards its /tools bridge).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from attention.settings import Settings


class SchedulerUnavailable(Exception):
    """The scheduler surface could not be read."""


def fetch_pending_pings(settings: Settings) -> list:
    """The scheduler's unacked pings, oldest first, as
    their outbox records (id, kind, job_id, created,
    detail, …). Raises SchedulerUnavailable on any
    failure — the caller keeps its last state."""
    url = settings.bridge_url.rstrip("/") + "/api/v1/pings"
    try:
        with urllib.request.urlopen(url, timeout=settings.bridge_timeout_s) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise SchedulerUnavailable(str(err)) from err
    pings = payload.get("pings")
    if not isinstance(pings, list):
        raise SchedulerUnavailable("pings payload malformed")
    return pings
