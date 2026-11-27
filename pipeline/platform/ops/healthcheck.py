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
         f"http://127.0.0.1:{os.environ.get('VENUE_LEASE_UI_PORT', '8793')}"
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


import importlib.util  # noqa: E402


def _load_paths():
    """The platform paths spine, loaded by path (the
    package's standing bootstrap form)."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_paths",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "paths.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_argv():
    """The unified argv module, located through the
    paths spine and loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_argv", _load_paths().ARGV)
    module = importlib.util.module_from_spec(spec)
    sys.modules["pipeline_platform_argv"] = module
    spec.loader.exec_module(module)
    return module


uargv = _load_argv()
from types import SimpleNamespace  # noqa: E402


# The declared surface, parsed by the unified argv
# module (pipeline/platform/argv.py): both value forms
# are one flag, unknown flags and surplus positionals
# refuse at exit 2, and help is generated from this
# declaration.
DECL = {
    "name": "healthcheck",
    "flags": {
        "unit": {"takes_value": True, "choices": sorted(UNIT_SURFACES), "help": 'probe only the surfaces this unit serves'},
    },
}

def _parse(argv):
    outcome = uargv.parse_only(
        DECL, sys.argv[1:] if argv is None else argv)
    if not outcome["ok"]:
        print(outcome["error"], file=sys.stderr)
        print(outcome["usage"], file=sys.stderr)
        raise SystemExit(uargv.USAGE_EXIT)
    if "help" in outcome:
        print(outcome["help"], end="")
        raise SystemExit(0)
    result = outcome["result"]
    merged = dict(result["flags"])
    merged.update(result["positionals"])
    return SimpleNamespace(
        **{key.replace("-", "_"): value
           for key, value in merged.items()})


def main(argv=None) -> int:
    args = _parse(argv)
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
