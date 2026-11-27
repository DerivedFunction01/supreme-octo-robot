#!/usr/bin/env python3
"""Capture/restore transient files between canonical homes and the repo mirror.

Registry: config/transient.json; runbook: ops/restore-cron.md. Canonical
paths resolve against $HOME, or $VENUE_RUNNER_HOME when set; under
that override the mirror resolves under the same root, so a
sandboxed run (the test suite) never touches the real mirror.
Reports carry only existence, size, mtime, and action taken.

The argument surface parses through the unified argv
contract (pipeline/platform/argv.py): the op is a verb,
an unknown verb or flag is a usage refusal (exit 2),
and --help prints the generated help.
"""

import importlib.util as _ilu
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation; bound by path — the bootstrap form.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).resolve().parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

REPO = _paths.REPO_RESOLVED
REGISTRY = _paths.TRANSIENT_REGISTRY

# The unified argv contract home, loaded by location
# through the paths spine.
_argv_spec = _ilu.spec_from_file_location(
    "pipeline_platform_argv", _paths.PLATFORM_ARGV)
platform_argv = _ilu.module_from_spec(_argv_spec)
_argv_spec.loader.exec_module(platform_argv)

DECLARATION = {
    "name": "mirror_transient",
    "summary": "capture/restore transient files between "
               "canonical homes and the repo mirror",
    "flags": {
        "item": {"takes_value": True,
                 "help": "only this registry id"},
        "json": {"help": "machine-readable report"},
    },
    "verbs": {
        "capture": {"summary": "copy canonical files into "
                               "the repo mirror"},
        "restore": {"summary": "copy mirror files back to "
                               "their canonical homes"},
        "status": {"summary": "report existence, size and "
                              "mtime on both sides"},
    },
}


def home() -> Path:
    override = os.environ.get("VENUE_RUNNER_HOME")
    return Path(override) if override else Path.home()


def load_registry() -> list[dict]:
    return json.loads(REGISTRY.read_text())["items"]


# The registry above mirrors fixed home-dir files one by one.
# Repo var/ holds a second transient population: per-session
# file CLASSES (a name pattern, not a fixed path), which ride
# the transient set as classes — they are restored with var/
# as a whole rather than item by item, so no registry item
# can name them. This manifest names the classes so the set
# stays enumerable: (prefix, suffix, class). The
# session-evidence class joins with the E2 evidence
# projection: a verbatim copy of each lease record's
# deadline fields, refreshed on every record save, kept so
# orphan derivation survives the record's own loss.
VAR_FILE_CLASSES = (
    ("lease-", ".json", "lease-record"),
    ("renewal-config-", ".json", "renewal-config"),
    ("liveness-", ".json", "liveness"),
    ("session-evidence-", ".json", "session-evidence"),
)


def var_file_class(filename: str) -> str | None:
    """The transient var class a var/ filename belongs to, or
    None when the file is not part of the transient set."""
    for prefix, suffix, name in VAR_FILE_CLASSES:
        if filename.startswith(prefix) and filename.endswith(suffix):
            return name
    return None


def resolve(item: dict) -> tuple[Path, Path]:
    canonical = Path(str(item["canonical"]).replace("~", str(home()), 1))
    # The mirror's root is the repo — except under the
    # VENUE_RUNNER_HOME override, where both sides resolve
    # under the override root (the suite's mirror
    # tests shared the one real mirror file through this seam
    # and raced under parallel workers).
    root = home() if os.environ.get("VENUE_RUNNER_HOME") else REPO
    return canonical, root / item["mirror"]


def atomic_copy(src: Path, dst: Path, mode: str | None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=dst.name + ".")
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out, length=1024 * 1024)
        if mode:
            os.chmod(tmp, int(mode, 8))
        os.replace(tmp, dst)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    # Preserve mtime so newest-wins comparisons stay honest across copies.
    st = src.stat()
    os.utime(dst, (st.st_atime, st.st_mtime))


def verify(path: Path, kind: str | None) -> bool:
    try:
        if kind == "json":
            json.loads(path.read_text())
        return path.exists()
    except Exception:
        return False


def token_valid(path: Path) -> bool:
    """The colab-token validation: parses as JSON and carries a
    refresh_token of plausible length. The interactive flow's stub (a
    lone 15-char refresh_token) fails it. Contents are never printed.
    Mirrors bin/venue-run's guard check."""
    try:
        parsed = json.loads(path.read_text())
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    rt = parsed.get("refresh_token")
    return isinstance(rt, str) and len(rt) >= 20


def file_report(item: dict) -> dict:
    canonical, mirror = resolve(item)
    rep = {"id": item["id"], "rule": item.get("rule"), "kind": item["kind"]}
    for label, p in (("canonical", canonical), ("mirror", mirror)):
        rep[label] = (
            {"exists": True, "bytes": p.stat().st_size, "mtime": int(p.stat().st_mtime)}
            if p.exists()
            else {"exists": False}
        )
    if canonical.exists() and mirror.exists():
        rep["identical"] = canonical.read_bytes() == mirror.read_bytes()
    return rep


def capture(item: dict) -> str:
    if item["kind"] != "file" or not item.get("enabled", True):
        return "skipped"
    canonical, mirror = resolve(item)
    if not canonical.exists():
        return "no-canonical"
    if item.get("validate") == "colab-token":
        # A clobbered credential must never propagate into the mirror
        # (the flow's stub overwrote the canonical token
        # and a capture carried the stub into the mirror, destroying
        # the last good copy). An invalid canonical with a valid
        # mirror heals from the mirror instead of capturing.
        if not token_valid(canonical):
            if mirror.exists() and token_valid(mirror):
                atomic_copy(mirror, canonical, item.get("mode"))
                return "canonical-healed-from-mirror"
            return "canonical-invalid-kept"
    if item.get("never_capture_empty") and mirror.exists():
        # A live binding clobbered to {} by a CLI side effect must not
        # overwrite the last good mirror copy (a
        # `colab run` emptied sessions.json while its assignment lived on).
        # An unparseable file counts as empty on both sides: the
        # guarded failure was a 0-byte canonical, which raised in
        # json.loads, fell through the old guard's except, and was
        # captured over the last good mirror in the same minute.

        def _is_empty(path: Path) -> bool:
            try:
                return json.loads(path.read_text()) in ({}, [])
            except Exception:  # noqa: BLE001
                return True

        if _is_empty(canonical) and not _is_empty(mirror):
            return "mirror-nonempty-kept"
    if mirror.exists():
        if item["rule"] == "newest-wins" and mirror.stat().st_mtime > canonical.stat().st_mtime:
            return "mirror-newer-kept"
        if item["rule"] in ("newest-wins", "restore-if-missing") and canonical.read_bytes() == mirror.read_bytes():
            return "in-sync"
    atomic_copy(canonical, mirror, item.get("mode"))
    return "captured" if verify(mirror, item.get("verify")) else "verify-failed"


def restore(item: dict) -> str:
    if item["kind"] != "file" or not item.get("enabled", True):
        return "skipped"
    canonical, mirror = resolve(item)
    if not mirror.exists():
        return "no-mirror"
    if item.get("validate") == "colab-token" and not token_valid(mirror):
        # An invalid mirror copy (a stub captured before the
        # validation rule, or a clobber that reached the mirror) never
        # overwrites the canonical file, whatever the mtimes say:
        # newest-wins applies to valid credentials only.
        return "mirror-invalid-kept"
    if canonical.exists():
        if item["rule"] == "restore-if-missing":
            return "canonical-present"
        if mirror.stat().st_mtime <= canonical.stat().st_mtime:
            return "canonical-newer-kept"
    atomic_copy(mirror, canonical, item.get("mode"))
    return "restored" if verify(canonical, item.get("verify")) else "verify-failed"


OPS = {"capture": capture, "restore": restore}


def main() -> int:
    try:
        parsed = platform_argv.parse(DECLARATION, sys.argv[1:])
    except platform_argv.UsageError as exc:
        print(str(exc), file=sys.stderr)
        print(platform_argv.help_text(DECLARATION),
              file=sys.stderr, end="")
        return platform_argv.USAGE_EXIT
    if "help" in parsed:
        print(parsed["help"], end="")
        return 0
    op = parsed["verb"]
    flags = parsed["flags"]

    items = [i for i in load_registry() if not flags["item"] or i["id"] == flags["item"]]
    if not items:
        print(f"no registry item matches {flags['item']!r}", file=sys.stderr)
        return 2
    results, failed = [], False
    for item in items:
        if op == "status":
            results.append(file_report(item) if item["kind"] == "file" else {"id": item["id"], "kind": item["kind"]})
            continue
        action = OPS[op](item)
        failed |= action == "verify-failed"
        results.append({"id": item["id"], op: action})
    if flags["json"]:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(" ".join(f"{k}={v}" for k, v in r.items() if not isinstance(v, dict)))
            for k, v in r.items():
                if isinstance(v, dict):
                    print(f"  {k}: {v}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
