"""Placement pinning: the binding recorded at launch time
governs every later verb (launch-path intermittency, Step 1).

The defect: placement resolved per invocation. A resume
that named no pin derived one from the record's session_pin
(an earlier invocation's request, resolvable through
renewal to a different generation) or its session (the
current binding, re-stamped by every acquire — including a
resume that acquired elsewhere and died before its launch
landed), and never consulted launch_session, the session
the launch actually bound. The cure: replace.record_pin
derives launch_session first, and the re-placement guard
recognizes a launch_session-derived pin as the record's own
binding. The pins below: a resume for a record carrying
launch_session S derives S and only S; an unpinned fresh
launch derives no pin and its acquire is untouched; a
record with no launch_session (pre-cure) falls back to the
prior resolution, session_pin then session, named as such.
These drive replace.py against a stub lease, in the
test_binding_replace form.
"""

import sys
import types
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
    package = types.ModuleType("runner_launchpin_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_launchpin_unit"] = package
    foundation = types.ModuleType("runner_launchpin_unit.foundation")
    foundation.REPO = Path("/fixture-repo")
    foundation.now = lambda: "2026-11-24T13:00:00+00:00"
    foundation.colab = object()
    foundation.lease = lease
    sys.modules["runner_launchpin_unit.foundation"] = foundation
    return load_module("runner_launchpin_unit.replace", REPO / "sync" / "runner" / "replace.py", register=True)


REFUSAL = {"action": "pin-unavailable", "reason": "no lease record for the named session or its lineage"}
ADOPTED = {"action": "adopted", "record": {"session": "live-peer"}}


def test_resume_pin_is_the_launch_session():
    """Specimen (a): the record carries all three session
    fields with distinct values — launch_session is the
    session the launch bound, session_pin an earlier
    invocation's request, session a later resume's
    re-stamped binding. The derived pin is launch_session:
    the resume acquires against S, never the shape's shared
    session and never either stale field."""
    replace = load_replace(StubLease())
    rec = {"run_id": "run-1", "launch_session": "bound-at-launch", "session_pin": "requested-earlier", "session": "restamped-later"}
    assert replace.record_pin(rec) == "bound-at-launch"


def test_launch_session_alone_still_pins():
    """Specimen (a), the adoption face: a record carrying
    launch_session and neither fallback field still derives
    its pin — the derivation never comes back empty for a
    launched run, so the resume's acquire is pinned to the
    launch's session instead of running unpinned and
    adopting the shape's shared session."""
    replace = load_replace(StubLease())
    assert replace.record_pin({"run_id": "run-1", "launch_session": "bound-at-launch"}) == "bound-at-launch"


def test_launch_session_pin_replaces_on_proven_absence():
    """Specimen (a), composed with re-placement: the resume
    derives its pin from launch_session, the bound session
    is proven gone (no lease record for the name or its
    lineage), and the re-placement fires — the guard
    recognizes a launch_session-derived pin as the record's
    own binding, journals the move from it, and the retry
    acquires unpinned against the pool."""
    lease = StubLease()
    lease.acquire_results = [dict(REFUSAL), dict(ADOPTED)]
    replace = load_replace(lease)
    rec = {"run_id": "run-1", "launch_session": "bound-at-launch", "session_pin": "requested-earlier", "session": "restamped-later"}
    pin = replace.record_pin(rec)
    got = replace.acquire_session(rec, "shape-a", "caller-x", pin, 600, "run-1")
    assert got["action"] == "adopted"
    assert lease.acquire_calls == ["bound-at-launch", None]
    assert rec["binding_replaced"]["from"] == "bound-at-launch"
    assert rec["binding_replaced"]["to"] == "live-peer"


def test_caller_named_pin_is_never_replaced_with_launch_session_present():
    """The guard's other face, with launch_session on the
    record: a pin the caller names on this invocation that
    matches none of the record's session fields is an
    instruction — its pin-unavailable refusal stands after
    exactly one acquire, even with absence provable."""
    lease = StubLease()
    lease.acquire_results = [dict(REFUSAL)]
    replace = load_replace(lease)
    rec = {"run_id": "run-1", "launch_session": "bound-at-launch", "session_pin": "requested-earlier", "session": "restamped-later"}
    got = replace.acquire_session(rec, "shape-a", "caller-x", "caller-named", 600, "run-1")
    assert got == REFUSAL
    assert lease.acquire_calls == ["caller-named"]
    assert "binding_replaced" not in rec


def test_fresh_launch_derives_no_pin():
    """Specimen (b): a fresh launch's record — the dict the
    launch path builds, and the daemonize parent's claim
    record — carries no session field of any kind at
    derivation time, so the derivation contributes no pin
    and the launch's unpinned acquire proceeds exactly as
    before the cure."""
    replace = load_replace(StubLease())
    fresh = {"run_id": "job-20261124T130000Z", "job": "job", "shape": "shape-a", "state": "starting", "started_at": "2026-11-24T13:00:00+00:00", "resumed": False}
    claim = {"run_id": "job-20261124T130000Z", "job": "job", "shape": None, "state": "claiming", "started_at": "2026-11-24T13:00:00+00:00", "resumed": False, "claim_by": "daemonize-parent"}
    assert replace.record_pin(fresh) is None
    assert replace.record_pin(claim) is None
    assert replace.record_pin(None) is None


def test_unpinned_acquire_is_untouched():
    """Specimen (b), the acquire itself: with no pin and no
    resume, acquire_session returns the lease's result
    as-is after exactly one unpinned acquire — the fresh
    launch's behaviour is byte-for-byte the current one."""
    lease = StubLease()
    lease.acquire_results = [dict(ADOPTED)]
    replace = load_replace(lease)
    got = replace.acquire_session({"run_id": "run-1"}, "shape-a", "caller-x", None, 600, None)
    assert got == ADOPTED
    assert lease.acquire_calls == [None]


def test_pre_cure_record_falls_back_to_the_prior_resolution():
    """Specimen (c): a record with no launch_session — a
    pre-cure record, or a run that never launched — falls
    back to the resolution that predates the launch_session
    authority, in its own order: session_pin (the recorded
    request) first, then session (the recorded binding).
    The fallback is the named behaviour, not an accident of
    the new derivation."""
    replace = load_replace(StubLease())
    assert replace.record_pin({"run_id": "run-1", "session_pin": "recorded-request", "session": "recorded-binding"}) == "recorded-request"
    assert replace.record_pin({"run_id": "run-1", "session": "recorded-binding"}) == "recorded-binding"
