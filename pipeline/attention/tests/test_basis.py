"""Basis detector pins (the decision-staleness plan,
Step 2): one fixture per detector — stale on the named
evidence, live on its absence, None where the record
cannot decide — plus the composed basis_for order and
the composition with Step 1's stale_state. Fixture
stores and temp trees only: no live store, no live
workspace, no repo .plans reads.
"""

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.domain import attention as dom  # noqa: E402
from attention.services.waits import basis, engine  # noqa: E402
from attention.services.waits import facts as wait_facts  # noqa: E402

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
TERMINAL = ("DONE", "CLOSED")

FACT_FIELDS = {
    "summary": "Land the formation",
    "status_code": "WORKING",
    "kind": None,
    "wait_class": "program_step",
    "program_approved": True,
    "reversible": True,
    "in_budget": True,
    "only_blocker": True,
}


def make_wait(**over):
    wait = {
        "id": "w0001",
        "handle": "lane-a",
        "posted_by": "lane-a",
        "posted_at": NOW,
        "decision": "pending",
        "last_fact_hash": None,
        **FACT_FIELDS,
        **over,
    }
    wait["fact_hash"] = engine.fact_hash(wait)
    return wait


def make_item(**over):
    item = {
        "id": "lane-a:ref-1",
        "handle": "lane-a",
        "kind": "decision",
        "title": "Decide the thing",
        "status_code": "BLOCKED-OWNER",
        "source_ref": "ref-1",
        "clears_at_source": True,
        "waiting_since": NOW,
        "triage": "open",
        **over,
    }
    return item


class FactDriftTests(unittest.TestCase):
    def test_unchanged_facts_are_live(self):
        wait = make_wait()
        verdict = basis.fact_drift(wait, {"wait_facts": {"w0001": dict(FACT_FIELDS)}})
        self.assertEqual(verdict, (False, "wait facts unchanged since surfacing"))

    def test_moved_facts_are_stale(self):
        wait = make_wait()
        moved = dict(FACT_FIELDS, summary="Land the other formation")
        verdict = basis.fact_drift(wait, {"wait_facts": {"w0001": moved}})
        self.assertTrue(verdict[0])
        self.assertIn("moved since surfacing", verdict[1])
        self.assertIn(wait["fact_hash"], verdict[1])

    def test_no_source_read_cannot_decide(self):
        wait = make_wait()
        self.assertIsNone(basis.fact_drift(wait, {}))
        self.assertIsNone(basis.fact_drift(wait, {"wait_facts": {}}))

    def test_no_surfaced_hash_cannot_decide(self):
        wait = make_wait()
        wait["fact_hash"] = None
        facts = {"wait_facts": {"w0001": dict(FACT_FIELDS)}}
        self.assertIsNone(basis.fact_drift(wait, facts))


class HandlerMovedTests(unittest.TestCase):
    def facts(self, code):
        return {
            "handler_status": {"lane-a": {"status_code": code}},
            "terminal_codes": TERMINAL,
        }

    def test_same_status_is_live(self):
        wait = make_wait()
        self.assertEqual(
            basis.handler_moved(wait, self.facts("WORKING")),
            (False, "handler lane-a still at WORKING"),
        )

    def test_terminal_status_is_stale(self):
        wait = make_wait()
        verdict = basis.handler_moved(wait, self.facts("DONE"))
        self.assertTrue(verdict[0])
        self.assertIn("terminal status DONE", verdict[1])

    def test_moved_status_is_stale(self):
        wait = make_wait()
        verdict = basis.handler_moved(wait, self.facts("REVIEW"))
        self.assertTrue(verdict[0])
        self.assertIn("WORKING → REVIEW", verdict[1])

    def test_unprobed_handler_cannot_decide(self):
        wait = make_wait()
        self.assertIsNone(basis.handler_moved(wait, {}))
        self.assertIsNone(
            basis.handler_moved(wait, {"handler_status": {"lane-a": {}}})
        )


PLAN_TEXT = """# Fixture plan

- [ ] First question?
  <!-- wb-question
  id=q-first
  type=choice
  options=yes | no
  recommended=yes
  answer=
  -->
- [ ] Second question?
  <!-- wb-question
  id=q-second
  type=choice
  options=adopt the priced table | basis only, no age caps
  recommended=adopt the priced table
  answer=adopt the priced table
  -->
"""


class PlanSentinelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".plans"
        self.root.mkdir()
        (self.root / "plan-a.md").write_text(PLAN_TEXT, encoding="utf-8")

    def item(self, ref):
        return make_item(source_ref=ref)

    def facts(self):
        return {"plans_root": self.root}

    def test_unanswered_sentinel_is_live(self):
        verdict = basis.plan_sentinel(self.item("plan-a.md#q-first"), self.facts())
        self.assertFalse(verdict[0])
        self.assertIn("still unanswered", verdict[1])

    def test_answered_sentinel_is_stale(self):
        verdict = basis.plan_sentinel(self.item("plan-a.md#q-second"), self.facts())
        self.assertTrue(verdict[0])
        self.assertIn("answered: adopt the priced table", verdict[1])

    def test_finished_plan_is_stale_even_unanswered(self):
        (self.root / "finished").mkdir()
        (self.root / "plan-a.md").rename(self.root / "finished" / "plan-a.md")
        verdict = basis.plan_sentinel(self.item("plan-a.md#q-first"), self.facts())
        self.assertTrue(verdict[0])
        self.assertIn("landed in finished/", verdict[1])

    def test_unresolvable_refs_cannot_decide(self):
        self.assertIsNone(basis.plan_sentinel(self.item("plain-ref"), self.facts()))
        self.assertIsNone(
            basis.plan_sentinel(self.item("plan-a.md#q-absent"), self.facts())
        )
        self.assertIsNone(
            basis.plan_sentinel(self.item("ghost.md#q-first"), self.facts())
        )
        self.assertIsNone(basis.plan_sentinel(self.item("plan-a.md#q-first"), {}))

    def test_non_decision_kind_is_not_probed(self):
        item = make_item(kind="action", source_ref="plan-a.md#q-second")
        self.assertIsNone(basis.plan_sentinel(item, self.facts()))

    def test_probe_reads_only_the_injected_root(self):
        probe = wait_facts.plan_sentinel("plan-a.md#q-second", self.root)
        self.assertEqual(probe["answer"], "adopt the priced table")
        self.assertFalse(probe["finished"])
        self.assertIsNone(wait_facts.plan_sentinel("../outside.md#q", self.root))


class PushMovedTests(unittest.TestCase):
    def item(self):
        return make_item(id="lane-a:push-1", kind="push_needed", source_ref="push-1")

    def verdict(self, measured):
        facts = {"push_facts": {"lane-a:push-1": measured}} if measured else {}
        return basis.push_moved(self.item(), facts)

    def test_superseded_head_is_stale(self):
        verdict = self.verdict({"state": "superseded", "head": "abcdef1234567"})
        self.assertTrue(verdict[0])
        self.assertIn("abcdef1", verdict[1])

    def test_current_head_is_live(self):
        verdict = self.verdict({"state": "current", "head": "abcdef1234567"})
        self.assertEqual(verdict, (False, "repo head unchanged since the push ask"))

    def test_gone_and_pushed_are_stale(self):
        self.assertTrue(self.verdict({"state": "gone"})[0])
        self.assertTrue(self.verdict({"state": "pushed"})[0])

    def test_unverifiable_or_unmeasured_cannot_decide(self):
        self.assertIsNone(self.verdict({"state": "unverifiable"}))
        self.assertIsNone(self.verdict(None))

    def test_other_kinds_are_not_probed(self):
        facts = {"push_facts": {"lane-a:ref-1": {"state": "gone"}}}
        self.assertIsNone(basis.push_moved(make_item(), facts))


class SourceClearedTests(unittest.TestCase):
    def test_standing_source_is_live(self):
        facts = {"source_records": {"ref-1": {"triage": "open", "decision": None}}}
        verdict = basis.source_cleared(make_item(), facts)
        self.assertEqual(verdict, (False, "source record ref-1 still stands"))

    def test_done_source_is_stale(self):
        facts = {"source_records": {"ref-1": {"triage": "done"}}}
        verdict = basis.source_cleared(make_item(), facts)
        self.assertTrue(verdict[0])
        self.assertIn("no longer stands", verdict[1])

    def test_gone_source_is_stale(self):
        verdict = basis.source_cleared(make_item(), {"source_records": {}})
        self.assertTrue(verdict[0])

    def test_terminal_source_is_stale(self):
        facts = {
            "source_records": {"ref-1": {"status_code": "DONE"}},
            "terminal_codes": TERMINAL,
        }
        self.assertTrue(basis.source_cleared(make_item(), facts)[0])

    def test_no_record_set_cannot_decide(self):
        self.assertIsNone(basis.source_cleared(make_item(), {}))

    def test_not_clears_at_source_is_not_probed(self):
        item = make_item(clears_at_source=False)
        self.assertIsNone(basis.source_cleared(item, {"source_records": {}}))

    def test_load_records_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = {
                "items": [{"id": "a:1", "triage": "open"}],
                "waits": [{"id": "w0001", "decision": "pending"}],
            }
            path.write_text(json.dumps(state), encoding="utf-8")
            records = wait_facts.load_records(path)
            self.assertEqual(set(records), {"a:1", "w0001"})
            self.assertTrue(wait_facts.source_standing("w0001", records))
            self.assertFalse(wait_facts.source_standing("absent", records))
            self.assertIsNone(wait_facts.source_standing("w0001", None))
            bad = Path(tmp) / "bad.json"
            bad.write_text("not json", encoding="utf-8")
            self.assertIsNone(wait_facts.load_records(bad))


class BasisForTests(unittest.TestCase):
    def test_fact_drift_beats_handler_evidence(self):
        wait = make_wait()
        facts = {
            "wait_facts": {"w0001": dict(FACT_FIELDS, summary="Moved summary")},
            "handler_status": {"lane-a": {"status_code": "DONE"}},
            "terminal_codes": TERMINAL,
        }
        verdict = basis.basis_for(wait, facts)
        self.assertTrue(verdict[0])
        self.assertIn("fact hash", verdict[1])

    def test_probed_live_does_not_mask_a_lower_stale(self):
        wait = make_wait()
        facts = {
            "wait_facts": {"w0001": dict(FACT_FIELDS)},
            "handler_status": {"lane-a": {"status_code": "DONE"}},
            "terminal_codes": TERMINAL,
        }
        verdict = basis.basis_for(wait, facts)
        self.assertTrue(verdict[0])
        self.assertIn("terminal status DONE", verdict[1])

    def test_probed_live_is_the_answer_when_nothing_is_stale(self):
        wait = make_wait()
        facts = {
            "handler_status": {"lane-a": {"status_code": "WORKING"}},
            "terminal_codes": TERMINAL,
        }
        self.assertEqual(
            basis.basis_for(wait, facts), (False, "handler lane-a still at WORKING")
        )

    def test_no_ports_cannot_decide(self):
        self.assertIsNone(basis.basis_for(make_wait(), {}))
        self.assertIsNone(basis.basis_for(make_item(), None))

    def test_verdict_composes_with_stale_state(self):
        wait = make_wait()
        record = {
            "waiting_since": NOW - timedelta(hours=1),
            "stale_after_hours": 72,
            "hard_stop": False,
        }
        facts = {
            "handler_status": {"lane-a": {"status_code": "CLOSED"}},
            "terminal_codes": TERMINAL,
        }
        verdict = basis.basis_for(wait, facts)
        adapted = {"stale": verdict[0], "evidence": verdict[1]}
        outcome = dom.stale_state(record, NOW, adapted)
        self.assertEqual(outcome["state"], dom.STALE_BASIS)
        self.assertEqual(dom.stale_state(record, NOW, None)["state"], dom.STALE_LIVE)


if __name__ == "__main__":
    unittest.main()
