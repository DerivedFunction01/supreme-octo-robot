"""Drain detection and actuation (superapp supervision
plan, Step 4): a programme or bundle whose todos are all
terminal with nothing doing is drained. On the drained
transition the detector raises the programme's registry
tail set as fresh todos on the same bundle — each minted
once per drain through the one writer path
(lib/writes/bundles.create_todo) and stamped with the
drain that raised it — and archives the programme's
standing worktrees down to two (the main tree and the
most recently active extra) through the existing
archive/trim lifecycle (pipeline/scheduling/ops/
worktree_trim.sh), indiscriminately: the 1-hour archive
grace window is the only recovery path, so this module
builds no per-tree exception machinery of its own. The
one seam it rides is the trim's drain-act flag
(WORKTREE_TRIM_DRAIN_ACT): the trim's standing census
holds unlanded trees, but a drained transition is the
programme's own evidence that its trees' unlanded
commits are finished work, so the unlanded hold does
not stand for a drain pass; the trim's dirty, live, and
explicit holds still bind it.

A lane's progress checkpoint is the lane's own act: the
detector mints plain todos and never writes a checkpoint
line into any todo, its own mints included.

Drain identity: a drain is named by a hash of the
bundle's terminal todo set (ids + updated stamps). The
minted tail todos carry the name in their body
(`drain: <id>`), so "already raised for this drain" is
read off the bundle itself — no side store, restart-safe.
New work landing and completing changes the set, hence
the name: a second drain raises the set again. While the
tail todos stand open the bundle is not drained, so a
drain fires exactly once per episode.

Registry seam: the tail set and the bundle link are read
from the programme declaration through tail_titles() and
resolve_bundles() — the two functions the Step 1
supervision registry binds when it lands. Declaration
fields consumed: `drain_tail` (titles, or {title} rows),
`drain_bundles` (bundle ids/slugs), `contract_path`,
`worktree_roots`, `slug`. An undeclared tail set falls
back to the standing defaults; an unresolvable bundle
link means the programme has no drain watch — nothing
is guessed.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
from fnmatch import fnmatch
from pathlib import Path

from . import paths as _paths
from .derived import worktrees as wt_mod
from .discovery.sweep import _main_checkout_root
from .plans import bundles as bundle_parser
from .writes import bundles as bundle_writer

# `done` is the parser's only terminal status (blocked
# is resumable work, not an ending).
TERMINAL_STATUS = "done"

DEFAULT_TAIL_TITLES = (
    "Consolidation",
    "Doc updates",
    "Performance pass",
)

DRAIN_STAMP_PREFIX = "drain:"

# The archive/trim lifecycle's script, ridden as-is: the
# drain act is one worker pass over the programme's repo
# with the keep cap set to the one most recently active
# extra (the main tree is never a census row). The path
# itself is the foundation paths module's derivation.
_TRIM_SCRIPT = _paths.WORKTREE_TRIM_SCRIPT

# How many extra trees stand after a drain: the main
# tree plus this many, ranked by the trim's own activity
# rule (newest of last commit and latest file touch).
KEEP_EXTRA = 1


class DrainError(Exception):
    """A drain act was refused or failed, with a reason."""


# ----------------------------------------------------------------
# The registry seam
# ----------------------------------------------------------------

def tail_titles(declaration: dict) -> list:
    """The programme's declared drain tail set: its
    registry row's titles verbatim, or the standing
    defaults when the row declares none."""
    declared = declaration.get("drain_tail")
    titles = []
    for entry in declared or []:
        if isinstance(entry, dict):
            entry = entry.get("title")
        if entry and str(entry).strip():
            titles.append(str(entry).strip())
    return titles or list(DEFAULT_TAIL_TITLES)


def _slugify(value: str) -> str:
    return bundle_writer.slugify_title(value or "")


def resolve_bundles(bundles: list, declaration: dict) -> list:
    """The bundles this programme's drain watches, in
    bundle order. Resolution, first hit wins: the
    declaration's explicit `drain_bundles`; the bundle
    its `contract_path` lives in; a bundle whose goal
    contract names this programme. No hit — no watch."""
    wanted = declaration.get("drain_bundles") or []
    if wanted:
        return [
            b for b in bundles
            if b["id"] in wanted or b["slug"] in wanted
        ]
    contract_path = declaration.get("contract_path")
    if contract_path:
        bundle_id = Path(contract_path).parent.name
        return [b for b in bundles if b["id"] == bundle_id]
    names = {_slugify(declaration.get("slug") or "")}
    contract = declaration.get("contract") or {}
    if contract.get("programme"):
        names.add(_slugify(contract["programme"]))
    out = []
    for b in bundles:
        fields = (b.get("contract") or {}).get("fields") or {}
        if _slugify(fields.get("Programme") or "") in names:
            out.append(b)
    return out


# ----------------------------------------------------------------
# The drain computation (pure reads)
# ----------------------------------------------------------------

def bundle_drained(todos: list) -> bool:
    """Every todo terminal and none doing: a non-empty
    bundle whose todos are all valid and all `done`.
    An invalid todo's state is unknown — the bundle is
    not drained on a guess."""
    return bool(todos) and all(
        t.get("valid") and t.get("status") == TERMINAL_STATUS
        for t in todos
    )


def drain_id(bundle_id: str, todos: list) -> str:
    """The name of one drain episode: a hash of the
    bundle's terminal todo set. Stable while the set
    stands; new work completing mints a new episode."""
    parts = sorted(
        (t.get("id") or "", t.get("updated") or "") for t in todos
    )
    digest = hashlib.sha1(repr(parts).encode("utf-8")).hexdigest()
    return f"{bundle_parser.bundle_slug(bundle_id)}-drain-{digest[:12]}"


def stamped_drain_ids(todos: list) -> set:
    """The drain names already raised on this bundle,
    read off the minted todos' stamp lines."""
    found = set()
    for t in todos:
        for line in (t.get("body") or "").splitlines():
            if line.startswith(DRAIN_STAMP_PREFIX):
                found.add(line[len(DRAIN_STAMP_PREFIX):].strip())
    return found


# ----------------------------------------------------------------
# The tail raise (the wb writer path)
# ----------------------------------------------------------------

def raise_tail(plans_dir, bundle: dict, titles: list,
               drain: str) -> list:
    """Mint the tail set on the bundle, once per drain.
    Titles ride verbatim; on a later drain the earlier
    episode's same-title todos stand in the bundle and
    the writer refuses a duplicate title, so the new
    mint's title carries the drain name as its qualifier
    — the set raised is the declared set either way."""
    if drain in stamped_drain_ids(bundle["todos"]):
        return []
    existing = {
        " ".join((t.get("title") or "").lower().split())
        for t in bundle["todos"]
    }
    minted = []
    for title in titles:
        text = title
        if " ".join(title.lower().split()) in existing:
            text = f"{title} [{drain}]"
        result = bundle_writer.create_todo(
            plans_dir, bundle["id"], text,
            body=(
                f"{DRAIN_STAMP_PREFIX} {drain}\n\n"
                "Raised by the workbench drain detector on "
                "the bundle's drained transition — the "
                "programme's supervision-registry tail set."
            ),
        )
        minted.append(result)
    return minted


# ----------------------------------------------------------------
# The archive act (the existing trim lifecycle, ridden)
# ----------------------------------------------------------------

def scoped_tree_paths(main_dir, worktree_roots) -> list | None:
    """The programme's standing extra trees when its
    declaration names `worktree_roots` globs: the repo's
    worktree paths matching any glob. None — no scoping —
    when the declaration names none (the trim's native
    unit is the whole repo)."""
    if not worktree_roots:
        return None
    result = wt_mod.list_worktrees(main_dir)
    if not result["available"]:
        return []
    main = str(Path(main_dir))
    return [
        w["path"]
        for w in result["worktrees"]
        if w["path"] != main
        and any(fnmatch(w["path"], pat) for pat in worktree_roots)
    ]


def archive_trees(main_dir, *, now_epoch: int,
                  keep_extra: int = KEEP_EXTRA,
                  scope_paths: list | None = None,
                  archive_root=None, state_dir=None,
                  trim_script=None) -> dict:
    """Archive the repo's standing worktrees down to the
    main tree plus `keep_extra` most recently active
    extras, in one worker pass of the existing trim
    script. `scope_paths` restricts the pass's census to
    those trees (WORKTREE_TRIM_SCOPE_PATHS); unset, the
    pass covers the repo as the lifecycle defines it.
    The outcome is read off the worker's result file —
    the ARCHIVED lines are the act's own record."""
    if scope_paths is not None and not scope_paths:
        # A declared scope matching no standing tree:
        # the pass archives nothing — an empty scope is
        # never an unscoped pass.
        return {"archived": [], "pruned": [],
                "failures": [], "partial": False}
    main_dir = Path(main_dir)
    slug = main_dir.name
    cap_var = "WT_TRIM_CAP_" + slug.upper().replace("-", "_")
    env = dict(os.environ)
    env["SCHEDULER_WORKSPACE"] = str(main_dir.parent)
    env["WORKTREE_TRIM_NOW"] = str(int(now_epoch))
    # The drain act's seam in the trim worker: this pass
    # fires on a drained transition — the programme's own
    # record that its work is finished — so the census's
    # unlanded hold does not stand for it (the archive
    # stays recoverable inside its grace window). The
    # trim's dirty/live/explicit holds still bind.
    env["WORKTREE_TRIM_DRAIN_ACT"] = "1"
    env[cap_var] = str(keep_extra)
    if scope_paths is not None:
        env["WORKTREE_TRIM_SCOPE_PATHS"] = ":".join(scope_paths)
    if archive_root is not None:
        env["WORKTREE_ARCHIVE_ROOT"] = str(archive_root)
    if state_dir is not None:
        env["WORKTREE_TRIM_STATE_DIR"] = str(state_dir)
    script = Path(trim_script) if trim_script else _TRIM_SCRIPT
    with tempfile.TemporaryDirectory(
            prefix="wb-drain-trim-") as tmp:
        result_file = Path(tmp) / "result.txt"
        ledger_file = Path(tmp) / "ledger.txt"
        proc = subprocess.run(
            ["bash", str(script), "--worker", slug,
             "--tier", "soft",
             "--result-file", str(result_file),
             "--ledger-file", str(ledger_file)],
            capture_output=True, text=True, env=env,
            timeout=1800)
        lines = (
            result_file.read_text(encoding="utf-8").splitlines()
            if result_file.is_file() else []
        )
    archived, pruned, failures = [], [], []
    for line in lines:
        fields = dict(
            part.split("=", 1) for part in line.split()
            if "=" in part
        )
        if line.startswith("ARCHIVED "):
            archived.append({
                "tree": fields.get("tree"),
                "branch": fields.get("branch"),
                "archive": fields.get("archive"),
                "expires": fields.get("expires"),
            })
        elif line.startswith("PRUNED "):
            pruned.append(fields.get("tree"))
        elif "FAIL" in line or line.startswith("CENSUS-ERROR"):
            failures.append(line)
    if proc.returncode not in (0, 3):
        raise DrainError(
            f"worktree trim worker for {slug} exited "
            f"{proc.returncode}: {(proc.stderr or '')[-300:]}")
    return {
        "archived": archived,
        "pruned": pruned,
        "failures": failures,
        "partial": proc.returncode == 3,
    }


# ----------------------------------------------------------------
# One project's drain pass (compute + raise + archive)
# ----------------------------------------------------------------

def run_project(plans_dir, project_root, declarations: list,
                *, now_epoch: int | None = None,
                archive_root=None, state_dir=None) -> list:
    """The drain pass for one workbench project: for each
    programme declaration, resolve its bundles, and on a
    drained transition raise the tail set; a programme
    that raised on this pass archives its repo's trees
    once, down to the main tree plus the most recently
    active extra. Returns one outcome per programme."""
    plans_dir = Path(plans_dir)
    now_epoch = int(now_epoch or time.time())
    bundles = bundle_parser.list_bundles(plans_dir)
    by_id = {b["id"]: b for b in bundles}
    outcomes = []
    main_dir = None
    main_resolved = False
    for declaration in declarations:
        outcome = {
            "programme": declaration.get("slug"),
            "drained": [],
            "raised": [],
            "drain_ids": [],
            "archived": [],
            "pruned": [],
            "archive_failures": [],
        }
        raised_any = False
        for bundle in resolve_bundles(bundles, declaration):
            if bundle.get("archived"):
                continue
            todos = bundle["todos"]
            if not bundle_drained(todos):
                continue
            drain = drain_id(bundle["id"], todos)
            outcome["drained"].append(bundle["id"])
            outcome["drain_ids"].append(drain)
            minted = raise_tail(
                plans_dir, by_id[bundle["id"]],
                tail_titles(declaration), drain)
            if minted:
                raised_any = True
                outcome["raised"].extend(
                    t["id"] for t in minted)
        if raised_any:
            if not main_resolved:
                main_dir = _main_checkout_root(Path(project_root))
                main_resolved = True
            if main_dir is not None:
                result = archive_trees(
                    main_dir, now_epoch=now_epoch,
                    scope_paths=scoped_tree_paths(
                        main_dir,
                        declaration.get("worktree_roots")),
                    archive_root=archive_root,
                    state_dir=state_dir)
                outcome["archived"] = result["archived"]
                outcome["pruned"] = result["pruned"]
                outcome["archive_failures"] = result["failures"]
                outcome["archive_partial"] = result["partial"]
            else:
                outcome["archive_failures"] = [
                    "no git main checkout for the project root"
                ]
        outcomes.append(outcome)
    return outcomes
