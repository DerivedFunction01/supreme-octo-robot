"""Bundle creation and goal contracts — split from
bundles.py along the creation seam; lib.writes.bundles
re-exports this surface.
"""

import re
from pathlib import Path

from ..plans import bundles as bundle_parser
from ..util import write_text

from .bundle_core import (
    BundleError,
    _all_bundle_dirs,
    _check_slug,
    _today,
    find_bundle_dir,
)
from .transitions import (
    append_transition,
    append_transition_line,
    block_lines,
)

# Bundle creation (§3.4)
# ----------------------------------------------------------------

def _plan_skeleton(slug: str, *, feature=None,
                   today: str) -> str:
    title = slug.replace("-", " ").title()
    lines = [
        f"# {title}",
        "",
        "Status: draft",
        f"Created: {today}",
    ]
    if feature:
        lines.append(f"Feature: {feature}")
    lines += ["", "## Steps", ""]
    return "\n".join(lines)


def create_bundle(plans_dir, slug, *, plan: bool = False,
                  feature=None, today: str = None) -> dict:
    """Create `.plans/<date>-<slug>/` (+ todos/, +
    plan.md skeleton with the house header when
    plan=True). Refuses when the slug already exists as
    a bundle (active or finished, any date)."""
    _check_slug(slug)
    today = today or _today()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        raise BundleError(f"bad date {today!r}: YYYY-MM-DD")
    plans_dir = Path(plans_dir)
    for d in _all_bundle_dirs(plans_dir):
        if bundle_parser.bundle_slug(d.name) == slug:
            raise BundleError(
                f"bundle slug {slug!r} already exists: "
                f"{d.name}")
    bundle_id = f"{today}-{slug}"
    bundle_dir = plans_dir / bundle_id
    if bundle_dir.exists():
        raise BundleError(
            f"bundle already exists: {bundle_id}")
    (bundle_dir / "todos").mkdir(parents=True)
    plan_written = False
    if plan:
        # The skeleton write carries the creation's
        # transition (timing-ledger Step 2) in its
        # transitions block, in the same write. A
        # bundle created without a plan writes no file
        # at all, so there is no write for a transition
        # to ride — that form records nothing.
        write_text(
            bundle_dir / "plan.md",
            append_transition(
                _plan_skeleton(slug, feature=feature,
                               today=today),
                verb="create-bundle", field="bundle",
                old=None, new=bundle_id))
        plan_written = True
    return {
        "id": bundle_id,
        "slug": slug,
        "path": str(bundle_dir),
        "plan": plan_written,
        "feature": feature,
    }


# ----------------------------------------------------------------
# Goal contracts (goal-prompt contract plan)
# ----------------------------------------------------------------

def _check_contract_gate(plans_dir, bundle_dir) -> None:
    """The arming gate for contract-carrying bundles:
    a bundle with a contract.md arms only when the
    contract is complete. An incomplete contract
    refuses the arm, naming the first empty field —
    the raise happens before any write, like every
    validation in the writers. A bundle carrying no
    contract is not a programme bundle and arms as
    before."""
    contract = bundle_parser.parse_contract(bundle_dir)
    if contract is None or contract["complete"]:
        return
    missing = contract["missing"]
    extra = (f" (also empty: {', '.join(missing[1:])})"
             if len(missing) > 1 else "")
    raise BundleError(
        f"goal contract incomplete: {missing[0]} is "
        f"empty — arming refused (bundle "
        f"{bundle_dir.name}){extra}")


def set_bundle_contract(plans_dir, bundle_ref, *,
                        programme, objective,
                        complete_when, work_record) -> dict:
    """Write a bundle's goal contract (contract.md):
    the four per-programme fields filled, the three
    fixed clauses verbatim from the template. The
    start gate applies at the write too — a contract
    with an empty filled field is not written."""
    filled = {
        "Programme": programme,
        "Objective": objective,
        "Complete when": complete_when,
        "Work record": work_record,
    }
    for field in bundle_parser.CONTRACT_FILLED_FIELDS:
        value = filled[field]
        if value is None or not str(value).strip():
            raise BundleError(
                f"goal contract field {field} is empty "
                f"— the contract is not written")
        if "\n" in str(value):
            raise BundleError(
                f"goal contract field {field} must be "
                f"one line")
    plans_dir = Path(plans_dir)
    bundle_dir = find_bundle_dir(plans_dir, bundle_ref)
    if bundle_dir is None:
        raise BundleError(
            f"unknown bundle: {bundle_ref!r} "
            f"(no such bundle under {plans_dir})")
    contract_path = bundle_dir / bundle_parser.CONTRACT_FILE
    # The contract renders wholesale, so its transitions
    # block (timing-ledger Step 2) is carried over from
    # the standing file before this write's own
    # transition is appended — the ledger survives the
    # regeneration, in the same write.
    carried = []
    if contract_path.is_file():
        carried = block_lines(
            contract_path.read_text(encoding="utf-8"))
    text = bundle_parser.render_contract(
        programme.strip(), objective.strip(),
        complete_when.strip(), work_record.strip())
    for line in carried:
        text = append_transition_line(text, line)
    text = append_transition(
        text, verb="set-contract", field="contract",
        old=None, new=bundle_dir.name)
    if not text.endswith("\n"):
        text += "\n"
    write_text(contract_path, text)
    return {
        "bundle": bundle_dir.name,
        "contract": bundle_parser.parse_contract(
            bundle_dir),
    }


# ----------------------------------------------------------------
