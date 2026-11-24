#!/usr/bin/env python3
"""Re-placement of a run whose recorded session binding is
proven gone (VENUE DEFECT 2, leg a).

A resume derives its pin from the run record — the recorded
lineage is the run's binding. When the bound session was
reaped mid-day, every resume refused pin-unavailable forever:
the record named a session that no longer exists, and nothing
re-placed the run (the decprof specimen: the lease stayed
bound to a reaped generation while a live sibling sat at the
same shape). The cure is narrow by construction:

- It fires only on a pin-unavailable refusal, only when the
  pin came from the record itself (a resume re-deriving its
  own binding). A pin the caller names on this invocation is
  an instruction: its refusal stands, untouched.
- It re-places only on PROVEN absence, in the lease core's
  own two forms: no lease record exists for the named session
  or its lineage (a record is deleted only on a confirmed-
  absent reading or a successful stop, so record absence is
  grounded), or the lineage's live record names a session the
  backend reads absent with the absence stamp past the core's
  confirmation window (ABSENT_CONFIRM_S). Every other refusal
  — lineage unhealthy, absence unconfirmed, deadline past,
  window short — is ambiguity, and ambiguity refuses loudly:
  the original refusal returns unchanged.
- The re-placement is journaled on the run record before the
  retry (binding_replaced: from, to, evidence, at), the
  record's pin moves to the new binding, and the retry is a
  plain unpinned acquire at the run's shape — the pool's own
  adoption and bind-probe discipline decides where the run
  lands. A bound session that exists is never swapped: a
  successful pinned acquire returns before any of this runs.
"""

from datetime import datetime, timezone

from .foundation import REPO, now


def _absence_proven(pin: str) -> tuple[bool, str]:
    """(proven, evidence) for a bound name, in the lease
    core's absence forms. colab / lease bind at call time:
    the unit tests' stub foundations carry a limited surface
    (the launch.resolve_branch_ctx precedent)."""
    from .foundation import colab, lease

    resolved = lease.resolve_session_record(REPO, pin)
    if resolved is None:
        return True, "no lease record for the named session or its lineage"
    target = resolved["session"]
    if lease.session_state(colab, target) != "absent":
        return False, ""
    since = lease.foundation.absent_since(REPO, target)
    if since is not None and (datetime.now(timezone.utc) - since).total_seconds() >= lease.foundation.ABSENT_CONFIRM_S:
        return True, f"session {target} read absent with the absence first stamped at {since.isoformat()}, past the {lease.foundation.ABSENT_CONFIRM_S}s confirmation window"
    return False, ""


def acquire_session(rec, shape_id, caller, pin_session, min_window_s, resume):
    """The launch path's acquire, with re-placement of a
    record-bound pin whose session is proven absent. Returns
    the lease.acquire result dict, exactly as the plain call
    does; on a re-placement the retry's result is returned and
    the journal stands on the record for the caller's saves."""
    from .foundation import colab, lease

    got = lease.acquire(colab, REPO, shape_id, via="runner", caller=caller, prefer_session=pin_session, min_window_s=min_window_s)
    if got["action"] != "pin-unavailable" or not pin_session or rec is None or not resume:
        return got
    if pin_session not in (rec.get("session_pin"), rec.get("session")):
        # The pin is this invocation's instruction, not the
        # record's binding — its refusal is the caller's to
        # act on, never silently re-placed.
        return got
    proven, evidence = _absence_proven(pin_session)
    if not proven:
        return got
    rec["binding_replaced"] = {"from": pin_session, "to": None, "evidence": evidence, "at": now()}
    retry = lease.acquire(colab, REPO, shape_id, via="runner", caller=caller, prefer_session=None, min_window_s=min_window_s)
    if retry.get("record"):
        rec["binding_replaced"]["to"] = retry["record"]["session"]
        rec["session_pin"] = retry["record"]["session"]
    return retry
