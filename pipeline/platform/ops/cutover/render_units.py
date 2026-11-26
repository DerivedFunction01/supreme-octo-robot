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

import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from durable_write import write_text

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
    "name": "render-units",
    "flags": {
        "spec": {"takes_value": True, "required": True},
        "out-dir": {"takes_value": True, "required": True},
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
        write_text(out_path, text)
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
