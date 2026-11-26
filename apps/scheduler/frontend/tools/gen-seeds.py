#!/usr/bin/env python3
"""Generate the scheduler frontend's mock seed entries from the S1
overlay capture + the S0 contract fixtures.

Sources (read-only):
  - docs/overlay/holding/scheduler/jobs/*.yaml   (24 held live entries)
  - contracts/fixtures/scheduler-entry-bridge-wake.yaml
  - contracts/fixtures/scheduler-entry-bridge-drain.yaml
    (the tracked pair; together the fleet of record is 26 entries)

Target form: contract 14's frozen field table. The migration field
family (migrated, migrated_at, migration_note, proof_pending) is
dropped per amendment 3: presence in the store is
admission; the fields do not exist in the target format.

The registry's YAML is a strict subset (nested maps by two-space
indentation, scalar lists only, no anchors/flow/multiline), so this
is a small purpose parser for exactly that subset — keys split on
the first ": ", which is how plain scalars may carry ": " inside
values (e.g. owner_reason in flap-watch.yaml defeats PyYAML).

Output: src/mock/seed-entries.json (entries sorted by id).
Also prints a contract-14 structural validation verdict per entry.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # supreme-octo-robot/
HOLDING = ROOT / "docs/overlay/holding/scheduler/jobs"
FIXTURES = ROOT / "contracts/fixtures"
OUT = Path(__file__).resolve().parents[1] / "src/mock/seed-entries.json"

MIGRATION_FAMILY = {"migrated", "migrated_at", "migration_note", "proof_pending"}

# Contract 14's frozen field table (top level).
ALLOWED_TOP = {
    "id", "title", "kind", "status", "suspend_reason", "suspended_on",
    "cadence", "timezone", "owner", "owner_reason", "run", "body",
    "escalate_body", "timeout_secs", "report", "state_paths",
    "classification", "lifetime", "self_removal", "source",
    "catalog", "catalog_version", "parameters",
    # machine-form source stamp fields (contract 14, flat on the entry)
    "writer", "project", "todo", "source_class",
}


def parse_scalar(text):
    text = text.strip()
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text.startswith("'"):
        assert text.endswith("'") and len(text) >= 2, f"bad single-quoted scalar: {text!r}"
        return text[1:-1].replace("''", "'")
    if text.startswith('"'):
        return json.loads(text)
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def parse_block(lines, i, indent):
    """Parse a block (map or scalar list) at the given indent.
    Returns (value, next_index)."""
    # Decide list vs map from the first line at this indent.
    first = lines[i][1]
    if first.startswith("- "):
        items = []
        while i < len(lines):
            ind, content = lines[i]
            if ind != indent or not content.startswith("- "):
                break
            items.append(parse_scalar(content[2:]))
            i += 1
        return items, i
    mapping = {}
    while i < len(lines):
        ind, content = lines[i]
        if ind != indent or content.startswith("- "):
            break
        # key is up to the first ':' followed by space or EOL.
        m = re.match(r"^([^:]+):(?: (.*))?$", content)
        assert m, f"unparseable line: {content!r}"
        key, rest = m.group(1), m.group(2)
        i += 1
        if rest is not None and rest != "":
            mapping[key] = parse_scalar(rest)
        elif i < len(lines) and lines[i][0] > indent:
            value, i = parse_block(lines, i, lines[i][0])
            mapping[key] = value
        else:
            mapping[key] = None
    return mapping, i


def parse_entry(text):
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, raw.strip()))
    value, _ = parse_block(lines, 0, 0)
    return value


def validate(entry, stem):
    """Structural check against contract 14's field table."""
    problems = []
    if entry.get("id") != stem:
        problems.append(f"id {entry.get('id')!r} != filename stem {stem!r}")
    unknown = set(entry) - ALLOWED_TOP
    if unknown:
        problems.append(f"unknown fields: {sorted(unknown)}")
    if entry.get("kind") not in ("scripted", "agent"):
        problems.append(f"kind not in enum: {entry.get('kind')!r}")
    if entry.get("status") not in ("active", "suspended"):
        problems.append(f"status not in enum: {entry.get('status')!r}")
    cad = entry.get("cadence") or {}
    ctype = cad.get("type")
    if ctype == "interval":
        if not re.fullmatch(r"\d+[smh]", str(cad.get("every", ""))):
            problems.append(f"interval cadence missing every <Ns|Nm|Nh>: {cad!r}")
    elif ctype == "daily":
        if not re.fullmatch(r"\d{2}:\d{2}", str(cad.get("at", ""))):
            problems.append(f"daily cadence missing at HH:MM: {cad!r}")
    elif ctype == "weekly":
        if not cad.get("dow") or not re.fullmatch(r"\d{2}:\d{2}", str(cad.get("at", ""))):
            problems.append(f"weekly cadence missing dow/at: {cad!r}")
    else:
        problems.append(f"cadence type not in enum: {ctype!r}")
    if "owner" not in entry:
        problems.append("owner missing")
    if entry.get("owner") == "none" and not entry.get("owner_reason"):
        problems.append("owner 'none' without owner_reason")
    if entry.get("kind") == "scripted" and not (entry.get("run") or {}).get("argv"):
        problems.append("scripted entry without run.argv")
    if entry.get("kind") == "agent" and not entry.get("body"):
        problems.append("agent entry without body")
    if entry.get("lifetime") not in ("permanent", "until_complete"):
        problems.append(f"lifetime not in enum: {entry.get('lifetime')!r}")
    if not entry.get("classification"):
        problems.append("classification evidence missing")
    leftover = MIGRATION_FAMILY & set(entry)
    if leftover:
        problems.append(f"migration family survived stripping: {sorted(leftover)}")
    return problems


def main():
    sources = sorted(HOLDING.glob("*.yaml")) + [
        FIXTURES / "scheduler-entry-bridge-wake.yaml",
        FIXTURES / "scheduler-entry-bridge-drain.yaml",
    ]
    entries = []
    failures = 0
    for path in sources:
        entry = parse_entry(path.read_text())
        for field in MIGRATION_FAMILY:
            entry.pop(field, None)
        problems = validate(entry, path.stem.replace("scheduler-entry-", ""))
        status = "OK  " if not problems else "FAIL"
        if problems:
            failures += 1
        print(f"{status} {entry.get('id')}: {'; '.join(problems) if problems else 'contract-14 form clean'}")
        entries.append(entry)
    entries.sort(key=lambda e: e["id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(entries)} entries -> {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    # The unified argv guard (pipeline/platform/argv.py):
    # this tool takes no arguments — any argument is a
    # usage refusal (exit 2) and --help prints the
    # generated help; a stray flag never falls through
    # to the regeneration.
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "pipeline_platform_argv",
        ROOT / "pipeline" / "platform" / "argv.py")
    uargv = importlib.util.module_from_spec(_spec)
    sys.modules["pipeline_platform_argv"] = uargv
    _spec.loader.exec_module(uargv)

    _outcome = uargv.parse_only({"name": "gen-seeds"}, sys.argv[1:])
    if not _outcome["ok"]:
        print(_outcome["error"], file=sys.stderr)
        print(_outcome["usage"], file=sys.stderr)
        sys.exit(uargv.USAGE_EXIT)
    if "help" in _outcome:
        print(_outcome["help"], end="")
        sys.exit(0)
    sys.exit(main())
