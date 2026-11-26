#!/usr/bin/env python3
"""The scheduler ledger export at quiesce + the mega-side
import (freeze step 7's state cutover, scripted).

At the freeze the original server is stopped and still.
This driver runs the ORIGINAL home's own export verb
(`sched logs export --all`, the JSONL export format with
its SHA-256), then the MEGA home's one-time import
(`sched logs import-jsonl` — it refuses a non-empty store,
which is the guard this sequence wants), then the mega
store's integrity check. Counts must agree three ways:
exported lines, the import's own count proof, and the
target's re-export. Any disagreement fails the run.

The rest of the server state that rides: the connector
bridge queue directory and the outbox file, when the
source state dir carries them — copied byte-for-byte and
hashed into the summary. Nothing in the source home is
written; the source state is the rollback's.

Prints one SUMMARY line (JSON). Prints no event content.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys


def _sched(home, *argv):
    proc = subprocess.run(
        [sys.executable, os.path.join(home, "bin", "sched"),
         *argv], cwd=home, capture_output=True, text=True)
    return proc


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _lines(path):
    with open(path, encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def _state_dir(home):
    config_path = os.path.join(home, "config.json")
    if os.path.isfile(config_path):
        with open(config_path, encoding="utf-8") as fh:
            configured = json.load(fh).get("home")
        if configured:
            return os.path.join(configured, "state")
    return os.path.join(home, "state")


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
    "name": "export-ledger",
    "flags": {
        "source-home": {"takes_value": True, "required": True, "help": 'the original scheduling home (quiesced; read-only here)'},
        "target-home": {"takes_value": True, "required": True, "help": 'the mega scheduling home'},
        "work-dir": {"takes_value": True, "required": True, "help": 'where the export lands'},
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

    source = os.path.abspath(args.source_home)
    target = os.path.abspath(args.target_home)
    os.makedirs(args.work_dir, exist_ok=True)
    export_path = os.path.join(args.work_dir, "ledger.jsonl")
    check_path = os.path.join(args.work_dir, "ledger.check.jsonl")

    proc = _sched(source, "logs", "export", "--all",
                  "--out", export_path)
    if proc.returncode != 0 or not os.path.isfile(export_path):
        print("FAIL source export: "
              + (proc.stderr or proc.stdout).strip()[-300:])
        return 1
    exported = _lines(export_path)
    digest = _sha256(export_path)

    # The target store must be empty: prove it by its own
    # export before importing into it.
    proc = _sched(target, "logs", "export", "--all",
                  "--out", check_path)
    if proc.returncode != 0:
        print("FAIL target pre-check export: "
              + (proc.stderr or proc.stdout).strip()[-300:])
        return 1
    if _lines(check_path) != 0:
        print("FAIL target ledger store is not empty; "
              "import-jsonl is a one-time migration into an "
              "empty store")
        return 1

    proc = _sched(target, "logs", "import-jsonl", export_path)
    if proc.returncode != 0:
        print("FAIL target import: "
              + (proc.stderr or proc.stdout).strip()[-300:])
        return 1
    proc = _sched(target, "logs", "verify")
    if proc.returncode != 0:
        print("FAIL target verify: "
              + (proc.stderr or proc.stdout).strip()[-300:])
        return 1
    proc = _sched(target, "logs", "export", "--all",
                  "--out", check_path)
    if proc.returncode != 0 or _lines(check_path) != exported:
        print("FAIL target re-export count disagrees with "
              "the source export")
        return 1
    if _sha256(check_path) != digest:
        print("FAIL target re-export hash disagrees with "
              "the source export")
        return 1

    carried = []
    source_state = _state_dir(source)
    target_state = _state_dir(target)
    for name in ("connector-bridge", "outbox.json"):
        src = os.path.join(source_state, name)
        dst = os.path.join(target_state, name)
        if not os.path.exists(src):
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
            for root, _dirs, files in os.walk(dst):
                for f in sorted(files):
                    p = os.path.join(root, f)
                    carried.append({
                        "path": os.path.relpath(p, target_state),
                        "sha256": _sha256(p)})
        else:
            os.makedirs(target_state, exist_ok=True)
            shutil.copy2(src, dst)
            carried.append({"path": name,
                            "sha256": _sha256(dst)})

    print(f"SUMMARY {json.dumps({'events': exported, 'export_sha256': digest, 'target_verified': True, 'state_carried': carried}, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
