#!/usr/bin/env python3
"""The workhorse health probe: every surface answers on
its own port, or the verdict names the silent ones.

Surfaces and their health shapes (each surface's own):
  scheduling  GET /health        -> 200, {"status": "ok",
                                  "state_error": null, ...}
  workbench   GET /api/health    -> 200, {"ok": true, ...}
  attention   GET /health        -> 200, {"status": "ok", ...}
  lease panel GET /api/outbox    -> 200, {"events": [...], ...}

Two forms. The whole-fleet form (no argument) is the
original conjunctive verdict: exit 0 iff every surface
answers. The per-unit form (--unit <name>) probes only
the surfaces the named systemd unit serves — workhorse
(scheduling + attention, the coupled process),
workbench (workbench), venue (lease panel) — and its
verdict carries the unit name; it is the form the
per-unit watchdog ladders confirm against, so one
unit's outage is never read through another unit's
surfaces.

Bounded (a per-surface timeout, a small total budget),
read-only, and quiet on success beyond the verdict line.
Exit 0 iff every probed surface answers; the verdict is
one JSON object on stdout either way. Ports and hosts
come from the surfaces' own env seams where they have
them, with WORKHORSE_HEALTH_TIMEOUT_S as the probe
budget.
"""

import argparse
import json
import os
import sys
import urllib.request

TIMEOUT_S = float(os.environ.get("WORKHORSE_HEALTH_TIMEOUT_S", "5"))

# Which surfaces each systemd unit serves (the serve
# split: process boundaries follow coupling). The
# whole-fleet form probes all of them.
UNIT_SURFACES = {
    "workhorse": ("scheduling", "attention"),
    "workbench": ("workbench",),
    "venue": ("lease-panel",),
}


def _get(url):
    req = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=TIMEOUT_S) as resp:
        return resp.status, json.loads(resp.read())


def _probe(name, url, healthy):
    try:
        status, payload = _get(url)
    except Exception as exc:  # refused, timed out, bad JSON
        return {"surface": name, "url": url, "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:200]}
    ok = status == 200 and healthy(payload)
    return {"surface": name, "url": url, "ok": ok,
            "status": status}


def _surfaces():
    return [
        ("scheduling",
         f"http://127.0.0.1:{os.environ.get('SCHEDULER_PORT', '8796')}"
         "/health",
         lambda p: p.get("status") == "ok"
         and p.get("state_error") is None),
        ("workbench",
         f"http://127.0.0.1:{os.environ.get('WB_VIEWER_PORT', '8792')}"
         "/api/health",
         lambda p: p.get("ok") is True),
        ("attention",
         f"http://127.0.0.1:{os.environ.get('ATTENTION_PORT', '8797')}"
         "/health",
         lambda p: p.get("status") == "ok"),
        ("lease-panel",
         f"http://127.0.0.1:{os.environ.get('COLAB_LEASE_UI_PORT', '8793')}"
         "/api/outbox",
         lambda p: "events" in p),
    ]


def surfaces_for(unit=None):
    """The surface definitions a probe form covers:
    one unit's surfaces, or every surface when unit is
    None (the whole-fleet form)."""
    surfaces = _surfaces()
    if unit is None:
        return surfaces
    names = UNIT_SURFACES[unit]
    return [surface for surface in surfaces
            if surface[0] in names]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Workhorse surface health probe")
    parser.add_argument(
        "--unit", choices=sorted(UNIT_SURFACES),
        default=None,
        help="probe only the surfaces this unit serves")
    args = parser.parse_args(argv)
    verdicts = [_probe(*surface)
                for surface in surfaces_for(args.unit)]
    ok = all(v["ok"] for v in verdicts)
    verdict = {"ok": ok, "surfaces": verdicts}
    if args.unit is not None:
        verdict["unit"] = args.unit
    print(json.dumps(verdict, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
