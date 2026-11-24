"""Re-placement of a run whose recorded session binding is
proven gone (VENUE DEFECT 2, leg a).

The pins: a resume whose record-bound pin refuses
pin-unavailable re-places onto the shape's live pool ONLY on
proven absence — no lease record for the name or its lineage,
or a confirmed-absent reading past the lease core's
confirmation window — journaling the move on the record
(binding_replaced) and moving the record's pin. Ambiguity
refuses loudly: absence unconfirmed, a live-but-unhealthy
lineage, an operator pin named on this invocation, and a
fresh launch all return the refusal untouched, with exactly
one acquire attempted. A successful pinned acquire is never
swapped. These drive replace.py against a stub lease.
"""

import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402


class StubLease:
    """The lease seams acquire_session consults: acquire
    (scripted results, calls recorded), the pin's record
    resolution, the tri-state session read, and the absence
    stamp."""

    def __init__(self):
        self.acquire_calls = []
        self.acquire_results = []
        self.records = {}
        self.states = {}
        self.stamps = {}
        self.foundation = types.SimpleNamespace(
            ABSENT_CONFIRM_S=900,
            absent_since=lambda repo, session: self.stamps.get(session),
        )

    def acquire(self, colab, repo, shape, via=None, caller=None, prefer_session=None, min_window_s=None):
        self.acquire_calls.append(prefer_session)
        return self.acquire_results.pop(0)

    def resolve_session_record(self, repo, name):
        return self.records.get(name)

    def session_state(self, colab, name):
        return self.states.get(name, "unknown")


def load_replace(lease):
    package = types.ModuleType("runner_replace_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_replace_unit"] = package
    foundation = types.ModuleType("runner_replace_unit.foundation")
    foundation.REPO = Path("/fixture-repo")
    foundation.now = lambda: "2026-11-24T13:00:00+00:00"
    foundation.colab = object()
    foundation.lease = lease
    sys.modules["runner_replace_unit.foundation"] = foundation
    return load_module("runner_replace_unit.replace", REPO / "sync" / "runner" / "replace.py", register=True)


REFUSAL = {"action": "pin-unavailable", "reason": "no lease record for the named session or its lineage"}
ADOPTED = {"action": "adopted", "record": {"session": "live-peer"}}


def _rec(pin="dead-name"):
    return {"run_id": "run-1", "session_pin": pin, "session": pin}


def test_replacement_on_a_recordless_binding():
    """The decprof form: the bound session was reaped and its
    record deleted on the confirmed-absent reading, so no
    record exists for the name or its lineage — proven
    absence. The resume re-places onto the pool's live
    session, journals the move, and moves the record's pin."""
    lease = StubLease()
    lease.acquire_results = [dict(REFUSAL), dict(ADOPTED)]
    replace = load_replace(lease)
    rec = _rec()
    got = replace.acquire_session(rec, "shape-a", "caller-x", "dead-name", 600, "run-1")
    assert got["action"] == "adopted"
    assert lease.acquire_calls == ["dead-name", None]
    journal = rec["binding_replaced"]
    assert journal["from"] == "dead-name" and journal["to"] == "live-peer"
    assert "no lease record" in journal["evidence"]
    assert journal["at"] == "2026-11-24T13:00:00+00:00"
    assert rec["session_pin"] == "live-peer"


def test_replacement_on_a_confirmed_absent_reading():
    """The record still stands but its session reads absent
    with the absence stamped past the confirmation window —
    the lease core's second proven form."""
    lease = StubLease()
    lease.acquire_results = [dict(REFUSAL), dict(ADOPTED)]
    lease.records = {"dead-name": {"session": "dead-name"}}
    lease.states = {"dead-name": "absent"}
    lease.stamps = {"dead-name": datetime.now(timezone.utc) - timedelta(seconds=1000)}
    replace = load_replace(lease)
    rec = _rec()
    got = replace.acquire_session(rec, "shape-a", "caller-x", "dead-name", 600, "run-1")
    assert got["action"] == "adopted"
    assert lease.acquire_calls == ["dead-name", None]
    assert "past the 900s confirmation window" in rec["binding_replaced"]["evidence"]


def test_unconfirmed_absence_refuses():
    """Absent from one live list, no stamp (or a young one):
    the flicker window, not a death — the refusal stands and
    no second acquire is attempted."""
    lease = StubLease()
    lease.acquire_results = [dict(REFUSAL)]
    lease.records = {"dead-name": {"session": "dead-name"}}
    lease.states = {"dead-name": "absent"}
    replace = load_replace(lease)
    rec = _rec()
    got = replace.acquire_session(rec, "shape-a", "caller-x", "dead-name", 600, "run-1")
    assert got == REFUSAL
    assert lease.acquire_calls == ["dead-name"]
    assert "binding_replaced" not in rec


def test_live_but_unhealthy_pin_refuses():
    """A pin refused for a dead channel (the lineage is alive,
    its bind probe failed) is not absence: re-placing would
    abandon a live binding on a channel verdict."""
    lease = StubLease()
    lease.acquire_results = [{"action": "pin-unavailable", "reason": "pin-lineage-unhealthy: bind probe failed"}]
    lease.records = {"dead-name": {"session": "dead-name"}}
    lease.states = {"dead-name": "alive"}
    replace = load_replace(lease)
    rec = _rec()
    got = replace.acquire_session(rec, "shape-a", "caller-x", "dead-name", 600, "run-1")
    assert got["action"] == "pin-unavailable"
    assert lease.acquire_calls == ["dead-name"]
    assert "binding_replaced" not in rec


def test_operator_pin_and_fresh_launch_are_never_replaced():
    """A pin named on this invocation is the caller's
    instruction even when its session is provably gone, and
    a fresh launch has no recorded binding to cure: both
    refusals stand after exactly one acquire."""
    lease = StubLease()
    lease.acquire_results = [dict(REFUSAL), dict(REFUSAL)]
    replace = load_replace(lease)
    rec = _rec(pin="recorded-name")
    got = replace.acquire_session(rec, "shape-a", "caller-x", "dead-name", 600, "run-1")
    assert got == REFUSAL
    got = replace.acquire_session(rec, "shape-a", "caller-x", "dead-name", 600, None)
    assert got == REFUSAL
    assert lease.acquire_calls == ["dead-name", "dead-name"]
    assert "binding_replaced" not in rec


def test_a_successful_pin_is_never_swapped():
    """The pinned acquire lands: returned as-is, one call,
    no journal — a bound session that exists keeps its run."""
    lease = StubLease()
    lease.acquire_results = [{"action": "adopted", "record": {"session": "dead-name"}}]
    replace = load_replace(lease)
    rec = _rec()
    got = replace.acquire_session(rec, "shape-a", "caller-x", "dead-name", 600, "run-1")
    assert got["record"]["session"] == "dead-name"
    assert lease.acquire_calls == ["dead-name"]
    assert "binding_replaced" not in rec
