#!/usr/bin/env python3
"""Kit drift check: the vendored kit matches its pin, or the
verdict names the files that moved.

The workhorse kit's source of truth is the starter repo's
workhorse-kit/ tree; this repo carries a vendored copy under
kit/ so clean formations resolve @workhorse/kit in-repo
(see kit/PROVENANCE.md for the sync discipline). This check
is the discipline's teeth, in two legs:

- internal: every vendored file's sha256 matches
  kit/manifest.json. A file added, removed, or changed
  against the manifest is drift — the vendored copy is
  never edited directly, so any mismatch means an
  unrecorded edit or a half-finished re-sync.
- external (only when a starter checkout is named, by
  --starter PATH or the WORKHORSE_KIT_STARTER env seam):
  every vendored file also matches the starter's live
  workhorse-kit/ tree, so a starter-side change that has
  not been re-synced is caught the same way.

Verdicts name files only, never contents. Exit 0 iff no
drift; 1 on drift; 2 on usage error (missing kit home,
missing or unreadable manifest, a named starter checkout
without a workhorse-kit/ tree). The governance files
(manifest.json, PROVENANCE.md) are not vendored files and
are excluded from both trees' file sets; node_modules and
build output are excluded on the starter side, mirroring
the vendoring exclusion.

The rebuild's step-5 publish pipeline calls this check; a
drifted kit does not publish.
"""

import argparse
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kit",
        type=Path,
        default=None,
        help="vendored kit home (default: the repo's kit/)",
    )
    parser.add_argument(
        "--starter",
        type=Path,
        default=None,
        help="starter checkout to compare against "
        "(default: the WORKHORSE_KIT_STARTER env seam, if set)",
    )
    args = parser.parse_args(argv)

    if args.kit is not None:
        kit_home = args.kit
    else:
        # The vendored kit's home, from the platform
        # paths spine: REPO_ROOT / kit.
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

    starter = args.starter
    if starter is None and os.environ.get("WORKHORSE_KIT_STARTER"):
        starter = Path(os.environ["WORKHORSE_KIT_STARTER"])
    if starter is not None:
        starter_kit = starter / "workhorse-kit"
        if not starter_kit.is_dir():
            print(
                f"kit drift: no workhorse-kit tree at {starter_kit}",
                file=sys.stderr,
            )
            return 2
        drift += diff_trees(
            "external", tree_hashes(starter_kit), tree_hashes(kit_home)
        )

    if drift:
        for line in drift:
            print(f"kit drift: {line}")
        print(f"kit drift: DRIFT ({len(drift)} file(s))")
        return 1
    scope = "internal + external" if starter is not None else "internal"
    print(f"kit drift: ok ({scope}, {len(pinned)} files pinned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
