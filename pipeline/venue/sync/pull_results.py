#!/usr/bin/env python3
"""Verify downloaded results against their manifest before trusting them.

A result manifest lists {path, sha256, bytes} per file, as produced on the
VM. Every downloaded file must match on size and SHA-256; a mismatch is a
hard rejection (exit 1) — a corrupted download is never accepted silently.
With --session, files are first fetched with `colab download`.

The argument surface parses through the unified argv
contract (pipeline/platform/argv.py): an unknown or
malformed token is a usage refusal (exit 2), and
--help prints the generated help.
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = importlib.util.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = importlib.util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

# The unified argv contract home, loaded by location
# through the paths spine.
_argv_spec = importlib.util.spec_from_file_location(
    "pipeline_platform_argv", _paths.PLATFORM_ARGV)
platform_argv = importlib.util.module_from_spec(_argv_spec)
_argv_spec.loader.exec_module(platform_argv)

DECLARATION = {
    "name": "pull_results",
    "summary": "verify downloaded results against their "
               "manifest before trusting them",
    "flags": {
        "session": {"takes_value": True,
                    "help": "if set, download each file from "
                            "this colab session first"},
    },
    "positionals": [
        {"name": "manifest", "required": True,
         "help": "the result manifest (JSON) to verify against"},
        {"name": "dest", "required": True,
         "help": "directory holding (or to hold) the "
                 "downloaded files"},
    ],
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    try:
        parsed = platform_argv.parse(DECLARATION, sys.argv[1:])
    except platform_argv.UsageError as exc:
        print(str(exc), file=sys.stderr)
        print(platform_argv.help_text(DECLARATION),
              file=sys.stderr, end="")
        return platform_argv.USAGE_EXIT
    if "help" in parsed:
        print(parsed["help"], end="")
        return 0
    pos = parsed["positionals"]
    flags = parsed["flags"]

    manifest = json.loads(Path(pos["manifest"]).read_text())
    dest = Path(pos["dest"])
    dest.mkdir(parents=True, exist_ok=True)
    cli = None
    if flags["session"]:
        # The CLI funnel is sync/cli.py's, the one implementation
        # every consumer loads (consolidation Lane B step 5; this
        # script used to carry its own inline resolution). Loaded
        # only on the --session path, so manifest verification
        # against already-downloaded files never touches it.
        spec = importlib.util.spec_from_file_location("cli", Path(__file__).resolve().parent / "cli.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)

    results, bad = [], False
    for entry in manifest["files"]:
        local = dest / Path(entry["path"]).name
        if cli:
            r = cli.colab("download", "-s", flags["session"], entry["path"], str(local))
            if r.returncode != 0:
                results.append({"path": entry["path"], "ok": False, "error": "download failed"})
                bad = True
                continue
        if not local.exists():
            results.append({"path": entry["path"], "ok": False, "error": "missing"})
            bad = True
            continue
        ok = local.stat().st_size == entry["bytes"] and sha256(local) == entry["sha256"]
        results.append({"path": entry["path"], "ok": ok, "bytes": local.stat().st_size})
        bad |= not ok
    print(json.dumps({"verified": not bad, "files": results}, indent=2))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
