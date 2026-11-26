"""Repo-scoped gate legs: the line cap, writer
uniqueness, import isolation, and scanner runners in
their repo forms, plus the folder census — each runs
over the whole tracked tree by default, from the gate
package's recorded declarations. runner re-exports
these names; check.py calls them through runner.
"""

from __future__ import annotations

from pathlib import Path

from . import argvidioms, foldercensus, importisolation, linecap
from . import staticlegs, writeruniqueness
from .runner import LegOutcome, Package, census_config, load_families


def linecap_config(packages: list[Package]) -> tuple[int, int]:
    """(cap, band) from the composed gate's repolinecap
    leg declaration; the component defaults otherwise.
    The declaration carries values only — coverage is the
    whole tracked tree by default and is never declared."""
    for pkg in packages:
        for leg in pkg.decl.get("legs", []):
            if leg.get("leg") == "repolinecap":
                return (int(leg.get("cap", linecap.DEFAULT_CAP)),
                        int(leg.get("band", linecap.DEFAULT_BAND)))
    return linecap.DEFAULT_CAP, linecap.DEFAULT_BAND


def run_repo_linecap(repo_root: Path,
                     packages: list[Package]) -> LegOutcome:
    """The repo-scoped line-cap leg: every tracked code
    file in the tree counts by default; fails on a file
    over the cap or a band file grown past its committed
    count."""
    cap, band = linecap_config(packages)
    result = linecap.scan_repo(repo_root, cap, band)
    print(f"== repo line cap (tracked code files; cap {cap}, "
          f"band {band})")
    for line in linecap.render(result, cap, band):
        print(line)
    ok = not result.findings and not result.growth
    return LegOutcome(
        name="repo line cap", ok=ok, code=0 if ok else 1)


def repo_leg_config(packages: list[Package], kind: str) -> dict:
    """The gate package's repo leg declaration of the given
    kind, or {} — a repo leg's recorded exceptions and
    values live there as data; coverage is never declared."""
    for pkg in packages:
        for leg in pkg.decl.get("legs", []):
            if leg.get("leg") == kind:
                return leg
    return {}


def run_repo_writeruniqueness(repo_root: Path,
                              packages: list[Package]) -> LegOutcome:
    """The repo-scoped writer-uniqueness leg: the shared
    component over every tracked Python source in the
    tree, by default; fails on an undeclared bypass of the
    unified writer or a stale recorded exception."""
    exceptions = repo_leg_config(
        packages, "repowriteruniqueness").get("exceptions", [])
    rows, failures, scanned = writeruniqueness.scan(
        repo_root, repo_root, exceptions, tracked=True)
    for line in writeruniqueness.render(rows, failures, scanned):
        print(line)
    return LegOutcome(
        name="repo writer uniqueness", ok=not failures,
        code=0 if not failures else 1)


def run_repo_argvidioms(repo_root: Path,
                        packages: list[Package]) -> LegOutcome:
    """The repo-scoped argv-idioms leg: the shared
    component over every tracked source in the tree, by
    default; fails on a hand-rolled argument-parsing
    idiom outside the unified argv implementations, the
    census's unmigrated entries, and the recorded
    exceptions, or on a stale recorded exception."""
    exceptions = repo_leg_config(
        packages, "repoargvidioms").get("exceptions", [])
    rows, failures, scanned = argvidioms.scan(
        repo_root, repo_root, exceptions, tracked=True)
    for line in argvidioms.render(rows, failures, scanned):
        print(line)
    return LegOutcome(
        name="repo argv idioms", ok=not failures,
        code=0 if not failures else 1)


def run_repo_importisolation(repo_root: Path,
                             packages: list[Package]) -> LegOutcome:
    """The repo-scoped import-isolation leg: the shared
    component run for every composed pipeline package
    automatically; fails on an undeclared sibling import
    or a stale recorded exception."""
    composed = [pkg for pkg in packages
                if pkg.source.name == "gate.json"]
    names = [pkg.name for pkg in composed]
    exceptions = repo_leg_config(
        packages, "repoimportisolation").get("exceptions", [])
    code = 0
    total = 0
    for pkg in composed:
        siblings = [name for name in names if name != pkg.name]
        prefix = pkg.root.relative_to(repo_root).as_posix() + "/"
        pkg_exceptions = [
            {**decl, "path": decl["path"][len(prefix):]}
            for decl in exceptions
            if decl.get("path", "").startswith(prefix)
        ]
        findings, scanned = importisolation.scan(
            pkg.root, repo_root, siblings,
            exceptions=pkg_exceptions)
        total += scanned
        if findings or getattr(findings, "notes", ()):
            for line in importisolation.render(findings, scanned):
                print(line)
        if findings:
            code = 1
    print(f"import-isolation: repo population {len(composed)} "
          f"packages, {total} files scanned")
    return LegOutcome(
        name="repo import isolation", ok=code == 0, code=code)


def run_repo_scanners(repo_root: Path,
                      packages: list[Package]) -> LegOutcome:
    """The repo-scoped scanner-runner leg: every pipeline
    package carrying a scanners.py module at its root is
    run automatically (the staticlegs.scanners contract);
    the population is printed either way, so an empty
    population is a stated fact, not a silent skip."""
    discovered = [
        pkg for pkg in packages
        if pkg.source.name == "gate.json"
        and (pkg.root / "scanners.py").is_file()
    ]
    code = 0
    for pkg in discovered:
        print(f"-- scanner runner discovered: {pkg.name} "
              f"(scanners.py)")
        rc = staticlegs.scanners(
            str(pkg.root), "scanners", python=pkg.python())
        if rc != 0:
            code = 1
    print(f"repo-scanners: {len(discovered)} scanner runner(s) "
          f"discovered"
          + (": " + ", ".join(pkg.name for pkg in discovered)
             if discovered else ""))
    return LegOutcome(
        name="repo scanner runners", ok=code == 0, code=code)


def run_folder_census(repo_root: Path,
                      packages: list[Package]) -> LegOutcome:
    """The repo-scoped census leg: prints on every run;
    fails on an undeclared folder at or over the fail
    threshold."""
    warn, fail = census_config(packages)
    rows, failures = foldercensus.scan(
        repo_root, load_families(packages), warn, fail)
    for line in foldercensus.render(rows, failures, warn, fail):
        print(line)
    return LegOutcome(
        name="folder census", ok=not failures,
        code=0 if not failures else 1)
