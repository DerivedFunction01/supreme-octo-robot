"""Handler/programme directory: the pinned upsert
semantics and stored-row validation."""

import unittest

from registry.attention import directory
from registry.store import Registry


class DirectoryTests(unittest.TestCase):

    def test_handler_upsert_requires_handle_and_label(self):
        reg = Registry()
        with self.assertRaises(ValueError):
            directory.upsert_handler(reg, {"handle": "@x"})
        with self.assertRaises(ValueError):
            directory.upsert_handler(reg, {"label": "x"})
        entry = directory.upsert_handler(
            reg, {"handle": "@x", "label": "X"})
        self.assertEqual(entry["color_slot"], 1)
        self.assertEqual(entry["icon"], "dot")
        self.assertIsNone(entry["thread_id"])
        self.assertIs(entry["ui_surface"], False)
        self.assertIs(entry["retired"], False)

    def test_handler_upsert_preserves_and_coerces(self):
        reg = Registry()
        directory.upsert_handler(reg, {
            "handle": "@x", "label": "X", "color_slot": 4,
            "thread_id": "chat-1", "ui_surface": 1})
        entry = directory.upsert_handler(
            reg, {"handle": "@x", "label": "X renamed"})
        self.assertEqual(entry["label"], "X renamed")
        self.assertEqual(entry["color_slot"], 4)
        self.assertEqual(entry["thread_id"], "chat-1")
        self.assertIs(entry["ui_surface"], True)  # coerced

    def test_handler_validation(self):
        self.assertEqual(directory.validate_handler_row(
            {"handle": "@x", "label": "X"}), [])
        self.assertEqual(directory.validate_handler_row(
            {"handle": "@x", "label": "X",
             "thread_id": None, "ui_surface": False}), [])
        self.assertTrue(directory.validate_handler_row(
            {"label": "X"}))
        self.assertTrue(directory.validate_handler_row(
            {"handle": "@x", "label": "X",
             "color_slot": "red"}))
        self.assertTrue(directory.validate_handler_row(
            {"handle": "@x", "label": "X",
             "ui_surface": "yes"}))

    def test_programme_upsert_and_validation(self):
        reg = Registry()
        entry = directory.upsert_programme(reg, {
            "slug": "demo", "label": "Demo",
            "handles": ["@x"], "venue": "colab",
            "cadence_minutes": 15,
            "staffing_band": {"min": 2, "max": 4}})
        self.assertEqual(entry["rule_text"], "")
        self.assertEqual(entry["settled"], [])
        self.assertEqual(entry["venue"], "colab")
        self.assertIs(directory.find_programme(reg, "demo"),
                      entry)
        self.assertIsNone(directory.find_programme(reg, "no"))
        self.assertEqual(
            directory.validate_programme_row(entry), [])
        for bad in ({"slug": "a/b", "label": "x"},
                    {"slug": ".hid", "label": "x"},
                    {"slug": "ok"},
                    {"slug": "ok", "label": "x",
                     "venue": "mars"},
                    {"slug": "ok", "label": "x",
                     "cadence_minutes": 0},
                    {"slug": "ok", "label": "x",
                     "staffing_band": {"min": 5, "max": 2}},
                    {"slug": "ok", "label": "x",
                     "handles": "@x"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                directory.upsert_programme(reg, bad)

    def test_programme_band_may_be_null_as_captured(self):
        row = {"slug": "p", "label": "P",
               "staffing_band": None, "venue": "none",
               "contract_path": None}
        self.assertEqual(
            directory.validate_programme_row(row), [])


if __name__ == "__main__":
    unittest.main()
