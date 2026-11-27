"""Timing-ledger Step 2 (wb timing-ledger plan): the
file store's transition ledger.

Every censused file writer appends exactly one
transition line through the one helper
(lib/writes/transitions.py), in the same write as the
mutation it records; the todo front-matter gains `est`
and `fanout_position` as additive fields a pre-change
file never needed; and the transitions block survives
the fields editor and the rename driver verbatim —
including the rename's corpus rewrite, which must
never falsify a transition's recorded `old` value.
All state lives in tmp dirs — no live store touched.
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
WB_ROOT = HERE.parents[2]
sys.path.insert(0, str(WB_ROOT))

from lib import drain as drain_mod  # noqa: E402
from lib import registry as reg  # noqa: E402
from lib.plans import bundles as parser  # noqa: E402
from lib.writes import bundles as bundle_mod  # noqa: E402
from lib.writes import todo_rename  # noqa: E402
from lib.writes import transitions as tr  # noqa: E402

AT = "2026-11-27T16:00:00+00:00"

LEGACY_A = "t-01K8Q00000000000000000000A"
LEGACY_B = "t-01K8Q00000000000000000000B"

PRE_CHANGE_TODO = """---
id: pre-change-work
title: Pre-change work
status: todo
created: 2026-11-01
updated: 2026-11-01
---
Written before the ledger existed.
"""


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def todo_text(plans: Path, todo_id: str) -> str:
    for t in parser.list_todos(plans):
        if t["id"] == todo_id:
            return (plans / t["path"]).read_text(
                encoding="utf-8")
    raise AssertionError(f"todo {todo_id} not found")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plans = Path(self.tmp.name) / ".plans"
        self.plans.mkdir(parents=True)
        bundle_mod.create_bundle(
            self.plans, "work", today="2026-11-27")

    def create(self, title="Ledger work", **kw):
        kw.setdefault("created", "2026-11-27")
        kw.setdefault("updated", "2026-11-27")
        return bundle_mod.create_todo(
            self.plans, "work", title, **kw)


class TestHelper(unittest.TestCase):
    def test_append_to_empty_body_creates_block(self):
        body = tr.append_transition(
            "", verb="create", field="status",
            old=None, new="todo", at=AT)
        lines = body.split("\n")
        self.assertEqual(lines[0], tr.TRANSITIONS_HEADER)
        records = tr.transitions_in(body)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["at"], AT)
        self.assertEqual(records[0]["verb"], "create")
        # No actor supplied: the verb's own name stands.
        self.assertEqual(records[0]["actor"], "create")
        self.assertIsNone(records[0]["old"])
        self.assertEqual(records[0]["new"], "todo")

    def test_append_lands_inside_existing_block(self):
        body = tr.append_transition(
            "Notes first.", verb="create", field="status",
            old=None, new="todo", at=AT)
        body = tr.append_transition(
            body + "\n\nTrailing note.", verb="set-status",
            field="status", old="todo", new="doing", at=AT)
        self.assertEqual(
            body.count(tr.TRANSITIONS_HEADER), 1)
        records = tr.transitions_in(body)
        self.assertEqual([r["verb"] for r in records],
                         ["create", "set-status"])
        # The second line joined the block, ahead of the
        # trailing note that follows it.
        self.assertLess(body.index('"set-status"'),
                        body.index("Trailing note."))

    def test_explicit_actor_is_recorded(self):
        body = tr.append_transition(
            "", verb="set-status", actor="viewer",
            field="status", old="todo", new="doing", at=AT)
        self.assertEqual(
            tr.transitions_in(body)[0]["actor"], "viewer")


class TestCreate(Fixture):
    def test_create_appends_exactly_one_transition(self):
        todo = self.create()
        records = tr.transitions_in(
            todo_text(self.plans, todo["id"]))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["verb"], "create")
        self.assertEqual(records[0]["actor"], "create")
        self.assertEqual(records[0]["field"], "status")
        self.assertIsNone(records[0]["old"])
        self.assertEqual(records[0]["new"], "todo")

    def test_est_and_position_round_trip(self):
        todo = self.create(est="45m",
                           fanout_position="branch")
        text = todo_text(self.plans, todo["id"])
        self.assertIn("est: 45m", text)
        self.assertIn("fanout_position: branch", text)
        parsed = parser.parse_todo(text)
        self.assertTrue(parsed["valid"], parsed["errors"])
        self.assertEqual(parsed["est"], "45m")
        self.assertEqual(parsed["fanout_position"],
                         "branch")
        self.assertEqual(parsed["fields"]["est"], "45m")

    def test_fields_absent_by_default(self):
        todo = self.create()
        text = todo_text(self.plans, todo["id"])
        self.assertNotIn("est:", text)
        self.assertNotIn("fanout_position:", text)
        parsed = parser.parse_todo(text)
        self.assertIsNone(parsed["est"])
        self.assertIsNone(parsed["fanout_position"])

    def test_bad_position_refused(self):
        with self.assertRaises(bundle_mod.BundleError):
            self.create(fanout_position="sideways")


class TestStatusMove(Fixture):
    def test_pre_change_file_mutates_cleanly(self):
        bundle = self.plans / "2026-11-27-work"
        write(bundle / "todos" / "pre-change-work.md",
              PRE_CHANGE_TODO)
        before = parser.parse_todo(PRE_CHANGE_TODO)
        self.assertTrue(before["valid"], before["errors"])
        bundle_mod.set_todo_status(
            self.plans, "pre-change-work", "doing",
            today="2026-11-27")
        text = todo_text(self.plans, "pre-change-work")
        parsed = parser.parse_todo(text)
        self.assertTrue(parsed["valid"], parsed["errors"])
        self.assertEqual(parsed["status"], "doing")
        self.assertIsNone(parsed["est"])
        # Unchanged apart from the mutation itself and
        # the one appended transition.
        self.assertIn("Written before the ledger "
                      "existed.", text)
        records = tr.transitions_in(text)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["verb"], "set-status")
        self.assertEqual(records[0]["old"], "todo")
        self.assertEqual(records[0]["new"], "doing")

    def test_each_move_appends_one_line_one_block(self):
        todo = self.create()
        bundle_mod.set_todo_status(
            self.plans, todo["id"], "doing",
            today="2026-11-27")
        bundle_mod.set_todo_status(
            self.plans, todo["id"], "done",
            today="2026-11-27")
        text = todo_text(self.plans, todo["id"])
        self.assertEqual(
            text.count(tr.TRANSITIONS_HEADER), 1)
        records = tr.transitions_in(text)
        self.assertEqual([r["verb"] for r in records],
                         ["create", "set-status",
                          "set-status"])
        self.assertEqual(
            [(r["old"], r["new"]) for r in records[1:]],
            [("todo", "doing"), ("doing", "done")])


class TestFieldsEdit(Fixture):
    def test_block_and_checkpoints_survive_notes_edit(self):
        todo = self.create()
        bundle_mod.set_todo_status(
            self.plans, todo["id"], "doing",
            today="2026-11-27",
            note="progress-checkpoint: "
                 "2026-11-27T16:05:00+00:00 working")
        before = todo_text(self.plans, todo["id"])
        block_before = [ln for ln in before.split("\n")
                        if tr.is_block_line(ln)]
        checkpoint = [ln for ln in before.split("\n")
                      if ln.startswith(
                          "progress-checkpoint: ")]
        self.assertTrue(block_before)
        self.assertTrue(checkpoint)
        bundle_mod.set_todo_fields(
            self.plans, todo["id"], notes="Fresh notes.",
            today="2026-11-27")
        after = todo_text(self.plans, todo["id"])
        for line in block_before + checkpoint:
            self.assertIn(line, after)
        self.assertIn("Fresh notes.", after)
        records = tr.transitions_in(after)
        self.assertEqual(records[-1]["verb"],
                         "set-fields")
        self.assertEqual(records[-1]["field"], "notes")
        self.assertEqual(
            len(records),
            len(tr.transitions_in(before)) + 1)

    def test_title_edit_records_old_and_new(self):
        todo = self.create()
        bundle_mod.set_todo_fields(
            self.plans, todo["id"], title="Renamed title",
            today="2026-11-27")
        records = tr.transitions_in(
            todo_text(self.plans, todo["id"]))
        self.assertEqual(records[-1]["field"], "title")
        self.assertEqual(records[-1]["old"], "Ledger work")
        self.assertEqual(records[-1]["new"],
                         "Renamed title")


class TestPlantCommission(Fixture):
    def test_plant_appends_one_transition(self):
        todo = self.create()
        bundle_mod.plant_commission(
            self.plans, todo["id"],
            commissioned_by="owner commission",
            commissioned_at=AT, today="2026-11-27")
        records = tr.transitions_in(
            todo_text(self.plans, todo["id"]))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[-1]["verb"],
                         "plant-commission")
        self.assertEqual(records[-1]["field"],
                         "commissioned_by")
        self.assertEqual(records[-1]["new"],
                         "owner commission")


class TestRename(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.proj = base / "fixture-proj"
        self.plans = self.proj / ".plans"
        self.jobs = base / "jobs"
        self.armed = base / "armed"
        for d in (self.jobs, self.armed):
            d.mkdir(parents=True)
        write(self.proj / "workbench.yaml",
              "name: Fixture Proj\nslug: fixture-proj\n"
              "plans: .plans\n")
        todos = self.plans / "2026-11-01-work" / "todos"
        write(todos / f"{LEGACY_A}-long-work.md",
              f"---\nid: {LEGACY_A}\ntitle: Long work\n"
              f"status: todo\ncreated: 2026-11-01\n"
              f"updated: 2026-11-01\n---\n\n"
              f"First half; the second half is "
              f"{LEGACY_B}.\n")
        write(todos / f"{LEGACY_B}-long-work.md",
              f"---\nid: {LEGACY_B}\ntitle: Long work\n"
              f"status: todo\ncreated: 2026-11-01\n"
              f"updated: 2026-11-01\n---\n\n"
              f"See {LEGACY_A} for the first half.\n")

    def test_rename_transition_survives_corpus_rewrite(self):
        report = todo_rename.rename_todos(
            self.plans, apply=True,
            jobs_directory=self.jobs,
            armed_directory=self.armed)
        self.assertEqual(len(report["renamed"]), 2)
        by_legacy = {r["legacy_id"]: r["name"]
                     for r in report["renamed"]}
        for legacy, name in by_legacy.items():
            text = todo_text(self.plans, name)
            records = tr.transitions_in(text)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["verb"], "rename")
            self.assertEqual(records[0]["field"], "id")
            # The recorded old token stands verbatim —
            # the corpus rewrite did not falsify it.
            self.assertEqual(records[0]["old"], legacy)
            self.assertEqual(records[0]["new"], name)
            self.assertIn(f"legacy_id: {legacy}", text)
            self.assertNotIn(
                legacy,
                report["unresolved_references"])
        # References in bodies re-pointed as before.
        other = todo_text(
            self.plans, by_legacy[LEGACY_B])
        self.assertIn(by_legacy[LEGACY_A], other)


class TestImport(Fixture):
    def test_imported_todos_carry_import_verb(self):
        db = Path(self.tmp.name) / "workbench" \
            / "registry.db"
        reg.init_registry(db)
        reg.add_todo(db, "mock-open", "Mock open item",
                     notes="Still open in the fixture.")
        result = bundle_mod.import_db_todos(
            self.plans, db, today="2026-11-27")
        self.assertEqual(len(result["imported"]), 1)
        records = tr.transitions_in(
            todo_text(self.plans, "mock-open"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["verb"], "import-db")
        self.assertEqual(records[0]["actor"], "import-db")


class TestRaiseTail(Fixture):
    def test_tail_todos_carry_raise_tail_verb(self):
        bundle_mod.create_todo(
            self.plans, "work", "Alpha work",
            status="done", created="2026-11-27",
            updated="2026-11-27")
        bundle = next(
            b for b in parser.list_bundles(self.plans)
            if b["slug"] == "work")
        drain = drain_mod.drain_id(bundle["id"],
                                   bundle["todos"])
        minted = drain_mod.raise_tail(
            self.plans, bundle, ["Tail item"], drain)
        self.assertEqual(len(minted), 1)
        records = tr.transitions_in(
            todo_text(self.plans, minted[0]["id"]))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["verb"], "raise-tail")


class TestBundleWrites(Fixture):
    def test_create_bundle_with_plan_carries_transition(
            self):
        created = bundle_mod.create_bundle(
            self.plans, "planned", plan=True,
            today="2026-11-27")
        text = (Path(created["path"])
                / "plan.md").read_text(encoding="utf-8")
        records = tr.transitions_in(text)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["verb"],
                         "create-bundle")
        self.assertEqual(records[0]["new"],
                         "2026-11-27-planned")

    def test_contract_write_carries_and_preserves(self):
        bundle_mod.set_bundle_contract(
            self.plans, "work", programme="Prog",
            objective="Obj", complete_when="Done",
            work_record="Record")
        bundle_dir = next(
            b for b in parser.list_bundles(self.plans)
            if b["slug"] == "work")
        contract = Path(self.plans) / bundle_dir["path"] \
            / "contract.md"
        first = tr.transitions_in(
            contract.read_text(encoding="utf-8"))
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["verb"], "set-contract")
        bundle_mod.set_bundle_contract(
            self.plans, "work", programme="Prog",
            objective="Obj v2", complete_when="Done",
            work_record="Record")
        second = tr.transitions_in(
            contract.read_text(encoding="utf-8"))
        self.assertEqual(len(second), 2)
        self.assertEqual(second[0], first[0])
        parsed = parser.parse_contract(
            contract.parent)
        self.assertTrue(parsed["complete"])


if __name__ == "__main__":
    unittest.main()
