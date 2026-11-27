"""P2 gate tests: the deployment/release record.

Proves (plan §6 P2 done-evidence, fixture form): a recorded
deploy resolves to its exact commit; an artifact with no
resolving entry reads undeployed, never deployed; a failed
result is history, not a deployment; writes ride the
unified writer and land in the pipeline ledger as `op`
events carrying the acting caller.
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
REPO_ROOT = PLATFORM.parents[1]
sys.path.insert(0, str(PLATFORM))

import releases  # noqa: E402


def _load_ledger_class():
    path = REPO_ROOT / "pipeline" / "dispatch" / "ledger.py"
    spec = importlib.util.spec_from_file_location(
        "pipeline_dispatch_ledger", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Ledger


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.tmp.name))
        Ledger = _load_ledger_class()
        self.ledger = Ledger(str(self.root / "ledger-state"))
        self.store = releases.ReleaseStore(
            self.root / "release-state", ledger=self.ledger,
            workspace_root=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, **kw):
        base = {"repo": "specimen-repo", "commit": "c7287cc",
                "artifact": "workhorse-superapp", "stage": "D5",
                "result": "deployed", "caller": "test-lane"}
        base.update(kw)
        return self.store.record(**base)


class TestRecord(Fixture):
    def test_recorded_deploy_resolves_to_exact_commit(self):
        self.record(commit="abc1234")
        hit = self.store.resolve("workhorse-superapp", "D5")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["commit"], "abc1234")
        check = self.store.drift_check("workhorse-superapp", "D5")
        self.assertEqual(check["status"], "deployed")
        self.assertEqual(check["commit"], "abc1234")

    def test_unrecorded_artifact_reads_undeployed(self):
        check = self.store.drift_check("never-deployed", "D1")
        self.assertEqual(check["status"], "undeployed")
        self.assertIsNone(check["commit"])
        self.assertIsNone(self.store.resolve("never-deployed"))

    def test_failed_result_is_history_not_a_deployment(self):
        self.record(result="failed", commit="bad9999")
        check = self.store.drift_check("workhorse-superapp", "D5")
        self.assertEqual(check["status"], "undeployed")
        self.record(commit="good111")
        check = self.store.drift_check("workhorse-superapp", "D5")
        self.assertEqual(check["status"], "deployed")
        self.assertEqual(check["commit"], "good111")

    def test_newest_deploy_wins(self):
        self.record(commit="first00")
        self.record(commit="second0")
        self.assertEqual(
            self.store.resolve("workhorse-superapp")["commit"],
            "second0")

    def test_stage_scoping(self):
        self.record(commit="stageD5", stage="D5")
        self.assertIsNone(self.store.resolve(
            "workhorse-superapp", "D6"))
        self.assertEqual(
            self.store.resolve("workhorse-superapp")["commit"],
            "stageD5")

    def test_writes_are_ledgered_op_events_with_caller(self):
        self.record()
        ops = self.ledger.query(kinds=["op"])
        self.assertTrue(ops)
        self.assertTrue(all(op["caller"] == "test-lane"
                            for op in ops))
        self.assertTrue(all(op["status"] == "ok" for op in ops))

    def test_missing_field_refused(self):
        with self.assertRaises(releases.ReleaseError) as cm:
            self.record(commit="")
        self.assertEqual(cm.exception.name, "bad_request")
        self.assertEqual(self.store.entries(), [])


if __name__ == "__main__":
    unittest.main()
