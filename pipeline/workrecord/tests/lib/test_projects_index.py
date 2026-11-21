"""lib/derived/projects: the canonical project index
(SPEC §21) — the sweep and the census joined into ONE
identity space.

Fixtures are plain dicts: sweep summary rows and
census summaries in their served shapes. Cases pin
the consolidation's rules: an adopted project and its
census main checkout are one row keyed by slug; a
linked worktree is a checkout, never a peer; a
manifest-less main checkout is a repository-only row;
scratch mains are excluded and counted; a missing
registry row folds into its project by root, else
stands as a missing row; exposure totals count
canonical mains only.
"""

import unittest

from lib.derived import projects as projects_mod

CAPTURED = "2026-11-20T12:00:00+00:00"


def sweep_row(slug, root, name=None):
    return {"slug": slug, "name": name or slug,
            "root": root,
            "sections": {"entries": True, "todos": True,
                         "plans": True,
                         "registry_declared": True,
                         "plans_declared": True},
            "also_at": []}


def summary(repo_id, root, **over):
    base = {
        "id": repo_id, "name": repo_id.rsplit("/", 1)[-1],
        "root": root, "is_worktree": False,
        "parent_id": None, "branch": "main",
        "head": "abc123", "head_full": "abc123full",
        "head_short": "abc123", "head_subject": "tip",
        "upstream": "origin/main", "ahead": 0, "behind": 0,
        "dirty_counts": {"staged": 0, "unstaged": 0,
                         "untracked": 0},
        "is_clean": True, "error": None, "remotes": [],
        "publication": "tracking",
        "sync": {"state": "synced", "unpushed_count": 0,
                 "oldest_unpushed_at": None},
        "exposure": {"level": "backed_up", "commits": 0,
                     "files": 0},
        "registry": None,
    }
    base.update(over)
    return base


class IdentityMapTests(unittest.TestCase):
    def test_slug_and_worktree_fold(self):
        sweep = [sweep_row("alpha", "/ws/alpha")]
        census = [
            {"id": "alpha", "root": "/ws/alpha",
             "is_worktree": False, "parent_id": None},
            {"id": "alpha-wt", "root": "/ws/alpha-wt",
             "is_worktree": True, "parent_id": "alpha"},
            {"id": "solo", "root": "/ws/solo",
             "is_worktree": False, "parent_id": None},
        ]
        id_map = projects_mod.identity_map(sweep, census)
        self.assertEqual(id_map["alpha"], "alpha")
        self.assertEqual(id_map["alpha-wt"], "alpha")
        self.assertEqual(id_map["solo"], "solo")


class BuildIndexTests(unittest.TestCase):
    def test_adopted_and_repository_only_rows(self):
        sweep = [sweep_row("alpha", "/ws/alpha")]
        summaries = [
            summary("alpha", "/ws/alpha"),
            summary("alpha-wt", "/ws/alpha-wt",
                    is_worktree=True, parent_id="alpha"),
            summary("delta", "/ws/delta",
                    dirty_counts={"staged": 1,
                                  "unstaged": 2,
                                  "untracked": 0},
                    sync={"state": "ahead",
                          "unpushed_count": 3,
                          "oldest_unpushed_at": None},
                    publication="local_only"),
        ]
        index = projects_mod.build_index(
            sweep, summaries, {}, [], CAPTURED)
        rows = {row["id"]: row for row in index["projects"]}
        self.assertEqual(set(rows), {"alpha", "delta"})
        alpha = rows["alpha"]
        self.assertEqual(alpha["membership"], "adopted")
        self.assertEqual(
            [c["id"] for c in alpha["checkouts"]],
            ["alpha", "alpha-wt"])
        self.assertEqual(alpha["code"]["branch"], "main")
        delta = rows["delta"]
        self.assertEqual(delta["membership"],
                         "repository-only")
        self.assertIsNone(delta["slug"])
        # Exposure counts canonical mains only: the
        # worktree's (clean) summary contributes
        # nothing; delta's 3 unpushed + 3 dirty files
        # and local-only publication are the totals.
        exposure = index["exposure"]
        self.assertEqual(exposure["tracked"], 2)
        self.assertEqual(exposure["unpushed_commits"], 3)
        self.assertEqual(exposure["uncommitted_repos"], 1)
        self.assertEqual(exposure["uncommitted_files"], 3)
        self.assertEqual(exposure["local_only"], 1)
        self.assertEqual(index["excluded_scratch"], 0)

    def test_scratch_main_excluded_and_counted(self):
        summaries = [
            summary("gate-clone", "/ws/scratch/gate-clone"),
            summary("real", "/ws/real"),
        ]
        index = projects_mod.build_index(
            [], summaries, {}, ["/ws/scratch"], CAPTURED)
        self.assertEqual(
            [row["id"] for row in index["projects"]],
            ["real"])
        self.assertEqual(index["excluded_scratch"], 1)

    def test_missing_row_folds_into_project_by_root(self):
        sweep = [sweep_row("alpha", "/ws/alpha")]
        entry = {"display_name": "Alpha",
                 "project": "", "expected": "published",
                 "pinned": True, "ignored": False,
                 "notes": "", "root": "/ws/alpha",
                 "first_seen": CAPTURED,
                 "last_seen": CAPTURED}
        summaries = [
            summary("alpha", "/ws/alpha"),
            {"id": "alpha", "name": "alpha",
             "root": "/ws/alpha", "is_worktree": False,
             "parent_id": None, "missing": True,
             "error": None, "registry": entry},
            {"id": "gone", "name": "gone",
             "root": "/ws/gone", "is_worktree": False,
             "parent_id": None, "missing": True,
             "error": None,
             "registry": {**entry, "root": "/ws/gone",
                          "display_name": "Gone"}},
        ]
        index = projects_mod.build_index(
            sweep, summaries, {}, [], CAPTURED)
        rows = {row["id"]: row for row in index["projects"]}
        # The found alpha row stands (not missing); the
        # duplicate missing summary for the same root
        # does not create a second row. The truly gone
        # repo stands as its own missing row.
        self.assertIn("alpha", rows)
        self.assertFalse(rows["alpha"]["missing"])
        self.assertIn("gone", rows)
        self.assertTrue(rows["gone"]["missing"])
        self.assertEqual(rows["gone"]["membership"],
                         "missing")


if __name__ == "__main__":
    unittest.main()
