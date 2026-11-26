#!/usr/bin/env python3
"""Gate runner: loads per-package declarations and composes
the shared legs into a package gate (plan §4.16).

A declaration is data (gate.json beside the package's
code), never a script. It names the package's interpreter,
its targeting layout, and its legs in order. Leg kinds:

- linecap      — the line-cap component (gate.linecap)
- portability  — the portability/denylist component
                 (gate.portability); fail_on_denylist is
                 "auto" (fail exactly when a denylist is
                 provisioned — the retired check.sh rule),
                 true, or false
- importisolation — the import-isolation component
                 (gate.importisolation): the package
                 imports nothing from sibling surfaces
                 (AC-14 invariant (a); not gate.isolation,
                 the test-isolation state hash)
- writeruniqueness — the writer-uniqueness component
                 (gate.writeruniqueness): one unified
                 writer (contract 15, §4.15) — no
                 truncate-write of a state-shaped path
                 and no duplicate staged-write
                 implementation outside
                 pipeline/platform/writer.py (AC-14
                 invariant (b), static half)
- dateuniqueness — the date-uniqueness component
                 (gate.dateuniqueness): one shared date
                 helper per intent per cluster — no
                 divergent parse / normalize / format /
                 epoch / now copy outside the homed
                 modules named in gate/date_families.json
- livingdates  — the living-dates component
                 (gate.livingdates): living documents
                 and code comments carry no dates.
                 Repo-scoped: its population is the whole
                 tracked tree, so it is declared once in
                 the gate package's declaration and the
                 dispatch scans from the repo root, never
                 a package root
- command      — a package's own leg, as argv data with
                 {python} / {root} substitution
- unittest     — a unittest suite (discover form); under
                 targeting it runs only the resolved test
                 modules instead of the whole suite
- isolation-unittest — a unittest suite wrapped in the
                 test-isolation state hash (gate.isolation)
- ruff-format / ruff-lint / scanners — the static legs
                 (gate.staticlegs)
- frontend     — a leg the app suites serve (declared,
                 not re-implemented): argv run in the app
                 directory when that package is gated
- foldercensus — the folder census (gate.foldercensus):
                 repo-scoped, not per-package. A package
                 declares it once as the composed gate's
                 config (warn/fail thresholds); the root
                 check executes it once per run against the
                 families every declaration names, so
                 run_package skips it (recorded as skipped)
- rootportability — the portability component over the
                 root coverage set (see root_coverage_files):
                 repo-scoped like the census. Declared once
                 in the gate package's declaration; the root
                 check executes it once per run, so
                 run_package skips it (recorded as skipped)
- repolinecap  — the line-cap component in its repo form
                 (gate.linecap.scan_repo): repo-scoped like
                 the census. The gate package's declaration
                 carries its cap/band values as config; the
                 root check executes it once per run over
                 every tracked code file in the tree —
                 coverage is by default, never declared per
                 package, so run_package skips it (recorded
                 as skipped). The per-package linecap kind
                 survives only as the component's CLI form;
                 no package declares it.
- repowriteruniqueness — the writer-uniqueness component
                 in its repo form (gate.writeruniqueness):
                 repo-scoped like the census. The gate
                 package's declaration carries the recorded
                 exceptions as data; the root check executes
                 it once per run over every tracked Python
                 source in the tree — coverage is by
                 default, never declared per package, so
                 run_package skips it (recorded as skipped).
                 The per-package writeruniqueness kind is
                 retired.
- repoargvidioms — the argv-idioms component in its
                 repo form (gate.argvidioms): repo-scoped
                 like the census. The gate package's
                 declaration carries the recorded
                 exceptions as data; the root check
                 executes it once per run over every
                 tracked source in the tree — coverage is
                 by default, never declared per package,
                 so run_package skips it (recorded as
                 skipped).
- repoimportisolation — the import-isolation component
                 in its repo form (gate.importisolation):
                 the invariant is per-package by nature, so
                 the root check runs the component for every
                 composed pipeline package automatically —
                 the population derives from the tree's
                 package set, never from a declaration. The
                 gate package's declaration carries the
                 recorded exceptions (repo-relative paths);
                 run_package skips the config declaration
                 (recorded as skipped). The per-package
                 importisolation kind is retired.
- reposcanners — the scanner-runner leg in its repo form
                 (gate.staticlegs.scanners): a pipeline
                 package carrying a scanners.py module at
                 its root (the runner contract: run_all
                 (root)) is run automatically — discovery is
                 tree-derived, never declared. Declared once
                 in the gate package as the composed gate's
                 config; run_package skips it (recorded as
                 skipped).

Execution runs every declared leg, in declared order,
and each leg verdicts independently: a red leg never
leaves later legs unverdicted. (The fail-fast form this
replaced — the retired check files' own semantics —
aborted the package at its first red leg; a composed
re-gate showed the cost:
attention's ruff-format failure left its ruff-lint and
suite legs unrun, and the platform suite verdicted
only through the formation's leg-1D diagnostic patch.)
The package verdict is the conjunction of its legs'
verdicts. An explicit leg filter is diagnostic in
selection only — it narrows which legs run, never how
they verdict.

Parallelism (tests always run parallel — parallelism
is what catches flaky tests):
package gates compose concurrently at the root check,
and a unittest suite with enough modules shards across
worker processes. The worker count is derived, never a
bare constant at a call site (see derive_workers). A
test that fails under parallel execution is reported
by name as a parallel failure — never retried into
green inside the gate, never silently quarantined.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import foldercensus, isolation, linecap, pathdiscipline
from . import importisolation, portability, staticlegs
from . import dateuniqueness, livingdates, writeruniqueness

TEST_LEG_KINDS = ("unittest", "isolation-unittest")
SCANNER_LEG_KINDS = ("portability", "scanners", "livingdates")
INTERPRETER_LEG_KINDS = (
    "command", "unittest", "isolation-unittest",
    "ruff-format", "ruff-lint", "scanners")


@dataclass
class Package:
    name: str
    root: Path               # absolute package root
    decl: dict
    source: Path             # the gate.json it came from

    def python(self) -> str:
        spec = self.decl.get("python", "system")
        if isinstance(spec, dict) and "venv" in spec:
            venv = Path(spec["venv"])
            if not venv.is_absolute():
                venv = self.root / venv
            return str(venv / "bin" / "python")
        return sys.executable if spec == "system" else str(spec)


@dataclass
class LegOutcome:
    name: str
    ok: bool
    code: int


@dataclass
class PackageResult:
    package: str
    ok: bool
    outcomes: list[LegOutcome] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def load_packages(repo_root: Path) -> list[Package]:
    """Every declaration in the repo: pipeline/*/gate.json,
    plus the gate package's frontend declarations."""
    packages: list[Package] = []
    pipeline = repo_root / "pipeline"
    for gate_json in sorted(pipeline.glob("*/gate.json")):
        decl = json.loads(gate_json.read_text(encoding="utf-8"))
        packages.append(Package(
            name=decl["package"], root=gate_json.parent,
            decl=decl, source=gate_json))
    frontends = pipeline / "gate" / "frontends.json"
    if frontends.is_file():
        for decl in json.loads(
                frontends.read_text(encoding="utf-8"))["packages"]:
            root = repo_root / decl["root"]
            packages.append(Package(
                name=decl["package"], root=root, decl=decl,
                source=frontends))
    return packages


def load_families(packages: list[Package]) -> list[dict]:
    """Every folder-family declaration in the repo, from
    every package's gate.json: structural facts about the
    tree, aggregated regardless of which packages a run
    selected."""
    families: list[dict] = []
    for pkg in packages:
        families.extend(pkg.decl.get("families", []))
    return families


def census_config(packages: list[Package]) -> tuple[int, int]:
    """(warn, fail) from the composed gate's foldercensus
    leg declaration; the component defaults otherwise."""
    for pkg in packages:
        for leg in pkg.decl.get("legs", []):
            if leg.get("leg") == "foldercensus":
                return (int(leg.get("warn", foldercensus.DEFAULT_WARN)),
                        int(leg.get("fail", foldercensus.DEFAULT_FAIL)))
    return foldercensus.DEFAULT_WARN, foldercensus.DEFAULT_FAIL


def root_coverage_files(repo_root: Path,
                        packages: list[Package]) -> list[str]:
    """The root coverage set: every tracked scannable file
    no package's portability leg scans. A package's
    portability leg scans its own root tree, so the covered
    trees are exactly the roots of the packages that
    declare one; the root set is the tracked tree minus
    those roots. The two sets are disjoint by construction
    and their union is the whole tracked tree — the
    coverage invariant the composed gate holds: every
    tracked file is portability-scanned exactly once.
    (Before this leg, the trees outside pipeline/ —
    apps/, contracts/, docs/, the root files — sat in no
    package's scan root and no leg ever read them.)"""
    covered = []
    for pkg in packages:
        if any(leg.get("leg") == "portability"
               for leg in pkg.decl.get("legs", [])):
            covered.append(
                pkg.root.relative_to(repo_root).as_posix() + "/")
    return [
        relpath
        for relpath in portability._tracked_files(str(repo_root))
        if not any(relpath.startswith(prefix) for prefix in covered)
    ]


def _root_portability_fail_mode(packages: list[Package]) -> str:
    """The declaring leg's fail_on_denylist, census-config
    style; "auto" when undeclared."""
    for pkg in packages:
        for leg in pkg.decl.get("legs", []):
            if leg.get("leg") == "rootportability":
                return leg.get("fail_on_denylist", "auto")
    return "auto"


def run_root_portability(repo_root: Path,
                         packages: list[Package]) -> LegOutcome:
    """The repo-scoped root portability leg: the shared
    component (gate.portability) over the root coverage
    set, printed in the component's own forms. The
    denylist leg carries the declaration's
    fail_on_denylist with the same auto semantics as a
    package leg — provisioned resolves against the repo
    root (env first, else state/denylist.txt under it)."""
    files = root_coverage_files(repo_root, packages)
    findings = portability.scan_generic(str(repo_root), files)
    for rule, relpath, lineno in findings:
        print(f"{rule}: {relpath}:{lineno} (content withheld)")
    fail_mode = _root_portability_fail_mode(packages)
    fail_on = (portability.denylist_provisioned(str(repo_root))
               if fail_mode == "auto" else bool(fail_mode))
    denylist_findings, notice, provisioned = portability.scan_denylist(
        str(repo_root), files)
    if notice:
        print(notice)
    if provisioned:
        for rule, relpath, lineno in denylist_findings:
            print(f"{rule}: {relpath}:{lineno} (content withheld)")
        print(f"denylist: {len(denylist_findings)} finding(s)"
              + ("" if fail_on else " (advisory)"))
    if not findings:
        print(f"portability: ok ({len(files)} files scanned)")
    ok = not findings and not (fail_on and denylist_findings)
    return LegOutcome(
        name="root portability coverage", ok=ok,
        code=0 if ok else 1)


from .repolegs import (  # noqa: F401 — re-exported for check.py
    linecap_config, repo_leg_config, run_folder_census,
    run_repo_argvidioms, run_repo_importisolation,
    run_repo_linecap, run_repo_scanners,
    run_repo_writeruniqueness)


def _run_argv(argv: list[str], cwd: Path) -> int:
    print(f"==> {' '.join(argv)}")
    return subprocess.run(argv, cwd=cwd, check=False).returncode


def _missing_interpreter(pkg: Package) -> str | None:
    """The bare-clone interpreter guard: a package whose
    declaration names an interpreter path (the venv form)
    that is not built would otherwise die inside
    subprocess with a FileNotFoundError traceback. The
    original gate's form instead: print the instruction
    naming the package's init step and fail the leg
    (exit 2 there; a failed leg here). Returns the message
    to print, or None when the interpreter stands. A bare
    command name (PATH-resolved) names no path and is not
    guarded."""
    python = pkg.python()
    if "/" not in python or os.path.isfile(python):
        return None
    init = pkg.root / "init_venv.py"
    if init.is_file():
        step = f"python3 init_venv.py (from {pkg.root})"
    else:
        step = f"provision the declared interpreter at {python}"
    return (f"interpreter not built: {python} "
            f"(package {pkg.name})\nrun: {step}")


def _unittest_argv(python: str, leg: dict, targeted_modules):
    if targeted_modules is not None:
        return [python, "-m", "unittest", *targeted_modules]
    return [python, "-m", "unittest", "discover",
            "-s", leg.get("start", "tests"),
            "-t", leg.get("top", ".")]


def _module_name(test_file: Path, top_abs: Path) -> str:
    rel = test_file.relative_to(top_abs)
    parts = list(rel.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


# --- parallelism -------------------------------------------------

DEFAULT_WORKERS = 2
WORKERS_ENV = "GATE_WORKERS"


def derive_workers(decl: dict | None = None,
                   leg: dict | None = None) -> int:
    """The worker count for parallel test execution,
    derived — never a bare constant at a call site.
    Precedence: the GATE_WORKERS environment override,
    the leg's own "workers", the package declaration's
    "workers", then the default for this machine (2 —
    the calibration for this box; a bigger venue
    declares in its gate.json or exports the env)."""
    raw = os.environ.get(WORKERS_ENV)
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    for source in (leg, decl):
        if source and "workers" in source:
            try:
                return max(1, int(source["workers"]))
            except (TypeError, ValueError):
                pass
    return DEFAULT_WORKERS


def shard_modules(modules: list[str],
                  workers: int) -> list[list[str]]:
    """Deal modules round-robin into at most `workers`
    shards: disjoint, complete, sizes within one."""
    count = max(1, min(workers, len(modules)))
    shards: list[list[str]] = [[] for _ in range(count)]
    for i, mod in enumerate(modules):
        shards[i % count].append(mod)
    return shards


_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)
_FAIL_RE = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)


def parse_shard_output(text: str) -> tuple[int, list[str]]:
    """(tests run, failing test names) from one shard's
    unittest output — progress and the summary ride
    stderr; the names are the FAIL:/ERROR: headers."""
    ran = sum(int(m.group(1)) for m in _RAN_RE.finditer(text))
    names = [f"{kind}: {name} ({where})"
             for kind, name, where in _FAIL_RE.findall(text)]
    return ran, names


def _run_unittest_sharded(python: str, modules: list[str],
                          workers: int, cwd: Path,
                          path_root: Path | None = None) -> int:
    """Run the suite as concurrent shard processes, each
    its own `python -m unittest <modules>`, then aggregate
    counts and verdicts. Shards share nothing but the
    working directory's read surface; each is a separate
    process with separate state. `path_root` (the leg's
    top dir) rides PYTHONPATH so module names resolve
    exactly as discover's sys.path insertion resolves
    them, while the working directory stays the serial
    run's. Failures are reported by name as parallel
    failures (the flake policy): no retry, no quarantine,
    inside the gate."""
    shards = shard_modules(modules, workers)
    print(f"==> parallel unittest: {len(modules)} module(s) "
          f"in {len(shards)} shard(s)")
    env = None
    if path_root is not None:
        env = dict(os.environ)
        prior = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(path_root) + (
            os.pathsep + prior if prior else "")

    def run_one(indexed):
        index, shard = indexed
        proc = subprocess.run(
            [python, "-m", "unittest", *shard],
            cwd=cwd, check=False, capture_output=True,
            text=True, env=env)
        return index, shard, proc

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(shards)) as pool:
        results = list(pool.map(run_one, enumerate(shards)))

    total = 0
    failures: list[str] = []
    bad = False
    for index, shard, proc in results:
        print(f"--> shard {index + 1}/{len(shards)} "
              f"({len(shard)} module(s), exit "
              f"{proc.returncode})")
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="")
        ran, names = parse_shard_output(
            (proc.stdout or "") + (proc.stderr or ""))
        total += ran
        failures.extend(names)
        if proc.returncode != 0 or ran == 0:
            bad = True
    print(f"==> parallel suite total: {total} test(s) across "
          f"{len(shards)} shard(s)")
    if failures:
        print("PARALLEL FAILURES — tests that failed under "
              "parallel execution, named (never retried "
              "into green, never quarantined):")
        for name in failures:
            print(f"  {name}")
    return 1 if (bad or failures) else 0


def _discover_modules(pkg: Package, leg: dict) -> list[str]:
    """The full suite's test modules in discover's own
    form: files matching test*.py under the leg's start
    dir, named against the leg's top dir."""
    top_abs = (pkg.root / leg.get("top", ".")).resolve()
    start_abs = (pkg.root / leg.get("start", "tests")).resolve()
    return [
        _module_name(path, top_abs)
        for path in sorted(start_abs.rglob("test*.py"))
    ]


def _run_unittest(pkg: Package, leg: dict, targeted_files,
                  repo_root: Path) -> int:
    python = pkg.python()
    top_abs = (pkg.root / leg.get("top", ".")).resolve()
    if targeted_files is not None:
        if not targeted_files:
            print("==> no tests affected by the changes")
            return 0
        modules = [
            _module_name(repo_root / f, top_abs)
            for f in targeted_files
        ]
        workers = derive_workers(pkg.decl, leg)
        if workers > 1 and len(modules) > workers:
            print(f"==> targeted unittest "
                  f"({len(modules)} module(s))")
            return _run_unittest_sharded(
                python, modules, workers, top_abs)
        print(f"==> targeted unittest ({len(modules)} module(s))")
        return _run_argv(
            _unittest_argv(python, leg, modules), top_abs)
    workers = derive_workers(pkg.decl, leg)
    if workers > 1:
        modules = _discover_modules(pkg, leg)
        if len(modules) > workers:
            return _run_unittest_sharded(
                python, modules, workers, pkg.root,
                path_root=top_abs)
    return _run_argv(_unittest_argv(python, leg, None), pkg.root)


def run_leg(pkg: Package, leg: dict, *, repo_root: Path,
            targeted_files=None, fix: bool = False) -> LegOutcome:
    kind = leg["leg"]
    name = leg.get("name", kind)
    print(f"== {name}")
    if kind in INTERPRETER_LEG_KINDS:
        missing = _missing_interpreter(pkg)
        if missing is not None:
            print(missing)
            return LegOutcome(name=name, ok=False, code=2)
    if kind == "linecap":
        cap = int(leg.get("cap", linecap.DEFAULT_CAP))
        band = int(leg.get("band", linecap.DEFAULT_BAND))
        result = linecap.scan(str(pkg.root), cap=cap, band=band)
        for line in linecap.render(result, cap, band):
            print(line)
        code = 1 if (result.findings or result.growth) else 0
    elif kind == "portability":
        fail_mode = leg.get("fail_on_denylist", "auto")
        fail_on = (portability.denylist_provisioned(str(pkg.root))
                   if fail_mode == "auto" else bool(fail_mode))
        argv = ["--root", str(pkg.root)]
        if fail_on:
            argv.append("--fail-on-denylist")
        code = portability.main(argv)
    elif kind == "importisolation":
        siblings = [
            other.name for other in load_packages(repo_root)
            if other.name != pkg.name
        ]
        findings, scanned = importisolation.scan(
            pkg.root, repo_root, siblings)
        for line in importisolation.render(findings, scanned):
            print(line)
        code = 1 if findings else 0
    elif kind == "writeruniqueness":
        rows, failures, scanned = writeruniqueness.scan(
            pkg.root, repo_root,
            exceptions=leg.get("exceptions", []))
        for line in writeruniqueness.render(
                rows, failures, scanned):
            print(line)
        code = 1 if failures else 0
    elif kind == "dateuniqueness":
        rows, failures, scanned = dateuniqueness.scan(
            pkg.root, repo_root,
            exceptions=leg.get("exceptions", []))
        for line in dateuniqueness.render(
                rows, failures, scanned):
            print(line)
        code = 1 if failures else 0
    elif kind == "livingdates":
        rows, failures, scanned = livingdates.scan(repo_root)
        for line in livingdates.render(rows, failures, scanned):
            print(line)
        code = 1 if failures else 0
    elif kind == "command":
        argv = [
            item.replace("{python}", pkg.python())
                .replace("{root}", str(pkg.root))
            for item in leg["argv"]
        ]
        code = _run_argv(argv, pkg.root)
    elif kind == "pathdiscipline":
        rows, failures = pathdiscipline.scan(
            pkg.root, repo_root,
            exceptions=leg.get("exceptions", []),
            exclude=leg.get("exclude", []))
        for line in pathdiscipline.render(rows, failures):
            print(line)
        code = 1 if failures else 0
    elif kind == "unittest":
        code = _run_unittest(pkg, leg, targeted_files, repo_root)
    elif kind == "isolation-unittest":
        state = leg.get("state", {})
        guard = isolation.IsolationGuard(
            str(pkg.root), state.get("subpaths", []),
            state.get("exclude_first", []))
        with guard:
            code = _run_unittest(pkg, leg, targeted_files, repo_root)
        code = code or guard.report()
    elif kind == "ruff-format":
        code = staticlegs.ruff_format(
            str(pkg.root), leg["targets"], pkg.python(), fix=fix)
    elif kind == "ruff-lint":
        code = staticlegs.ruff_lint(
            str(pkg.root), leg["targets"], pkg.python(), fix=fix)
    elif kind == "scanners":
        code = staticlegs.scanners(
            str(pkg.root), leg["module"],
            leg.get("function", "run_all"), leg.get("args", "root"),
            python=pkg.python())
    elif kind == "frontend":
        argv = [
            item.replace("{root}", str(pkg.root))
            for item in leg["argv"]
        ]
        code = _run_argv(argv, pkg.root)
    else:
        print(f"unknown leg kind: {kind}", file=sys.stderr)
        code = 2
    return LegOutcome(name=name, ok=code == 0, code=code)


def run_package(pkg: Package, *, repo_root: Path,
                legs_filter: list[str] | None = None,
                skip_tests: bool = False, fix: bool = False,
                targeted_files=None) -> PackageResult:
    """Compose the package's declared legs. targeted_files,
    when not None, is the AST-resolved test set for its
    test legs (repo-relative paths); an empty list means
    the changes touch no test in this package."""
    result = PackageResult(package=pkg.name, ok=True)
    diagnostic = legs_filter is not None
    for leg in pkg.decl.get("legs", []):
        kind = leg["leg"]
        name = leg.get("name", kind)
        if kind in ("foldercensus", "rootportability", "repolinecap",
                    "repowriteruniqueness", "repoimportisolation",
                    "reposcanners"):
            # Repo-scoped: executed once per run by the
            # root check, never per package.
            result.skipped.append(name)
            continue
        if diagnostic and kind not in legs_filter \
                and name not in legs_filter:
            result.skipped.append(name)
            continue
        if skip_tests and kind in TEST_LEG_KINDS:
            result.skipped.append(name)
            continue
        outcome = run_leg(
            pkg, leg, repo_root=repo_root,
            targeted_files=targeted_files, fix=fix)
        result.outcomes.append(outcome)
        print(f"-- {'PASS' if outcome.ok else 'FAIL'}: {outcome.name}")
        if not outcome.ok:
            result.ok = False
    return result
