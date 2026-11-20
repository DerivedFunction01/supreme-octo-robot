"""The feeds document's per-repo diff batching
(assemble._repo_document): the eager peek pass pays
repo_peek's git-diff subprocess only for the files the
status derivation's porcelain pass names as staged or
unstaged. A dirty file's peek carries its real diff;
a clean file's and an untracked file's peeks carry
None — the value _repo_diff itself returns for them —
with content and sha256 intact.

The document proof runs in a fresh interpreter (a
driver script over the shared fixture workspace), the
same way test_feeds_document_cold_assembly's does: the
server package reads its config at import, so the
fixture config must be installed before the import.
The seam proof is a plain unit test over
lib/writes/files.repo_peek: with_diff=False must not
reach _repo_diff at all.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.writes import files as files_mod

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
import hashlib
import json
import subprocess
import sys
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

# One repo, four file states: clean tracked, staged,
# unstaged, untracked.
repo = ws / "diffrepo"
repo.mkdir()
(repo / "clean-a.txt").write_text(
    "alpha\n", encoding="utf-8")
(repo / "clean-b.txt").write_text(
    "beta\ngamma\n", encoding="utf-8")
(repo / "staged.txt").write_text(
    "staged base\n", encoding="utf-8")
(repo / "unstaged.txt").write_text(
    "unstaged base\n", encoding="utf-8")
git(repo, "init", "-q", "-b", "main")
git(repo, "add", "-A")
git(repo, "-c", "user.email=fixture@example.com",
    "-c", "user.name=Fixture", "commit", "-q",
    "-m", "diffrepo fixture root")
(repo / "staged.txt").write_text(
    "staged base\nstaged addition\n", encoding="utf-8")
git(repo, "add", "staged.txt")
(repo / "unstaged.txt").write_text(
    "unstaged base\nunstaged addition\n",
    encoding="utf-8")
(repo / "untracked.txt").write_text(
    "never committed\n", encoding="utf-8")
# The manifest makes diffrepo a swept project, so
# the document's detail scope (W4) details it as a
# project-linked repo; without it the repo would
# ride as a summary only and serve no peeks here.
(repo / "workbench.yaml").write_text(
    "name: Diffrepo\n"
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

doc = assemble._build_feeds_compute()
by_root = {}
for summary in doc["repos"]["repos"]:
    by_root[Path(summary["root"]).name] = summary["id"]
detail = doc["repoDetails"][by_root["diffrepo"]]
peeks = detail["peeks"]

def peek(name):
    p = peeks[name]
    return {"content": p.get("content"),
            "sha256": p.get("sha256"),
            "diff": p.get("diff")}

result = {
    "clean_a": peek("clean-a.txt"),
    "clean_b": peek("clean-b.txt"),
    "staged": peek("staged.txt"),
    "unstaged": peek("unstaged.txt"),
    "untracked": peek("untracked.txt"),
    "clean_a_sha_expected": hashlib.sha256(
        b"alpha\n").hexdigest(),
    "clean_b_sha_expected": hashlib.sha256(
        b"beta\ngamma\n").hexdigest(),
    "status_staged": [r["path"] for r in
                      detail["status"]["staged"]],
    "status_unstaged": [r["path"] for r in
                        detail["status"]["unstaged"]],
}
print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _git(cwd, *args):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    out = subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=T",
         "-c", "user.email=t@t", *args],
        capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)}: {out.stderr}")
    return out.stdout.strip()


class FeedsDocumentBatchedDiffsTest(unittest.TestCase):

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

    def test_status_names_the_dirty_paths(self):
        self.assertEqual(self.result["status_staged"],
                         ["staged.txt"])
        self.assertEqual(self.result["status_unstaged"],
                         ["unstaged.txt"])

    def test_dirty_files_carry_their_real_diff(self):
        self.assertIn("+staged addition",
                      self.result["staged"]["diff"])
        self.assertIn("+unstaged addition",
                      self.result["unstaged"]["diff"])

    def test_clean_files_carry_no_diff_and_intact_content(
            self):
        clean_a = self.result["clean_a"]
        self.assertIsNone(clean_a["diff"])
        self.assertEqual(clean_a["content"], "alpha\n")
        self.assertEqual(clean_a["sha256"],
                         self.result["clean_a_sha_expected"])
        clean_b = self.result["clean_b"]
        self.assertIsNone(clean_b["diff"])
        self.assertEqual(clean_b["content"], "beta\ngamma\n")
        self.assertEqual(clean_b["sha256"],
                         self.result["clean_b_sha_expected"])

    def test_untracked_file_carries_no_diff(self):
        untracked = self.result["untracked"]
        self.assertIsNone(untracked["diff"])
        self.assertEqual(untracked["content"],
                         "never committed\n")


class RepoPeekWithDiffSeamTest(unittest.TestCase):
    """repo_peek's with_diff seam over a real git
    fixture: False records the no-diff value without
    reaching _repo_diff (the module's one git
    subprocess); the default still derives it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text(
            "one\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "base")
        (self.repo / "a.txt").write_text(
            "one\ntwo\n", encoding="utf-8")

    def test_with_diff_false_never_derives(self):
        with mock.patch.object(
                files_mod, "_repo_diff",
                side_effect=AssertionError(
                    "diff derived")):
            out = files_mod.repo_peek(
                self.repo, "a.txt", with_diff=False)
        self.assertIsNone(out["diff"])
        self.assertEqual(out["content"], "one\ntwo\n")
        self.assertEqual(
            out["sha256"],
            hashlib.sha256(b"one\ntwo\n").hexdigest())

    def test_default_derives_the_diff(self):
        with mock.patch.object(
                files_mod, "_repo_diff",
                return_value="DIFF") as derive:
            out = files_mod.repo_peek(self.repo, "a.txt")
        derive.assert_called_once()
        self.assertEqual(out["diff"], "DIFF")


if __name__ == "__main__":
    unittest.main()
