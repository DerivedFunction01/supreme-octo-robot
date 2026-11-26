#!/usr/bin/env python3
"""Apply a snapshot bundle inside a base clone (runs on the Colab VM, or
locally against a scratch clone for verification).

Verifies the bundle's SHA-256 against the manifest BEFORE touching git,
fetches the snapshot commit, fast-forwards, and prints the resulting tree
hash, which must equal the manifest's tree.

The clone is a scratch copy whose only job is to become the snapshot
tree, so before the fast-forward the apply resets it to the snapshot's
parent and cleans untracked non-ignored files: residue a previous
gate's overlay work left at paths the snapshot tracks would otherwise
make the ff-merge refuse ("would be overwritten") and the apply fail
closed on a stale clone (the Wingdings seam gate). Ignored
files — the repo venv, caches — are the gate substrate and survive
(no -x on the clean).

The argument surface is declared on the unified argv contract
(pipeline/platform/argv.py): two required positionals (bundle,
repo) and four optional value flags. Parse refusals (unknown
flag, missing value or positional, surplus positional) exit 2
with the generated usage; the domain verdicts stay the main
logic's own 0/1. This file executes in two homes — in-tree,
where tests run it by path, and on a venue as a lone uploaded
payload — so the contract module is loaded by location: the
copy uploaded beside the payload first, then the in-tree
platform home derived from this file's own location. No paths
spine exists at the payload home, and none is imported.
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _load_argv():
    here = Path(__file__).parent
    candidates = (
        here / "argv.py",
        Path(__file__).parent.parent.parent / "platform" / "argv.py",
    )
    for candidate in candidates:
        if candidate.exists():
            spec = importlib.util.spec_from_file_location(
                "pipeline_platform_argv", candidate
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise SystemExit(
        "apply_bundle_remote: the unified argv module is neither "
        "beside the script nor in the platform home"
    )


platform_argv = _load_argv()

DECLARATION = {
    "name": "apply_bundle_remote",
    "summary": "apply a snapshot bundle inside a base clone",
    "flags": {
        "manifest": {"takes_value": True, "help": "default: <bundle>.manifest.json"},
        "origin-url": {
            "takes_value": True,
            "help": "recorded as the seeded repo's origin (seed mode only)",
        },
        "user-name": {
            "takes_value": True,
            "help": "the source repo's configured user.name, planted repo-locally in the formed tree",
        },
        "user-email": {
            "takes_value": True,
            "help": "the source repo's configured user.email (may be empty — a configured value), planted alongside --user-name; the plant happens only when both flags are given",
        },
    },
    "positionals": [
        {"name": "bundle", "required": True},
        {"name": "repo", "required": True},
    ],
}


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def main() -> int:
    try:
        parsed = platform_argv.parse(DECLARATION, sys.argv[1:])
    except platform_argv.UsageError as exc:
        print(str(exc), file=sys.stderr)
        print(platform_argv.help_text(DECLARATION), file=sys.stderr)
        return platform_argv.USAGE_EXIT
    if "help" in parsed:
        print(parsed["help"])
        return 0
    flags = parsed["flags"]
    manifest_flag = flags["manifest"]
    origin_url = flags["origin-url"]
    user_name = flags["user-name"]
    user_email = flags["user-email"]

    def plant_identity(repo: Path) -> "dict | None":
        # The git identity plant (sync/git_identity.py): a
        # formed tree carries the source repo's configured
        # identity, never the forming shell's inheritance.
        # Both flags or no plant; a plant failure is reported
        # in the verdict JSON, never fatal to the apply.
        if user_name is None or user_email is None:
            return None
        try:
            git(repo, "config", "user.name", user_name)
            git(repo, "config", "user.email", user_email)
            got = {
                "name": git(repo, "config", "--local", "--get", "user.name"),
                "email": git(repo, "config", "--local", "--get", "user.email"),
            }
        except SystemExit as exc:
            return {"planted": False, "error": str(exc)[:300]}
        return {"planted": got == {"name": user_name, "email": user_email}, **got}

    bundle, repo = (
        Path(parsed["positionals"]["bundle"]).resolve(),
        Path(parsed["positionals"]["repo"]).resolve(),
    )
    manifest = json.loads(
        Path(manifest_flag or str(bundle) + ".manifest.json").read_text()
    )
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    if digest != manifest["sha256"]:
        print(
            json.dumps(
                {
                    "applied": False,
                    "error": "bundle sha256 mismatch",
                    "expected": manifest["sha256"],
                    "got": digest,
                }
            )
        )
        return 1
    if not (repo / ".git").exists():
        # Seed mode: no base clone exists. A private repo's plain
        # HTTPS clone cannot authenticate on the VM (no credential
        # lives there by design), so the bundle is the code route:
        # init the repo, fetch the snapshot, and put main on it.
        # The tree is verified against the manifest exactly as the
        # apply path verifies it.
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(repo), "init"], capture_output=True, text=True)
        if origin_url:
            git(repo, "remote", "add", "origin", origin_url)
        git(repo, "fetch", str(bundle), manifest["snapshot_commit"])
        git(repo, "checkout", "-B", "main", "FETCH_HEAD")
        tree = git(repo, "rev-parse", "HEAD^{tree}")
        print(
            json.dumps(
                {
                    "applied": True,
                    "seeded": True,
                    "head": git(repo, "rev-parse", "HEAD"),
                    "tree": tree,
                    "tree_matches_manifest": tree == manifest["tree"],
                    "git_identity": plant_identity(repo),
                }
            )
        )
        return 0 if tree == manifest["tree"] else 1
    git(repo, "fetch", str(bundle), manifest["snapshot_commit"])
    # The base clone's main may have moved since the bundle was built
    # (parallel work pushing to origin) or sit on a sibling commit, which
    # makes the ff-only merge refuse as "diverging". The clone is a
    # scratch copy whose only job is to become the snapshot tree, so pin
    # it to the snapshot's parent first — the parent object is present
    # after the fetch — then fast-forward.
    git(repo, "reset", "--hard", "FETCH_HEAD^")
    git(repo, "clean", "-fd")
    git(repo, "merge", "--ff-only", "FETCH_HEAD")
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    print(
        json.dumps(
            {
                "applied": True,
                "head": git(repo, "rev-parse", "HEAD"),
                "tree": tree,
                "tree_matches_manifest": tree == manifest["tree"],
                "git_identity": plant_identity(repo),
            }
        )
    )
    return 0 if tree == manifest["tree"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
