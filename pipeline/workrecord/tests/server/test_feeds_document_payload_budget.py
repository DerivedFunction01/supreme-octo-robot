"""The per-repo eager-payload budget
(assemble._repo_document, config
feeds_repo_document_payload_max_bytes): the per-file
caps (a 200 KB peek, a 1 MB dataset page) have no
aggregate, so a corpus-shaped repo — thousands of
capped files — produced a 170+ MB document by itself
and the ruled corpus persisted 773 MB. Past the
budget, a file's peek takes the deferred form and
its dataset is omitted; the files listing stays
whole and the pinned routes serve the real content
on demand.

The proof runs in a fresh interpreter (a driver
script over the shared fixture workspace), the same
way the other document suites' do: alpha's document
is built at the default budget (nothing deferred)
and at a 200-byte budget (the tail deferred), and
the two are compared.
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

from server import assemble, repos_feed

record = repos_feed._census()["alpha"]

# A warm-up build first: the fixture's registry WAL
# files (-shm/-wal) appear when the tree is first
# read, and both measured builds must see the same
# tree.
assemble._repo_document(record)


def describe(doc):
    peeks = doc["peeks"]
    sizes = []
    for peek in peeks.values():
        sizes.append(len(json.dumps(
            peek, ensure_ascii=False).encode("utf-8")))
    for dataset in doc["datasets"].values():
        sizes.append(len(json.dumps(
            dataset, ensure_ascii=False).encode("utf-8")))
    return {
        "peeks": sorted(peeks),
        "deferred": sum(1 for p in peeks.values()
                        if p.get("deferred")),
        "datasets": len(doc["datasets"]),
        "payload_sum": sum(sizes),
        "max_single": max(sizes) if sizes else 0,
        "files": sorted(e["path"] for e in
                        doc["files"]["entries"]),
    }


full = describe(assemble._repo_document(record))
assemble.CFG[
    "feeds_repo_document_payload_max_bytes"] = 200
bounded = describe(assemble._repo_document(record))
print(json.dumps({"full": full, "bounded": bounded}))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class FeedsDocumentPayloadBudgetTest(unittest.TestCase):

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

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_default_budget_defers_nothing(self):
        full = self.result["full"]
        self.assertEqual(full["deferred"], 0)
        self.assertGreaterEqual(full["datasets"], 1)
        self.assertGreater(full["payload_sum"], 200)

    def test_past_the_budget_peeks_defer(self):
        bounded = self.result["bounded"]
        self.assertGreaterEqual(bounded["deferred"], 1)
        # No peek is dropped: every file peeked at the
        # default budget is present (deferred or whole)
        # at the small one.
        self.assertTrue(
            set(self.result["full"]["peeks"])
            <= set(bounded["peeks"]))

    def test_bounded_payload_is_bounded(self):
        full = self.result["full"]
        bounded = self.result["bounded"]
        self.assertLess(bounded["payload_sum"],
                        full["payload_sum"])
        # The file that crosses the budget is kept
        # whole; everything after it defers.
        self.assertLessEqual(
            bounded["payload_sum"],
            200 + full["max_single"])

    def test_listing_stays_whole(self):
        # The budget never drops a listing entry.
        self.assertTrue(
            set(self.result["full"]["files"])
            <= set(self.result["bounded"]["files"]))

    def test_datasets_never_grow_past_the_budget(self):
        self.assertLessEqual(
            self.result["bounded"]["datasets"],
            self.result["full"]["datasets"])
