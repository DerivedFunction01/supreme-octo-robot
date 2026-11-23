"""The feeds document prime's size guard
(assemble.prime_document_cache): a persisted
document above the configured bound (config
feeds_document_prime_max_bytes) is not primed —
the prime's parse transient runs ~6x the payload's
size, so an oversized persist (a 752 MB document
persisted by a scope-uncured assembly)
killed every restart before the service could
assemble the document's successor. The refusal is
read off the persisted payload's length (the shapes
database row's, since the database became the
persist), logs the refusal and the
size, and the cold assembly stands; a document at
or under the bound primes exactly as before.

The proof runs in a fresh interpreter (a driver
script over the shared fixture workspace), the same
way the other document suites' do. The driver
assembles once to learn the fixture document's real
persisted size, then sets the bound one byte under
it (the document is oversized: prime refuses,
nothing is primed, the cold path assembles) and
finally at it (the document primes, its payload
served from the store).
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
import json
import subprocess
import sys
from pathlib import Path

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))

from tests.server import fixture_ws

info = fixture_ws.build_fixture_workspace(base)
cfg = fixture_ws.fixture_config(base, base / "state-test")

import os
os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])

from server import assemble, shapestore

# Assemble once: the compute persists the fixture's
# real document, whose size the bound is then set
# against (the shapes row's payload length — the
# prime reads the same number off the row).
doc = assemble.build_feeds()
size = shapestore.open_store(
    assemble.CFG).payload_size(
    shapestore.FEEDS_DOCUMENT)

def fresh():
    assemble._document_store = assemble._DocumentStore()

def entry_present():
    return assemble._document_store._result is not None

# Oversized: the bound one byte under the document.
fresh()
assemble.CFG["feeds_document_prime_max_bytes"] = \
    size - 1
refused = assemble.prime_document_cache()
oversized = {
    "refused": refused,
    "payload_primed": assemble.feeds_payload_bytes()
        is not None,
    "entry_primed": entry_present(),
}
# The cold path stands: a build assembles fresh and
# returns the whole document.
cold = assemble.build_feeds()
oversized["cold_shape_keys"] = sorted(cold)
oversized["cold_alpha"] = "alpha" in \
    cold["projectFeeds"]

# At the bound: the same document primes as today,
# and the store serves its persisted bytes.
fresh()
assemble.CFG["feeds_document_prime_max_bytes"] = size
primed = assemble.prime_document_cache()
payload = assemble.feeds_payload_bytes()
at_bound = {
    "primed": primed,
    "entry_primed": entry_present(),
    "payload_alpha": "alpha" in json.loads(
        payload)["projectFeeds"],
}

result = {"size": size, "oversized": oversized,
          "at_bound": at_bound}
print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class FeedsDocumentPrimeGuardTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name) / "fx"
        proc = subprocess.run(
            [_python(), "-c", DRIVER, str(base),
             str(WORKRECORD_ROOT)],
            capture_output=True, text=True, timeout=280)
        if proc.returncode != 0:
            raise AssertionError(
                f"driver failed:\n{proc.stdout}\n"
                f"{proc.stderr}")
        cls.result = json.loads(
            proc.stdout.strip().splitlines()[-1])
        cls.stderr = proc.stderr

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_oversized_document_primes_nothing(self):
        over = self.result["oversized"]
        self.assertFalse(over["refused"])
        self.assertFalse(over["payload_primed"])
        self.assertFalse(over["entry_primed"])

    def test_refusal_logs_the_size(self):
        self.assertIn("prime refused", self.stderr)
        self.assertIn(f"{self.result['size']} bytes",
                      self.stderr)

    def test_cold_path_assembles_after_refusal(self):
        over = self.result["oversized"]
        self.assertEqual(
            over["cold_shape_keys"],
            sorted(["config", "home", "projects",
                    "projectFeeds", "projectsIndex",
                    "messages", "outbox", "settings",
                    "armedRows", "armedSkipped",
                    "statusVocabulary", "goals",
                    "goalsSource"]))
        self.assertTrue(over["cold_alpha"])

    def test_document_at_the_bound_primes(self):
        at = self.result["at_bound"]
        self.assertTrue(at["primed"])
        self.assertTrue(at["entry_primed"])
        self.assertTrue(at["payload_alpha"])


if __name__ == "__main__":
    unittest.main()
