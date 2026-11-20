#!/usr/bin/env python3
"""Workbench harness store migration (freeze step 5,
scripted).

The store is files: registry.db (with its WAL sidecars
when present), the registry.json export, and the entries/
tree. Migration is a byte copy — the verification is that
the bytes agree and the mega harness reads its own store
clean: the db's SHA-256 identical on both sides, the
export's entry count identical, and a read probe through
the mega `wb` against the migrated db exiting clean (the
harness's doctor is the freeze's fuller check, run by the
workbench thread over the live set).

Refuses a non-empty target unless --force-with-backup,
which moves the existing target aside first (timestamped
sibling) — a migration never silently overwrites a store.

The source store is never written. Prints one SUMMARY
line (JSON).
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
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


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _export_count(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        export = json.load(fh)
    entries = export.get("entries")
    return len(entries) if isinstance(entries, list) else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-store", required=True)
    ap.add_argument("--target-store", required=True)
    ap.add_argument("--workrecord-home",
                    help="the mega workrecord package dir "
                    "(default: derived from this file)")
    ap.add_argument("--probe-verb", default="list",
                    help="the wb verb used as the read "
                    "probe (default: list)")
    ap.add_argument("--force-with-backup", action="store_true")
    args = ap.parse_args(argv)

    source = os.path.abspath(args.source_store)
    target = os.path.abspath(args.target_store)
    source_db = os.path.join(source, "registry.db")
    if not os.path.isfile(source_db):
        print(f"FAIL no registry.db in {source}")
        return 1
    home = args.workrecord_home or paths.WORKRECORD_ROOT
    python = os.path.join(home, ".venv", "bin", "python")
    wb = os.path.join(home, "wb")

    if os.path.isdir(target) and os.listdir(target):
        if not args.force_with_backup:
            print(f"FAIL target store is not empty: {target}")
            return 1
        stamp = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ")
        aside = f"{target}.pre-freeze-{stamp}"
        shutil.move(target, aside)
        print(f"note: existing target moved to {aside}")
    os.makedirs(target, exist_ok=True)

    copied = []
    for name in ("registry.db", "registry.db-wal",
                 "registry.db-shm", "registry.json"):
        src = os.path.join(source, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(target, name))
            copied.append(name)
    entries_src = os.path.join(source, "entries")
    entries_copied = 0
    if os.path.isdir(entries_src):
        shutil.copytree(entries_src,
                        os.path.join(target, "entries"))
        entries_copied = sum(
            len(files) for _r, _d, files in
            os.walk(os.path.join(target, "entries")))

    target_db = os.path.join(target, "registry.db")
    if _sha256(source_db) != _sha256(target_db):
        print("FAIL registry.db hash disagrees after copy")
        return 1
    source_count = _export_count(
        os.path.join(source, "registry.json"))
    target_count = _export_count(
        os.path.join(target, "registry.json"))
    if source_count != target_count:
        print(f"FAIL export entry counts disagree: "
              f"{source_count} vs {target_count}")
        return 1

    # The harness resolves its project by walking up from
    # the cwd for a manifest: the probe runs from the
    # target store's project root (the store dir's parent,
    # whose manifest names this store) when one is there,
    # else from the package home.
    probe_cwd = os.path.dirname(target)
    if not os.path.isfile(os.path.join(probe_cwd,
                                       "workbench.yaml")):
        probe_cwd = home
    proc = subprocess.run(
        [python, wb, "--db", target_db, args.probe_verb],
        cwd=probe_cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"FAIL wb {args.probe_verb} probe on the "
              f"migrated db exited {proc.returncode}: "
              + (proc.stderr or proc.stdout).strip()[-300:])
        return 1
    print(f"SUMMARY {json.dumps({'copied': copied, 'entries_files': entries_copied, 'export_entries': target_count, 'db_sha256': _sha256(target_db), 'probe': args.probe_verb}, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
