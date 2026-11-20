"""Basis detectors (the decision-staleness plan, Step 2):
has the state a waiting record's ask was about moved
since the ask was surfaced? Each detector is a pure
reader over injected facts — a facts-provider dict — so
every verdict is fixture-testable without the live
store, the live workspace, or live threads.

A detector returns (stale, evidence) or None: None is
cannot-decide (its port is absent or the record does not
carry what it probes), never a guess — the age cap
governs a record no detector can probe. basis_for
composes the detectors in the plan's reliability order
(fact-hash drift, handler moved, plan sentinel, push
facts, source standing): the first stale verdict wins;
when none is stale, the first probed-live verdict is the
answer; when no detector could probe, None.

The verdict tuple is the detector layer's shape; the
domain evaluation (domain/attention.stale_state) takes
the same verdict as a {"stale", "evidence"} dict — the
tick wiring (Step 3) adapts between the two.

Facts ports (every key optional):
  wait_facts:     {wait_id: the wait's fact fields as
                  currently read at the source}
  handler_status: {handle: {"status_code": ...}} — the
                  handler thread's current status record
  terminal_codes: the status registry's terminal codes
  plans_root:     the .plans root plan_sentinel reads
  push_facts:     {item_id: a facts.measure result}
  source_records: {id: record} for source standing
"""

from __future__ import annotations

from attention.services.waits import engine
from attention.services.waits import facts as wait_facts


def fact_drift(record: dict, facts: dict):
    """A wait's facts, re-read at the source, no longer
    hash to the hash the wait was surfaced with (stamped
    on the wait at post time — ingest.post_wait)."""
    surfaced = record.get("fact_hash")
    if not surfaced:
        return None
    current = (facts.get("wait_facts") or {}).get(record.get("id"))
    if current is None:
        return None
    now_hash = engine.fact_hash(current)
    if now_hash != surfaced:
        return (
            True,
            f"wait facts moved since surfacing (fact hash {surfaced} → {now_hash})",
        )
    return (False, "wait facts unchanged since surfacing")


def handler_moved(record: dict, facts: dict):
    """The handler thread's current status is terminal,
    or has moved past the status the ask was surfaced
    under (the record's own status_code)."""
    handle = record.get("handle")
    if not handle:
        return None
    current = (facts.get("handler_status") or {}).get(handle)
    if not current:
        return None
    code = current.get("status_code")
    if code is None:
        return None
    if code in (facts.get("terminal_codes") or ()):
        return (True, f"handler {handle} is at terminal status {code}")
    surfaced = record.get("status_code")
    if surfaced is not None and code != surfaced:
        return (True, f"handler {handle} status moved {surfaced} → {code}")
    return (False, f"handler {handle} still at {code}")


def plan_sentinel(record: dict, facts: dict):
    """A decision item whose source names a plan sentinel
    (plan file + question id): the question was answered,
    or the plan landed in finished/ — either way the ask
    has been settled elsewhere."""
    if record.get("kind") != "decision":
        return None
    root = facts.get("plans_root")
    if root is None:
        return None
    probe = wait_facts.plan_sentinel(record.get("source_ref") or "", root)
    if probe is None:
        return None
    if probe["finished"]:
        return (
            True,
            f"plan {probe['plan']} landed in finished/ — "
            f"question {probe['question']} settled by the landing",
        )
    if probe["answered"]:
        return (
            True,
            f"plan sentinel {probe['question']} in {probe['plan']} "
            f"answered: {probe['answer'][:80]}",
        )
    return (
        False,
        f"plan sentinel {probe['question']} in {probe['plan']} still unanswered",
    )


def push_moved(record: dict, facts: dict):
    """A push_needed item's measured fact state (the
    existing facts.measure): the head moved past the ask,
    the repo retired, or the push already landed — the
    basis the ask stood on is gone. An unverifiable
    measurement cannot decide."""
    if record.get("kind") != "push_needed":
        return None
    measured = (facts.get("push_facts") or {}).get(record.get("id"))
    if measured is None:
        return None
    state = measured.get("state")
    if state == "superseded":
        head = (measured.get("head") or "")[:7]
        moved = f"repo head moved to {head}" if head else "repo head moved"
        return (True, f"{moved} since the push ask")
    if state == "gone":
        return (True, "repo gone since the push ask")
    if state == "pushed":
        return (True, "the push already landed — nothing left to push")
    if state == "current":
        return (False, "repo head unchanged since the push ask")
    return None


def source_cleared(record: dict, facts: dict):
    """A clears_at_source item whose source record no
    longer stands (done, decided, terminal, or gone)."""
    if not record.get("clears_at_source") or not record.get("source_ref"):
        return None
    records = facts.get("source_records")
    if records is None:
        return None
    standing = wait_facts.source_standing(
        record["source_ref"], records, facts.get("terminal_codes") or ()
    )
    if standing is None:
        return None
    if not standing:
        return (True, f"source record {record['source_ref']} no longer stands")
    return (False, f"source record {record['source_ref']} still stands")


DETECTORS = (fact_drift, handler_moved, plan_sentinel, push_moved, source_cleared)


def basis_for(record: dict, facts: dict | None):
    """The composed basis verdict for one waiting record:
    (stale, evidence) or None, per the module docstring."""
    facts = facts or {}
    live = None
    for detector in DETECTORS:
        verdict = detector(record, facts)
        if verdict is None:
            continue
        if verdict[0]:
            return verdict
        if live is None:
            live = verdict
    return live
