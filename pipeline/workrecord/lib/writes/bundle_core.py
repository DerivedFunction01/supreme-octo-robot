"""Bundle/todo writer core: the status vocabulary, the
slug rule, todo names, and bundle resolution — split
from bundles.py along the discovery seam; lib.writes.
bundles re-exports this surface.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from ..plans import bundles as bundle_parser

TODO_STATUSES = bundle_parser.TODO_STATUSES

# Statuses that end a todo's active life: a move to one
# of these disarms its progress schedule (the schedule
# stops at done/blocked, per the progress-schedules
# plan's rulings). `done` is also the parser's only
# terminal status — blocked is resumable work, but its
# schedule has already surfaced the blocker and stopped.
# The set itself is homed with the vocabulary
# (lib/plans/bundles.py: TODO_STOP_STATUSES) — the
# writers, the schedule, and the stall derivation all
# rule against the one definition.
PROGRESS_STOP_STATUSES = bundle_parser.TODO_STOP_STATUSES

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class BundleError(Exception):
    """A bundle/todo mutation was refused, with a reason."""


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _check_slug(slug: str, what: str = "slug"):
    if not _SLUG_RE.match(slug or ""):
        raise BundleError(
            f"bad {what} {slug!r}: lowercase letters, "
            f"digits, hyphens; must start with a letter "
            f"or digit")


# ----------------------------------------------------------------
# Todo names: a todo's id IS its name — a GitHub-like
# slug (the owner's naming ruling), validated
# by the one rule in the parser family
# (lib/plans/bundles.py: check_todo_name). A name is
# unique across the whole project (every bundle, active
# and finished): that is the namespace every lookup
# resolves in — `wb todo set <name>` and
# `wb progress-check <name>` take no bundle argument.
# The retired ULID generator is gone; a pre-ruling
# record's token survives only as its `legacy_id` data
# (the rename driver, lib/todo_rename.py, performs the
# migration).
# ----------------------------------------------------------------

def derive_todo_name(title: str, taken) -> str:
    """The name a title derives: its slugified form,
    suffixed `-2`, `-3`, ... until it is free in `taken`
    (the project's whole name set). Deterministic for a
    given title and set — the same derivation the
    rename driver applies to the existing corpus."""
    base = slugify_title(title)
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def check_todo_name(name: str):
    """Refuse a caller-chosen name that breaks the slug
    rule (the parser family's verdict, raised as this
    module's refusal)."""
    problem = bundle_parser.check_todo_name(name)
    if problem is not None:
        raise BundleError(problem)



def slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-",
                  (title or "").lower()).strip("-")
    return slug[:50].strip("-") or "todo"


# ----------------------------------------------------------------
# Bundle resolution
# ----------------------------------------------------------------

def _bundle_dirs(plans_dir: Path, *, archived: bool):
    base = plans_dir / "finished" if archived else plans_dir
    if not base.is_dir():
        return
    for d in sorted(base.iterdir()):
        if d.is_dir() and (archived or d.name != "finished"):
            yield d


def find_bundle_dir(plans_dir, bundle_ref: str, *,
                    archived: bool = False) -> Path | None:
    """Resolve a bundle reference (full bundle id, slug,
    or id with a finished/ prefix) to its directory."""
    plans_dir = Path(plans_dir)
    ref = (bundle_ref or "").removesuffix("/")
    if ref.startswith("finished/"):
        archived = True
        ref = ref[len("finished/"):]
    for d in _bundle_dirs(plans_dir, archived=archived):
        if d.name == ref \
                or bundle_parser.bundle_slug(d.name) == ref:
            return d
    return None


def _all_bundle_dirs(plans_dir: Path):
    yield from _bundle_dirs(plans_dir, archived=False)
    yield from _bundle_dirs(plans_dir, archived=True)


# ----------------------------------------------------------------
