"""The todo rename driver: legacy ids → GitHub-like
names (the owner's naming ruling).

The one migration path from the retired generator's
`t-<token>` ids to slug names. For one project (one
plans dir) it:

- plans a name for every todo still carrying a legacy
  id — derived from its title by the writers' own
  derivation (lib/bundles.py: derive_todo_name), in
  deterministic scan order, against the project's whole
  name set (existing slug names are pre-claimed; a
  shared title suffixes `-2`, `-3`, … — every
  resolution is reported, none is silent);
- rewrites each renamed todo's file in place: the
  `id:` line takes the name, a `legacy_id:` line
  records the old token directly beneath it (the old
  id kept as data — the audit/reversibility join for
  anything that ever referenced it — and never again
  a lookup path), and the file itself renames to
  `<name>.md`;
- re-points references: every other mention of a
  renamed token in the project's Markdown corpus
  (plan files, flat plans, todo bodies — including
  the renamed todos' own bodies) is rewritten to the
  name. The `legacy_id:` lines themselves are never
  rewritten: they are the record of the old token;
- re-points derived state: an armed renamed todo's
  scheduler entry is deleted under its old name and
  not re-created (the rendering is retired, Step 6);
  its attention row is deleted under its old name and
  re-synced under the new one, through the same sync
  functions the writers use.

Dry-run by default: the full plan and counts are
computed and nothing is written. `apply=True` performs
it. What cannot be renamed is named in the report, not
skipped silently: a todo with no readable id, two
todos sharing one legacy id, a target filename that
already exists, and corpus mentions of legacy tokens
that belong to no todo in this project (cross-project
mentions and historical references — left untouched,
listed under `unresolved_references`).
"""

import os
import re
from pathlib import Path

from . import bundles as bundle_mod
from ..plans import bundles as bundle_parser
from ..progress import attention as attention_mod
from ..progress import schedule as schedule_mod
from ..util import write_text

_LEGACY_TOKEN_RE = re.compile(r"t-[0-9A-HJKMNP-TV-Z]{10,}")
_TOKEN_SCAN_RE = re.compile(
    r"(?<![A-Za-z0-9-])(t-[0-9A-HJKMNP-TV-Z]+)"
    r"(?![A-Za-z0-9-])")


def _scan(plans_dir: Path):
    """(todos, by_id) over the project's whole corpus,
    in the parser's deterministic order."""
    todos = bundle_parser.list_todos(plans_dir)
    by_id = {}
    for t in todos:
        if t["id"]:
            by_id.setdefault(t["id"], []).append(t)
    return todos, by_id


def plan_renames(plans_dir) -> dict:
    """The rename plan for one project: the mapping
    (legacy id → name), the collisions it resolved, and
    what it cannot rename. Pure — reads only."""
    plans_dir = Path(plans_dir)
    todos, by_id = _scan(plans_dir)
    taken = set()
    legacy = []
    already_named = 0
    unresolved = []
    for t in todos:
        if t["id"] is None:
            unresolved.append({
                "path": t["path"],
                "reason": "todo has no readable id"})
            continue
        if len(by_id[t["id"]]) > 1:
            unresolved.append({
                "path": t["path"],
                "reason": f"id {t['id']} is shared by "
                          f"{len(by_id[t['id']])} todos "
                          f"— ambiguous, not renamed"})
            continue
        if t["id_form"] == "slug":
            taken.add(t["id"])
            already_named += 1
        elif t["id_form"] == "legacy":
            legacy.append(t)
        else:
            unresolved.append({
                "path": t["path"],
                "reason": f"id {t['id']!r} matches "
                          f"neither the slug rule nor "
                          f"the legacy form"})
    mapping = {}
    collisions = []
    for t in legacy:
        base = bundle_mod.slugify_title(t["title"] or "")
        name = bundle_mod.derive_todo_name(
            t["title"] or "", taken)
        taken.add(name)
        mapping[t["id"]] = name
        if name != base:
            collisions.append({
                "legacy_id": t["id"], "title": t["title"],
                "derived": base, "name": name})
    return {
        "mapping": mapping,
        "collisions": collisions,
        "unresolved": unresolved,
        "already_named": already_named,
        "scanned": len(todos),
        "legacy": legacy,
    }


def _repoint_text(text: str, mapping: dict):
    """(new_text, replacements): every mapped legacy
    token in `text` rewritten to its name, line-wise.
    Two front-matter lines are never rewritten: the
    `id:` line (the rewrite pass owns it — counting it
    would also inflate the reference count) and the
    `legacy_id:` line (the record of the old token)."""
    if not mapping:
        return text, 0
    total = 0

    def _sub(match):
        nonlocal total
        new = mapping.get(match.group(1))
        if new is None:
            return match.group(0)
        total += 1
        return new

    out_lines = []
    lines = text.split("\n")
    in_fm = bool(lines) and lines[0].strip() == "---"
    for i, line in enumerate(lines):
        if in_fm and i > 0 and line.strip() == "---":
            in_fm = False
        if in_fm and (line.startswith("id:")
                      or line.startswith("legacy_id:")):
            out_lines.append(line)
            continue
        if not in_fm and line.startswith("legacy_id:"):
            out_lines.append(line)
            continue
        out_lines.append(_TOKEN_SCAN_RE.sub(_sub, line))
    return "\n".join(out_lines), total


def _corpus_files(plans_dir: Path):
    return sorted(plans_dir.rglob("*.md"))


def _count_references(plans_dir: Path, mapping: dict):
    """(total, {relpath: count}) of mapped-token
    mentions across the Markdown corpus — the dry-run
    count; the apply pass recounts as it rewrites."""
    total = 0
    per_file = {}
    for path in _corpus_files(plans_dir):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        _, n = _repoint_text(text, mapping)
        if n:
            rel = path.relative_to(plans_dir).as_posix()
            per_file[rel] = n
            total += n
    return total, per_file


def _leftover_references(plans_dir: Path, mapping: dict):
    """Legacy-form tokens still mentioned in the corpus
    after the rename that belong to no renamed todo:
    {token: [relpaths]}. `legacy_id:` lines excluded —
    they are records, not references."""
    leftovers = {}
    for path in _corpus_files(plans_dir):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(plans_dir).as_posix()
        for line in text.split("\n"):
            if line.startswith("legacy_id:"):
                continue
            for token in _LEGACY_TOKEN_RE.findall(line):
                if token not in mapping:
                    leftovers.setdefault(
                        token, []).append(rel)
    return {k: sorted(set(v))
            for k, v in sorted(leftovers.items())}


def _rewrite_todo_file(path: Path, todo, name: str):
    """The todo file's new text: `id:` takes the name,
    `legacy_id:` records the old token beneath it (an
    existing legacy_id line is kept, never duplicated),
    everything else byte-identical."""
    text = path.read_text(encoding="utf-8")
    fields, body, fm_lines = \
        bundle_parser.split_front_matter(text)
    if fields is None:
        return None
    out = []
    for line in fm_lines:
        key = line.partition(":")[0].strip() \
            if ":" in line else None
        if key == "id":
            out.append(f"id: {name}")
            if not any(
                    l.partition(":")[0].strip()
                    == "legacy_id" for l in fm_lines):
                out.append(
                    f"legacy_id: {todo['id']}")
        else:
            out.append(line)
    rendered = "---\n" + "\n".join(out) + "\n---\n"
    if body.strip():
        rendered += "\n" + body.strip("\n") + "\n"
    return rendered


def rename_todos(plans_dir, *, apply: bool = False,
                 jobs_directory=None,
                 armed_directory=None) -> dict:
    """Plan (and with apply=True, perform) one project's
    rename pass. Derived-state directories default to
    the progress seams' own resolution
    (lib/progress/schedule.py's jobs dir,
    lib/progress/attention.py's armed dir); an explicit
    directory overrides — the rehearsal seam."""
    plans_dir = Path(plans_dir)
    plan = plan_renames(plans_dir)
    mapping = plan["mapping"]
    ref_total, ref_files = _count_references(
        plans_dir, mapping)
    report = {
        "plans_dir": str(plans_dir),
        "applied": apply,
        "todos_scanned": plan["scanned"],
        "already_named": plan["already_named"],
        "renamed": [],
        "collisions": plan["collisions"],
        "references_repointed": ref_total,
        "reference_files": ref_files,
        "entries_removed": [],
        "entries_written": [],
        "rows_removed": [],
        "rows_written": [],
        "derived_skipped": None,
        "unresolved": list(plan["unresolved"]),
        "unresolved_references":
            _leftover_references(plans_dir, mapping),
    }
    if not apply:
        for t in plan["legacy"]:
            report["renamed"].append({
                "legacy_id": t["id"],
                "name": mapping[t["id"]],
                "bundle": t["bundle"],
                "title": t["title"],
                "armed": schedule_mod.is_armed(t)})
        return report

    by_legacy = {t["id"]: t for t in plan["legacy"]}
    renamed = []
    for legacy_id, name in mapping.items():
        todo = by_legacy[legacy_id]
        old_path = plans_dir / todo["path"]
        new_path = old_path.parent / f"{name}.md"
        if new_path != old_path and new_path.exists():
            report["unresolved"].append({
                "path": todo["path"],
                "reason": f"target file {new_path.name} "
                          f"already exists — not renamed"})
            continue
        rendered = _rewrite_todo_file(
            old_path, todo, name)
        if rendered is None:
            report["unresolved"].append({
                "path": todo["path"],
                "reason": "todo file has no front-matter "
                          "to rewrite"})
            continue
        write_text(new_path, rendered)
        if new_path != old_path:
            old_path.unlink()
        renamed.append({
            "legacy_id": legacy_id, "name": name,
            "bundle": todo["bundle"],
            "title": todo["title"],
            "armed": schedule_mod.is_armed(todo)})
    report["renamed"] = renamed
    done = {r["legacy_id"]: r["name"] for r in renamed}

    # References: rewrite mapped tokens corpus-wide
    # (the renamed files' bodies ride this same pass).
    if done:
        for path in _corpus_files(plans_dir):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            new_text, n = _repoint_text(text, done)
            if n:
                write_text(path, new_text)
    report["unresolved_references"] = \
        _leftover_references(plans_dir, done)

    # Derived state: drop each renamed armed todo's
    # entry/row under its old name, then re-sync the
    # renamed todo's attention row under its new one.
    # The scheduler entry is NOT re-synced: the
    # rendering is retired (Step 6), so no entry is
    # ever written under the new name — entries_written
    # stays empty by design.
    root = schedule_mod._project_root(plans_dir)
    if root is None:
        report["derived_skipped"] = \
            "project root not found"
        return report
    project_slug = root.name
    jdir = Path(jobs_directory) \
        if jobs_directory is not None \
        else schedule_mod.jobs_dir()
    adir = Path(armed_directory) \
        if armed_directory is not None \
        else attention_mod.armed_dir()
    # The sync functions resolve their directories
    # through the env seams; explicit directory
    # arguments steer those seams for this pass (and
    # are restored after), so a rehearsal's syncs land
    # in the rehearsal's dirs, never the live ones.
    seam_env = {}
    if jobs_directory is not None:
        seam_env["WB_SCHEDULER_JOBS_DIR"] = \
            str(jobs_directory)
    if armed_directory is not None:
        seam_env["WB_ATTENTION_ARMED_DIR"] = \
            str(armed_directory)
    saved_env = {k: os.environ.get(k) for k in seam_env}
    os.environ.update(seam_env)
    try:
        fresh = {t["legacy_id"]: t
                 for t in bundle_parser.list_todos(plans_dir)
                 if t["legacy_id"]}
        for r in renamed:
            if not r["armed"]:
                continue
            old_id, name = r["legacy_id"], r["name"]
            if jdir is not None:
                old_entry = jdir / (
                    f"{schedule_mod.entry_id(project_slug, old_id)}"
                    ".yaml")
                if old_entry.is_file():
                    old_entry.unlink()
                    report["entries_removed"].append(
                        old_entry.stem)
            if adir is not None:
                old_row = adir / (
                    f"{attention_mod.row_id(project_slug, old_id)}"
                    ".json")
                if old_row.is_file():
                    old_row.unlink()
                    report["rows_removed"].append(
                        old_row.stem)
            todo = fresh.get(old_id)
            if todo is None:
                report["unresolved"].append({
                    "path": r["bundle"],
                    "reason": f"renamed todo {name} not "
                              f"found on re-read — derived "
                              f"state not re-synced"})
                continue
            outcome = attention_mod.sync_todo(
                plans_dir, todo)
            if outcome.get("action") in ("written",
                                         "unchanged"):
                report["rows_written"].append(
                    outcome["row"])
            elif adir is not None and outcome.get(
                    "action") in ("skipped", "error"):
                report["unresolved"].append({
                    "path": todo["path"],
                    "reason": f"attention row not "
                              f"re-synced: {outcome}"})
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return report


def main(argv=None) -> int:
    """Standalone entry (the freeze act's driver form):
    python -m lib.todo_rename --root <project>
    [--jobs-dir D] [--armed-dir D] [--apply]."""
    import argparse
    import json

    from ..discovery.manifest import load_manifest

    parser = argparse.ArgumentParser(
        prog="todo_rename",
        description="Rename legacy todo ids to "
                    "GitHub-like names (dry-run "
                    "unless --apply).")
    parser.add_argument("--root", required=True,
                        help="the project root (holds "
                             "workbench.yaml)")
    parser.add_argument("--jobs-dir",
                        help="scheduler jobs dir override")
    parser.add_argument("--armed-dir",
                        help="attention armed dir override")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root)
    manifest = load_manifest(root / "workbench.yaml")
    plans_dir = manifest.plans or (root / ".plans")
    report = rename_todos(
        plans_dir, apply=args.apply,
        jobs_directory=args.jobs_dir,
        armed_directory=args.armed_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
