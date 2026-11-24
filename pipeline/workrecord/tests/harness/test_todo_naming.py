"""Slug identity for file todos (the owner's
naming ruling): the slug rule's accept/reject table, the
legacy form's transition acceptance, name derivation,
and the armed-name shapes the rule produces.

Pre-ruling records (the `t-<token>` fixtures in
test_bundles.py & friends) stay in the suite on purpose:
they pin that a legacy-form record still parses, lists,
and moves while a project awaits its rename pass.
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
WB_ROOT = HERE.parents[2]
sys.path.insert(0, str(WB_ROOT))

from lib.writes import bundles as bundle_mod  # noqa: E402
from lib.plans import bundles as parser  # noqa: E402
from lib.progress import attention as att  # noqa: E402
from lib.progress import schedule as ps  # noqa: E402


class TestSlugRule(unittest.TestCase):
    def test_accepts_github_like_names(self):
        for name in ("venue-runner", "a", "x1", "a-b-c",
                     "fix-2fa-login", "0-9"):
            self.assertIsNone(parser.check_todo_name(name),
                              name)
            self.assertEqual(parser.id_form(name), "slug")

    def test_rejects_non_slugs(self):
        for name in ("", "Upper", "has space", "-lead",
                     "trail-", "double--hyphen",
                     "under_score", "dot.name", "a" * 101,
                     "café"):
            self.assertIsNotNone(
                parser.check_todo_name(name), name)
            self.assertIsNone(parser.id_form(name), name)

    def test_length_boundary(self):
        self.assertIsNone(
            parser.check_todo_name("a" * 100))
        self.assertIsNotNone(
            parser.check_todo_name("a" * 101))

    def test_legacy_form_classified_not_valid(self):
        legacy = "t-01K8Q00000000000000000000A"
        self.assertEqual(parser.id_form(legacy), "legacy")
        self.assertIsNotNone(parser.check_todo_name(legacy))


class TestParseForms(unittest.TestCase):
    def _todo(self, id_line, extra=""):
        return parser.parse_todo(
            "---\n"
            f"id: {id_line}\n"
            "title: Some work\n"
            "status: todo\n"
            "created: 2026-11-01\n"
            "updated: 2026-11-01\n"
            f"{extra}"
            "---\n\nBody.\n",
            path="b/todos/x.md")

    def test_slug_record_parses_with_form(self):
        todo = self._todo("some-work")
        self.assertTrue(todo["valid"], todo["errors"])
        self.assertEqual(todo["id_form"], "slug")
        self.assertIsNone(todo["legacy_id"])

    def test_legacy_record_parses_as_pre_migration(self):
        todo = self._todo("t-01K8Q00000000000000000000A")
        self.assertTrue(todo["valid"], todo["errors"])
        self.assertEqual(todo["id_form"], "legacy")

    def test_migrated_record_carries_legacy_id_as_data(self):
        todo = self._todo(
            "some-work",
            extra="legacy_id: t-01K8Q00000000000000000000A\n")
        self.assertTrue(todo["valid"], todo["errors"])
        self.assertEqual(todo["id"], "some-work")
        self.assertEqual(todo["legacy_id"],
                         "t-01K8Q00000000000000000000A")

    def test_malformed_id_is_an_error(self):
        todo = self._todo("Not A Name")
        self.assertFalse(todo["valid"])
        self.assertTrue(any("GitHub-like" in e
                            for e in todo["errors"]))


class TestDerivation(unittest.TestCase):
    def test_derives_from_title(self):
        self.assertEqual(
            bundle_mod.derive_todo_name("Ship the shell", set()),
            "ship-the-shell")
        self.assertEqual(
            bundle_mod.derive_todo_name(
                "Fix: 2FA login (again!)", set()),
            "fix-2fa-login-again")

    def test_suffixes_until_free(self):
        taken = {"long-work", "long-work-2"}
        self.assertEqual(
            bundle_mod.derive_todo_name("Long work", taken),
            "long-work-3")

    def test_empty_title_falls_back(self):
        self.assertEqual(
            bundle_mod.derive_todo_name("!!!", set()), "todo")
        self.assertEqual(
            bundle_mod.derive_todo_name("!!!", {"todo"}),
            "todo-2")

    def test_long_titles_truncate_to_the_slug_cap(self):
        title = " ".join(["segment"] * 30)
        name = bundle_mod.derive_todo_name(title, set())
        self.assertLessEqual(len(name), 50)
        self.assertFalse(name.endswith("-"))
        self.assertIsNone(parser.check_todo_name(name))


class TestArmedNames(unittest.TestCase):
    def test_entry_and_row_carry_the_slug_verbatim(self):
        self.assertEqual(
            ps.entry_id("fixture-proj", "long-work"),
            "wb-progress-fixture-proj-long-work")
        self.assertEqual(
            att.row_id("fixture-proj", "long-work"),
            "wb-armed-fixture-proj-long-work")

    def test_entry_and_row_names_parse_back(self):
        todo = {
            "id": "long-work", "title": "Long work",
            "status": "doing", "bundle": "b",
            "archived": False, "body": "",
            "progress_check": "30m",
            "progress_armed": "2026-11-01T11:30:00+00:00",
        }
        text = (
            "id: wb-progress-fixture-proj-long-work\n"
            "kind: scripted\n"
            "run:\n"
            "  argv:\n"
            "    - ${WS}/workbench-viewer/wb\n"
            "    - --root\n"
            "    - ${WS}/fixture-proj\n"
            "    - progress-check\n"
            "    - long-work\n")
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / (
                "wb-progress-fixture-proj-long-work.yaml")
            entry.write_text(text, encoding="utf-8")
            self.assertEqual(
                ps.parse_entry_todo_id(entry), "long-work")
        # The row filename is never parsed back — the
        # feed joins on the row's own fields, which
        # carry the slug.
        row = att.render_row("fixture-proj", todo,
                             source_class="fixture")
        self.assertEqual(row["todo"], "long-work")
        self.assertEqual(row["handle"], "long-work")
        self.assertEqual(row["source"]["todo"], "long-work")


if __name__ == "__main__":
    unittest.main()
