#!/usr/bin/env python3
"""File-registry checker (file-registry contract v1).

After a restart, walk the registry of must-exist files,
restore the ones with a restore source, and flag the rest
to their owners — so a loss is reported at the restart
that reveals it, by the file's own name. The contract's
full text lives with the starter kit (SPEC.md,
`file-registry: v1`); this checker implements it for the
scheduler's domain and never extends the format.

Manifest: registry/file-registry.yaml (untracked live
data; the tracked specimen is
examples/file-registry/example-file-registry.yaml). Roots are
declared once in the manifest's `roots:` map; entry paths
are relative to their root anchor, or globs. Presence is
evaluated exactly: missing fails every rule; zero bytes
fails `non-empty` and `sha256`; a digest mismatch fails
`sha256`. Restore classes: tracked (the file's bytes from
its repo's HEAD), generated (re-run the declared
generator), backup (copy the declared backup back — a
backup that itself fails presence flags, never chains),
flag-only (never written, ever). A restored file is
re-checked; a restore that does not satisfy the rule is
flagged, not restored. For a glob entry, a backup restore
copies from the same relative path under the backup
directory (the v1 reading for globs; single-path entries
are the unambiguous case).

Trigger and report: the pass runs on a cadence; the boot
identity (/proc/sys/kernel/random/boot_id, the restart
detector's source) is compared with the recorded one. The
evaluation is the same code path on every pass — boot,
interval, or manual (--report-always additionally forces
the report). One findings-first report prints when there
is something to report (any flag or restore) AND the boot
changed or the findings differ from the last reported
set; a clean or unchanged pass is silent.

Exit codes: 0 = pass completed (any verdicts);
3 = the manifest or the boot-id source is unreadable or
invalid — loud, never a silent no-op.
Stdlib only; paths derive from this file's location.
"""
import glob as glob_mod
import hashlib
import json
import os
import subprocess
import sys
import time

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

_timestamps_spec = _importlib_util.spec_from_file_location(
    "ops_timestamps",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "timestamps.py"),
                       os.path.join(_here, "timestamps.py"))
         if os.path.isfile(_p)))
timestamps = _importlib_util.module_from_spec(_timestamps_spec)
_timestamps_spec.loader.exec_module(timestamps)

REPO = paths.REPO_ROOT
MANIFEST = os.environ.get(
    "FILE_REGISTRY_MANIFEST",
    paths.FILE_REGISTRY_MANIFEST)
STATE = os.environ.get(
    "FILE_REGISTRY_STATE",
    os.path.join(paths.STATE_DIR, "file-registry-state.json"))
BOOT_ID_FILE = os.environ.get(
    "FILE_REGISTRY_BOOT_ID_FILE",
    "/proc/sys/kernel/random/boot_id")

PRESENCE_RULES = ("exists", "non-empty", "sha256")
RESTORE_CLASSES = ("tracked", "generated", "backup", "flag-only")


class ManifestError(Exception):
    pass


# ------------------------------------------------------------ manifest YAML
# The manifest subset: indentation maps, lists of maps,
# scalar lists, quoted/plain scalars, booleans, comments.
# (The registry's job-entry parser excludes lists of maps
# by design; the file-registry format requires them, so
# the checker carries its own reader for the contract's
# format. Unknown top-level keys are ignored.)

def _scalar(text):
    text = text.strip()
    if text in ("", "null", "~"):
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    return text


def _strip_comment(raw):
    out = []
    quote = None
    for ch in raw:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _lines(text):
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        stripped = _strip_comment(raw)
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        if indent % 2:
            raise ManifestError(f"line {no}: indentation must be "
                                "two-space steps")
        out.append((indent, stripped.strip(), no))
    return out


def _parse_block(lines, pos, indent):
    if pos >= len(lines) or lines[pos][0] < indent:
        return None, pos
    if lines[pos][1].startswith("- ") or lines[pos][1] == "-":
        items = []
        while pos < len(lines) and lines[pos][0] == indent \
                and (lines[pos][1].startswith("- ")
                     or lines[pos][1] == "-"):
            text = lines[pos][1]
            rest = text[1:].strip()
            no = lines[pos][2]
            if rest == "":
                value, pos = _parse_block(lines, pos + 1, indent + 2)
                items.append(value)
            elif ":" in rest and not rest.startswith(("'", '"', "[")):
                # A map opened inline: rewrite the dash line as
                # a map line at the deeper indent and parse it.
                lines[pos] = (indent + 2, rest, no)
                value, pos = _parse_block(lines, pos, indent + 2)
                items.append(value)
            else:
                items.append(_scalar(rest))
                pos += 1
        return items, pos
    mapping = {}
    while pos < len(lines) and lines[pos][0] == indent \
            and not lines[pos][1].startswith("- "):
        _ind, text, no = lines[pos]
        if ":" not in text:
            raise ManifestError(f"line {no}: expected 'key: value'")
        key, _, rest = text.partition(":")
        key = key.strip()
        rest = rest.strip()
        pos += 1
        if rest:
            mapping[key] = _scalar(rest)
        elif pos < len(lines) and lines[pos][0] > indent:
            mapping[key], pos = _parse_block(lines, pos, lines[pos][0])
        else:
            mapping[key] = None
    return mapping, pos


def parse_manifest(text):
    lines = _lines(text)
    if not lines:
        raise ManifestError("empty manifest")
    value, pos = _parse_block(lines, 0, lines[0][0])
    if pos != len(lines):
        raise ManifestError(f"line {lines[pos][2]}: trailing content")
    if not isinstance(value, dict):
        raise ManifestError("a manifest is one map")
    return value


def validate_manifest(data):
    roots = data.get("roots")
    if not isinstance(roots, dict) or not roots:
        raise ManifestError("manifest needs a non-empty roots map")
    for name, path in roots.items():
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ManifestError(f"root {name!r} must be an absolute path")
    files = data.get("files")
    if files is None:
        files = []
    if not isinstance(files, list):
        raise ManifestError("files must be a list")
    for i, entry in enumerate(files):
        where = f"files[{i}]"
        if not isinstance(entry, dict):
            raise ManifestError(f"{where}: an entry is a map")
        if not entry.get("path") or not isinstance(entry["path"], str):
            raise ManifestError(f"{where}: path is required")
        if entry.get("root") not in roots:
            raise ManifestError(f"{where}: root must name a declared root")
        if entry.get("presence") not in PRESENCE_RULES:
            raise ManifestError(f"{where}: presence must be one of "
                                f"{PRESENCE_RULES}")
        if entry["presence"] == "sha256" and not entry.get("sha256"):
            raise ManifestError(f"{where}: sha256 rule needs a sha256 value")
        if not entry.get("owner"):
            raise ManifestError(f"{where}: owner is required")
        restore = entry.get("restore") or {}
        cls = restore.get("class", "flag-only")
        if cls not in RESTORE_CLASSES:
            raise ManifestError(f"{where}: restore class must be one of "
                                f"{RESTORE_CLASSES}")
        if cls == "generated":
            gen = restore.get("generator") or {}
            if not gen.get("argv") or gen.get("root") not in roots:
                raise ManifestError(f"{where}: generated restore needs "
                                    "generator.argv and a declared "
                                    "generator.root")
        if cls == "backup" and not restore.get("backup"):
            raise ManifestError(f"{where}: backup restore needs a "
                                "backup path")
    return roots, files


# ------------------------------------------------------------ presence

def check_presence(path, entry):
    rule = entry["presence"]
    if not os.path.isfile(path):
        return False, "missing"
    if rule == "exists":
        return True, ""
    if os.path.getsize(path) == 0:
        return False, "empty"
    if rule == "non-empty":
        return True, ""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != str(entry["sha256"]).lower():
        return False, "sha256 mismatch"
    return True, ""


# ------------------------------------------------------------ restore

def _load_writer():
    """The pipeline's unified writer (contract 15), loaded
    by path from the paths spine's PLATFORM_WRITER value —
    the liveness entry's standing pattern for cross-pipeline
    loads. None when the ops tree runs standalone, outside
    the mega repo, where _staged_write performs the same
    protocol inline: the protocol, not the module, is the
    invariant."""
    cand = paths.PLATFORM_WRITER
    if not os.path.isfile(cand):
        return None
    spec = _importlib_util.spec_from_file_location(
        "pipeline_platform_writer", cand)
    module = _importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _staged_write(path, data):
    """Write bytes through the unified writer's protocol
    (stage to a fresh sibling, fsync, read-back compare,
    rename over — contract 15), so a restore never opens a
    target for truncate-write and a denied or torn write
    leaves the standing file byte-identical. Standalone
    (no pipeline), the same staging is performed locally."""
    writer = _load_writer()
    if writer is not None:
        writer.staged_write(path, data)
        return
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp-registry"
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp, "rb") as fh:
            if fh.read() != data:
                raise OSError(f"read-back mismatch for {path}")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _restore_tracked(root_dir, rel):
    proc = subprocess.run(["git", "-C", root_dir, "show", f"HEAD:{rel}"],
                          capture_output=True, timeout=60)
    if proc.returncode != 0:
        return None, "tracked source unavailable"
    return proc.stdout, ""


def _restore_generated(roots, restore):
    gen = restore["generator"]
    proc = subprocess.run([str(a) for a in gen["argv"]],
                          cwd=roots[gen["root"]],
                          capture_output=True, timeout=300)
    if proc.returncode != 0:
        return False, f"generator exited {proc.returncode}"
    return True, ""


def _restore_backup(roots, entry, target, rel):
    backup = entry["restore"]["backup"]
    source = backup if os.path.isabs(backup) \
        else os.path.join(roots[entry["root"]], backup)
    if os.path.isdir(source) or entry.get("_glob"):
        source = os.path.join(source, rel)
    ok, _reason = check_presence(source, entry)
    if not ok:
        return False, "backup source fails presence"
    with open(source, "rb") as fh:
        _staged_write(target, fh.read())
    return True, ""


def restore_file(roots, entry, target, rel):
    """(attempted, ok, detail). flag-only never attempts."""
    cls = (entry.get("restore") or {}).get("class", "flag-only")
    if cls == "flag-only":
        return False, False, ""
    root_dir = roots[entry["root"]]
    if cls == "tracked":
        data, detail = _restore_tracked(root_dir, rel)
        if data is None:
            return True, False, detail
        _staged_write(target, data)
        return True, True, ""
    if cls == "generated":
        ok, detail = _restore_generated(roots, entry["restore"])
        return True, ok, detail
    if cls == "backup":
        ok, detail = _restore_backup(roots, entry, target, rel)
        return True, ok, detail
    return False, False, ""


# ------------------------------------------------------------ the pass

def evaluate(roots, files):
    """Returns (flagged, restored, passed_count). flagged and
    restored are report line lists (without the header)."""
    flagged, restored, passed = [], [], 0
    for entry in files:
        root_dir = roots[entry["root"]]
        pattern = os.path.join(root_dir, entry["path"])
        is_glob = any(c in entry["path"] for c in "*?[")
        if is_glob:
            targets = sorted(p for p in glob_mod.glob(pattern)
                             if os.path.isfile(p))
            entry = dict(entry, _glob=True)
            if not targets:
                if entry.get("optional"):
                    passed += 1
                else:
                    flagged.append(
                        f"FLAGGED owner={entry['owner']} "
                        f"{entry['root']}:{entry['path']} — "
                        "glob matched nothing")
                continue
        else:
            targets = [pattern]
        entry_ok = True
        for target in targets:
            ok, reason = check_presence(target, entry)
            if ok:
                continue
            rel = os.path.relpath(target, root_dir)
            label = f"{entry['root']}:{rel}"
            attempted, rok, detail = restore_file(
                roots, entry, target, rel)
            if attempted and rok:
                ok2, reason2 = check_presence(target, entry)
                if ok2:
                    restored.append(
                        f"RESTORED {label} — class="
                        f"{entry['restore']['class']}")
                    continue
                flagged.append(
                    f"FLAGGED owner={entry['owner']} {label} — "
                    f"restored file still fails: {reason2}")
                entry_ok = False
            elif attempted:
                flagged.append(
                    f"FLAGGED owner={entry['owner']} {label} — {detail}")
                entry_ok = False
            else:
                flagged.append(
                    f"FLAGGED owner={entry['owner']} {label} — {reason}")
                entry_ok = False
        if entry_ok:
            passed += 1
    return flagged, restored, passed


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state):
    data = json.dumps(state, indent=1, sort_keys=True).encode("utf-8")
    _staged_write(STATE, data)


now = timestamps.zstamp_now


def run(manifest_path, boot_file, report_always=False, at=None):
    """One pass: (exit_code, report_text_or_None)."""
    try:
        with open(boot_file, encoding="utf-8") as fh:
            boot_id = fh.read().strip()
    except OSError:
        return 3, "FILE REGISTRY: boot-id source unreadable"
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data = parse_manifest(fh.read())
        roots, files = validate_manifest(data)
    except (OSError, ManifestError) as e:
        return 3, f"FILE REGISTRY: manifest invalid: {e}"
    flagged, restored, passed = evaluate(roots, files)
    state = load_state()
    boot_changed = state.get("boot_id") not in (None, boot_id)
    findings = flagged + restored
    signature = hashlib.sha256(
        "\n".join(sorted(findings)).encode("utf-8")).hexdigest()[:16]
    report = None
    if findings and (report_always or boot_changed
                     or signature != state.get("signature")):
        header = (f"FILE REGISTRY {at or now()} "
                  f"boot={'changed' if boot_changed else 'same'} "
                  f"flagged={len(flagged)} restored={len(restored)} "
                  f"passed={passed}")
        report = "\n".join([header] + flagged + restored)
    save_state({"boot_id": boot_id, "signature": signature,
                "updated": at or now()})
    return 0, report


DECL = {
    "name": "file_registry",
    "summary": "The file-registry watch: declared generated "
               "files verified against their generators.",
    "flags": {"report-always": {"help": "print the report even "
                                        "when nothing changed"}},
}


def main(argv=()):
    result, code = paths.parse_argv(DECL, argv)
    if result is None:
        return code
    code, report = run(MANIFEST, BOOT_ID_FILE,
                       report_always=result["flags"]["report-always"])
    if report:
        print(report)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
