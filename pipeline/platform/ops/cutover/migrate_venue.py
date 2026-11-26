#!/usr/bin/env python3
"""Venue state cutover (freeze step 6, scripted): copy
the venue home's state to the mega venue home, run the
§10.3 binding-stamp migration on the migrated copy, and
verify the lease census is unchanged by the move.

Sequence inside the driver:

  1. Pre-census of the SOURCE store with the migration's
     own dry-run form (which writes nothing — the driver
     proves that by hashing the source tree before and
     after the dry run).
  2. Copy var/ + results/ and the live config set
     (callers, lease, repos, notify-routes, transient,
     and the denylist) into the target home.
  3. The §10.3 stamp on the TARGET copy only: legacy
     lease/run records gain their venue stamp once;
     already-stamped records are counted, never rewritten;
     unparseable or out-of-vocabulary run records are
     quarantined by the migration itself and named here.
  4. Post-census: lease-record count identical to the
     pre-census, every run record accounted (stamped +
     already + quarantined), config files hash-identical
     to the source's.

The source home is never written. Refuses a non-empty
target state unless --force-with-backup. Prints one
SUMMARY line (JSON).
"""

import hashlib
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = importlib.util.spec_from_file_location(
    "platform_paths",
    next(_p for _p in (
        os.path.join(os.path.dirname(
            os.path.dirname(_here)), "paths.py"),
        os.path.join(os.path.dirname(_here), "paths.py"),
        os.path.join(_here, "paths.py"))
        if os.path.isfile(_p)))
paths = importlib.util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

CONFIG_FILES = ["callers.json", "lease.json", "repos.json",
                "notify-routes.json", "transient.json",
                "denylist.txt"]


def _tree_hashes(root):
    hashes = {}
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            path = os.path.join(base, name)
            digest = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20),
                                  b""):
                    digest.update(chunk)
            hashes[os.path.relpath(path, root)] = \
                digest.hexdigest()
    return hashes


def _load_migrate(venue_home):
    path = os.path.join(venue_home, "sync", "venue_migrate.py")
    spec = importlib.util.spec_from_file_location(
        "cutover_venue_migrate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    "name": "migrate-venue",
    "flags": {
        "source-home": {"takes_value": True, "required": True, "help": 'the original venue home (var/, results/, config/; read-only)'},
        "target-home": {"takes_value": True, "required": True, "help": 'the mega-side venue home to fill (a scratch or staging home in rehearsal; the mega venue home at the freeze)'},
        "venue-home": {"takes_value": True, "help": 'the mega venue package dir (default: derived from this file)'},
        "venue-name": {"takes_value": True, "default": 'colab'},
        "force-with-backup": {},
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
    venue_home = args.venue_home or os.path.join(
        paths.PIPELINE_ROOT, "venue")
    migrate = _load_migrate(venue_home)

    source_var = os.path.join(source, "var")
    source_runs = os.path.join(source, "results", "runs")
    if not os.path.isdir(source_var):
        print(f"FAIL no var/ in {source}")
        return 1

    hashes_before = _tree_hashes(source)
    pre = migrate.migrate_store(source_var, source_runs,
                                venue=args.venue_name,
                                dry_run=True)
    if _tree_hashes(source) != hashes_before:
        print("FAIL the dry-run census wrote to the source "
              "store; refusing to continue")
        return 1

    for sub in ("var", "results"):
        dst = os.path.join(target, sub)
        if os.path.isdir(dst) and os.listdir(dst):
            if not args.force_with_backup:
                print(f"FAIL target {sub}/ is not empty: "
                      f"{dst}")
                return 1
            stamp = datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%SZ")
            aside = f"{dst}.pre-freeze-{stamp}"
            shutil.move(dst, aside)
            print(f"note: existing target moved to {aside}")
        shutil.copytree(os.path.join(source, sub), dst)

    config_copied = {}
    target_config = os.path.join(target, "config")
    os.makedirs(target_config, exist_ok=True)
    for name in CONFIG_FILES:
        src = os.path.join(source, "config", name)
        if os.path.isfile(src):
            dst = os.path.join(target_config, name)
            shutil.copy2(src, dst)
            config_copied[name] = (
                _tree_hashes(os.path.dirname(src))[name]
                == _tree_hashes(
                    os.path.dirname(dst))[name])

    post = migrate.migrate_store(
        os.path.join(target, "var"),
        os.path.join(target, "results", "runs"),
        venue=args.venue_name)

    # Verification. The dry-run census is a projection —
    # its "stamped" counts are what a real run would do —
    # so the real run must land exactly on the projection:
    # same totals accounted, same quarantine list, and a
    # second dry run over the migrated copy must find
    # nothing left to stamp.
    problems = []
    for family in ("runs", "lease", "evidence"):
        pre_total = pre.get(f"{family}_already", 0) + \
            pre.get(f"{family}_stamped", 0)
        post_total = post.get(f"{family}_already", 0) + \
            post.get(f"{family}_stamped", 0)
        if pre_total != post_total:
            problems.append(
                f"{family}: {pre_total} accounted before, "
                f"{post_total} after")
    if pre.get("quarantined") != post.get("quarantined"):
        problems.append("quarantine lists disagree")
    if pre.get("lease_unreadable") != \
            post.get("lease_unreadable"):
        problems.append("unreadable lease lists disagree")
    if not all(config_copied.values()):
        problems.append("a config file's hash disagrees "
                        "after copy")
    settle = migrate.migrate_store(
        os.path.join(target, "var"),
        os.path.join(target, "results", "runs"),
        venue=args.venue_name, dry_run=True)
    for family in ("runs", "lease", "evidence"):
        if settle.get(f"{family}_stamped", 0) != 0:
            problems.append(
                f"{family}: {settle[f'{family}_stamped']} "
                f"records still unstamped after the stamp")
    if problems:
        print("FAIL " + "; ".join(problems))
        return 1
    print(f"SUMMARY {json.dumps({'pre_census': pre, 'post_stamp': post, 'configs': sorted(config_copied), 'verified': True}, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
