#!/usr/bin/env python3
"""Render systemd units from their templates and verify
the renders (freeze steps 8 + the rollback's renders).

One mechanism for every unit the freeze touches: the ONE
mega unit the run.py serving build lands (its template is
a freeze input — this script consumes it by path, exactly
like the existing four), and the four originals' units
whose renders are the rollback's way back.

Spec (JSON): [{"template": path, "out": filename,
"values": {"ROOT": ..., "PYTHON": ..., "HOME": ...,
"PORT": ...}}, ...]. Substitution is @KEY@ for each
value key; a render that still carries an @TOKEN@ after
substitution fails. Every render must pass
`systemd-analyze verify` (with the host's unrelated-unit
complaints filtered by name: only lines naming the
rendered file count against it).

Rendered units are machine-local artefacts, never
tracked. This script writes renders only — installing
them is the runbook's act, never the script's.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

TOKEN_RE = re.compile(r"@[A-Z_]+@")


def render(template_path, values):
    with open(template_path, encoding="utf-8") as fh:
        text = fh.read()
    for key, value in values.items():
        text = text.replace(f"@{key}@", str(value))
    leftover = TOKEN_RE.findall(text)
    if leftover:
        raise ValueError(
            f"{template_path}: unsubstituted tokens "
            f"{sorted(set(leftover))}")
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)

    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    os.makedirs(args.out_dir, exist_ok=True)
    analyzer = shutil.which("systemd-analyze")
    if analyzer is None:
        print("FAIL systemd-analyze not available; a "
              "render that cannot be verified does not ship")
        return 1

    results, failed = [], False
    for entry in spec:
        out_path = os.path.join(args.out_dir, entry["out"])
        try:
            text = render(entry["template"],
                          entry["values"])
        except ValueError as exc:
            print(f"FAIL {exc}")
            failed = True
            continue
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        proc = subprocess.run([analyzer, "verify", out_path],
                              capture_output=True, text=True)
        complaints = [line for line in
                      (proc.stderr + proc.stdout).splitlines()
                      if entry["out"] in line]
        ok = proc.returncode == 0 and not complaints
        results.append({"unit": entry["out"], "verified": ok,
                        "complaints": complaints})
        failed |= not ok
    print(f"SUMMARY {json.dumps({'rendered': results}, sort_keys=True)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
