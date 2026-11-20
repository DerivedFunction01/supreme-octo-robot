"""Token callers (contract 01, SCH7): hashes only, the
closed scope set, read-fresh authentication, and the
pinned cleaning rules — a malformed entry is not a
caller, and a missing registry refuses every call."""

import hashlib
import unittest

from registry.callers import tokens
from registry.store import Registry

RAW = "a-test-token-that-exists-only-in-this-test"
DIGEST = hashlib.sha256(RAW.encode("utf-8")).hexdigest()


def make_registry():
    return Registry({
        "token_callers": {
            "good-caller": {"token_sha256": DIGEST,
                            "scopes": ["read", "send"]},
            "short-digest": {"token_sha256": "abc123",
                             "scopes": ["read"]},
            "no-real-scopes": {"token_sha256": DIGEST,
                               "scopes": ["teleport"]},
            "not-a-dict": "nope",
        },
    })


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.registry = make_registry()

    def test_cleaning_drops_malformed_entries(self):
        clean = tokens.load_token_callers(self.registry)
        self.assertEqual(sorted(clean), ["good-caller"])
        self.assertEqual(clean["good-caller"]["scopes"],
                         ["read", "send"])

    def test_authenticate_round_trip(self):
        self.assertEqual(
            tokens.authenticate(self.registry, RAW),
            ("good-caller", ["read", "send"]))

    def test_wrong_and_absent_tokens_refused(self):
        self.assertIsNone(tokens.authenticate(self.registry, "nope"))
        self.assertIsNone(tokens.authenticate(self.registry, ""))
        self.assertIsNone(tokens.authenticate(self.registry, None))

    def test_empty_registry_refuses_every_call(self):
        self.assertIsNone(tokens.authenticate(Registry.empty(), RAW))

    def test_authenticate_fresh_reads_the_file_each_call(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            Registry({"token_callers": {}}).save(path)
            self.assertIsNone(tokens.authenticate_fresh(path, RAW))
            # A mint lands without any restart: rewrite the
            # store and the very next call authenticates.
            make_registry().save(path)
            self.assertEqual(
                tokens.authenticate_fresh(path, RAW),
                ("good-caller", ["read", "send"]))

    def test_public_view_never_carries_hashes(self):
        import json
        view = tokens.public_view(self.registry)
        self.assertEqual(view, {"callers": {
            "good-caller": ["read", "send"]}})
        self.assertNotIn("token_sha256", json.dumps(view))
        self.assertNotIn(DIGEST, json.dumps(view))


if __name__ == "__main__":
    unittest.main()
