"""AST-based static import lineage analyzer and targeted
test resolver. Ported from the source reference
(foundation/checks/lineage.py); see the package docstring
for the generalization notes. Two adaptations are
deliberate and load-bearing here:

- A file carries one module name per import root that
  contains it (the mega repo's packages import through
  more than one root — the package root and the pipeline
  root — where the source house has exactly one tree).
- `from A import b` records both A and A.b. The source
  house's import style is leaf-module imports, so its
  graph never needs the expansion; this repo's houses
  write `from lib import registry` pervasively, and
  without the expansion a change to lib/registry.py would
  under-select — the one failure a gate must never have.
  The cost is over-selection when b is a symbol, never
  under-selection.
"""
from __future__ import annotations

import ast
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FileImportData:
    names: tuple[str, ...]
    imports: tuple[str, ...]


@dataclass(frozen=True)
class SelectionResult:
    test_files: tuple[str, ...]
    reasons: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_tests(self) -> bool:
        return bool(self.test_files)


def path_to_module(rel_path: str) -> str:
    """Convert a relative python file path to its canonical
    module dotted path."""
    p = Path(rel_path)
    parts = list(p.parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def resolve_relative_import(
    current_module: str, level: int, target_name: str | None
) -> str:
    """Canonicalize a relative import (level=1 is the
    importing file's own package, level=2 its parent)."""
    parts = current_module.split(".")
    if level > len(parts):
        return target_name or ""
    base_parts = parts[: len(parts) - level]
    if target_name:
        return ".".join((*base_parts, target_name))
    return ".".join(base_parts)


def _is_internal(dotted: str, top_levels: set[str]) -> bool:
    return bool(dotted) and dotted.split(".", 1)[0] in top_levels


def parse_file_imports(file_path: Path, names: tuple[str, ...],
                       top_levels: set[str]) -> tuple[str, ...]:
    """Parse a Python file with ast and extract its internal
    imports (absolute, plus relative imports resolved
    against each of the file's module names)."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ()

    discovered: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_internal(alias.name, top_levels):
                    discovered.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            modules: list[str] = []
            if node.level and node.level > 0:
                for name in names:
                    resolved = resolve_relative_import(
                        name, node.level, node.module)
                    if _is_internal(resolved, top_levels):
                        modules.append(resolved)
            elif node.module and _is_internal(node.module, top_levels):
                modules.append(node.module)
            for module in modules:
                discovered.add(module)
                for alias in node.names:
                    candidate = f"{module}.{alias.name}"
                    if _is_internal(candidate, top_levels):
                        discovered.add(candidate)
    return tuple(sorted(discovered))


class LineageGraph:
    """The static dependency graph between a repo's modules
    and its tests, rebuilt in memory per run."""

    def __init__(self, repo_root: Path, import_roots: list[Path],
                 scan_dirs: list[Path] | None = None):
        self.repo_root = Path(repo_root)
        self.import_roots = [Path(r) for r in import_roots]
        # Files enter the graph from the scan dirs; their
        # module names are computed against the import roots.
        # The two differ where a package imports a sibling
        # through the pipeline root but only that sibling's
        # tree belongs in its graph.
        self.scan_dirs = ([Path(d) for d in scan_dirs]
                          if scan_dirs is not None
                          else list(self.import_roots))
        self._entries: dict[str, FileImportData] = {}

    def _names_for(self, abs_path: Path) -> tuple[str, ...]:
        names = []
        for root in self.import_roots:
            try:
                rel = abs_path.relative_to(root)
            except ValueError:
                continue
            names.append(path_to_module(str(rel)))
        return tuple(dict.fromkeys(names))

    def sync_files(self) -> None:
        """Scan every .py file under the import roots and
        (re)build the graph."""
        files: dict[str, Path] = {}
        for root in self.scan_dirs:
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                try:
                    rel = str(path.relative_to(self.repo_root))
                except ValueError:
                    continue
                files[rel] = path
        names_by_rel = {
            rel: self._names_for(path) for rel, path in files.items()
        }
        top_levels = {
            name.split(".", 1)[0]
            for names in names_by_rel.values() for name in names if name
        }
        self._entries = {
            rel: FileImportData(
                names=names_by_rel[rel],
                imports=parse_file_imports(
                    path, names_by_rel[rel], top_levels),
            )
            for rel, path in files.items()
        }

    def build_reverse_map(self) -> dict[str, set[str]]:
        """Imported dotted name -> the files that import it."""
        reverse: dict[str, set[str]] = defaultdict(set)
        for rel_path, data in self._entries.items():
            for imported in data.imports:
                reverse[imported].add(rel_path)
        return reverse

    def _mirror_tests(self, source_rel: str,
                      mirror_dirs: list[Path]) -> list[str]:
        p = Path(source_rel)
        if p.name == "__init__.py" or not p.name.endswith(".py"):
            return []
        wanted = f"test_{p.name}"
        found = []
        for directory in mirror_dirs:
            if not directory.is_dir():
                continue
            for candidate in directory.rglob(wanted):
                try:
                    found.append(
                        str(candidate.relative_to(self.repo_root)))
                except ValueError:
                    continue
        return sorted(found)

    def resolve_tests(
        self,
        changed_sources: tuple[str, ...],
        changed_tests: tuple[str, ...],
        changed_conftests: tuple[str, ...],
        *,
        test_prefixes: tuple[str, ...],
        mirror_dirs: list[Path],
    ) -> SelectionResult:
        """Resolve all affected test files via direct edits,
        conftest scoping, name mirrors, and reverse AST
        traversal. All paths are repo-relative; a test file
        is one under a test prefix whose name matches the
        unittest discovery pattern (test*.py)."""

        def is_test_file(rel: str) -> bool:
            name = Path(rel).name
            return (rel.startswith(test_prefixes)
                    and name.startswith("test")
                    and name.endswith(".py"))

        selected: set[str] = set()
        reasons: dict[str, list[str]] = defaultdict(list)

        for t in changed_tests:
            if (self.repo_root / t).is_file():
                selected.add(t)
                reasons[t].append("direct_test_edit")

        for s in changed_sources:
            for mirror in self._mirror_tests(s, mirror_dirs):
                selected.add(mirror)
                reasons[mirror].append(f"mirror_of:{s}")

        for c in changed_conftests:
            c_dir = (self.repo_root / c).parent
            if c_dir.is_dir():
                for t_file in c_dir.rglob("test_*.py"):
                    rel_t = str(t_file.relative_to(self.repo_root))
                    if is_test_file(rel_t):
                        selected.add(rel_t)
                        reasons[rel_t].append(f"scoped_conftest:{c}")

        reverse_map = self.build_reverse_map()
        queue: deque[str] = deque()
        visited: set[str] = set()
        for s in changed_sources:
            entry = self._entries.get(s)
            if entry:
                for name in entry.names:
                    queue.append(name)
                    visited.add(name)
            queue.append(s)
            visited.add(s)

        while queue:
            current = queue.popleft()
            for dep in reverse_map.get(current, set()):
                if dep in visited:
                    continue
                visited.add(dep)
                if is_test_file(dep):
                    selected.add(dep)
                    reasons[dep].append(
                        f"transitive_dependency_of:{current}")
                else:
                    queue.append(dep)
                    dep_entry = self._entries.get(dep)
                    if dep_entry:
                        queue.extend(dep_entry.names)

        return SelectionResult(
            test_files=tuple(sorted(selected)),
            reasons=dict(reasons),
        )
