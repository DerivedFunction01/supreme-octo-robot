"""The permission-card watcher (card-owner plan):
Step 6 — surfacing and hard-stop
verification.

This file is the watcher's shared test home: the spine
lane's Steps 2-4 suites live here too, beside the source
seam's pins in test_cardsource.py. The Step 6 section
below pins the surface the owner actually sees:

- one observed card surfaces as exactly one
  owner-actionable item in the served Today shape,
  counted once in the glance decision count, however
  many watcher passes observe it;
- a card the runtime resolves leaves the open queue
  with its wait, closed as a stored fact;
- an approved card with no measured resumption stays
  visible as verifying — open, counted, never fulfilled.

The served shape is contract 05's: the wait-rule engine
dedupes on a fact hash, a surfaced wait becomes exactly
one owner item (the owner-item schema), hard-stop
classes are always surfaced and never auto-applied;
the Today derivation counts open items (no decision
subrecord) of decision kind. The projections below
mirror that rule over watcher-produced state — the
contract the attention services consume, stated once,
here.

STEP 7 SWAP (done): wait production is the spine's
registry.cards.cardwatch, and the Step 6 pins below drive its
REAL pass (`cardwatch.run_pass` over the store), fed by
the frozen Step 1 seam (registry.cards.cardsource +
registry.cards.cardwatch_fakes). The plan-shape builder that
stood in for the core until it landed is removed; the
two stored-shape divergences it had encoded are now
read in the core's own form — closure lands on the wait
as `decision: resolved` with the outcome on the `card`
subrecord (never the outcome verb on the wait), and the
linked item is marked done on its face (`triage: done`)
rather than gaining a decision subrecord, so the
served-Today mirror below reads triage alongside the
decision subrecord. The module-surface audit at the end
skips, with its reason named, if registry.cards.cardwatch is
absent.

Deterministic throughout: fake source, fake clock,
temporary store. No live server, no wall clock, no
timing assertions. Every fixture is fictional.
"""

import ast
import importlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

# Per-module path seam (the suite's established form,
# as in attention's test modules): the pipeline root
# goes at sys.path[0] unconditionally, ahead of the
# runner's working directory — the registry package
# root carries its own `attention` subpackage, which
# would otherwise shadow the top-level attention
# package under the sharded runner (cwd-first path).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import attstore  # noqa: E402
from registry.cards import cardsource, cardwatch  # noqa: E402
from registry.cards import cardwatch_fakes as fakes  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
WAIT_CLASSES = (REPO_ROOT / "contracts" / "fixtures" /
                "attention-wait-classes.json")

# The specimens' raw payload strings (mirrors
# test_cardsource.POISON): they ride the raw records the
# fake source normalizes, and must survive nowhere in
# watcher-produced waits or items.
POISON = ("git -C fixture/repo push origin main",
          "send digest to the list",
          "fixture@example.invalid")

HANDLER_HANDLE = "@fixture-lane"
HANDLERS = [{"handle": HANDLER_HANDLE,
             "thread_id": fakes.RAW_CARD_CHAT["origin_chat_id"]}]


def hard_stop_classes():
    rows = json.loads(WAIT_CLASSES.read_text(encoding="utf-8"))
    return {row["name"] for row in rows if row["hard_stop"]}


# ---------------------------------------------------------------
# The contract-05 surfacing mirror. Wait production is
# the real watcher pass (registry.cards.cardwatch.run_pass,
# driven in SurfacingCase.run_pass below); what remains
# here is Step 6's own half — the served-shape projection
# the attention surface derives over watcher-produced
# state, stated once, in the module docstring's terms.

def surface_waits(state):
    """Contract 05's surfacing, mirrored: a pending
    hard-stop wait is surfaced (`decision: surfaced`) and
    becomes exactly one owner item, linked by wait_id —
    the item id is ATT5's handle:source_ref form. A wait
    already holding an item gains no second one."""
    stops = hard_stop_classes()
    linked = {item.get("wait_id") for item in state["items"]}
    for wait in state["waits"]:
        if wait.get("decision") != "pending" or \
                wait.get("wait_class") not in stops:
            continue
        wait["decision"] = "surfaced"
        if wait["id"] in linked:
            continue
        card = wait.get("card") or {}
        state["items"].append({
            "id": f"{wait['handle']}:permission-card-"
                  f"{card.get('approval_id', '')}",
            "handle": wait["handle"],
            "wait_id": wait["id"],
            "kind": "decision",
            "title": wait["summary"],
            "detail": card.get("scope", ""),
            "waiting_since": wait.get("at") or wait.get("posted_at"),
            "due_at": card.get("expires_at"),
            "notice_type": None,
            "verbs": ["approve_once", "deny"],
            "options": None,
            "fulfillment": "recorded",
            "decision": None,
            "decision_history": [],
        })


def served_today(state):
    """The served Today derivation over state: open items
    carry no decision subrecord and are not marked done
    on their face (the real closure's stored form:
    `triage: done`); the glance decision count is the
    open decision-kind items."""
    open_items = [i for i in state["items"]
                  if not i.get("decision")
                  and i.get("triage") != "done"]
    decisions = [i for i in open_items if i.get("kind") == "decision"]
    return {"open": open_items, "decisions": decisions,
            "decision_count": len(decisions)}


# ---------------------------------------------------------------
# Step 6 pins

class SurfacingCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="registry-cardwatch-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = attstore.AttentionStateStore(self.tmp / "state.json")
        self.clock = fakes.FakeClock()
        state = attstore.empty_state()
        state["handlers"] = [dict(h) for h in HANDLERS]
        self.store.save_state(state)

    def run_pass(self, source):
        """One REAL watcher pass over the fake source
        (registry.cards.cardwatch.run_pass over the store),
        then the surfacing mirror over the state the
        pass saved — so every assertion below reads
        state the unified writer carried."""
        result = cardwatch.run_pass(
            self.store, source, _at(self.clock()))
        self.assertEqual(result.kind, cardwatch.PASS_COMPLETE)
        state = self.store.load_state()
        surface_waits(state)
        self.store.save_state(state)
        return self.store.load_state()


class OrphanSurfacingTests(SurfacingCase):
    def test_cron_orphan_surfaces_as_exactly_one_item(self):
        source = fakes.FakeCardSource(
            self.clock, pending=[fakes.RAW_CARD_CRON])
        state = self.run_pass(source)
        waits = [w for w in state["waits"]
                 if w["wait_class"] == "permission_card"]
        self.assertEqual(len(waits), 1)
        wait = waits[0]
        # The orphan self-poster: no watching lane, so the
        # card posts under main with its provenance named.
        self.assertEqual(wait["handle"], "main")
        self.assertEqual(wait["card"]["origin_kind"], "orphan")
        self.assertEqual(wait["card"]["approval_id"],
                         "appr-fixture-002")
        self.assertEqual(wait["decision"], "surfaced")
        today = served_today(state)
        self.assertEqual(today["decision_count"], 1)
        item = today["decisions"][0]
        self.assertEqual(item["wait_id"], wait["id"])
        self.assertEqual(item["handle"], "main")
        self.assertIsNone(item["decision"])

    def test_second_pass_posts_no_twin(self):
        source = fakes.FakeCardSource(
            self.clock, pending=[fakes.RAW_CARD_CRON])
        self.run_pass(source)
        self.clock.set("2026-11-14T15:15:00Z")
        state = self.run_pass(source)
        waits = [w for w in state["waits"]
                 if w["wait_class"] == "permission_card"]
        self.assertEqual(len(waits), 1)
        self.assertEqual(len(state["items"]), 1)
        self.assertEqual(served_today(state)["decision_count"], 1)


class MappedCardTests(SurfacingCase):
    def test_chat_card_posts_under_its_handler_with_provenance(self):
        source = fakes.FakeCardSource(
            self.clock, pending=[fakes.RAW_CARD_CHAT])
        state = self.run_pass(source)
        wait = state["waits"][0]
        self.assertEqual(wait["handle"], HANDLER_HANDLE)
        self.assertEqual(wait["card"]["origin_kind"], "chat")
        self.assertEqual(wait["card"]["origin_id"],
                         "chat-fixture-alpha")
        today = served_today(state)
        self.assertEqual(today["decision_count"], 1)
        self.assertEqual(today["decisions"][0]["handle"],
                         HANDLER_HANDLE)
        self.assertEqual(today["decisions"][0]["wait_id"], wait["id"])

    def test_raw_payload_survives_nowhere_in_waits_or_items(self):
        source = fakes.FakeCardSource(
            self.clock, pending=list(fakes.RAW_PENDING))
        state = self.run_pass(source)
        # One pass, both provenance forms surface and count.
        self.assertEqual(served_today(state)["decision_count"], 2)
        for record in state["waits"] + state["items"]:
            blob = json.dumps(record, default=str)
            for poison in POISON:
                self.assertNotIn(poison, blob)
            self.assertNotIn("tool_params", blob)


class ResolutionSurfacingTests(SurfacingCase):
    def test_denied_card_leaves_the_open_queue_with_its_wait(self):
        # Pass 1: the card is observed with no history
        # outcome yet — it posts and surfaces, counted.
        source = fakes.FakeCardSource(
            self.clock, pending=[fakes.RAW_CARD_CRON])
        state = self.run_pass(source)
        self.assertEqual(served_today(state)["decision_count"], 1)
        # Pass 2: the history record stamps the denial;
        # the real pass closes the wait as a stored fact.
        self.clock.set("2026-11-14T15:15:00Z")
        source = fakes.FakeCardSource(
            self.clock, pending=[fakes.RAW_CARD_CRON],
            history_records={
                "appr-fixture-002": fakes.RAW_HISTORY_DENIED})
        state = self.run_pass(source)
        wait = state["waits"][0]
        self.assertEqual(wait["decision"], "resolved")
        self.assertEqual(wait["card"]["outcome"], "denied")
        # The stamp is the history record's own; the
        # store's decode heuristic restores it to a
        # datetime on load, so compare in that form.
        self.assertEqual(wait["card"]["decided_at"],
                         _at(fakes.RAW_HISTORY_DENIED["decided_at"]))
        entry = state["card_watch"]["appr-fixture-002"]
        self.assertEqual(entry["state"], "closed")
        self.assertEqual(entry["close_kind"], "denied")
        today = served_today(state)
        self.assertEqual(today["decision_count"], 0)
        self.assertEqual(today["open"], [])
        # A denial mints nothing: no send, no continuation.
        self.assertEqual(state["sends"], [])
        # The closure is a stored fact: it survives the
        # store round-trip unchanged.
        reloaded = self.store.load_state()
        self.assertEqual(served_today(reloaded)["decision_count"], 0)
        self.assertEqual(reloaded["waits"][0]["decision"], "resolved")
        self.assertEqual(
            reloaded["waits"][0]["card"]["outcome"], "denied")

    def test_approved_unresumed_card_stays_open_as_verifying(self):
        source = fakes.FakeCardSource(
            self.clock, pending=[fakes.RAW_CARD_CHAT])
        state = self.run_pass(source)
        self.assertEqual(served_today(state)["decision_count"], 1)
        # The history record stamps the approval; the
        # real pass moves the card to verifying — closure
        # waits on measured movement, none has occurred.
        self.clock.set("2026-11-14T15:15:00Z")
        source = fakes.FakeCardSource(
            self.clock, pending=[fakes.RAW_CARD_CHAT],
            history_records={
                "appr-fixture-001": fakes.RAW_HISTORY_APPROVED})
        state = self.run_pass(source)
        entry = state["card_watch"]["appr-fixture-001"]
        self.assertEqual(entry["state"], "verifying")
        self.assertEqual(entry["outcome"], "approved")
        # Still visible in the open queue, still counted,
        # and not recorded fulfilled anywhere.
        today = served_today(state)
        self.assertEqual(today["decision_count"], 1)
        self.assertIsNone(today["decisions"][0]["decision"])
        self.assertEqual(state["waits"][0]["decision"], "surfaced")
        self.assertFalse(state.get("fulfilled"))


class ModuleSurfaceAuditTests(unittest.TestCase):
    """The hard-stop floor on the watcher's own module
    surface: no public callable names a resolving verb,
    and no call in the module addresses a connector tool
    outside the two card reads. Skips — reason named —
    until the spine's registry.cards.cardwatch lands (an
    ImportError inside the module would also read as
    not-landed here; the Step 7 wiring re-checks)."""

    FORBIDDEN_TOOLS = {"chat_send", "ping_ack", "bridge_fulfill",
                       "bridge_poll", "workbench_read"}
    CARD_TOOLS = {cardsource.LIST_TOOL, cardsource.HISTORY_TOOL}

    def setUp(self):
        try:
            self.cardwatch = importlib.import_module("registry.cards.cardwatch")
        except ImportError:
            self.skipTest(
                "registry.cards.cardwatch not landed yet (spine Steps "
                "2-4); the audit activates on landing")

    def test_no_public_callable_names_a_resolving_verb(self):
        for name in dir(self.cardwatch):
            if name.startswith("_"):
                continue
            parts = set(name.split("_"))
            self.assertNotIn("approve", parts, name)
            self.assertNotIn("deny", parts, name)

    def test_module_calls_no_tool_outside_the_card_reads(self):
        tree = ast.parse(
            Path(self.cardwatch.__file__).read_text(encoding="utf-8"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.args and \
                    isinstance(node.args[0], ast.Constant) and \
                    isinstance(node.args[0].value, str):
                called.add(node.args[0].value)
        self.assertFalse(called & self.FORBIDDEN_TOOLS)
        named = {c for c in called if c.startswith("permissions_")}
        self.assertLessEqual(named, self.CARD_TOOLS)


# ---------------------------------------------------------------
# Spine pins (Steps 2–4): the real watcher core,
# registry.cards.cardwatch, over the same fakes and store.

SPINE_APPROVED_CHAT = {
    "approval_id": "appr-fixture-001",
    "outcome": "approved",
    "decided_at": "2026-11-14T15:03:00Z",
}
SPINE_DENIED_CHAT = {
    "approval_id": "appr-fixture-001",
    "outcome": "denied",
    "decided_at": "2026-11-14T15:04:00Z",
}
SPINE_APPROVED_CRON = {
    "approval_id": "appr-fixture-002",
    "outcome": "approved",
    "decided_at": "2026-11-14T15:04:00Z",
}


def _at(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


class SpineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="registry-cardwatch-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = self.tmp / "state.json"
        self.store = attstore.AttentionStateStore(self.path)
        state = attstore.empty_state()
        state["handlers"] = [dict(h) for h in HANDLERS]
        self.store.save_state(state)

    def watch(self, now, pending=(), history=None, stale=None,
              probe=None):
        source = fakes.FakeCardSource(
            fakes.FakeClock(), pending=pending,
            history_records=history, stale=stale)
        return cardwatch.run_pass(
            self.store, source, _at(now), movement_probe=probe)

    def state(self):
        return self.store.load_state()

    def waits(self):
        return self.state()["waits"]

    def entry(self, approval_id="appr-fixture-001"):
        return self.state()["card_watch"][approval_id]


class SpineReconcileTests(SpineCase):
    def test_mapped_card_posts_under_its_handler(self):
        result = self.watch("2026-11-14T15:00:00Z",
                            pending=[fakes.RAW_CARD_CHAT])
        self.assertEqual(result.kind, cardwatch.PASS_COMPLETE)
        (wait,) = self.waits()
        self.assertEqual(wait["handle"], HANDLER_HANDLE)
        self.assertEqual(wait["wait_class"], "permission_card")
        self.assertEqual(wait["decision"], "pending")
        self.assertEqual(wait["posted_by"], "card-watch")
        self.assertEqual(wait["idempotency_key"],
                         "permission-card:appr-fixture-001")
        self.assertEqual(wait["card"]["origin_kind"], "chat")
        self.assertEqual(wait["card"]["approval_id"],
                         "appr-fixture-001")
        entry = self.entry()
        self.assertEqual(entry["state"], "pending")
        self.assertEqual(entry["wait_id"], wait["id"])
        self.assertEqual(entry["handle"], HANDLER_HANDLE)

    def test_orphan_card_posts_under_main(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=[fakes.RAW_CARD_CRON])
        (wait,) = self.waits()
        self.assertEqual(wait["handle"], "main")
        self.assertEqual(wait["card"]["origin_kind"], "orphan")
        self.assertEqual(self.entry("appr-fixture-002")["handle"],
                         "main")

    def test_unmatched_chat_posts_as_orphan(self):
        raw = dict(fakes.RAW_CARD_CHAT,
                   approval_id="appr-fixture-009",
                   origin_chat_id="chat-fixture-stranger")
        self.watch("2026-11-14T15:00:00Z", pending=[raw])
        (wait,) = self.waits()
        self.assertEqual(wait["handle"], "main")
        self.assertEqual(wait["card"]["origin_kind"], "orphan")

    def test_second_pass_posts_no_twin(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=list(fakes.RAW_PENDING))
        self.watch("2026-11-14T15:15:00Z",
                   pending=list(fakes.RAW_PENDING))
        self.assertEqual(len(self.waits()), 2)
        keys = [w["idempotency_key"] for w in self.waits()]
        self.assertEqual(len(set(keys)), 2)

    def test_raw_payload_never_enters_saved_state(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=list(fakes.RAW_PENDING))
        blob = self.path.read_text(encoding="utf-8")
        for poison in POISON:
            self.assertNotIn(poison, blob)
        self.assertNotIn('"command"', blob)
        self.assertNotIn('"tool_params"', blob)

    def test_source_stale_is_a_non_run(self):
        before = self.path.read_bytes()
        stale = cardsource.SourceStale(cardsource.STALE_UNDRAINED)
        result = self.watch("2026-11-14T15:00:00Z", stale=stale)
        self.assertEqual(result.kind, cardwatch.PASS_SOURCE_STALE)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.waits(), [])


class SpineResolutionTests(SpineCase):
    def test_denial_closes_with_no_continuation_minted(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=[fakes.RAW_CARD_CRON],
                   history={"appr-fixture-002":
                            fakes.RAW_HISTORY_DENIED})
        (wait,) = self.waits()
        self.assertEqual(wait["decision"], "resolved")
        entry = self.entry("appr-fixture-002")
        self.assertEqual(entry["state"], "closed")
        self.assertEqual(entry["close_kind"], "denied")
        self.assertEqual(entry["outcome"], "denied")
        self.assertEqual(wait["card"]["outcome"], "denied")
        self.assertEqual(self.state()["sends"], [])
        # An orphan's outcome has no known lane to notify.
        self.assertFalse(entry["notify_due"])

    def test_denial_of_a_mapped_card_marks_notify_due(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=[fakes.RAW_CARD_CHAT],
                   history={"appr-fixture-001": SPINE_DENIED_CHAT})
        self.assertEqual(self.entry()["close_kind"], "denied")
        self.assertTrue(self.entry()["notify_due"])

    def test_expiry_outcome_closes_as_expired(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=[fakes.RAW_CARD_CRON],
                   history={"appr-fixture-002": {
                       "approval_id": "appr-fixture-002",
                       "outcome": "expired",
                       "decided_at": "2026-11-14T15:05:00Z"}})
        self.assertEqual(self.entry("appr-fixture-002")["close_kind"],
                         "expired")

    def test_other_terminal_outcome_closes_as_other(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=[fakes.RAW_CARD_CHAT],
                   history={"appr-fixture-001": {
                       "approval_id": "appr-fixture-001",
                       "outcome": "cancelled",
                       "decided_at": "2026-11-14T15:04:00Z"}})
        entry = self.entry()
        self.assertEqual(entry["state"], "closed")
        self.assertEqual(entry["close_kind"], "other")

    def test_disappearance_without_history_stays_open(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=[fakes.RAW_CARD_CHAT])
        self.watch("2026-11-14T15:15:00Z", pending=[])
        entry = self.entry()
        self.assertEqual(entry["state"], "resolution_unconfirmed")
        (wait,) = self.waits()
        self.assertEqual(wait["decision"], "pending")
        self.watch("2026-11-14T15:30:00Z", pending=[])
        self.assertEqual(self.entry()["state"],
                         "resolution_unconfirmed")
        self.assertEqual(self.waits()[0]["decision"], "pending")

    def test_clock_expiry_escalates_without_closing(self):
        # The cron specimen expires 15:52; at 16:00 it is
        # still listed pending with no history outcome.
        self.watch("2026-11-14T15:00:00Z",
                   pending=[fakes.RAW_CARD_CRON])
        self.watch("2026-11-14T16:00:00Z",
                   pending=[fakes.RAW_CARD_CRON])
        entry = self.entry("appr-fixture-002")
        self.assertEqual(entry["state"], "pending")
        self.assertIsNotNone(entry["expired_unresolved_at"])
        self.assertIsNotNone(entry["escalated_at"])
        self.assertEqual(self.waits()[0]["decision"], "pending")

    def test_linked_item_is_marked_done_on_closure(self):
        self.watch("2026-11-14T15:00:00Z",
                   pending=[fakes.RAW_CARD_CHAT])
        wait_id = self.waits()[0]["id"]
        state = self.state()
        state["items"].append({
            "id": f"wait-{wait_id}", "wait_id": wait_id,
            "handle": HANDLER_HANDLE, "kind": "approval",
            "triage": "open",
        })
        self.store.save_state(state)
        self.watch("2026-11-14T15:15:00Z",
                   pending=[fakes.RAW_CARD_CHAT],
                   history={"appr-fixture-001": SPINE_DENIED_CHAT})
        item = self.state()["items"][0]
        self.assertEqual(item["triage"], "done")
        self.assertEqual(self.entry()["item_id"], f"wait-{wait_id}")


class SpineVerificationTests(SpineCase):
    def approve_chat(self):
        self.watch("2026-11-14T15:05:00Z",
                   pending=[fakes.RAW_CARD_CHAT],
                   history={"appr-fixture-001": SPINE_APPROVED_CHAT})
        self.assertEqual(self.entry()["state"], "verifying")
        self.assertEqual(self.waits()[0]["decision"], "pending")

    def post_status(self, code, stamp):
        state = self.state()
        state["handler_status"][HANDLER_HANDLE] = {
            "status_code": code, "summary": "moving",
            "at": _at(stamp),
        }
        self.store.save_state(state)

    def test_approval_then_status_post_closes_verified(self):
        self.approve_chat()
        self.post_status("WORKING", "2026-11-14T15:20:00Z")
        self.watch("2026-11-14T15:20:00Z", pending=[])
        entry = self.entry()
        self.assertEqual(entry["state"], "closed")
        self.assertEqual(entry["close_kind"], "verified_resumed")
        self.assertEqual(entry["verification"], "verified")
        self.assertEqual(self.waits()[0]["decision"], "resolved")

    def test_terminal_status_post_is_completion(self):
        self.approve_chat()
        self.post_status("DONE", "2026-11-14T15:20:00Z")
        self.watch("2026-11-14T15:20:00Z", pending=[])
        entry = self.entry()
        self.assertEqual(entry["close_kind"], "verified_resumed")
        self.assertTrue(
            entry["movement"].startswith("terminal_status"))

    def test_status_post_before_the_decision_is_not_movement(self):
        self.post_status("WORKING", "2026-11-14T15:01:00Z")
        self.approve_chat()
        self.watch("2026-11-14T15:20:00Z", pending=[])
        self.assertEqual(self.entry()["state"], "verifying")

    def test_no_movement_mints_one_redrive_and_no_twin(self):
        self.approve_chat()
        self.watch("2026-11-14T15:33:00Z", pending=[])
        sends = self.state()["sends"]
        self.assertEqual(len(sends), 1)
        send = sends[0]
        self.assertEqual(send["producer"], "continuation")
        self.assertEqual(send["template"], "continuation")
        self.assertEqual(send["handle"], HANDLER_HANDLE)
        self.assertEqual(send["wait_id"], self.waits()[0]["id"])
        self.assertEqual(self.entry()["redrive_send_id"], send["id"])
        # The send stands undelivered: no twin at the
        # next pass inside the bound.
        self.watch("2026-11-14T15:40:00Z", pending=[])
        self.assertEqual(len(self.state()["sends"]), 1)
        self.assertEqual(self.entry()["state"], "verifying")

    def test_delivered_unanswered_neither_closes_nor_twins_early(self):
        self.approve_chat()
        self.watch("2026-11-14T15:33:00Z", pending=[])
        state = self.state()
        send = state["sends"][0]
        # Delivered, unanswered — evidenced the post-fold
        # way. The claim+ack lifecycle this pin once drove
        # is retired: the fold's load backfill settles
        # every standing undelivered send retired, so a
        # claim on the minted send is refused by design.
        # Delivery stands as a stamp on the record — the
        # history the backfill leaves untouched (its leg
        # skips delivered sends) and the state the
        # watcher's delivered branch reads, through
        # state_of, on the next pass.
        dispatch = send.setdefault("dispatch", {})
        dispatch["delivered_at"] = _at("2026-11-14T15:35:00Z")
        dispatch["delivery_ref"] = "submission-1"
        self.store.save_state(state)
        self.watch("2026-11-14T15:45:00Z", pending=[])
        self.assertEqual(self.entry()["state"], "verifying")
        self.assertEqual(len(self.state()["sends"]), 1)
        # Past the repeat bound and the one-hour bound: a
        # second attempt mints, and the row has escalated.
        self.watch("2026-11-14T16:04:00Z", pending=[])
        sends = self.state()["sends"]
        self.assertEqual(len(sends), 2)
        self.assertEqual(sends[1]["attempt"], 2)
        self.assertIsNotNone(self.entry()["escalated_at"])
        self.assertEqual(self.entry()["state"], "verifying")

    def test_orphan_approval_escalates_verification_unavailable(self):
        self.watch("2026-11-14T15:05:00Z",
                   pending=[fakes.RAW_CARD_CRON],
                   history={"appr-fixture-002": SPINE_APPROVED_CRON})
        self.assertEqual(self.entry("appr-fixture-002")["state"],
                         "verifying")
        self.watch("2026-11-14T15:40:00Z", pending=[])
        entry = self.entry("appr-fixture-002")
        self.assertEqual(entry["verification"],
                         "verification_unavailable")
        self.assertIsNotNone(entry["escalated_at"])
        self.assertEqual(entry["state"], "verifying")
        self.assertEqual(self.state()["sends"], [])
        self.assertEqual(self.waits()[0]["decision"], "pending")


if __name__ == "__main__":
    unittest.main()
