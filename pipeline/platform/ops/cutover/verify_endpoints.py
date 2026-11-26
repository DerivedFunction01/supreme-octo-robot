#!/usr/bin/env python3
"""Probe the serving surfaces and report each one's
verdict (freeze step 8's verification, scripted).

The one mega unit mounts all four backends on one serving
core; the ports are per-surface and preserved. The freeze
probes, at minimum:

  scheduler   http://127.0.0.1:8796/health
  workbench   the viewer health endpoint on 8792
  attention   the ATTN_URL default endpoint on 8797
  panel       the panel state endpoint on 8793

--check name=url, repeatable; the runbook names the exact
set for the freeze. A surface that does not answer with a
2xx fails the run — one FAIL line each, never a summary
that averages a dead surface into a pass. With
--expect-status, a JSON surface whose top-level "status"
field differs also fails: a 200 that reports its own
degraded state (a server whose state failed to load
answers 200 with a non-ok status and an empty registry)
is not a raised surface. Read-only: GET only, nothing is
started or stopped here.
"""

import os
import json
import sys
import urllib.error
import urllib.request


def probe(name, url, timeout, expect_status=None):
    try:
        with urllib.request.urlopen(url, timeout=timeout) \
                as response:
            body = response.read(65536).decode(
                "utf-8", "replace")
            detail = ""
            ok = response.status < 300
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict) and \
                        "status" in parsed:
                    detail = f"status={parsed['status']}"
                    if expect_status is not None:
                        ok = ok and \
                            parsed["status"] == expect_status
                if isinstance(parsed, dict) and \
                        "registry_count" in parsed:
                    detail += \
                        f" registry_count={parsed['registry_count']}"
            except ValueError:
                pass
            return {"name": name, "url": url, "ok": ok,
                    "code": response.status, "detail": detail}
    except (urllib.error.URLError, OSError) as exc:
        return {"name": name, "url": url, "ok": False,
                "code": None, "detail": str(exc)}


import importlib.util  # noqa: E402


def _load_paths():
    """The platform paths spine, loaded by path (the
    package's standing bootstrap form)."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_paths",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "paths.py"))
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
    "name": "verify-endpoints",
    "flags": {
        "check": {"takes_value": True, "required": True, "repeatable": True},
        "timeout": {"takes_value": True, "default": 5.0},
        "expect-status": {"takes_value": True, "help": "require this top-level status value from JSON surfaces (the scheduler health's healthy value)"},
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


def main(argv=None):
    args = _parse(argv)
    try:
        args.timeout = float(args.timeout)
    except (TypeError, ValueError):
        print("verify-endpoints: flag --timeout needs a number",
              file=sys.stderr)
        raise SystemExit(uargv.USAGE_EXIT)

    results, failed = [], False
    for spec in args.check:
        name, _, url = spec.partition("=")
        result = probe(name, url, args.timeout,
                       args.expect_status)
        results.append(result)
        failed |= not result["ok"]
        print(f"{'PASS' if result['ok'] else 'FAIL'} "
              f"{name} {url} -> {result['code']} "
              f"{result['detail']}")
    print(f"SUMMARY {json.dumps({'probes': results}, sort_keys=True)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
