#!/usr/bin/env python3
"""Kit drift check: the kit matches its pin, or the verdict
names the files that moved.

The workhorse kit's home and one source of truth is this
repo's kit/ tree (see kit/PROVENANCE.md): the kit was forked
from the starter's kit into this repo's own kit at the
starter's kit consolidation, so there is no external tree
to drift against. This check is the discipline's teeth:

- every kit file's sha256 matches kit/manifest.json. A file
  added, removed, or changed against the manifest is
  drift — the manifest is regenerated in the same change as
  any kit edit, so any mismatch means an unrecorded edit or
  a half-finished change.

Verdicts name files only, never contents. Exit 0 iff no
drift; 1 on drift; 2 on usage error (missing kit home,
missing or unreadable manifest). The governance files
(manifest.json, PROVENANCE.md) are not kit files and are
excluded from the file set; node_modules and build output
are excluded as well.

The rebuild's step-5 publish pipeline calls this check; a
drifted kit does not publish.
"""

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

GOVERNANCE_FILES = {"manifest.json", "PROVENANCE.md"}
EXCLUDED_DIRS = {"node_modules", "dist", "__pycache__"}


def _load_paths():
    """The platform paths spine, loaded by path (the
    package's standing bootstrap form): the vendored
    kit's home is the spine's REPO_ROOT derivation,
    never this script's own climb."""
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_paths",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "paths.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root):
    """relpath -> sha256 for every governed file under root."""
    out = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if rel.as_posix() in GOVERNANCE_FILES and len(rel.parts) == 1:
            continue
        out[rel.as_posix()] = sha256_of(path)
    return out


def diff_trees(label, expected, actual):
    """Drift lines for two relpath->sha256 maps."""
    lines = []
    for rel in sorted(set(expected) | set(actual)):
        if rel not in actual:
            lines.append(f"{label}: missing {rel}")
        elif rel not in expected:
            lines.append(f"{label}: unmanifested {rel}")
        elif expected[rel] != actual[rel]:
            lines.append(f"{label}: changed {rel}")
    return lines


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
    "name": "kit-drift",
    "flags": {
        "kit": {"takes_value": True, "help": "kit home (default: the repo's kit/)"},
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

    if args.kit is not None:
        kit_home = Path(args.kit)
    else:
        # The kit's home, from the platform paths spine:
        # REPO_ROOT / kit.
        kit_home = Path(_load_paths().REPO_ROOT) / "kit"
    if not kit_home.is_dir():
        print(f"kit drift: no kit home at {kit_home}", file=sys.stderr)
        return 2
    manifest_path = kit_home / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
        pinned = manifest["files"]
    except (OSError, ValueError, KeyError) as exc:
        print(f"kit drift: manifest unreadable: {exc}", file=sys.stderr)
        return 2

    drift = diff_trees("internal", pinned, tree_hashes(kit_home))

    if drift:
        for line in drift:
            print(f"kit drift: {line}")
        print(f"kit drift: DRIFT ({len(drift)} file(s))")
        return 1
    print(f"kit drift: ok (internal, {len(pinned)} files pinned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
