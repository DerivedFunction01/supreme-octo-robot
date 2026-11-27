"""Unit tests for ops/proof/proof_run.py's anchor derivation.

The proof load must expand entries with the anchors the
server derives: ${WS} at the real workspace root.
derive_anchors' own default puts WS at dirname(home) — one
level too deep when home is the scheduling root — which made
every ${WS}-anchored entry unproofable: its argv resolved
into the pipeline dir instead of the workspace.
"""
import importlib.util
import os
import tempfile
import unittest

from server import registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "proof_run", os.path.join(ROOT, "ops", "proof", "proof_run.py")
)
proof_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof_run)


class ProofAnchorsTests(unittest.TestCase):
    def test_ws_anchor_is_the_workspace_root(self):
        anchors = proof_run.anchors()
        self.assertEqual(anchors["WS"], proof_run.paths.WORKSPACE_ROOT)
        self.assertNotEqual(anchors["WS"], os.path.dirname(proof_run.ROOT))
        self.assertEqual(anchors["REPO"], proof_run.ROOT)
        self.assertEqual(
            anchors["HOME"],
            os.path.dirname(proof_run.paths.WORKSPACE_ROOT))

    def test_ws_anchored_entry_argv_expands_against_workspace_root(self):
        tmp = tempfile.mkdtemp()
        jobs = os.path.join(tmp, "jobs")
        os.makedirs(jobs)
        text = (
            "id: ws-job\n"
            "title: Test ws-job\n"
            "kind: scripted\n"
            "cadence:\n  type: interval\n  every: 5m\n"
            "owner: goal:test-goal\n"
            "run:\n  argv:\n    - python3\n    - ${WS}/specimen-tool\n"
            "timeout_secs: 10\n"
            "report:\n  when: on_failure\n  ok_exit_codes:\n    - 0\n"
            "state_paths: []\n"
            "classification: test fixture\n"
        )
        with open(os.path.join(jobs, "ws-job.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(text)
        entries, errors = registry.load_dir(
            jobs, proof_run.ROOT, anchors=proof_run.anchors())
        self.assertEqual(errors, [])
        argv = entries["ws-job"].data["run"]["argv"]
        self.assertEqual(
            argv[1],
            os.path.join(proof_run.paths.WORKSPACE_ROOT, "specimen-tool"))


if __name__ == "__main__":
    unittest.main()
