#!/usr/bin/env python3
"""Verify that every assembled registry entry's argv
targets exist (freeze step 7, scripted).

An entry's argv is, by the registry's own portability
rule, a list of bare command names (resolved via PATH at
fire time) and anchored paths — tokens beginning
${REPO}/, ${WS}/ or ${HOME}/, the anchors the server
expands at load. A bare name cannot be checked against
the filesystem; an anchored path can, and must: an
assembled entry whose anchored argv target does not
exist fires into a missing file on its first post-freeze
run. Assembly re-points the pointers it knows and
provisions the scheduler home's own instance files, but
nothing else in the kit ever resolved the targets — this
verifier is that check, in standalone form (preflight
runs it over the assembled registry; assemble_registry
runs the same check inline and fails its own run).

Bindings (the server's derive_anchors, applied to the
assembled state):
  REPO  the mega scheduling home
        (<mega-root>/pipeline/scheduling)
  WS    the workspace root (an argument)
  HOME  the directory above the workspace root

A target that resolves to a directory counts as existing
(entries pass project roots as arguments). Every miss is
listed, one line per entry + token + resolved path.

Exit 0 = every anchored argv target exists. Exit 1 =
one MISSING line per miss. Read-only.
"""

import json
import os
import re
import sys

ANCHOR_PREFIXES = ("${REPO}/", "${WS}/", "${HOME}/")
ANCHOR_RE = re.compile(r"\$\{(REPO|WS|HOME)\}")


def bindings(mega_root, ws, home=None):
    return {
        "REPO": os.path.join(mega_root, "pipeline",
                             "scheduling"),
        "WS": ws,
        "HOME": home or os.path.dirname(ws),
    }


def expand(token, anchors):
    return ANCHOR_RE.sub(lambda m: anchors[m.group(1)],
                         token)


def argv_tokens(text):
    """The argv list of one entry, extracted textually
    (the kit carries no YAML dependency; entries write
    run.argv as a block list, the schema's one shape)."""
    tokens = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "argv:" or \
                stripped.startswith("argv:"):
            indent = len(lines[i]) - len(lines[i].lstrip())
            i += 1
            while i < len(lines):
                line = lines[i]
                item = line.strip()
                if not item:
                    i += 1
                    continue
                cur = len(line) - len(line.lstrip())
                if cur <= indent or not item.startswith("- "):
                    break
                token = item[2:].strip()
                if len(token) >= 2 and token[0] == token[-1] \
                        and token[0] in ("'", '"'):
                    token = token[1:-1]
                tokens.append(token)
                i += 1
            break
        i += 1
    return tokens


def anchored_tokens(text):
    return [t for t in argv_tokens(text)
            if t.startswith(ANCHOR_PREFIXES)]


def missing_targets(jobs_dir, anchors):
    """One 'entry: token -> resolved' string per anchored
    argv target that does not exist."""
    missing = []
    for name in sorted(os.listdir(jobs_dir)):
        if not name.endswith(".yaml"):
            continue
        with open(os.path.join(jobs_dir, name),
                  encoding="utf-8") as fh:
            text = fh.read()
        entry_id = name[:-len(".yaml")]
        for token in anchored_tokens(text):
            resolved = expand(token, anchors)
            if not os.path.exists(resolved):
                missing.append(
                    f"{entry_id}: {token} -> {resolved}")
    return missing


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
    "name": "verify-argv-targets",
    "flags": {
        "jobs-dir": {"takes_value": True, "required": True, "help": 'the assembled registry dir'},
        "mega-root": {"takes_value": True, "required": True, "help": 'the mega repo checkout root (REPO binds to its scheduling home)'},
        "ws": {"takes_value": True, "required": True, "help": 'the workspace root the ${WS} anchor names'},
        "home": {"takes_value": True, "help": 'the ${HOME} anchor (default: the directory above --ws)'},
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

    anchors = bindings(os.path.abspath(args.mega_root),
                       os.path.abspath(args.ws),
                       os.path.abspath(args.home)
                       if args.home else None)
    missing = missing_targets(args.jobs_dir, anchors)
    for line in missing:
        print(f"MISSING {line}")
    print(f"SUMMARY {json.dumps({'missing': len(missing)}, sort_keys=True)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
