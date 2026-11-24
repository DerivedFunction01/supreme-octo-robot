"""Staffing rows, plan family: the plan-step overdue
rows (estimate-rule enforcement plan, Step 3) — split
in the staffing_rows pattern; attention.services.
measure.staffing_rows re-exports this surface.
"""

from __future__ import annotations

from datetime import datetime

from attention.services.measure import registry

from .staffing_common import _as_dt, _row


def _overdue_rows(state: dict, now: datetime) -> list:
    """The plan-step overdue class, from the plan
    snapshot: a step standing open past its own
    estimate, the elapsed time measured from the
    plan's adoption stamp the record carries. The
    row names the plan, the step, the estimate, and
    the overrun, and serves estimate against actual
    in the lane pair's form — expected_minutes
    against elapsed_minutes, with the overrun
    derived. A step with no measurable estimate
    raises nothing (the missing estimate is the
    starter lint's gate finding), a closed step
    raises nothing, and a step not yet past its
    estimate raises nothing. Owner-only steps raise
    the same row flagged owner_only: they stand in
    the served view the digest embeds and never
    steer a coordinator. Gated on the programme
    declaring the stall class."""
    snapshot = state.get("plan_snapshot") or {}
    if not snapshot:
        return []
    rows = []
    for slug, entry in sorted(snapshot.items()):
        declaration = registry.for_slug(slug)
        if declaration is None:
            continue
        if "stall" not in registry.measure_classes_for(slug):
            continue
        handle = (declaration.get("handles") or [slug])[0]
        for plan in entry.get("plans") or []:
            adopted = _as_dt(plan.get("adopted_at"))
            if adopted is None:
                continue
            elapsed = int((now - adopted).total_seconds() // 60)
            plan_title = plan.get("title") or plan.get("name") or "unnamed plan"
            for step in plan.get("steps") or []:
                estimate = step.get("estimate_minutes")
                if estimate is None or step.get("closed"):
                    continue
                if elapsed <= estimate:
                    continue
                overrun = elapsed - estimate
                number = step.get("number")
                step_title = step.get("title") or ""
                step_name = (
                    f"Step {number} ({step_title})" if step_title else f"Step {number}"
                )
                detail = (
                    f"{step_name} of plan {plan_title} stands open "
                    f"{overrun} minutes past its {estimate}-minute "
                    f"estimate — {elapsed} minutes elapsed since the "
                    f"plan's adoption stamp. The estimate is the "
                    f"plan's own and the overrun is measured from "
                    f"it, never acknowledged away; the row clears "
                    f"only when the step closes or the plan is "
                    f"re-estimated with its reason stated."
                )
                rows.append(
                    _row(
                        slug,
                        handle,
                        declaration["label"],
                        "step_overdue",
                        detail,
                        key=f"step_overdue:{slug}:{plan.get('name')}:{number}",
                        extra={
                            "plan": plan.get("name"),
                            "plan_title": plan_title,
                            "step": number,
                            "step_title": step_title,
                            "expected_minutes": estimate,
                            "elapsed_minutes": elapsed,
                            "overrun_minutes": overrun,
                            "owner_only": bool(step.get("owner_only")),
                        },
                    )
                )
    return rows
