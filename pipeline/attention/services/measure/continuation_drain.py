"""Continuation drain: the drain pass's declaration
hand-over (supervision plan Step 4) — split from
continuation.py; attention.services.measure.
continuation re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime

from attention.infra import wb_client
from attention.services import programmes
from attention.services.measure import registry

# ----------------------------------------------------------------
# Drain (supervision plan Step 4): a programme whose
# bundle's todos are all terminal with nothing doing is
# drained; on the transition the workbench raises the
# programme's registry tail set as fresh todos on the
# bundle and archives its standing worktrees down to
# two, through the existing archive/trim lifecycle. The
# computation and both acts live workbench-side
# (lib/drain, behind POST /api/projects/<slug>/drain);
# this leg only hands over the declarations and reports
# that a drain fired. The detector never writes a lane's
# progress checkpoint — checkpoints stay the lane's act.
#
# Registry seam: the declaration fields below are what
# Step 4 reads from a programme row. The Step 1
# supervision registry has landed: its accessor is the
# tail set's one binding (the registry is the tail's
# home), and the store row's own field is the fallback
# for a programme the registry does not declare. The
# bundle-link and tree-scope fields stay store picks —
# the registry carries no worktree roots by design.
# ----------------------------------------------------------------

# A drain pass can archive trees and drain the trim's
# origin-deletion queue; it gets a longer leash than a
# read-time pull.
DRAIN_TIMEOUT_S = 300.0


def _drain_declaration(programme: dict) -> dict:
    """The drain fields of one programme row, picked for
    the workbench detector: the tail set, the bundle
    link, and the tree scope."""
    tail = registry.drain_tail_for(programme["slug"])
    return {
        "slug": programme["slug"],
        "drain_tail": tail or programme.get("drain_tail"),
        "drain_bundles": programme.get("drain_bundles"),
        "contract_path": programme.get("contract_path"),
        "contract": programme.get("contract"),
        "worktree_roots": programme.get("worktree_roots"),
    }


def run_drain_pass(state: dict, settings, now: datetime) -> bool:
    """One drain pass over every active programme,
    grouped by workbench project. A project the
    workbench cannot serve skips its programmes — the
    pass clears nothing and retries next tick."""
    by_project: dict = {}
    for programme in programmes.active_declarations(state):
        declaration = _drain_declaration(programme)
        for project in programmes.wb_projects(programme):
            by_project.setdefault(project, []).append(declaration)
    changed = False
    for project, declarations in by_project.items():
        try:
            payload = wb_client.run_drain(
                settings.wb_url,
                project,
                declarations,
                DRAIN_TIMEOUT_S,
            )
        except wb_client.WbUnavailable:
            continue
        for outcome in payload.get("drain") or []:
            if outcome.get("raised") or outcome.get("archived"):
                changed = True
    return changed
