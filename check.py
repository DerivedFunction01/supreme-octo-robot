#!/usr/bin/env python3
"""Root validation gate: the one gate for the mega repo
(plan §4.16).

Every package declares its gate as data (gate.json beside
its code; the app frontends in pipeline/gate/frontends.json
as served-by declarations). The shared legs — line cap,
portability/denylist, ruff, policy scanners, test
isolation, AST-targeted tests — live once, in
pipeline/gate. This file composes them:

  python3 check.py                     # union gate: every pipeline
                                       # package's full declared legs
  python3 check.py scheduling          # one package's full gate
  python3 check.py scheduling dispatch # several packages
  python3 check.py <path> [...]        # pathspec: affected packages,
                                       # test legs AST-targeted to
                                       # the named paths
  python3 check.py --test              # test legs only, AST-targeted
                                       # from the working tree
  python3 check.py --fast              # all legs except test legs
  python3 check.py --scan              # portability + scanner legs only
  python3 check.py --fix               # apply ruff fixes (declared
                                       # ruff legs only), then exit
  python3 check.py --explain           # print test-targeting decisions
  python3 check.py --frontends         # include the app frontends'
                                       # served-by legs in a union run
  python3 check.py --legs linecap,portability [--] <package>
                                       # diagnostic: run only the named
                                       # legs, no fail-fast

Every run also executes the repo-scoped folder census
(gate.foldercensus) once and prints it: folders at/over
the warn threshold, family declarations exempt from
warn/fail but always reported. It enters the summary as
the repo-census row. A --legs filter that does not name
foldercensus suppresses it. Beside it, the repo-scoped
root portability coverage (gate.runner's rootportability
leg) scans every tracked file no package's portability
leg covers, so the whole tracked tree is scanned exactly
once; it enters the summary as the repo-portability row,
and a --legs filter that does not name rootportability
suppresses it.

Parallelism (owner ruling 2026-11-13: tests always run
parallel): a multi-package run executes the independent
package gates concurrently — one child process per
package, outputs replayed in selection order — with the
pool sized by the gate's worker derivation
(gate.runner.derive_workers: GATE_WORKERS env, else 2 on
this machine). Suites shard inside each package (see
gate.runner). Diagnostic (--legs), --fix, a single
package, or GATE_SERIAL=1 keep the serial in-process
path. --child is the internal worker form: one package,
no census, no summary.

Exit: 0 = every gated package green; 1 = a package is red
(the summary names it); 2 = usage error.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "pipeline"))

from gate import runner  # noqa: E402
from gate.targeting import resolve as targeting  # noqa: E402


def _print_header(pkg) -> None:
    rel = pkg.root.relative_to(REPO_ROOT).as_posix()
    print(f"\n##### package: {pkg.name} ({rel})")


def _run_full(pkg, args) -> bool:
    _print_header(pkg)
    result = runner.run_package(
        pkg, repo_root=REPO_ROOT,
        legs_filter=args.legs.split(",") if args.legs else None,
        skip_tests=args.fast, fix=args.fix)
    return result.ok


def _run_scanners(pkg) -> bool:
    _print_header(pkg)
    result = runner.run_package(
        pkg, repo_root=REPO_ROOT,
        legs_filter=list(runner.SCANNER_LEG_KINDS))
    return result.ok


def _run_targeted(pkg, args, explicit_paths=None) -> bool:
    _print_header(pkg)
    selection = targeting.resolve_for_package(
        pkg, REPO_ROOT, explicit_paths=explicit_paths,
        explain=args.explain)
    if selection == "none":
        print(f"==> {pkg.name}: no tests selected")
        return True
    targeted_files = (
        None if selection == "full" else list(selection.test_files))
    result = runner.run_package(
        pkg, repo_root=REPO_ROOT,
        legs_filter=list(runner.TEST_LEG_KINDS),
        targeted_files=targeted_files)
    return result.ok


def _run_pathspec(pkg, args, paths) -> bool:
    _print_header(pkg)
    selection = targeting.resolve_for_package(
        pkg, REPO_ROOT, explicit_paths=[str(Path(p)) for p in paths],
        explain=args.explain)
    if selection == "full":
        return runner.run_package(
            pkg, repo_root=REPO_ROOT,
            legs_filter=args.legs.split(",") if args.legs else None,
            skip_tests=args.fast).ok
    targeted_files = (
        [] if selection == "none" else list(selection.test_files))
    return runner.run_package(
        pkg, repo_root=REPO_ROOT,
        legs_filter=args.legs.split(",") if args.legs else None,
        skip_tests=args.fast,
        targeted_files=targeted_files).ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true",
                        help="with a pathspec or --test: full "
                             "suites instead of AST-targeted")
    parser.add_argument("--fast", action="store_true",
                        help="all legs except test legs")
    parser.add_argument("--scan", action="store_true",
                        help="portability + scanner legs only")
    parser.add_argument("--test", action="store_true",
                        help="test legs only, AST-targeted")
    parser.add_argument("--fix", action="store_true",
                        help="apply ruff fixes and exit")
    parser.add_argument("--explain", action="store_true",
                        help="print test-targeting decisions")
    parser.add_argument("--frontends", action="store_true",
                        help="include the app frontends in a "
                             "union run")
    parser.add_argument("--legs", metavar="A,B",
                        help="diagnostic: run only these leg "
                             "kinds/names, no fail-fast")
    parser.add_argument("--child", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("targets", nargs="*",
                        help="package names, or paths for a "
                             "pathspec run")
    args = parser.parse_args()

    packages = runner.load_packages(REPO_ROOT)
    by_name = {p.name: p for p in packages}
    frontend_names = {
        p.name for p in packages
        if p.source.name == "frontends.json"}

    names = [t for t in args.targets if t in by_name]
    paths = [t for t in args.targets if t not in by_name]
    for path in paths:
        if not (REPO_ROOT / path).exists():
            print(f"check: no such package or path: {path}",
                  file=sys.stderr)
            return 2

    verdicts: dict[str, bool] = {}

    def gate(pkg) -> None:
        if args.scan:
            ok = _run_scanners(pkg)
        elif args.test and not args.all:
            ok = _run_targeted(
                pkg, args,
                explicit_paths=[str(Path(p)) for p in paths]
                if paths else None)
        elif paths and not args.all:
            ok = _run_pathspec(pkg, args, paths)
        elif args.legs:
            ok = _run_full(pkg, args)
        else:
            ok = _run_full(pkg, args)
        verdicts[pkg.name] = ok

    if names:
        selected = [by_name[n] for n in names]
    elif paths:
        selected = [
            p for p in packages
            if any(
                (REPO_ROOT / path).resolve().is_relative_to(
                    p.root.resolve())
                for path in paths)
        ]
        if not selected:
            print("check: no package contains the given paths",
                  file=sys.stderr)
            return 2
    else:
        selected = [
            p for p in packages
            if args.frontends or p.name not in frontend_names]

    if args.child:
        # The parallel parent's worker form: exactly the
        # named package, verdict as the exit code; census
        # and summary stay with the parent.
        for pkg in selected:
            gate(pkg)
        return 0 if all(verdicts.values()) else 1

    parallel = (
        len(selected) > 1 and not args.legs and not args.fix
        and os.environ.get("GATE_SERIAL") != "1")
    if parallel:
        # Across packages: independent gates, separate
        # child processes with separate state, run
        # concurrently; outputs replay in selection order
        # so the record reads exactly as the serial run's.
        mode_flags = [
            flag for flag, on in (
                ("--all", args.all), ("--fast", args.fast),
                ("--scan", args.scan), ("--test", args.test),
                ("--explain", args.explain),
                ("--frontends", args.frontends)) if on]

        def run_child(pkg):
            argv = [sys.executable, str(Path(__file__).resolve()),
                    "--child", *mode_flags, pkg.name, *paths]
            proc = subprocess.run(
                argv, cwd=REPO_ROOT, check=False,
                capture_output=True, text=True)
            return pkg.name, proc

        pool_size = min(runner.derive_workers(), len(selected))
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=pool_size) as pool:
            results = list(pool.map(run_child, selected))
        for name, proc in results:
            sys.stdout.write(proc.stdout)
            if proc.stderr:
                sys.stderr.write(proc.stderr)
            verdicts[name] = proc.returncode == 0
    else:
        for pkg in selected:
            gate(pkg)

    if not args.legs or "foldercensus" in args.legs.split(","):
        print("\n##### repo (folder census)")
        outcome = runner.run_folder_census(REPO_ROOT, packages)
        verdicts["repo-census"] = outcome.ok

    if not args.legs or "rootportability" in args.legs.split(","):
        print("\n##### repo (root portability coverage)")
        outcome = runner.run_root_portability(REPO_ROOT, packages)
        verdicts["repo-portability"] = outcome.ok

    print("\n== gate summary")
    for name, ok in verdicts.items():
        print(f"{name:<16} {'green' if ok else 'RED'}")
    red = [n for n, ok in verdicts.items() if not ok]
    if red:
        print(f"check: RED — {', '.join(red)}")
        return 1
    print("check: green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
