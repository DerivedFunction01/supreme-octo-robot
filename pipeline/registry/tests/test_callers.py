"""Claim semantics (contract 01, RUN3): the merged
registry validates exactly as the pinned runner registry
did — registered validates, lane suffix rides its base,
presented-but-unregistered is refused, absent is
unattributed, active means detached-only."""

import unittest

from registry.callers import callers
from registry.store import Registry


def make_registry():
    return Registry({
        "thread_callers": {
            "callers": ["alpha-thread", "beta-thread"],
            "active": ["beta-thread"],
        },
    })


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.registry = make_registry()

    def test_registered_base_validates(self):
        self.assertEqual(
            callers.validate_claim(self.registry, "alpha-thread"),
            "alpha-thread")

    def test_lane_suffix_validates_against_base(self):
        self.assertEqual(
            callers.validate_claim(self.registry, "alpha-thread:lane-1"),
            "alpha-thread:lane-1")

    def test_machinery_always_valid(self):
        for name in ("panel", "standing", "test", "lease"):
            self.assertEqual(
                callers.validate_claim(self.registry, name), name)

    def test_unregistered_claim_is_refused(self):
        self.assertIsNone(
            callers.validate_claim(self.registry, "ghost-thread"))
        error = callers.claim_error(self.registry, flag="ghost-thread")
        self.assertIsNotNone(error)
        self.assertIn("unregistered caller", error)

    def test_absent_claim_is_unattributed_not_an_error(self):
        self.assertIsNone(callers.resolve_claim(self.registry))
        self.assertIsNone(callers.claim_error(self.registry))
        self.assertIsNone(
            callers.validate_claim(self.registry, None))

    def test_flag_over_env_and_presented_flag_governs(self):
        self.assertEqual(
            callers.resolve_claim(
                self.registry, flag=None, env="alpha-thread"),
            "alpha-thread")
        self.assertEqual(
            callers.resolve_claim(
                self.registry, flag="beta-thread", env="alpha-thread"),
            "beta-thread")
        # A presented-but-unregistered flag is refused even
        # with a valid env behind it: flag over env.
        self.assertIsNone(
            callers.resolve_claim(
                self.registry, flag="ghost", env="alpha-thread"))
        self.assertIsNotNone(
            callers.claim_error(
                self.registry, flag="ghost", env="alpha-thread"))

    def test_malformed_shapes_do_not_validate(self):
        for raw in ("", " alpha-thread", "alpha-thread:",
                    ":lane", "alpha-thread:lane:two", "Alpha"):
            self.assertIsNone(
                callers.validate_claim(self.registry, raw), raw)

    def test_active_marking(self):
        self.assertEqual(callers.active_bases(self.registry),
                         {"beta-thread"})
        self.assertTrue(
            callers.is_active(self.registry, "beta-thread:lane-9"))
        self.assertFalse(
            callers.is_active(self.registry, "alpha-thread"))
        self.assertFalse(
            callers.is_active(self.registry, "ghost"))

    def test_active_marking_ignores_unregistered_names(self):
        registry = Registry({"thread_callers": {
            "callers": ["alpha-thread"],
            "active": ["beta-thread", "alpha-thread"],
        }})
        self.assertEqual(callers.active_bases(registry),
                         {"alpha-thread"})

    def test_empty_registry_is_machinery_alone(self):
        empty = Registry.empty()
        self.assertEqual(callers.caller_bases(empty),
                         set(callers.MACHINERY_CALLERS))
        self.assertIsNone(
            callers.validate_claim(empty, "alpha-thread"))

    def test_malformed_store_file_is_machinery_alone(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "registry.json"
            bad.write_text("{not json", encoding="utf-8")
            registry = Registry.load(bad)
        self.assertEqual(callers.caller_bases(registry),
                         set(callers.MACHINERY_CALLERS))


class JournalTests(unittest.TestCase):
    def test_claims_journal_round_trip(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "var" / "caller-claims.jsonl"
            self.assertTrue(callers.append_claim(
                journal, "sess-1", "alpha-thread", "venue-lease"))
            self.assertTrue(callers.append_claim(
                journal, "sess-1", "beta-thread", "venue-run"))
            self.assertTrue(callers.append_claim(
                journal, "sess-2", None, "venue-run"))
            claims = callers.load_claims(journal)
        self.assertEqual(claims["sess-1"]["caller"], "beta-thread")
        self.assertNotIn("sess-2", claims)


if __name__ == "__main__":
    unittest.main()
