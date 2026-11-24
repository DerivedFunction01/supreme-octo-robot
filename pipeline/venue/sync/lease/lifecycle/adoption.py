"""Nameless-assignment adoption: the endpoint form of adopt.

Local why: adoption was name-keyed end to end, so a live
assignment whose name was lost server-side — absent by name
from the listing, or wearing "?" — could not re-enter the
lease at all (the first-rotation pair, assigned
and billing for hours, released unadopted). The name is the
machinery's own identifier, not evidence: this flow mints a
fresh one through the naming module, binds it to the
endpoint, and restores the record from the endpoint's own
evidence under that name — renewal-config first, extension
events over it, nothing invented, exactly as the named
adoption restores. The evidence is recovered by endpoint:
identity stamps bind names to endpoints, so the endpoint's
prior name (when one exists) names the evidence chain the
census reads. Mechanics: docs/lease-workflow.md.
"""

from datetime import datetime, timezone
from pathlib import Path
from ..core import foundation, records
from ..sessions import sessions
from .lifecycle import adopt_orphan


def adopt_nameless(colab, repo: Path, endpoint: str, deadline=None, hours: float | None = None, caller: str | None = None, shape: str | None = None, now_dt: datetime | None = None) -> dict:
    """Adopt one live assignment that carries no usable name,
    by its endpoint. Verdicts mirror the named path's:
    adopt-absent when the server holds no such assignment,
    adopt-unknown when a read cannot be made, adopt-has-record
    when a prior name for the endpoint already holds the lease
    (the namelessness is then a binding problem, not an
    adoption). Two verdicts are this flow's own:
    adopt-nameless-named when the endpoint already displays a
    usable name (the named path owns it), and adopt-bind-failed
    when the minted name's bind does not verify on a listing
    re-read — no record is planted on an unverified bind.
    Caller validation happens at the wrapper seam, as for
    adopt; the record's caller is the evidence's creator, with
    the operator's claim journaled as a ride, exactly as the
    named adoption does it."""
    now_dt = now_dt or datetime.now(timezone.utc)
    cfg = foundation.load_config(repo)
    if not cfg.get("enabled"):
        return {"action": "lease-disabled"}
    assignments = sessions.assignments_list()
    if assignments is None:
        return {"action": "adopt-unknown", "endpoint": endpoint}
    if not any(sessions.endpoints_match(a.get("endpoint"), endpoint) for a in assignments):
        return {"action": "adopt-absent", "endpoint": endpoint}
    live = sessions.live_sessions(colab, repo)
    if live is None:
        return {"action": "adopt-unknown", "endpoint": endpoint}
    named = next((e for e in live if sessions.endpoints_match(e.get("endpoint"), endpoint) and e.get("session") not in (None, "", "?")), None)
    if named is not None:
        return {"action": "adopt-nameless-named", "endpoint": endpoint, "session": named["session"]}
    priors = sessions.prior_names_for_endpoint(repo, endpoint)
    for prior in priors:
        if records.load_record(repo, prior) is not None:
            return {"action": "adopt-has-record", "session": prior, "endpoint": endpoint}
    prior = priors[0] if priors else None
    name = sessions.generate_session_name(repo, colab)
    while name == prior:
        # The taken set does not read identity stamps, so a
        # draw can land on the prior name itself; a minted
        # name must be fresh, never the name it replaces.
        name = sessions.generate_session_name(repo, colab)
    if not sessions.bind_name_to_endpoint(name, endpoint):
        return {"action": "adopt-bind-failed", "endpoint": endpoint, "session": name}
    live = sessions.live_sessions(colab, repo)
    entry = next((e for e in live if e.get("session") == name), None) if live else None
    if entry is None:
        return {"action": "adopt-bind-failed", "endpoint": endpoint, "session": name}
    out = adopt_orphan(colab, repo, name, deadline=deadline, hours=hours, caller=caller, shape=shape, now_dt=now_dt, evidence_session=prior, nameless={"endpoint": endpoint, "prior_session": prior})
    if out.get("action") == "adopted":
        out["adopted_nameless"] = {"endpoint": endpoint, "prior_session": prior, "session": name}
    return out
