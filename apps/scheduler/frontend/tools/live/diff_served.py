#!/usr/bin/env python3
"""Diff the two served-payload captures (dump_served.py).

Verdict rule (plan §5 S8 done-evidence + contract 09): the
pipeline-served payloads must be IDENTICAL to the pinned app's
for every preserve-listed route, except the differences a
contract amendment itself orders. The ordered set is exactly
amendment 3's migration family, which contract 09 names as
not existing in the target:

  - job view:            `migrated`            (pinned only)
  - overview registry:   `migrated` count      (pinned only)
  - job detail block:    `migrated_at`,
                         `proof_pending`       (pinned only)

The pipeline-serving landing (contract 09's pipeline-
serving section) ordered a second set: additions the pin
never served, which the live adapter now CONSUMES — the
classification axis on every job view (audience / family /
open_in, list + detail), the four detail projections
(suspended_on / self_removal / catalog / config), and the
whole G5 acked window (recent_pings: the route did not
exist at the pin). Those are dispositioned as ADDITIONS:
pipeline carries the path, the pin must not carry it at
all. (260 axis/projection paths + the one window path on
the fixture capture.)

Any other difference fails the diff and is printed with its
path and both values. Two measurements are reported but never
failed: the process pid (an environment fact, not a shape)
and the ledger store's byte size (a storage measurement whose
event content is compared exactly elsewhere in the payload).
"""
import json
import re
import sys

MISSING = object()

DISPOSITIONED = [
    re.compile(r"^jobs\.jobs\[\d+\]\.migrated$"),
    re.compile(r"^details\.[^.]+\.migrated$"),
    re.compile(r"^details\.[^.]+\.detail\.migrated_at$"),
    re.compile(r"^details\.[^.]+\.detail\.proof_pending$"),
    re.compile(r"^overview\.registry\.migrated$"),
]
# Additions ordered by the pipeline-serving landing: present
# in the pipeline payload, absent at the pin. The live
# adapter consumes every one of these shapes.
ADDITIONS = [
    re.compile(r"^jobs\.jobs\[\d+\]\.(audience|family|open_in)$"),
    re.compile(r"^details\.[^.]+\.(audience|family|open_in)$"),
    re.compile(
        r"^details\.[^.]+\.detail\."
        r"(suspended_on|self_removal|catalog|config)$"),
    re.compile(r"^recent_pings$"),
]
VOLATILE = {"overview.pid", "overview.storage.db_bytes"}


def walk(path, a, b, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            walk(f"{path}.{key}" if path else key,
                 a.get(key, MISSING), b.get(key, MISSING), out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((path, f"<{len(a)} items>", f"<{len(b)} items>"))
        for i, (x, y) in enumerate(zip(a, b)):
            walk(f"{path}[{i}]", x, y, out)
    elif a is MISSING or b is MISSING or a != b:
        out.append((path, a, b))


def show(value):
    if value is MISSING:
        return "<absent>"
    text = json.dumps(value, sort_keys=True)
    return text if len(text) <= 120 else text[:117] + "..."


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        pinned = json.load(fh)
    with open(sys.argv[2], encoding="utf-8") as fh:
        pipeline = json.load(fh)
    for key in ("tree", "pin", "served_at",
                "seed_ledger_events", "seed_ledger_sha256"):
        pinned.pop(key, None)
        pipeline.pop(key, None)
    diffs = []
    walk("", pinned, pipeline, diffs)

    dispositioned, additions, volatile, failures = [], [], [], []
    for path, a, b in diffs:
        if path in VOLATILE:
            volatile.append((path, a, b))
        elif any(rx.match(path) for rx in DISPOSITIONED):
            # The disposition is a REMOVAL: pinned carries the
            # field, the target must not carry it at all.
            if a is not MISSING and b is MISSING:
                dispositioned.append((path, a, b))
            else:
                failures.append((path, a, b))
        elif any(rx.match(path) for rx in ADDITIONS):
            # The disposition is an ADDITION: the pipeline
            # carries the shape, the pin must not carry it.
            if a is MISSING and b is not MISSING:
                additions.append((path, a, b))
            else:
                failures.append((path, a, b))
        else:
            failures.append((path, a, b))

    print(f"total differing paths: {len(diffs)}")
    print(f"dispositioned (amendment 3 migration family, "
          f"removed in target): {len(dispositioned)}")
    for path, a, b in dispositioned:
        print(f"  DISPOSITIONED  {path}: {show(a)} -> <absent>")
    print(f"dispositioned (pipeline-serving additions, "
          f"consumed by the live adapter): {len(additions)}")
    for path, a, b in additions:
        print(f"  ADDED          {path}: <absent> -> {show(b)}")
    for path, a, b in volatile:
        print(f"  VOLATILE       {path}: {show(a)} vs {show(b)} "
              f"(environment measurement, not a shape)")
    if failures:
        print(f"UNDISPOSITIONED: {len(failures)}")
        for path, a, b in failures:
            print(f"  DIFF  {path}:\n        pinned:   {show(a)}\n"
                  f"        pipeline: {show(b)}")
        return 1
    print("VERDICT: served payloads identical except the "
          "dispositioned amendment-3 removals and the "
          "pipeline-serving additions the adapter consumes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
