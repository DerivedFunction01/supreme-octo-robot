#!/usr/bin/env python3
"""Publish sync — move a prep-verified tree into an
artifact mirror, drift-guarded (contract 09 rebuild,
design sections 3 and 5).

The repo keeps the artifact source at artifact/ in a
repo-shaped tree (apps/ and kit/ are its siblings; the
composition imports them by relative path). A ts-spaces
mirror is a SPACE-shaped tree: the space's own files sit
at the mirror root, with apps/ and kit/ carried inside
it. The sync is therefore a transform, not a copy:

- artifact/** lands at the mirror root (client/, server/,
  space.json, package.json, ...), with the files that
  name the repo root by relative path rewritten one level
  shallower: client/tsconfig.json (the ../../apps/ path
  mapping and the ../.. rootDir; it carries no
  ../../kit/ mapping —
  the kit resolves through the artifact's own install —
  and the rewrite asserts none appears). Each rewrite
  asserts its expected occurrence count; a source that
  has moved fails the sync loudly rather than syncing
  unrewritten.
- apps/<app>/frontend/** lands at mirror apps/<app>/
  frontend/ (sources only; build outputs never sync).
- kit/** lands at mirror kit/**.
- each app's materialized node_modules (prep's real copy,
  react/react-dom pruned) is carried to the mirror when
  missing or on --refresh-deps, and verified pruned: the
  builder installs only the space root's package, so the
  app installs the composed build resolves through must
  arrive with the sync. node_modules are regenerable
  installs and are NOT in the hash manifest; the governed
  set is the source.

Drift guard, in the kit_drift.py idiom: the sync writes
publish-manifest.json at the mirror root — sha256 over
every governed file's TRANSFORMED bytes, the variant in
force, and the source tree's prep verdict. --check
recomputes the expected set from the tree and compares
three ways: tree vs manifest (the source moved since the
sync), target vs manifest (the mirror was touched outside
the sync). Any mismatch is a hard failure naming the
files; a file whose hash differs without going through
the sync does not publish.

Variants (staging-only overlays, recorded in the
manifest; canonical source is never rewritten):
- --variant dead-port-runner: the mirror's
  server/src/runner/config.ts default port 8793 -> 8799
  (a port nothing answers), for the publish proof's
  honest-unreachable leg. Re-sync without the variant to
  restore the faithful tree.

The sync never touches the mirror's own furniture:
AGENTS.md, audits/, .space-build/, icon.webp, the root
node_modules the builder installs, app.db. Deletions are
limited to paths the previous manifest governed.

Exit 0 = synced / check clean; 1 = drift or a failed
assertion; 2 = usage error (unprepped tree, missing
pieces).
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone

APPS = ["workbench", "scheduler", "runner"]
MANIFEST_NAME = "publish-manifest.json"

ARTIFACT_EXCLUDES = ("node_modules", ".bun-cache", "dist",
                     "dist-cvm", ".generated", "app.db")
FRONTEND_EXCLUDES = ("node_modules", "dist", "dist-integration",
                     "dist-relay")
PREP_GENERATED = ("client/build-local.mjs", "serve.local.ts")


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _walk(base, excludes, skip_files=()):
    out = {}
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in excludes]
        for name in files:
            if "tsbuildinfo" in name:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, base)
            if rel in skip_files:
                continue
            out[rel] = path
    return out


def _rewrite(rel, data):
    """The mirror-layout transforms. Returns the bytes the
    mirror must carry; raises SyncError when a source no
    longer has the shape the transform anchors on."""
    if rel == os.path.join("client", "tsconfig.json"):
        text = data.decode("utf-8")
        # A None replacement asserts absence: the integrated
        # client tsconfig carries no ../../kit/ mapping (the
        # kit resolves through the artifact's own install),
        # and one appearing is a shape the sync refuses to
        # guess at, not one it rewrites.
        rules = [('"../../kit/', None, 0),
                 ('"../../apps/', '"../apps/', 1),
                 ('"rootDir":"../.."', '"rootDir":".."', 1)]
        for old, new, expected in rules:
            count = text.count(old)
            if count != expected:
                raise SyncError(
                    f"client/tsconfig.json carries {count} "
                    f"{old!r}, expected {expected} — the sync "
                    f"refuses to guess the new shape")
            if new is not None:
                text = text.replace(old, new)
        return text.encode("utf-8")
    return data


class SyncError(Exception):
    pass


def governed_map(tree, variant):
    """{target_relpath: bytes} for the fullstack sync."""
    out = {}
    artifact = os.path.join(tree, "artifact")
    for rel, path in _walk(artifact, ARTIFACT_EXCLUDES,
                           skip_files=PREP_GENERATED).items():
        with open(path, "rb") as fh:
            out[rel] = _rewrite(rel, fh.read())
    for app in APPS:
        fe = os.path.join(tree, "apps", app, "frontend")
        for rel, path in _walk(fe, FRONTEND_EXCLUDES).items():
            with open(path, "rb") as fh:
                out[os.path.join("apps", app, "frontend", rel)] = \
                    fh.read()
    kit = os.path.join(tree, "kit")
    for rel, path in _walk(kit, ("node_modules",)).items():
        with open(path, "rb") as fh:
            out[os.path.join("kit", rel)] = fh.read()
    if variant == "dead-port-runner":
        key = os.path.join("server", "src", "runner", "config.ts")
        if key not in out:
            raise SyncError("runner config.ts not in the sync set")
        text = out[key].decode("utf-8")
        anchor = "const DEFAULT_PORT = 8793;"
        if text.count(anchor) != 1:
            raise SyncError("runner config.ts default-port anchor "
                            "not found exactly once")
        out[key] = text.replace(anchor,
                                "const DEFAULT_PORT = 8799;") \
            .encode("utf-8")
    return out


def _load_manifest(target):
    path = os.path.join(target, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_manifest(target, files, mode, variant, tree):
    manifest = {
        "mode": mode,
        "variant": variant,
        "synced_at": datetime.now(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_tree": tree,
        "files": {rel: _sha256_bytes(data)
                  for rel, data in sorted(files.items())},
    }
    with open(os.path.join(target, MANIFEST_NAME), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return manifest


def _sync_deps(tree, target, refresh):
    """Carry each app's materialized node_modules (prep's
    pruned copy) into the mirror; verify the prune."""
    notes = []
    for app in APPS:
        src = os.path.join(tree, "apps", app, "frontend",
                           "node_modules")
        dst = os.path.join(target, "apps", app, "frontend",
                           "node_modules")
        if refresh and os.path.isdir(dst):
            shutil.rmtree(dst)
        if not os.path.isdir(dst):
            if not os.path.isdir(src):
                raise SyncError(f"{app}: prep tree carries no "
                                f"node_modules to sync")
            shutil.copytree(src, dst, symlinks=True)
            notes.append(f"{app}: node_modules materialized")
        for pkg in ("react", "react-dom"):
            if os.path.exists(os.path.join(dst, pkg)):
                raise SyncError(
                    f"{app}: {pkg} present in the mirror's "
                    f"app install — the prune did not hold")
    return notes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", help="the prep tree (repo-shaped)")
    ap.add_argument("--target", required=True,
                    help="the mirror directory to sync into")
    ap.add_argument("--check", action="store_true",
                    help="verify only: tree vs manifest vs target")
    ap.add_argument("--variant", choices=["dead-port-runner"],
                    help="a named staging overlay")
    ap.add_argument("--refresh-deps", action="store_true",
                    help="re-copy the app node_modules")
    args = ap.parse_args(argv)

    target = os.path.abspath(args.target)
    os.makedirs(target, exist_ok=True)
    variant = args.variant
    try:
        if not args.tree:
            print("FAIL the fullstack sync needs --tree")
            return 2
        tree = os.path.abspath(args.tree)
        prep_report = os.path.join(tree, "prep-report.json")
        if os.path.isfile(prep_report):
            with open(prep_report, encoding="utf-8") as fh:
                verdict = json.load(fh).get("verdict")
            if verdict != "pass":
                raise SyncError(
                    f"the prep tree's verdict is {verdict!r}, "
                    f"not pass — an unverified tree does not "
                    f"sync")
        else:
            raise SyncError(
                "the tree carries no prep-report.json — run "
                "publish_prep.py first; an unprepped tree "
                "does not sync")
        files = governed_map(tree, variant)
        mode = "fullstack"
        tree_label = tree
    except SyncError as exc:
        print(f"FAIL sync: {exc}")
        return 2

    manifest = _load_manifest(target)
    if args.check:
        if manifest is None:
            print("FAIL no manifest in the target — nothing "
                  "was synced here by this pipeline")
            return 1
        problems = []
        expected = {rel: _sha256_bytes(data)
                    for rel, data in files.items()}
        if manifest.get("files") != expected:
            recorded = manifest.get("files", {})
            for rel in sorted(set(recorded) | set(expected)):
                if recorded.get(rel) != expected.get(rel):
                    problems.append(f"source moved since sync: {rel}")
        if manifest.get("variant") != variant:
            problems.append(
                f"variant differs: manifest {manifest.get('variant')!r} "
                f"vs requested {variant!r}")
        for rel, digest in (manifest.get("files") or {}).items():
            path = os.path.join(target, rel)
            if not os.path.isfile(path):
                problems.append(f"missing in target: {rel}")
            elif _sha256_bytes(open(path, "rb").read()) != digest:
                problems.append(f"target drifted outside the sync: {rel}")
        if problems:
            for problem in problems:
                print("FAIL " + problem)
            return 1
        print(f"PASS sync check — {len(expected)} governed files, "
              f"mode {mode}, variant {variant}")
        return 0

    # Deletions: only paths the previous manifest governed.
    if manifest and manifest.get("mode") == mode:
        for rel in manifest.get("files", {}):
            if rel not in files:
                path = os.path.join(target, rel)
                if os.path.isfile(path):
                    os.remove(path)
    written = 0
    for rel, data in files.items():
        path = os.path.join(target, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.isfile(path) and \
                open(path, "rb").read() == data:
            continue
        with open(path, "wb") as fh:
            fh.write(data)
        written += 1
    notes = []
    if mode == "fullstack":
        notes = _sync_deps(tree_label, target, args.refresh_deps)
    _write_manifest(target, files, mode, variant, tree_label)
    print(f"PASS synced {len(files)} governed files "
          f"({written} written) to {target} "
          f"[mode {mode}, variant {variant}]")
    for note in notes:
        print("  " + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
