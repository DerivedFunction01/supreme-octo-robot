"""The Code status serve's request-path caches:
repo_status_feed serves a per-checkout
TTL cache in the repos feed's idiom — a second status
call within the TTL does not recompute the git
derivation, and the registry invalidation busts the
cache; _id_map is memoized on (sweep identity, census
timestamp) — the identical map across calls, a
recompute when the census timestamp moves;
resolve_checkout answers through a resolved-root map
keyed by the census state, with its main / worktree /
unknown / foreign-checkout verdicts unchanged.

The proof runs in a fresh interpreter (a driver script
over the shared fixture workspace), the same way
test_shape_persistence's census legs do: the server
package reads its config at import, so the fixture
config must be installed before the import — a
subprocess keeps this suite's in-process server tests
untouched by the second config. Every verdict is read
off counts and identities the driver leaves behind —
no wall clock, no thread waits: the TTL legs stay
inside the default repos_ttl_s, and the census
timestamp leg moves the stored timestamp by hand.
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
import os
import subprocess
import sys
from pathlib import Path

base = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(root))

from tests.server import fixture_ws

info = fixture_ws.build_fixture_workspace(base)
cfg = fixture_ws.fixture_config(base, base / "state-test")
os.environ["WB_VIEWER_CONFIG"] = str(cfg)
os.environ["WB_ATTENTION_ARMED_DIR"] = str(
    info["armed_dir"])

# A linked worktree of alpha, so the census carries a
# worktree record and resolve_checkout's checkout leg
# has something real to resolve.
env = {**os.environ, **fixture_ws.GIT_ENV}
subprocess.run(
    ["git", "-C", str(info["alpha"]), "worktree", "add",
     str(base / "ws" / "alpha-wt"), "HEAD"],
    check=True, env=env, capture_output=True, text=True)

from server import projects_feed, repos_feed
from server.common import ApiError

census = repos_feed._census_cached()
result = {}
result["census_ids"] = sorted(census)
wt = next(r for r in census.values()
          if r.get("is_worktree"))
result["worktree_id"] = wt["id"]
result["worktree_parent"] = wt.get("parent_id")

# -- (i) the per-checkout status cache ------------------
calls = {"n": 0}
real_status = repos_feed.repos_mod.repo_status

def counting_status(record):
    calls["n"] += 1
    return real_status(record)

repos_feed.repos_mod.repo_status = counting_status
record = census["delta-repo"]
first = repos_feed.repo_status_feed(record)
result["calls_first"] = calls["n"]
result["first_branch"] = first.get("branch")
second = repos_feed.repo_status_feed(record)
result["calls_second_within_ttl"] = calls["n"]
result["second_is_first"] = second is first
repos_feed._repos_invalidate_cache()
third = repos_feed.repo_status_feed(record)
result["calls_after_invalidate"] = calls["n"]
result["third_branch"] = third.get("branch")
repos_feed.repos_mod.repo_status = real_status

# -- (ii) the _id_map memo -------------------------------
m1 = repos_feed._id_map()
m2 = repos_feed._id_map()
result["id_map_same_object"] = m1 is m2
result["id_map"] = m1
repos_feed._census_cache["at"] += 0.5
m3 = repos_feed._id_map()
result["id_map_recomputed_on_census_move"] = \
    m3 is not m1
result["id_map_content_stable"] = m3 == m1

# -- (iii) resolve_checkout, unchanged verdicts ----------
rec, main_id, checkouts = \
    projects_feed.resolve_checkout("alpha")
result["alpha_main"] = {
    "record": rec["id"], "main": main_id,
    "checkouts": [c["id"] for c in checkouts]}
rec, main_id, checkouts = \
    projects_feed.resolve_checkout("delta-repo")
result["delta_main"] = {
    "record": rec["id"], "main": main_id,
    "checkouts": [c["id"] for c in checkouts]}
rec, main_id, checkouts = \
    projects_feed.resolve_checkout(
        "alpha", result["worktree_id"])
result["alpha_worktree"] = {
    "record": rec["id"], "main": main_id,
    "checkouts": [c["id"] for c in checkouts]}
# A repeat resolve answers through the cached root
# map with the same verdict.
rec2, main2, _ = projects_feed.resolve_checkout("alpha")
result["alpha_main_repeat"] = \
    rec2["id"] == "alpha" and main2 == "alpha"
for label, args in (
        ("unknown", ("nope",)),
        ("foreign", ("alpha", "delta-repo"))):
    try:
        projects_feed.resolve_checkout(*args)
        result[label] = None
    except ApiError as e:
        result[label] = e.status
print(json.dumps(result))
'''


def _python():
    venv = WORKRECORD_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


class StatusCacheTest(unittest.TestCase):

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

    def test_status_within_ttl_does_not_recompute(self):
        self.assertEqual(self.result["calls_first"], 1)
        self.assertEqual(
            self.result["calls_second_within_ttl"], 1)
        self.assertTrue(self.result["second_is_first"])
        self.assertEqual(self.result["first_branch"],
                         "main")

    def test_status_invalidation_recomputes(self):
        self.assertEqual(
            self.result["calls_after_invalidate"], 2)
        self.assertEqual(self.result["third_branch"],
                         "main")

    def test_id_map_memoized_until_census_moves(self):
        self.assertTrue(
            self.result["id_map_same_object"])
        self.assertTrue(
            self.result[
                "id_map_recomputed_on_census_move"])
        self.assertTrue(
            self.result["id_map_content_stable"])
        self.assertEqual(
            self.result["id_map"]["delta-repo"],
            "delta-repo")
        self.assertEqual(
            self.result["id_map"][self.result["worktree_id"]],
            "alpha")

    def test_resolve_checkout_main_and_worktree(self):
        self.assertEqual(self.result["alpha_main"], {
            "record": "alpha", "main": "alpha",
            "checkouts": ["alpha",
                          self.result["worktree_id"]]})
        self.assertEqual(self.result["delta_main"], {
            "record": "delta-repo", "main": "delta-repo",
            "checkouts": ["delta-repo"]})
        wt = self.result["alpha_worktree"]
        self.assertEqual(wt["record"],
                         self.result["worktree_id"])
        self.assertEqual(wt["main"], "alpha")
        self.assertEqual(self.result["worktree_parent"],
                         "alpha")
        self.assertTrue(
            self.result["alpha_main_repeat"])

    def test_resolve_checkout_errors_unchanged(self):
        self.assertEqual(self.result["unknown"], 404)
        self.assertEqual(self.result["foreign"], 400)


if __name__ == "__main__":
    unittest.main()
