#!/usr/bin/env python3
"""Post-rename verification for the todo slug migration.

The ruling: todos carry GitHub-like slug names in place of
the opaque legacy ids, at or before the cutover — and after
the rename migration runs, every armed/progress reference
must resolve by slug, and no live reference may resolve
only by a legacy id. The one place a legacy id may still
appear is the stored legacy-id mapping on its own record —
that mapping is the rollback for the rename act, so it is
preserved, never treated as a live reference.

This verifier is the mechanical form of that condition,
over the three reference surfaces the freeze assembles:

  --jobs-dir         the assembled scheduler registry:
                     wb-progress entries must name their
                     todo by slug in filename and argv,
                     consistently, and the slug must exist
                     in the workrecord export when given.
  --attention-state  the migrated attention store: no
                     legacy-id string outside a mapping key.
  --workrecord-store the migrated harness store: registry
                     export + entry filenames, same rule.

Exit 0 = every reference resolves by slug. Exit 1 = one
FAIL line per offending reference. Read-only: this script
never writes.
"""

import argparse
import json
import os
import re
import sys

# The legacy id shape: t- followed by a long base-ish
# tail (the generated form runs 20+ characters). Both
# cases occur in the wild: entry filenames and ids carry
# the lowercase form, while argv lists and source blocks
# carry the uppercase ULID form. Slugs are lowercase
# words joined by dashes and never match this.
LEGACY_RE = re.compile(r"\bt-[0-9A-Za-z]{16,}\b")

# Keys under which a legacy id is a stored mapping (the
# rollback artifact), not a live reference.
MAPPING_KEYS = {"legacy_id", "legacy_ids", "legacy_map",
                "legacy_mapping", "legacy"}


def _walk(node, path, in_mapping, fails, surface):
    if isinstance(node, dict):
        for key, value in node.items():
            _walk(value, f"{path}.{key}",
                  in_mapping or key in MAPPING_KEYS,
                  fails, surface)
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            _walk(value, f"{path}[{idx}]", in_mapping,
                  fails, surface)
    elif isinstance(node, str):
        for match in LEGACY_RE.finditer(node):
            if not in_mapping:
                fails.append(
                    f"{surface}: legacy id {match.group(0)} "
                    f"at {path} is a live reference, not a "
                    f"stored mapping")


def check_attention_state(path):
    fails = []
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    _walk(state, "$", False, fails, "attention-state")
    return fails


def check_workrecord(store_dir):
    fails = []
    export_path = os.path.join(store_dir, "registry.json")
    slug_ids = set()
    if os.path.isfile(export_path):
        with open(export_path, encoding="utf-8") as fh:
            export = json.load(fh)
        _walk(export, "$", False, fails, "workrecord-export")
        for entry in export.get("entries", []):
            if isinstance(entry, dict) and entry.get("id"):
                slug_ids.add(entry["id"])
        for todo in export.get("todos", []):
            if isinstance(todo, dict) and todo.get("id"):
                slug_ids.add(todo["id"])
    entries_dir = os.path.join(store_dir, "entries")
    if os.path.isdir(entries_dir):
        for name in sorted(os.listdir(entries_dir)):
            if LEGACY_RE.search(name) and "legacy" not in name:
                fails.append(
                    f"workrecord-store: entry file {name} is "
                    f"named by a legacy id")
    return fails, slug_ids


def check_jobs(jobs_dir, slug_ids):
    fails = []
    if not os.path.isdir(jobs_dir):
        return [f"jobs-dir: {jobs_dir} does not exist"]
    for name in sorted(os.listdir(jobs_dir)):
        if not (name.startswith("wb-progress-")
                and name.endswith(".yaml")):
            continue
        if LEGACY_RE.search(name):
            fails.append(
                f"jobs: entry file {name} is named by a "
                f"legacy id")
        path = os.path.join(jobs_dir, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        # Both spellings occur: an inline command string
        # (progress-check <id>) and an argv list, where
        # the id is the next list item on its own line.
        argv_ids = re.findall(
            r"progress-check[\s-]+(\S+)", text)
        for argv_id in argv_ids:
            if LEGACY_RE.search(argv_id):
                fails.append(
                    f"jobs: {name} progress-check names "
                    f"legacy id {argv_id}")
            elif slug_ids and argv_id not in slug_ids:
                fails.append(
                    f"jobs: {name} progress-check names "
                    f"{argv_id}, which no migrated todo "
                    f"record carries")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "legacy" in line.lower():
                continue  # a mapping line may carry the id
            for match in LEGACY_RE.finditer(line):
                fails.append(
                    f"jobs: {name}:{lineno} carries legacy "
                    f"id {match.group(0)} outside a mapping")
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs-dir")
    ap.add_argument("--attention-state")
    ap.add_argument("--workrecord-store")
    args = ap.parse_args(argv)
    if not (args.jobs_dir or args.attention_state
            or args.workrecord_store):
        ap.error("name at least one surface to verify")

    fails = []
    slug_ids = set()
    if args.workrecord_store:
        found, slug_ids = check_workrecord(args.workrecord_store)
        fails.extend(found)
    if args.attention_state:
        fails.extend(check_attention_state(args.attention_state))
    if args.jobs_dir:
        fails.extend(check_jobs(args.jobs_dir, slug_ids))

    for line in fails:
        print(f"FAIL {line}")
    summary = {"surfaces": [s for s, given in (
        ("jobs", args.jobs_dir),
        ("attention-state", args.attention_state),
        ("workrecord-store", args.workrecord_store)) if given],
        "legacy_only_references": len(fails),
        "slug_ids_seen": len(slug_ids)}
    print(f"SUMMARY {json.dumps(summary, sort_keys=True)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
