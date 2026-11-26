#!/usr/bin/env python3
"""Publish prep — stage and verify the tree a publish
builds from (contract 09 rebuild, design section 5 step 5).

The prep stages a build tree in the repo's own shape
(artifact/ + apps/ + kit/ under one root) from the current
repo tree, and proves the staging discipline the step-3
integration evidenced, before anything is synced to a
mirror or published:

- the client is ONE integrated build (owner ruling:
  one app, one bundle, the four apps as views
  of the one client): there are no per-app integration
  builds and no frame documents to stage — the frame
  shell's frames.ts and the apps' integration/embedded
  entries it composed are gone. The staged client's shape
  is asserted by running the client's own
  parity-check.mjs over it (the shape's specification of
  record, invoked — not re-derived here), plus the dist
  hygiene assertions below.
- materialized deps: each app's node_modules is a real
  copy of the repo's install — never a symlink farm — with
  the app-local react/react-dom copies REMOVED, so the one
  React the artifact pins (19.2.5, at the tree root and in
  the artifact's own install) is the only copy any importer
  can resolve. A symlink farm silently shipped a second
  React in step 3 (React #525); the produced bundle is
  asserted to carry exactly one React version string.
- react + katex resolvable from the kit tree's ancestor
  chain: the tree root carries a small install (react,
  react-dom, katex) that kit/ and the app graphs resolve
  by walking up.
- the composed client build runs from an empty
  client/dist, through the repo build.mjs's own build —
  build.mjs carries the SDK buildClient's Bun.build
  call inline (its own mirror, in the canonical
  single-bundle form — the splitting: true delta is
  retired: the platform's CVM publish stage
  accepts exactly one JS bundle), so the prep's local
  build is build.mjs itself with only its driver guard
  (the check reserving builds to the artifact tools)
  neutralized, mechanically transformed — if
  build.mjs's shape moves, the transform's anchors
  fail and the prep stops rather than building wrong.
- the staged server keeps its tracked .generated (the
  privileged contract): the build's actionFields macro
  requires the server actions, whose @space/privileged
  import resolves only through that contract (see
  _ignore_artifact).
- dist hygiene: the staged dist contains EXACTLY the
  referenced set — the one entry document and its
  canonical single bundle: the one JS bundle and the
  stylesheet the document names (fonts ride inside the
  stylesheet as data URIs) — and a same-bundle
  assertion runs over the staged document: it names
  the one bundle and the one stylesheet. (Step 3's run 3
  drove a stale frame document against a fresh bundle;
  the exactly-the-referenced-set half of this assertion
  is that lesson mechanized.)
- the vendored kit passes kit_drift.py's internal leg: a
  drifted kit does not publish.
- the staged artifact's package metadata is rewritten
  to the published home's shape as the last staging
  step (see home_shape): the home is flattened — kit/
  inside the artifact root — so the kit spec the sync
  consumes reads file:./kit there while the repo keeps
  file:../kit, and the d3-dsv patch the platform's
  closed-bundle build requires rides as repo source
  (artifact/patches/, named in patchedDependencies)
  with the lockfile's agreement asserted.

The prep writes nothing to the repo and nothing to any
mirror: its output is the staged tree plus a
prep-report.json at the tree root naming every assertion's
outcome. Sync (publish_sync.py) and the builder publish
consume the verified tree's SOURCE; the local dist is the
prep's proof, and the acceptance drive/serve run against
this tree.

Exit 0 = every assertion passes; 1 = a named assertion
failed; 2 = usage error (missing tools, unstageable tree).
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

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

REPO_ROOT = paths.REPO_ROOT

APPS = ["workbench", "scheduler", "runner"]
REACT_PIN = "19.2.5"
WRONG_REACTS = ["18.3.1", "19.3.1"]

# The local-build transform's anchors on
# artifact/client/build.mjs (applied in composed_build).
# build.mjs once called the SDK's buildClient, which
# refuses non-builder runs, so the prep substituted a
# replica of its Bun.build call. build.mjs now carries
# that call inline — its own mirror of buildClient,
# parameter-for-parameter, in the canonical
# single-bundle form — so there is no call left to
# substitute: the local build is build.mjs itself with
# its driver guard (the check reserving builds to the
# artifact tools, the refusal's new home) neutralized.
# A replica block would only drift from the file's own
# call — the step-1/3 replica silently carried platform
# version 25 after space.json had moved to 26, and
# lacked splitting when the split landed. Each anchor
# is counted exactly; a build.mjs whose shape has moved
# fails the prep rather than staging a wrongly built
# bundle. The splitting anchor is counted in reverse:
# the retired delta must be ABSENT — a build.mjs that
# splits again fails the prep here rather than at the
# platform's CVM stage, which accepts exactly one JS
# bundle.
GUARD_ANCHOR = ('if (process.env.HATCH_SPACES_BUILD_DRIVER'
                ' !== "1") {')
BUILD_CALL_ANCHOR = "const result = await Bun.build({"
SPLIT_ANCHOR = "splitting: true,"
GUARD_NEUTRALIZED = (
    "if (false) { // prep-local transform: the driver "
    "guard is neutralized in this generated copy only "
    "(publish_prep.py); build.mjs itself is untouched")

def _ignore_artifact(dirpath, names):
    # server/.generated stages: its one tracked file is
    # the privileged contract (@space/privileged, mapped
    # by server/tsconfig.json's paths) that the server
    # actions resolve through — and the composed client
    # build's actionFields macro requires those actions,
    # so a staging without the contract fails the build
    # inside the macro (Bun reports the macro's
    # resolution error as an AST coercion error at the
    # macro call site). Every other .generated is
    # builder output and stays excluded.
    stage_contract = os.path.normpath(dirpath).endswith(
        os.path.join("artifact", "server"))
    out = []
    for name in names:
        if name in ("node_modules", ".bun-cache", "dist",
                    "dist-cvm", "app.db"):
            out.append(name)
        elif name == ".generated" and not stage_contract:
            out.append(name)
        elif "tsbuildinfo" in name:
            out.append(name)
    return out


def _ignore_frontend(_dir, names):
    return [n for n in names
            if n in ("node_modules", "dist", "dist-integration",
                     "dist-relay")]


def _run(cmd, cwd, timeout=1200):
    proc = subprocess.run(cmd, cwd=cwd, shell=True, timeout=timeout,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Prep:
    def __init__(self, tree, repo):
        self.tree = tree
        self.repo = repo
        self.assertions = []
        self.notes = []

    def check(self, name, ok, detail):
        self.assertions.append(
            {"name": name, "pass": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'} {name} — {detail}")
        return ok

    # --------------------------------------------------------------
    def stage(self):
        tree = self.tree
        if os.path.exists(tree):
            shutil.rmtree(tree)
        os.makedirs(tree)
        shutil.copytree(os.path.join(self.repo, "artifact"),
                        os.path.join(tree, "artifact"),
                        ignore=_ignore_artifact)
        shutil.copytree(os.path.join(self.repo, "kit"),
                        os.path.join(tree, "kit"),
                        ignore=shutil.ignore_patterns("node_modules"))
        for app in APPS:
            src = os.path.join(self.repo, "apps", app, "frontend")
            dst = os.path.join(tree, "apps", app, "frontend")
            shutil.copytree(src, dst, ignore=_ignore_frontend)
            # Materialized deps: a real copy of the repo's
            # install (the react prune runs after the
            # integration builds — see prune_react).
            nm_src = os.path.join(src, "node_modules")
            nm_dst = os.path.join(dst, "node_modules")
            if not os.path.isdir(nm_src):
                raise PrepError(f"{app}: repo frontend has no "
                                f"node_modules to materialize")
            shutil.copytree(nm_src, nm_dst, symlinks=True)
        # The tree-root install the kit ancestor chain
        # resolves react/react-dom/katex from.
        with open(os.path.join(tree, "package.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"name": "workhorse-prep-root",
                       "private": True,
                       "dependencies": {
                           "react": REACT_PIN,
                           "react-dom": REACT_PIN,
                           "katex": "^0.16.11"}}, fh, indent=2)
        code, out = _run("bun install", tree)
        if code != 0:
            raise PrepError("tree-root bun install failed:\n"
                            + out[-2000:])
        code, out = _run("bun install",
                         os.path.join(tree, "artifact"))
        if code != 0:
            raise PrepError("artifact bun install failed:\n"
                            + out[-2000:])

    # --------------------------------------------------------------
    def parity_check(self):
        """The integrated shape's specification of record is
        the client's own parity-check.mjs (dist = exactly
        one HTML document, one JS bundle, one CSS file; no
        frame-shell iframes or relay markers; one action
        client; the four app ids + route roots in the
        bundle). Run it over the staged client rather than
        re-deriving its rules here, so the prep's shape
        verdict can never drift from the client's."""
        artifact = os.path.join(self.tree, "artifact")
        runner = shutil.which("node") or shutil.which("bun")
        if runner is None:
            self.check("client parity (parity-check.mjs)", False,
                       "neither node nor bun on PATH to run it")
            return
        code, out = _run(f"{runner} ./client/parity-check.mjs",
                         artifact)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.check("client parity (parity-check.mjs)",
                   code == 0,
                   f"exit {code} via {os.path.basename(runner)}; "
                   + (lines[-1] if lines else "no output")
                   + ("" if code == 0 else
                      " — tail: " + out[-400:].replace("\n", " ")))

    # --------------------------------------------------------------
    def prune_react(self):
        """Remove the app-local react/react-dom copies from
        the staged app installs: the mirror's app installs
        must arrive pruned (publish_sync.py verifies the
        prune and refuses an app install carrying react),
        so the one React the artifact pins is the only copy
        any importer can resolve. What remains resolves
        react by walking up to the tree root's pinned
        install."""
        for app in APPS:
            nm = os.path.join(self.tree, "apps", app,
                              "frontend", "node_modules")
            for pkg in ("react", "react-dom"):
                victim = os.path.join(nm, pkg)
                if os.path.isdir(victim):
                    shutil.rmtree(victim)
            left = [p for p in ("react", "react-dom")
                    if os.path.exists(os.path.join(nm, p))]
            self.check(f"app-local react pruned: {app}",
                       not left,
                       "react/react-dom absent from the app "
                       "install; resolution walks to the tree "
                       "root pin" if not left else
                       f"still present: {left}")

    # --------------------------------------------------------------
    def composed_build(self):
        artifact = os.path.join(self.tree, "artifact")
        build_mjs_path = os.path.join(artifact, "client",
                                      "build.mjs")
        source = open(build_mjs_path, encoding="utf-8").read()
        if source.count(GUARD_ANCHOR) != 1 or \
                source.count(BUILD_CALL_ANCHOR) != 1 or \
                source.count(SPLIT_ANCHOR) != 0:
            raise PrepError(
                "artifact/client/build.mjs no longer has the "
                "shape the local-build transform anchors on "
                "(one driver guard, one inline Bun.build call "
                "in the canonical single-bundle form — no "
                "splitting: true) — the prep refuses "
                "to guess a new shape")
        local = source.replace(GUARD_ANCHOR, GUARD_NEUTRALIZED)
        local_path = os.path.join(artifact, "client",
                                  "build-local.mjs")
        with open(local_path, "w", encoding="utf-8") as fh:
            fh.write(local)
        dist = os.path.join(artifact, "client", "dist")
        if os.path.isdir(dist):
            shutil.rmtree(dist)
        code, out = _run("bun ./client/build-local.mjs", artifact)
        self.check("composed client build", code == 0,
                   "exit 0; single bundle staged through "
                   "build.mjs's own build + staging code and "
                   "its one-document / one-bundle shape check"
                   if code == 0
                   else "exit " + str(code) + " — tail: "
                   + out[-600:].replace("\n", " "))
        return code == 0

    # --------------------------------------------------------------
    def dist_assertions(self):
        dist = os.path.join(self.tree, "artifact", "client", "dist")
        files = []
        for root, _dirs, names in os.walk(dist):
            for name in names:
                files.append(os.path.relpath(
                    os.path.join(root, name), dist))
        files.sort()
        docs = [f for f in files if f.endswith(".html")]
        bundles = [f for f in files if f.endswith(".js")]
        styles = [f for f in files if f.endswith(".css")]
        expected = sorted(docs + bundles + styles)
        self.check("dist hygiene: exactly the referenced set",
                   files == expected and docs == ["index.html"]
                   and len(bundles) == 1,
                   f"dist = {files}")
        if docs != ["index.html"] or not bundles or not styles:
            return
        # The one document names the canonical single
        # bundle and its one stylesheet (parity-check.mjs
        # proves the shape — exactly one JS bundle, no
        # orphans, no second entry).
        text = open(os.path.join(dist, "index.html"),
                    encoding="utf-8").read()
        scripts = [os.path.basename(s) for s in
                   re.findall(r'<script[^>]*\ssrc="([^"]+)"', text)
                   if s.endswith(".js")]
        links = [os.path.basename(s) for s in
                 re.findall(r'<link[^>]*\shref="([^"]+)"', text)
                 if s.endswith(".css")]
        bundle_names = [os.path.basename(b) for b in bundles]
        style_names = [os.path.basename(s) for s in styles]
        named = (len(scripts) == 1 and scripts[0] in bundle_names
                 and len(links) == 1 and links[0] in style_names)
        self.check("same bundle + stylesheet over every document",
                   named,
                   f"the document names the bundle {scripts[0]} "
                   f"+ stylesheet {links[0]} of the canonical "
                   f"single bundle ({len(bundles)} JS bundle, "
                   f"{len(styles)} stylesheets staged)"
                   if named else
                   f"document names scripts {scripts}, styles "
                   f"{links}; staged bundle names {bundle_names}, "
                   f"style names {style_names}")
        # One React, in the single bundle.
        bundle_text = "\n".join(
            open(os.path.join(dist, b), encoding="utf-8",
                 errors="replace").read() for b in bundles)
        versions = set(re.findall(r'version:"(\d+\.\d+\.\d+)"',
                                  bundle_text))
        wrong = [v for v in WRONG_REACTS if v in versions]
        entry_rel = next((b for b in bundles
                          if os.path.basename(b) in scripts), "")
        entry_sha = (_sha256(os.path.join(dist, entry_rel))[:16]
                     if entry_rel else "n/a")
        self.check("exactly one React version in the bundle",
                   REACT_PIN in versions and not wrong,
                   f"react pin {REACT_PIN} "
                   f"{'present' if REACT_PIN in versions else 'ABSENT'}; "
                   f"foreign react versions {wrong or 'none'}; "
                   f"searched the {len(bundles)} bundle; "
                   f"entry sha256 {entry_sha}…")
        # Fonts inlined, none referenced as files.
        css_text = "\n".join(
            open(os.path.join(dist, s), encoding="utf-8",
                 errors="replace").read() for s in styles)
        file_refs = re.findall(r'url\((?!data:)[^)]*\.woff2[^)]*\)',
                               css_text)
        self.check("fonts inlined as data URIs",
                   "data:font/woff2" in css_text and not file_refs,
                   "stylesheets carry data:font/woff2 and no "
                   "file-referenced woff2" if "data:font/woff2"
                   in css_text and not file_refs else
                   f"data:font/woff2 {'present' if 'data:font/woff2' in css_text else 'ABSENT'}; "
                   f"file refs {file_refs[:3]}")

    # --------------------------------------------------------------
    def kit_drift(self):
        script = os.path.join(self.repo, "pipeline", "platform",
                              "ops", "kit_drift.py")
        code, out = _run(f"python3 {script}", self.repo)
        if code == 0:
            detail = "kit_drift.py exit 0"
        elif out.strip():
            detail = ("kit_drift.py exit " + str(code) + " — "
                      + out.strip().splitlines()[-1])
        else:
            detail = "kit_drift.py failed without output"
        self.check("vendored kit drift (internal leg)", code == 0,
                   detail)

    # --------------------------------------------------------------
    def home_shape(self):
        """Rewrite the staged artifact's package metadata
        to the published home's shape — the last staging
        step, after every build has run repo-shaped.

        The staged tree builds repo-shaped: artifact/ and
        kit/ are siblings, and the artifact's install
        resolves the kit as file:../kit. The published
        home is flattened — kit/ lives inside the artifact
        root — so the metadata the sync consumes must read
        file:./kit, and the lockfile must carry the same
        move in both places bun records it: the workspace
        spec verbatim (file:./kit) and the resolved
        package key in bun's normalized form (file:kit).
        Each rewrite asserts its expected occurrence
        count, in the sync's idiom — a source that has
        moved fails the prep rather than staging
        unrewritten. The staged install stays usable
        through its existing node_modules; only the
        metadata text moves.

        The d3-dsv patch the platform's closed-bundle
        build requires (its row converter is a
        new Function() the closed bundle rejects; the
        patch is a semantics-identical closure) is repo
        source — artifact/patches/, named by
        package.json's patchedDependencies — and stages
        like any other source; this step asserts it
        arrived and that the lockfile records it."""
        artifact = os.path.join(self.tree, "artifact")
        pkg_path = os.path.join(artifact, "package.json")
        lock_path = os.path.join(artifact, "bun.lock")
        pkg_text = open(pkg_path, encoding="utf-8").read()
        lock_text = open(lock_path, encoding="utf-8").read()
        patch_name = "d3-dsv@3.0.2"
        patch_rel = "patches/d3-dsv@3.0.2.patch"
        problems = []
        try:
            pkg = json.loads(pkg_text)
        except ValueError:
            pkg = {}
        if pkg.get("patchedDependencies") != {patch_name: patch_rel}:
            problems.append(
                "package.json does not name the d3-dsv patch "
                "in patchedDependencies")
        if not os.path.isfile(os.path.join(artifact, patch_rel)):
            problems.append(f"{patch_rel} did not stage")
        if lock_text.count('"patchedDependencies"') != 1 or \
                lock_text.count(f'"{patch_name}": "{patch_rel}"') != 1:
            problems.append(
                "bun.lock does not record the d3-dsv patch")
        pkg_count = pkg_text.count('"file:../kit"')
        if pkg_count != 1:
            problems.append(
                f"package.json carries {pkg_count} kit specs "
                f"of file:../kit, expected 1")
        lock_spec = lock_text.count('"file:../kit"')
        lock_key = lock_text.count('"@workhorse/kit@file:../kit"')
        if lock_spec != 1 or lock_key != 1:
            problems.append(
                f"bun.lock carries {lock_spec} kit specs of "
                f"file:../kit and {lock_key} resolved "
                f"@workhorse/kit@file:../kit keys, expected "
                f"1 each")
        if problems:
            self.check("staged package metadata home-shaped",
                       False, "; ".join(problems))
            return
        with open(pkg_path, "w", encoding="utf-8") as fh:
            fh.write(pkg_text.replace('"file:../kit"',
                                      '"file:./kit"'))
        lock_text = lock_text.replace(
            '"@workhorse/kit@file:../kit"',
            '"@workhorse/kit@file:kit"')
        lock_text = lock_text.replace('"file:../kit"',
                                      '"file:./kit"')
        with open(lock_path, "w", encoding="utf-8") as fh:
            fh.write(lock_text)
        self.check("staged package metadata home-shaped", True,
                   "kit spec file:./kit in package.json and "
                   "bun.lock (resolved key file:kit); d3-dsv "
                   "patch named in patchedDependencies, "
                   "staged, and recorded in the lockfile")


class PrepError(Exception):
    pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", required=True,
                    help="the staging tree to (re)build")
    ap.add_argument("--repo", default=REPO_ROOT,
                    help="the mega repo (default: this repo)")
    args = ap.parse_args(argv)

    if shutil.which("bun") is None:
        print("FAIL bun is not on PATH")
        return 2
    prep = Prep(os.path.abspath(args.tree),
                os.path.abspath(args.repo))
    try:
        prep.stage()
        prep.prune_react()
        if prep.composed_build():
            prep.dist_assertions()
            prep.parity_check()
        prep.kit_drift()
        prep.home_shape()
    except PrepError as exc:
        print(f"FAIL prep: {exc}")
        return 2
    failed = [a for a in prep.assertions if not a["pass"]]
    report = {"tree": prep.tree, "repo": prep.repo,
              "assertions": prep.assertions,
              "verdict": "pass" if not failed else "fail"}
    with open(os.path.join(prep.tree, "prep-report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    print(f"SUMMARY {json.dumps({'verdict': report['verdict'], 'failed': len(failed), 'tree': prep.tree}, sort_keys=True)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
