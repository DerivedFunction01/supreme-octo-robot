"""The feeds document's cold assembly at file scale
(assemble._build_feeds_compute): a census repo with
hundreds of files assembles completely and serves the
pinned shape; a file over the peek byte cap records
its deferred entry instead of a content read; and a
repo whose assembly raises degrades to that repo's
error entry while the rest of the document serves.

The proof runs in a fresh interpreter (a driver script
over the shared fixture workspace), the same way
test_feeds_document_cache's does: the server package
reads its config at import, so the fixture config must
be installed before the import. The driver's own
subprocess timeout is the completion bound — no
wall-clock assertion rides the result.
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
import time
from pathlib import Path

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))

from tests.server import fixture_ws

info = fixture_ws.build_fixture_workspace(base)
ws = Path(info["ws"])

def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args],
                   check=True, capture_output=True)

# A repo with many files: hundreds of small text files
# (each one a full peek + git-diff subprocess on the
# serial path), one file over the peek byte cap, and
# one small dataset.
many = ws / "manyfiles"
many.mkdir()
for i in range(240):
    (many / f"file-{i:03d}.txt").write_text(
        f"fixture line {i}\n", encoding="utf-8")
from lib.writes import files as files_mod
(many / "big.txt").write_bytes(
    b"x" * (files_mod.PEEK_MAX_BYTES + 1))
(many / "data.csv").write_text(
    "a,b\n1,2\n3,4\n", encoding="utf-8")
git(many, "init", "-q", "-b", "main")
git(many, "add", "-A")
git(many, "-c", "user.email=fixture@example.com",
    "-c", "user.name=Fixture", "commit", "-q",
    "-m", "manyfiles fixture root")
# The manifest makes manyfiles a swept project, so
# the document's detail scope (W4) details it as a
# project-linked repo; the manifest itself rides as
# one more (untracked) peeked file.
(many / "workbench.yaml").write_text(
    "name: Manyfiles\n"
    "registry: workbench/registry.db\n"
    "plans: .plans\n"
    "mockups: workbench/entries\n"
    "archive: workbench/archive\n"
    "catalog_origin: machine\n"
    "catalog_generality: deployment-specific\n"
    "catalog_use_case: work-tracking\n",
    encoding="utf-8")

# A second plain repo; the driver makes its assembly
# raise, to prove per-repo containment.
broken = ws / "brokenrepo"
broken.mkdir()
(broken / "README.md").write_text(
    "# Broken fixture repo\n", encoding="utf-8")
git(broken, "init", "-q", "-b", "main")
git(broken, "add", "-A")
git(broken, "-c", "user.email=fixture@example.com",
    "-c", "user.name=Fixture", "commit", "-q",
    "-m", "brokenrepo fixture root")
# Project-linked (see manyfiles above), so the
# scope reaches its assembly — and the raising
# guard below still fires for it.
(broken / "workbench.yaml").write_text(
    "name: Brokenrepo\n"
    "registry: workbench/registry.db\n"
    "plans: .plans\n"
    "mockups: workbench/entries\n"
    "archive: workbench/archive\n"
    "catalog_origin: machine\n"
    "catalog_generality: deployment-specific\n"
    "catalog_use_case: work-tracking\n",
    encoding="utf-8")

cfg = fixture_ws.fixture_config(base, base / "state-test")

import os
os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])

from server import assemble

real_document = assemble._repo_document

def guarded(record):
    if str(record["root"]).endswith("brokenrepo"):
        raise RuntimeError("fixture boom")
    return real_document(record)

assemble._repo_document = guarded

started = time.monotonic()
doc = assemble._build_feeds_compute()
elapsed = time.monotonic() - started

by_root = {}
for summary in doc["repos"]["repos"]:
    by_root[Path(summary["root"]).name] = summary["id"]
many_detail = doc["repoDetails"][by_root["manyfiles"]]
broken_detail = doc["repoDetails"][by_root["brokenrepo"]]

result = {
    "elapsed_s": elapsed,
    "shape_keys": sorted(doc),
    "many_peek_count": len(many_detail["peeks"]),
    "many_small_content": many_detail["peeks"][
        "file-000.txt"]["content"],
    "many_big_deferred": many_detail["peeks"][
        "big.txt"].get("deferred"),
    "many_big_content": many_detail["peeks"][
        "big.txt"]["content"],
    "many_big_size": many_detail["peeks"][
        "big.txt"]["size_bytes"],
    "many_datasets": sorted(many_detail["datasets"]),
    "broken_keys": sorted(broken_detail),
    "broken_error": broken_detail.get("error"),
    "broken_status": broken_detail.get("status"),
    "broken_files": broken_detail["files"]["entries"],
    "delta_scoped": "delta-repo" in by_root
        and by_root["delta-repo"]
        not in doc["repoDetails"],
}
print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class FeedsDocumentColdAssemblyTest(unittest.TestCase):

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

    def test_many_file_repo_assembles_the_pinned_shape(
            self):
        self.assertEqual(
            self.result["shape_keys"],
            sorted(["config", "home", "projects",
                    "projectFeeds", "repos", "repoDetails",
                    "messages", "outbox", "settings",
                    "armedRows", "armedSkipped",
                    "statusVocabulary", "goals",
                    "goalsSource"]))
        # 240 small files + big.txt + data.csv + the
        # linking manifest.
        self.assertEqual(self.result["many_peek_count"],
                         243)
        self.assertEqual(self.result["many_small_content"],
                         "fixture line 0\n")
        self.assertEqual(self.result["many_datasets"],
                         ["data.csv"])

    def test_plain_top_level_repo_gets_a_document(
            self):
        # delta-repo is the fixture's plain repo (no
        # manifest): present in the repos summaries
        # and, under the cured scope (leg 7a), present
        # in repoDetails too — delta_scoped (its
        # summary-only flag) no longer holds.
        self.assertFalse(self.result["delta_scoped"])

    def test_over_cap_file_records_a_deferred_peek(self):
        self.assertTrue(self.result["many_big_deferred"])
        self.assertIsNone(self.result["many_big_content"])
        self.assertGreater(self.result["many_big_size"],
                           200 * 1024)

    def test_raising_repo_degrades_to_its_error_entry(
            self):
        self.assertEqual(
            self.result["broken_keys"],
            sorted(["status", "files", "history", "peeks",
                    "datasets", "error"]))
        self.assertIn("fixture boom",
                      self.result["broken_error"])
        self.assertIsNone(self.result["broken_status"])
        self.assertEqual(self.result["broken_files"], [])


if __name__ == "__main__":
    unittest.main()
