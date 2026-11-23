"""Lease unit tests: the reap's approval-gate scope.

Pins the 2026-11-23 blast radius: one renewed session's
unproven tunnel host made the reaper hook skip the whole reap
between hourly probes, so two proven hosts lost their kernel
pulses, keepalive maintenance, and deadline enforcement for an
hour at a time and read as stalled. The gate now scopes inside
the pass: a record on a pending host gets no network contact
except its one probe pulse on a probe pass, and every other
record gets full duties. The protection itself is unchanged —
a pending host is still dialed at most once an hour, and only
by the probe.
"""

import json
from datetime import timedelta

import pytest

from unit_harness import NOW, cp, gate_permissive, lease, repo  # noqa: F401

PROVEN = "sess-proven"
PENDING = "sess-pending"
PROVEN_HOST = "proven.example"
PENDING_HOST = "pending.example"


def seed(repo, session, host, **over):
    rec = {
        "session": session,
        "host": host,
        "shape": "cpu",
        "shape_spec": {"gpu": None, "tpu": None, "high_mem": False},
        "rate_cu_per_hour": 0.08,
        "acquired_at": "2026-10-29T17:00:00+00:00",
        "deadline": "2026-10-30T01:00:00+00:00",
        "last_used_at": "2026-10-29T17:30:00+00:00",
        "jobs": [],
    }
    rec.update(over)
    lease.save_record(repo, rec)
    return rec


def seed_pair(repo):
    seed(repo, PROVEN, PROVEN_HOST)
    seed(repo, PENDING, PENDING_HOST)


def make_stub(alive, calls):
    def stub(*a, **k):
        calls.append(a)
        if a and a[0] == "sessions":
            return cp(json.dumps(sorted(alive)))
        if a and a[0] == "download":
            return cp("", rc=1)  # no heartbeat file: keepalive reads stale
        return cp("")

    return stub


def target(call):
    if "-s" in call:
        return call[call.index("-s") + 1]
    return None


def dials(calls, session):
    """Every session-targeting channel call: exec, download,
    upload, stop, new — the acts that reach a session's tunnel."""
    return [c for c in calls if c and c[0] in ("exec", "download", "upload", "stop", "new") and target(c) == session]


def pulse_execs(calls, session):
    return [c for c in dials(calls, session) if c[0] == "exec" and any("lease-pulse" in str(x) for x in c)]


def entry(out, session):
    return next(r for r in out["records"] if r["session"] == session)


def test_pending_record_gets_no_dial_off_probe(repo):
    """(a) Off a probe pass, the pending record is not dialed
    at all — no pulse, no heartbeat read, no identity probe,
    no keepalive launch — while the proven record pulses on
    cadence and gets its keepalive launch: (b) and the
    keepalive half of (c)."""
    seed_pair(repo)
    calls = []
    gate = lease.GateScope(pending_hosts=frozenset({PENDING_HOST}))
    out = lease.reap(make_stub({PROVEN, PENDING}, calls), repo, now_dt=NOW, gate=gate)
    assert dials(calls, PENDING) == []
    pending = entry(out, PENDING)
    assert pending["action"] == "kept"
    assert pending["gate"] == "pending"
    assert pending["pulse"] == "gated"
    assert "last_pulse_at" not in (lease.load_record(repo, PENDING) or {})
    proven = entry(out, PROVEN)
    assert proven["pulse"] == "ok"
    assert len(pulse_execs(calls, PROVEN)) == 1
    # The stale heartbeat read owes a launch, and the launch
    # dials the proven session — full duties while gated.
    assert any(c[0] in ("upload", "exec") and c not in pulse_execs(calls, PROVEN) for c in dials(calls, PROVEN))
    assert out["gate"] == {"pending_sessions": [PENDING], "probe_sessions": []}


def test_pending_record_probe_pass_dials_exactly_one_pulse(repo):
    """(a) On a probe pass the pending record gets exactly
    one network contact — the kernel pulse, the gate's contact
    test — stamped on its record like a cadenced pulse; the
    freshness read, the identity probe, and any launch stay
    reserved."""
    seed_pair(repo)
    calls = []
    gate = lease.GateScope(pending_hosts=frozenset({PENDING_HOST}), probe_hosts=frozenset({PENDING_HOST}))
    out = lease.reap(make_stub({PROVEN, PENDING}, calls), repo, now_dt=NOW, gate=gate)
    pending_dials = dials(calls, PENDING)
    assert len(pending_dials) == 1
    assert pending_dials == pulse_execs(calls, PENDING)
    pending = entry(out, PENDING)
    assert pending["gate"] == "probe"
    assert pending["pulse"] == "ok"
    saved = lease.load_record(repo, PENDING)
    assert saved["last_pulse_at"] == NOW.isoformat()
    assert saved["last_pulse_result"] == "ok"
    assert out["gate"] == {"pending_sessions": [PENDING], "probe_sessions": [PENDING]}


def test_proven_deadline_enforced_while_pending_waits(repo):
    """(c) Deadline enforcement is a dial (the stop), so it
    runs for the proven record while gated and waits for the
    pending record, whose lease stands past its deadline with
    the gate marker naming why."""
    past = "2026-10-29T17:30:00+00:00"
    seed(repo, PROVEN, PROVEN_HOST, deadline=past)
    seed(repo, PENDING, PENDING_HOST, deadline=past)
    calls = []
    gate = lease.GateScope(pending_hosts=frozenset({PENDING_HOST}))
    out = lease.reap(make_stub({PROVEN, PENDING}, calls), repo, now_dt=NOW, gate=gate)
    assert entry(out, PROVEN)["action"] == "released-deadline"
    assert any(c[0] == "stop" for c in dials(calls, PROVEN))
    assert not any(c[0] == "stop" for c in dials(calls, PENDING))
    pending = entry(out, PENDING)
    assert pending["action"] == "kept"
    assert pending["gate"] == "pending"
    assert lease.load_record(repo, PENDING) is not None


def test_pending_absent_record_still_clears(repo):
    """The absent path is local bookkeeping over the pass's
    shared snapshot, not a dial: a pending record whose
    session is confirmed absent is cleared on the usual
    two-pass confirmation, gate or no gate."""
    seed_pair(repo)
    calls = []
    gate = lease.GateScope(pending_hosts=frozenset({PENDING_HOST}))
    stub = make_stub({PROVEN}, calls)
    out = lease.reap(stub, repo, now_dt=NOW, gate=gate)
    assert entry(out, PENDING)["action"] == "kept-absent-unconfirmed"
    later = NOW + timedelta(seconds=lease.ABSENT_CONFIRM_S + 1)
    out = lease.reap(stub, repo, now_dt=later, gate=gate)
    assert entry(out, PENDING)["action"] == "cleared-dead"
    assert lease.load_record(repo, PENDING) is None
    assert entry(out, PROVEN)["action"] == "kept"


def test_unscoped_pass_is_unchanged(repo):
    """No gate scope is the pre-gate behaviour: both records
    pulse on cadence, hosts or no hosts."""
    seed_pair(repo)
    calls = []
    out = lease.reap(make_stub({PROVEN, PENDING}, calls), repo, now_dt=NOW)
    assert entry(out, PROVEN)["pulse"] == "ok"
    assert entry(out, PENDING)["pulse"] == "ok"
    assert "gate" not in out


def test_malformed_gate_scope_refuses():
    """(d) A malformed pending set is a refusal at parse
    time, never a silent pass: bad tokens raise, and a probe
    host that is not pending raises."""
    with pytest.raises(ValueError):
        lease.parse_gate_scope("bad host", None)
    with pytest.raises(ValueError):
        lease.parse_gate_scope("ok.example", "other.example")
    with pytest.raises(ValueError):
        lease.GateScope(pending_hosts=frozenset({"bad host"}))
    with pytest.raises(ValueError):
        lease.GateScope(pending_hosts=frozenset({"ok.example"}), probe_hosts=frozenset({"*.example"}))
    empty = lease.parse_gate_scope(None, None)
    assert empty.pending_hosts == frozenset() and empty.probe_hosts == frozenset()
    parsed = lease.parse_gate_scope("a.example, b.example", "b.example")
    assert parsed.pending_hosts == frozenset({"a.example", "b.example"})
    assert parsed.probe_hosts == frozenset({"b.example"})
