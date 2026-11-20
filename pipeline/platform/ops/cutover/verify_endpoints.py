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

import argparse
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="append",
                    required=True, metavar="NAME=URL")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--expect-status",
                    help="require this top-level status "
                    "value from JSON surfaces (the "
                    "scheduler health's healthy value)")
    args = ap.parse_args(argv)

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
