"""Resolve one package's targeted test set from a change
set — the check.py flow, per package: snapshot,
prose-only exclusion, trigger check, then AST lineage.
Returns "full" (run the whole suite), "none" (the changes
select no test in this package), or a SelectionResult.
"""
from __future__ import annotations

from pathlib import Path

from .gitdiff import (GitStatusSnapshot, PackageLayout,
                      classify, get_git_status)
from .lineage import LineageGraph
from .prose import prose_only_python_files


def _layout(pkg, repo_root: Path) -> PackageLayout:
    cfg = pkg.decl.get("targeting", {})
    root_rel = pkg.root.relative_to(repo_root).as_posix()
    return PackageLayout(
        root=root_rel,
        test_dirs=tuple(cfg.get("test_dirs", ["tests"])),
        full_suite_triggers=tuple(
            cfg.get("full_suite_triggers", [])))


def _changeset(pkg, repo_root: Path,
               explicit_paths: list[str] | None,
               explain: bool) -> ChangeSet:
    layout = _layout(pkg, repo_root)
    if explicit_paths is not None:
        # An explicit pathspec names logic changes; the
        # prose filter compares against HEAD and applies
        # only to the git-status-driven form.
        snapshot = GitStatusSnapshot(
            modified_files=tuple(explicit_paths))
        return classify(snapshot, layout)
    snapshot = get_git_status(repo_root)
    prefix = layout.root + "/"
    candidates = tuple(
        p for p in snapshot.all_active_files
        if p.startswith(prefix) and p.endswith(".py"))
    prose = prose_only_python_files(
        candidates, snapshot.untracked_files, repo_root)
    if prose:
        if explain:
            print("==> prose-only python edits (comments/docstrings) "
                  "excluded from selection:")
            for path in sorted(prose):
                print(f"      - {path}")
        snapshot = snapshot.excluding(prose)
    return classify(snapshot, layout)


def resolve_for_package(pkg, repo_root: Path, *,
                        explicit_paths: list[str] | None = None,
                        explain: bool = False):
    """The package's targeted selection: "full", "none", or
    a SelectionResult of repo-relative test files."""
    layout = _layout(pkg, repo_root)
    changes = _changeset(pkg, repo_root, explicit_paths, explain)
    if not changes.has_changes:
        if explain:
            print(f"==> {pkg.name}: no changes")
        return "none"
    if changes.docs_only:
        if explain:
            print(f"==> {pkg.name}: documentation/prose only; "
                  "no tests selected")
        return "none"
    if changes.touches_trigger:
        if explain:
            print(f"==> {pkg.name}: a full-suite trigger "
                  "changed; running the whole suite")
        return "full"
    cfg = pkg.decl.get("targeting", {})
    prefix = layout.root + "/"
    import_roots = [
        (pkg.root / r).resolve()
        for r in cfg.get("import_roots", ["."])]
    scan_dirs = [
        (pkg.root / r).resolve()
        for r in cfg.get("scan_dirs", cfg.get("import_roots", ["."]))]
    graph = LineageGraph(repo_root, import_roots, scan_dirs)
    graph.sync_files()
    test_prefixes = tuple(
        prefix + d.strip("/") + "/" for d in layout.test_dirs)
    mirror_dirs = [pkg.root / d for d in layout.test_dirs]
    result = graph.resolve_tests(
        changed_sources=tuple(prefix + p for p in changes.sources),
        changed_tests=tuple(prefix + p for p in changes.tests),
        changed_conftests=tuple(
            prefix + p for p in changes.conftests),
        test_prefixes=test_prefixes,
        mirror_dirs=mirror_dirs)
    if explain:
        print(f"==> {pkg.name}: lineage & test selection:")
        print(f"    changed sources   ({len(changes.sources)}): "
              f"{list(changes.sources)}")
        print(f"    changed tests     ({len(changes.tests)}): "
              f"{list(changes.tests)}")
        print(f"    changed conftests ({len(changes.conftests)}): "
              f"{list(changes.conftests)}")
        print(f"    resolved test targets ({len(result.test_files)}):")
        for test_path in result.test_files:
            reasons = ", ".join(result.reasons.get(test_path, []))
            print(f"      - {test_path} (via {reasons})")
    return result
