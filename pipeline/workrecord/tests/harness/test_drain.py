"""Drain detector tests (supervision plan Step 4):
lib/drain.py — the drain computation, the tail raise
through the writer path, and the archive act riding
the existing trim lifecycle — plus the server's drain
action shape.

Isolation: every fixture lives in a temporary
directory — hand-written todo files under a temp plans
dir, real git repos under a temp workspace, the trim's
archive/state roots pointed at temp dirs through the
module's own parameters. Nothing here touches a live
plans dir, a live worktree, or the live archive root.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lib import drain as drain_mod
from lib.plans import bundles as parser
from lib.writes import bundles as bundle_mod

NOW = 1795000000  # fixed fake clock for the trim passes

TAIL = ["Consolidation", "Doc updates", "Performance pass",
        "Reconcile the register"]


def _write_todo(plans_dir, bundle_id, name, title, status,
                updated="2026-11-18", body=""):
    todos_dir = Path(plans_dir) / bundle_id / "todos"
    todos_dir.mkdir(parents=True, exist_ok=True)
    text = (
        "---\n"
        f"id: {name}\n"
        f"title: {title}\n"
        f"status: {status}\n"
        "created: 2026-11-18\n"
        f"updated: {updated}\n"
        "---\n"
    )
    if body:
        text += "\n" + body + "\n"
    (todos_dir / f"{name}.md").write_text(
        text, encoding="utf-8")


def _bundle(plans_dir, bundle_id="2026-11-18-fixture-plan",
            todos=(("alpha-work", "Alpha work", "done"),
                   ("beta-work", "Beta work", "done"))):
    for name, title, status in todos:
        _write_todo(plans_dir, bundle_id, name, title, status)
    return bundle_id


def _declaration(bundle_id, **extra):
    decl = {"slug": "fixture-programme",
            "drain_bundles": [bundle_id],
            "drain_tail": list(TAIL)}
    decl.update(extra)
    return decl


def _todos(plans_dir, bundle_id):
    return parser.list_todos(plans_dir, bundle=bundle_id)


class DrainComputeTests(unittest.TestCase):

    def test_drained_requires_all_done(self):
        self.assertTrue(drain_mod.bundle_drained(
            [{"valid": True, "status": "done"}]))
        self.assertFalse(drain_mod.bundle_drained(
            [{"valid": True, "status": "doing"}]))
        self.assertFalse(drain_mod.bundle_drained(
            [{"valid": True, "status": "blocked"}]))
        self.assertFalse(drain_mod.bundle_drained(
            [{"valid": True, "status": "todo"}]))
        self.assertFalse(drain_mod.bundle_drained(
            [{"valid": False, "status": "done"}]))
        self.assertFalse(drain_mod.bundle_drained([]))

    def test_drain_id_stable_then_new_episode(self):
        todos = [{"id": "a", "updated": "2026-11-18"},
                 {"id": "b", "updated": "2026-11-18"}]
        first = drain_mod.drain_id("2026-11-18-x", todos)
        self.assertEqual(
            first, drain_mod.drain_id("2026-11-18-x", todos))
        todos.append({"id": "c", "updated": "2026-11-19"})
        self.assertNotEqual(
            first, drain_mod.drain_id("2026-11-18-x", todos))

    def test_tail_titles_defaults_and_declared(self):
        self.assertEqual(
            drain_mod.tail_titles({}),
            list(drain_mod.DEFAULT_TAIL_TITLES))
        self.assertEqual(
            drain_mod.tail_titles(
                {"drain_tail": ["A", {"title": "B"}, ""]}),
            ["A", "B"])


def _init_repo(path):
    """A throwaway git repo at `path`, so a drain pass's
    main-checkout resolution lands on the fixture itself
    and never on an ambient repo the temp dir might sit
    inside."""
    subprocess.run(["git", "init", str(path)],
                   check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(path), "symbolic-ref", "HEAD",
         "refs/heads/main"],
        check=True, capture_output=True, text=True)


class TailRaiseTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        _init_repo(self._tmp.name)
        self.plans = Path(self._tmp.name) / ".plans"
        self.plans.mkdir(parents=True)

    def _run(self, declarations, **kw):
        return drain_mod.run_project(
            self.plans, self._tmp.name, declarations, **kw)

    def test_last_todo_terminal_raises_declared_tail_once(self):
        bundle_id = _bundle(self.plans)
        outcome = self._run([_declaration(bundle_id)])[0]
        self.assertEqual(outcome["drained"], [bundle_id])
        raised = _todos(self.plans, bundle_id)
        self.assertEqual(len(raised), 2 + len(TAIL))
        tail = [t for t in raised
                if t["id"] not in ("alpha-work", "beta-work")]
        self.assertEqual(
            sorted(t["title"] for t in tail), sorted(TAIL))
        self.assertEqual(
            sorted(outcome["raised"]),
            sorted(t["id"] for t in tail))
        for t in tail:
            self.assertEqual(t["status"], "todo")
            self.assertIn(f"drain: {outcome['drain_ids'][0]}",
                          t["body"])
        # The same pass again: the tail stands open, so
        # the bundle is not drained and nothing re-raises.
        again = self._run([_declaration(bundle_id)])[0]
        self.assertEqual(again["drained"], [])
        self.assertEqual(again["raised"], [])
        self.assertEqual(
            len(_todos(self.plans, bundle_id)), 2 + len(TAIL))

    def test_raise_tail_idempotent_per_drain(self):
        bundle_id = _bundle(self.plans)
        bundles = parser.list_bundles(self.plans)
        bundle = next(b for b in bundles
                      if b["id"] == bundle_id)
        drain = drain_mod.drain_id(bundle_id, bundle["todos"])
        minted = drain_mod.raise_tail(
            self.plans, bundle, TAIL, drain)
        self.assertEqual(len(minted), len(TAIL))
        bundles = parser.list_bundles(self.plans)
        bundle = next(b for b in bundles
                      if b["id"] == bundle_id)
        self.assertEqual(
            drain_mod.raise_tail(
                self.plans, bundle, TAIL, drain), [])

    def test_doing_todo_raises_nothing(self):
        bundle_id = _bundle(
            self.plans,
            todos=(("alpha-work", "Alpha work", "doing"),
                   ("beta-work", "Beta work", "done")))
        outcome = self._run([_declaration(bundle_id)])[0]
        self.assertEqual(outcome["drained"], [])
        self.assertEqual(outcome["raised"], [])
        self.assertEqual(
            len(_todos(self.plans, bundle_id)), 2)

    def test_blocked_bundle_is_not_drained(self):
        bundle_id = _bundle(
            self.plans,
            todos=(("alpha-work", "Alpha work", "blocked"),
                   ("beta-work", "Beta work", "done")))
        outcome = self._run([_declaration(bundle_id)])[0]
        self.assertEqual(outcome["drained"], [])
        self.assertEqual(outcome["raised"], [])

    def test_second_drain_after_new_work_raises_again(self):
        bundle_id = _bundle(self.plans)
        decl = _declaration(bundle_id)
        first = self._run([decl])[0]
        self.assertEqual(len(first["raised"]), len(TAIL))
        # The tail is worked and completed, plus one new
        # piece of programme work lands and completes.
        for todo in _todos(self.plans, bundle_id):
            if todo["status"] != "done":
                bundle_mod.set_todo_status(
                    self.plans, todo["id"], "done")
        bundle_mod.create_todo(
            self.plans, bundle_id, "Follow-on work")
        follow = next(
            t for t in _todos(self.plans, bundle_id)
            if t["title"] == "Follow-on work")
        bundle_mod.set_todo_status(
            self.plans, follow["id"], "done")
        second = self._run([decl])[0]
        self.assertEqual(second["drained"], [bundle_id])
        self.assertNotEqual(second["drain_ids"],
                            first["drain_ids"])
        self.assertEqual(len(second["raised"]), len(TAIL))
        raised = _todos(self.plans, bundle_id)
        self.assertEqual(
            len(raised), 2 + len(TAIL) + 1 + len(TAIL))
        # The first episode's titles stand in the bundle,
        # so the second raise carries the drain qualifier.
        second_titles = sorted(
            t["title"] for t in raised
            if t["id"] in second["raised"])
        for title in TAIL:
            self.assertIn(
                f"{title} [{second['drain_ids'][0]}]",
                second_titles)

    def test_default_tail_set_when_undeclared(self):
        bundle_id = _bundle(self.plans)
        decl = {"slug": "fixture-programme",
                "drain_bundles": [bundle_id]}
        outcome = self._run([decl])[0]
        self.assertEqual(
            len(outcome["raised"]),
            len(drain_mod.DEFAULT_TAIL_TITLES))
        titles = sorted(
            t["title"] for t in _todos(self.plans, bundle_id)
            if t["id"] in outcome["raised"])
        self.assertEqual(
            titles, sorted(drain_mod.DEFAULT_TAIL_TITLES))

    def test_resolution_by_contract_path(self):
        bundle_id = _bundle(self.plans)
        decl = {"slug": "fixture-programme",
                "drain_tail": list(TAIL),
                "contract_path":
                    f"/elsewhere/.plans/{bundle_id}/contract.md"}
        outcome = self._run([decl])[0]
        self.assertEqual(outcome["drained"], [bundle_id])
        self.assertEqual(len(outcome["raised"]), len(TAIL))

    def test_unresolvable_programme_has_no_watch(self):
        _bundle(self.plans)
        outcome = self._run(
            [{"slug": "other-programme",
              "drain_tail": list(TAIL)}])[0]
        self.assertEqual(outcome["drained"], [])
        self.assertEqual(outcome["raised"], [])

    def test_no_progress_checkpoint_is_written(self):
        bundle_id = _bundle(self.plans)
        before = {
            p: p.read_bytes()
            for p in self.plans.rglob("*.md")
        }
        self._run([_declaration(bundle_id)])
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        for path in self.plans.rglob("*.md"):
            self.assertNotIn(
                "progress-checkpoint:",
                path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------
# The archive act: real git fixture repos, the real trim
# script, temp archive/state roots (the trim suite's own
# isolation pattern).
# ----------------------------------------------------------------

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}

BASE_EPOCH = 1794900000


def _git(cwd, *args, epoch=None):
    env = dict(os.environ)
    env.update(GIT_ENV)
    if epoch is not None:
        env["GIT_AUTHOR_DATE"] = f"@{epoch} +0000"
        env["GIT_COMMITTER_DATE"] = f"@{epoch} +0000"
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, env=env, capture_output=True, text=True)


def _touch_tree(tree, epoch):
    for path in Path(tree).rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            os.utime(path, (epoch, epoch))


def _fixture_repo(ws):
    """ws/repo-a (main) + ws/repo-a-wt1..wt4, activity
    staggered oldest wt1 → newest wt4."""
    repo = ws / "repo-a"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base", epoch=BASE_EPOCH)
    trees = {}
    for i in range(1, 5):
        tree = ws / f"repo-a-wt{i}"
        epoch = BASE_EPOCH + i * 10000
        _git(repo, "worktree", "add", "-b", f"lane/wt{i}",
             str(tree), epoch=epoch)
        (tree / f"work{i}.txt").write_text(
            f"work {i}\n", encoding="utf-8")
        _git(tree, "add", ".")
        _git(tree, "commit", "-m", f"work {i}", epoch=epoch)
        _touch_tree(tree, epoch + 10)
        trees[f"wt{i}"] = tree
    return repo, trees


def _standing(repo):
    out = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list",
         "--porcelain"],
        check=True, capture_output=True, text=True).stdout
    return {
        line[len("worktree "):]
        for line in out.splitlines()
        if line.startswith("worktree ")
    }


class ArchiveActTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name) / "ws"
        self.repo, self.trees = _fixture_repo(self.ws)
        self.plans = self.repo / ".plans"
        self.bundle_id = _bundle(self.plans)
        self.archive_root = self.ws / "worktree-archive"
        self.state_dir = self.ws / "state"

    def _run(self, **decl_extra):
        decl = _declaration(self.bundle_id, **decl_extra)
        return drain_mod.run_project(
            self.plans, self.repo, [decl], now_epoch=NOW,
            archive_root=self.archive_root,
            state_dir=self.state_dir)[0]

    def test_five_trees_archive_down_to_two(self):
        self.assertEqual(
            len(_standing(self.repo)), 5)
        outcome = self._run()
        self.assertEqual(len(outcome["raised"]), len(TAIL))
        archived = {a["tree"] for a in outcome["archived"]}
        self.assertEqual(
            archived, {"repo-a-wt1", "repo-a-wt2", "repo-a-wt3"})
        self.assertEqual(
            _standing(self.repo),
            {str(self.repo), str(self.trees["wt4"])})
        for name in ("repo-a-wt1", "repo-a-wt2", "repo-a-wt3"):
            packages = list(
                self.archive_root.glob(f"*/repo-a__{name}"))
            self.assertEqual(len(packages), 1)
            self.assertTrue(
                (packages[0] / "manifest.txt").is_file())
            self.assertTrue((packages[0] / "tree").is_dir())

    def test_scoped_archive_only_touches_declared_trees(self):
        scope = [str(self.trees["wt2"]), str(self.trees["wt3"])]
        outcome = self._run(worktree_roots=scope)
        archived = {a["tree"] for a in outcome["archived"]}
        self.assertEqual(archived, {"repo-a-wt2"})
        self.assertEqual(
            _standing(self.repo),
            {str(self.repo), str(self.trees["wt1"]),
             str(self.trees["wt3"]), str(self.trees["wt4"])})

    def test_no_raise_no_archive(self):
        # Bundle not drained (a doing todo): no tail, and
        # the trees all stand.
        _write_todo(self.plans, self.bundle_id, "live-work",
                    "Live work", "doing")
        outcome = self._run()
        self.assertEqual(outcome["raised"], [])
        self.assertEqual(outcome["archived"], [])
        self.assertEqual(len(_standing(self.repo)), 5)


# The server package reads its config at import, so the
# action surface is driven in a fresh interpreter with a
# fixture config installed first (the server suites'
# pattern) — the live viewer's config is never loaded.

WORKRECORD_ROOT = Path(__file__).resolve().parents[2]

ACTION_DRIVER = r'''
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))
os.environ["WB_VIEWER_CONFIG"] = str(base / "config.json")

from server import actions
from server.common import ApiError

plans = base / ".plans"
bundle_id = "2026-11-18-fixture-plan"
project = SimpleNamespace(
    root=base, manifest=SimpleNamespace(plans=plans))
decl = {"slug": "fixture-programme",
        "drain_bundles": [bundle_id],
        "drain_tail": ["Consolidation", "Doc updates",
                       "Performance pass",
                       "Reconcile the register"]}
result = {}
result["drain"] = actions.drain_action(
    project, {"programmes": [decl]})
try:
    actions.drain_action(project, {"programmes": "nope"})
    result["bad_shape"] = "no error"
except ApiError as e:
    result["bad_shape"] = e.status
created = actions.todo_action(
    project, {"verb": "create", "bundle": bundle_id,
              "title": "Stamped todo",
              "body": "drain: fixture-drain-1"})
result["created_body"] = created["todo"]["body"]
print(json.dumps(result))
'''


class ServerActionTests(unittest.TestCase):

    def test_actions_in_a_fresh_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _init_repo(base)
            plans = base / ".plans"
            plans.mkdir(parents=True)
            bundle_id = _bundle(plans)
            (base / "config.json").write_text(
                "{}", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-c", ACTION_DRIVER,
                 str(base), str(WORKRECORD_ROOT)],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(
                proc.returncode, 0, proc.stderr[-2000:])
            result = json.loads(proc.stdout)
            outcome = result["drain"]["drain"][0]
            self.assertEqual(outcome["drained"], [bundle_id])
            self.assertEqual(len(outcome["raised"]), len(TAIL))
            self.assertEqual(result["bad_shape"], 400)
            self.assertEqual(result["created_body"],
                             "drain: fixture-drain-1")


if __name__ == "__main__":
    unittest.main()
