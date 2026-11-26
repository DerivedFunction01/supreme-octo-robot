#!/usr/bin/env python3
"""Provision the mega scheduler's live config (freeze
step 7's OI-2 residue, scripted).

Shape: the OI-2 build's own. If the target home has no
live config, provision one from its shipped example (the
`bin/sched config-init` act — refuse to overwrite an
existing live config). Then apply the carried values from
an operator-supplied values file (the machine's port,
workspace root, home, and the owners/drain thread mapping
the original's live config carries — a value carry by the
operator; this script never opens the original's config).
Finally validate through the home's own config loader:
unknown keys and bad types refuse loudly there, so a
carried key that does not typecheck against the mega
schema stops the freeze here, not at server start.

Writes ride the unified state writer (contract 15,
pipeline/platform/writer.py): staged to a fresh sibling,
flushed and fsync'd, read back and compared, renamed
over, directory fsync'd — a failure at any stage leaves
the standing config byte-identical. With --dry-run the
merged config goes to a scratch file and is validated
there; the home is not touched.

Prints one SUMMARY line (JSON). The values file's contents
are never printed.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile


def _validate(home, config_path):
    pipeline_root = os.path.dirname(os.path.abspath(home))
    code = (
        "import sys;"
        f"sys.path.insert(0, {pipeline_root!r});"
        f"sys.path.insert(0, {os.path.abspath(home)!r});"
        "from server import config;"
        f"config.require_live_config({config_path!r});"
        f"values, _ = config.resolve({config_path!r});"
        "print(values['port']); print(values['home'])")
    proc = subprocess.run([sys.executable, "-c", code],
                          cwd=home, capture_output=True,
                          text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        raise SystemExit(
            "FAIL config validation: "
            + (tail[-1] if tail else "loader refused"))
    port, resolved_home = proc.stdout.strip().splitlines()[-2:]
    return {"port": int(port), "home": resolved_home}


def _load_platform_writer():
    """The unified state writer (contract 15), loaded by
    path through the platform paths spine — the platform
    package's standing seam form (releases.py, backup.py):
    the spine's WRITER is the writer's one derivation, so
    the protocol has exactly one implementation and this
    script's writes ride it. This file lives two levels
    below the package root (ops/cutover/), where the
    spine sits."""
    paths_spec = importlib.util.spec_from_file_location(
        "pipeline_platform_paths",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "paths.py"))
    paths = importlib.util.module_from_spec(paths_spec)
    paths_spec.loader.exec_module(paths)
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", paths.WRITER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_writer = _load_platform_writer()


def _write_config(path, rendered):
    """Write the provisioned config through the unified
    writer's staged protocol. Its WriterError propagates
    to main, which maps it onto this script's FAIL form —
    the write either lands whole or the standing config
    stays byte-identical."""
    _writer.staged_write(path, rendered.encode("utf-8"))


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
    "name": "provision-config",
    "flags": {
        "sched-home": {"takes_value": True, "required": True, "help": 'the mega scheduling package dir'},
        "values": {"takes_value": True, "help": 'JSON of carried top-level config values (default: none)'},
        "dry-run": {"safety": True},
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

    home = os.path.abspath(args.sched_home)
    config_path = os.path.join(home, "config.json")
    example_path = os.path.join(home, "config.example.json")
    if not os.path.isfile(example_path):
        print(f"FAIL no config.example.json in {home}")
        return 1

    carried = {}
    if args.values:
        with open(args.values, encoding="utf-8") as fh:
            carried = json.load(fh)

    provisioned = False
    if os.path.isfile(config_path):
        with open(config_path, encoding="utf-8") as fh:
            merged = json.load(fh)
    else:
        with open(example_path, encoding="utf-8") as fh:
            merged = json.load(fh)
        provisioned = True
    merged.update(carried)
    rendered = json.dumps(merged, indent=2, sort_keys=True) + "\n"

    if args.dry_run:
        fd, scratch = tempfile.mkstemp(suffix=".json",
                                       dir=tempfile.gettempdir())
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(rendered)
            resolved = _validate(home, scratch)
        finally:
            os.unlink(scratch)
        print(f"SUMMARY {json.dumps({'dry_run': True, 'provisioned': provisioned, 'carried_keys': sorted(carried), 'resolved': resolved}, sort_keys=True)}")
        return 0

    if provisioned or carried:
        try:
            _write_config(config_path, rendered)
        except _writer.WriterError as exc:
            print(f"FAIL config write: {exc.name}: {exc.detail}")
            return 1
    resolved = _validate(home, config_path)
    print(f"SUMMARY {json.dumps({'dry_run': False, 'provisioned': provisioned, 'carried_keys': sorted(carried), 'resolved': resolved}, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
