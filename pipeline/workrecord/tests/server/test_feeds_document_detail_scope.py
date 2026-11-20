"""The feeds document's repo-detail scope
(assemble._linked_repo_ids): a full repo document
(files, peeks, datasets, history) assembles for the
workspace's own repos — a swept project's main
checkout and every other top-level main checkout
the census finds. The remaining census repos ride
the document as their repos-feed summary only, with
no repoDetails entry — worktrees and nested
discoveries: their untracked data files were most
of the document's weight (an ~871 MB persisted
document at production scale), and the adapter's
detail reads are optional-chained with summary
fallbacks, while the pinned per-repo routes serve
such a repo's detail on demand. (Scope history: the
W4 scope detailed project-linked repos only; the
leg 7a cure, 2026-11-15, extended it to plain
top-level repos — summary-only had left them
unbrowsable, no tree/dataset/save, because the
adapter builds repo documents from this document
alone.)

One exclusion stands in front of both arms (the
detail-scope ruling, 2026-11-16): a census repo
under one of the configured scratch roots (config
repos_detail_scratch_roots — the gate's scratch
trees, whose pristine per-gate clones are reset
and discarded) earns no document either; it rides
its census summary like any unlinked repo. The
driver plants a plain top-level repo under a
fixture scratch root to pin it.

The proof runs in a fresh interpreter (a driver
script over the shared fixture workspace), the same
way test_feeds_document_cold_assembly's does: the
server package reads its config at import, so the
fixture config must be installed before the import.
The fixture workspace supplies the halves by
construction — alpha is a manifest project in a git
repo (linked), delta-repo is a plain git repo with
no manifest (a top-level main checkout, detailed
under the cured scope) — and the driver adds a
linked worktree of alpha to pin that the parent_id
arm earns no document. The driver also drops
ignored files into alpha to pin the eager pass's
other scope rule: ignored entries stay in the files
block's listing but are never peeked (tracked and
untracked files are).
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
ws = Path(info["ws"])

def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args],
                   check=True, capture_output=True)

# A linked worktree of the alpha project checkout:
# the census keys it by parent_id ("alpha"), and the
# scope rule details main checkouts only — the
# worktree rides its summary.
git(info["alpha"], "worktree", "add", "-q",
    str(ws / "alpha-wt"), "-b", "alpha-wt-branch")

# Ignored entries in the linked checkout: a working-
# tree .gitignore (itself untracked, so itself
# peeked) drops build/ out of the eager payload
# pass — its files stay listed in the files block
# but earn no peek and no dataset entry. A plain
# untracked file pins the untracked arm alongside.
alpha_dir = Path(info["alpha"])
(alpha_dir / ".gitignore").write_text(
    "build/\n", encoding="utf-8")
(alpha_dir / "build").mkdir()
(alpha_dir / "build" / "output.txt").write_text(
    "build output\n", encoding="utf-8")
(alpha_dir / "build" / "data.csv").write_text(
    "a,b\n1,2\n", encoding="utf-8")
(alpha_dir / "notes-untracked.txt").write_text(
    "untracked fixture notes\n", encoding="utf-8")

cfg = fixture_ws.fixture_config(base, base / "state-test")

import os
os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])

# A plain top-level repo under the fixture's scratch
# root: by the leg-7a letter it earns a document,
# but the ruled scope excludes scratch trees — the
# config names the root, and the repo rides its
# census summary. The config is rewritten here,
# before the server import installs it.
cfg_doc = json.loads(cfg.read_text(encoding="utf-8"))
cfg_doc["repos_detail_scratch_roots"] = ["gate-scratch"]
cfg.write_text(json.dumps(cfg_doc, indent=2),
               encoding="utf-8")
scratch_repo = ws / "gate-scratch" / "clone-repo"
scratch_repo.mkdir(parents=True)
(scratch_repo / "README.md").write_text(
    "scratch clone fixture\n", encoding="utf-8")
git_env = {**os.environ,
           "GIT_AUTHOR_NAME": "Fixture",
           "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "Fixture",
           "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}

def git_in(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args],
                   check=True, capture_output=True,
                   env=git_env)

git_in(scratch_repo, "init", "-q", "-b", "main")
git_in(scratch_repo, "add", "-A")
git_in(scratch_repo, "commit", "-q", "-m",
       "scratch fixture root")

from server import assemble

doc = assemble._build_feeds_compute()
details = doc["repoDetails"]
summaries = {s["id"]: s for s in doc["repos"]["repos"]}
alpha = details.get("alpha") or {}
alpha_wt = summaries.get("alpha-wt") or {}
delta = summaries.get("delta-repo") or {}
delta_detail = details.get("delta-repo") or {}

def peek_content(detail, path):
    peek = (detail.get("peeks") or {}).get(path) or {}
    return peek.get("content")

probe_paths = (".gitignore", "notes-untracked.txt",
               "build/output.txt", "build/data.csv",
               "workbench.yaml")
alpha_kinds = {e["path"]: e.get("kind")
               for e in (alpha.get("files") or {})
               .get("entries", [])}
alpha_peeks = alpha.get("peeks") or {}
alpha_datasets = alpha.get("datasets") or {}

result = {
    "shape_keys": sorted(doc),
    "summary_ids": sorted(summaries),
    "detail_ids": sorted(details),
    "alpha_entry_kinds": {
        p: alpha_kinds.get(p) for p in probe_paths},
    "alpha_peeked": {
        p: p in alpha_peeks for p in probe_paths},
    "alpha_dataseted": {
        p: p in alpha_datasets for p in probe_paths},
    "alpha_untracked_peek": peek_content(
        alpha, "notes-untracked.txt"),
    "alpha_peek": peek_content(alpha, "workbench.yaml"),
    "alpha_history": len(
        (alpha.get("history") or {}).get("records", [])),
    "alpha_status_branch": (
        alpha.get("status") or {}).get("branch"),
    "alpha_wt_branch": alpha_wt.get("branch"),
    "delta_branch": delta.get("branch"),
    "delta_dirty": delta.get("dirty_counts"),
    "delta_detail_branch": (
        delta_detail.get("status") or {}).get("branch"),
    "delta_detail_readme": peek_content(
        delta_detail, "README.md"),
    "delta_detail_datasets": sorted(
        delta_detail.get("datasets") or {}),
    "scratch_branch": (
        summaries.get("gate-scratch/clone-repo") or {})
        .get("branch"),
}
print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class FeedsDocumentDetailScopeTest(unittest.TestCase):

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

    def test_document_shape_holds(self):
        self.assertEqual(
            self.result["shape_keys"],
            sorted(["config", "home", "projects",
                    "projectFeeds", "repos", "repoDetails",
                    "messages", "outbox", "settings",
                    "armedRows", "armedSkipped",
                    "statusVocabulary", "goals",
                    "goalsSource"]))

    def test_only_workspace_repos_get_documents(
            self):
        # The census sees all four repos; the document
        # details the workspace's own repos — the
        # project's main checkout and the plain
        # top-level repo — not the linked worktree and
        # not the scratch-root clone.
        self.assertEqual(
            self.result["summary_ids"],
            ["alpha", "alpha-wt", "delta-repo",
             "gate-scratch/clone-repo"])
        self.assertEqual(self.result["detail_ids"],
                         ["alpha", "delta-repo"])

    def test_scratch_root_repo_rides_as_summary_only(
            self):
        # gate-scratch/clone-repo is a plain top-level
        # main checkout by construction — the leg-7a
        # letter would detail it — but it stands under
        # the config's named scratch root, and the
        # ruled scope excludes scratch trees: it is in
        # the census summaries (its branch served)
        # with no repoDetails entry (the exact
        # detail_ids assertion above).
        self.assertEqual(self.result["scratch_branch"],
                         "main")

    def test_linked_documents_are_full(self):
        self.assertIn("name: Alpha",
                      self.result["alpha_peek"])
        self.assertEqual(
            self.result["alpha_status_branch"], "main")
        self.assertGreaterEqual(
            self.result["alpha_history"], 1)

    def test_linked_worktree_rides_as_summary_only(
            self):
        # alpha-wt is alpha's own worktree (census
        # parent_id "alpha"): no repoDetails entry (the
        # exact detail_ids assertion above), and the
        # summary carries the fields the adapter falls
        # back to — here its worktree branch.
        self.assertEqual(
            self.result["alpha_wt_branch"],
            "alpha-wt-branch")

    def test_ignored_files_listed_but_never_peeked(
            self):
        # The ignored entries ride the files block's
        # listing with their kind intact — the tree
        # the adapter renders is unchanged — but the
        # eager pass skips them: no peek, no dataset.
        kinds = self.result["alpha_entry_kinds"]
        self.assertEqual(kinds["build/output.txt"],
                         "ignored")
        self.assertEqual(kinds["build/data.csv"],
                         "ignored")
        self.assertFalse(
            self.result["alpha_peeked"]
            ["build/output.txt"])
        self.assertFalse(
            self.result["alpha_peeked"]
            ["build/data.csv"])
        self.assertFalse(
            self.result["alpha_dataseted"]
            ["build/data.csv"])
        # The tracked and untracked arms still peek:
        # the manifest (tracked), the .gitignore and
        # the plain notes file (both untracked).
        self.assertEqual(kinds["workbench.yaml"],
                         "tracked")
        self.assertTrue(
            self.result["alpha_peeked"]
            ["workbench.yaml"])
        self.assertEqual(kinds[".gitignore"],
                         "untracked")
        self.assertTrue(
            self.result["alpha_peeked"][".gitignore"])
        self.assertEqual(kinds["notes-untracked.txt"],
                         "untracked")
        self.assertEqual(
            self.result["alpha_untracked_peek"],
            "untracked fixture notes\n")

    def test_plain_top_level_repo_gets_a_document(
            self):
        # delta-repo (no manifest, no project) carries
        # a full document under the cured scope — the
        # leg 7a pin: its README peeks (the modified
        # working-tree text) and its CSV earns a
        # dataset entry. Its summary still rides too,
        # with the fields the adapter falls back to:
        # branch and dirty counts (the README is
        # modified and notes.txt untracked by
        # construction).
        self.assertEqual(self.result["delta_branch"],
                         "main")
        self.assertEqual(
            self.result["delta_dirty"],
            {"staged": 0, "unstaged": 1, "untracked": 1})
        self.assertEqual(
            self.result["delta_detail_branch"], "main")
        self.assertIn("Modified after the commit.",
                      self.result["delta_detail_readme"])
        self.assertEqual(
            self.result["delta_detail_datasets"],
            ["data/filings.csv"])


if __name__ == "__main__":
    unittest.main()
