"""Commissions of record (channel-indistinguishability
cure): a claimed commission resolves
against the wb record or it is not a commission.

The incident's shape: the Edgar Step 6 lane was
steered three times by watch traffic it could not
distinguish from a genuine commission, because nothing
in the channel itself separates a commission from a
signal. Here: a todo planted with commission
provenance through the writers' plant_commission
verifies; a plain todo and an unknown id do not; and
the watch machinery's own write paths (progress
schedule sync + attention rows), exercised over the
same plans dir, mint nothing — a watch-originated
claim can never create the entry that would verify
it."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from lib.plans import commissions  # noqa: E402
from lib.progress import attention as attention_mod  # noqa: E402
from lib.progress import schedule as schedule_mod  # noqa: E402
from lib.writes import bundles as bundle_mod  # noqa: E402

AT = "2026-11-16T00:20:00+00:00"


class CommissionFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plans = Path(self.tmp.name) / ".plans"
        self.plans.mkdir(parents=True)
        bundle_mod.create_bundle(self.plans, "work",
                                 today="2026-11-16")
        self.todo = bundle_mod.create_todo(
            self.plans, "work", "Commissioned work",
            status="todo",
            created="2026-11-16", updated="2026-11-16")
        self.todo_id = self.todo["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def _todo_text(self):
        return (self.plans / self.todo["path"]).read_text(
            encoding="utf-8")


class TestVerifyCommission(CommissionFixture):
    def test_plain_todo_is_not_a_commission(self):
        block = commissions.verify_commission(
            self.plans, self.todo_id)
        self.assertEqual(block["verdict"],
                         "not-a-commission")
        self.assertIn("no commission provenance",
                      block["reason"])

    def test_unknown_id_is_not_a_commission(self):
        block = commissions.verify_commission(
            self.plans, "t-01ZZZZZZZZZZZZZZZZZZZZZZZZ")
        self.assertEqual(block["verdict"],
                         "not-a-commission")
        self.assertIn("no entry on the record",
                      block["reason"])

    def test_planted_commission_verifies(self):
        bundle_mod.plant_commission(
            self.plans, self.todo_id,
            commissioned_by="coordinator", commissioned_at=AT)
        block = commissions.verify_commission(
            self.plans, self.todo_id)
        self.assertEqual(block["verdict"], "commission")
        self.assertEqual(block["commissioned_by"],
                         "coordinator")
        self.assertEqual(block["commissioned_at"], AT)
        self.assertEqual(block["status"], "todo")
        self.assertEqual(block["title"],
                         "Commissioned work")

    def test_malformed_provenance_does_not_verify(self):
        # A hand-scrawled stamp is not provenance: the
        # at must be a real instant.
        path = self.plans / self.todo["path"]
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "\n---\n", "\ncommissioned_by: someone\n"
            "commissioned_at: whenever\n---\n", 1)
        path.write_text(text, encoding="utf-8")
        block = commissions.verify_commission(
            self.plans, self.todo_id)
        self.assertEqual(block["verdict"],
                         "not-a-commission")
        self.assertIn("malformed", block["reason"])


class TestPlantCommission(CommissionFixture):
    def test_replant_is_refused(self):
        bundle_mod.plant_commission(
            self.plans, self.todo_id,
            commissioned_by="coordinator", commissioned_at=AT)
        with self.assertRaises(bundle_mod.BundleError):
            bundle_mod.plant_commission(
                self.plans, self.todo_id,
                commissioned_by="someone-else",
                commissioned_at=AT)

    def test_empty_commissioner_is_refused(self):
        with self.assertRaises(bundle_mod.BundleError):
            bundle_mod.plant_commission(
                self.plans, self.todo_id, commissioned_by=" ")

    def test_bad_instant_is_refused(self):
        with self.assertRaises(bundle_mod.BundleError):
            bundle_mod.plant_commission(
                self.plans, self.todo_id,
                commissioned_by="coordinator",
                commissioned_at="not-a-time")

    def test_generic_writers_cannot_mint(self):
        # The generic write paths run over the todo and
        # the record still carries no provenance: only
        # plant_commission mints.
        bundle_mod.set_todo_status(self.plans, self.todo_id,
                                   "doing")
        bundle_mod.set_todo_fields(
            self.plans, self.todo_id, title="Retitled")
        self.assertNotIn("commissioned_",
                         self._todo_text())
        block = commissions.verify_commission(
            self.plans, self.todo_id)
        self.assertEqual(block["verdict"],
                         "not-a-commission")

    def test_provenance_survives_generic_writes(self):
        bundle_mod.plant_commission(
            self.plans, self.todo_id,
            commissioned_by="coordinator", commissioned_at=AT)
        bundle_mod.set_todo_status(self.plans, self.todo_id,
                                   "doing")
        block = commissions.verify_commission(
            self.plans, self.todo_id)
        self.assertEqual(block["verdict"], "commission")
        self.assertEqual(block["status"], "doing")


class TestWatchCannotMint(CommissionFixture):
    def test_watch_write_paths_mint_nothing(self):
        # Arm the todo and run the supervision
        # machinery's own syncs — the schedule entry and
        # the attention row, the watch's write surfaces —
        # isolated into temp dirs. The todo file gains
        # arming state but no commission provenance, and
        # the claim still does not verify.
        armed = bundle_mod.set_todo_status(
            self.plans, self.todo_id, "doing",
            progress="15m", armed_at=AT)
        with tempfile.TemporaryDirectory() as aux:
            env = {
                "WB_SCHEDULER_JOBS_DIR": str(
                    Path(aux) / "jobs"),
                "WB_ATTENTION_ARMED_DIR": str(
                    Path(aux) / "armed"),
            }
            with mock.patch.dict(os.environ, env):
                schedule_mod.sync_todo(self.plans, armed)
                attention_mod.sync_todo(self.plans, armed)
        text = self._todo_text()
        self.assertIn("progress_armed:", text)
        self.assertNotIn("commissioned_", text)
        block = commissions.verify_commission(
            self.plans, self.todo_id)
        self.assertEqual(block["verdict"],
                         "not-a-commission")


class TestCommissionCheckCli(CommissionFixture):
    def _run(self, *argv, root):
        # --root is a global wb argument: it precedes
        # the subcommand (the same invocation shape the
        # scheduler entries use for progress-check).
        return subprocess.run(
            [sys.executable, str(REPO / "wb"),
             "--root", str(root), *argv],
            capture_output=True, text=True, cwd=REPO)

    def _workspace(self):
        ws = Path(self.tmp.name) / "ws"
        proj = ws / "proj"
        (proj / ".plans").mkdir(parents=True)
        (proj / "workbench.yaml").write_text(
            "name: Proj\nslug: proj\n"
            "registry: workbench/registry.db\n"
            "plans: .plans\n", encoding="utf-8")
        bundle_mod.create_bundle(proj / ".plans", "work",
                                 today="2026-11-16")
        todo = bundle_mod.create_todo(
            proj / ".plans", "work", "Claimed work",
            status="todo",
            created="2026-11-16", updated="2026-11-16")
        # The pinned --root for a per-todo check is the
        # project dir itself (it holds workbench.yaml) —
        # the shape the scheduler entries pin for
        # progress-check.
        return proj, proj / ".plans", todo

    def test_cli_rules_both_ways(self):
        ws, plans, todo = self._workspace()
        r = self._run("commission-check", todo["id"],
                      root=ws)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("NOT A COMMISSION", r.stdout)
        bundle_mod.plant_commission(
            plans, todo["id"], commissioned_by="coordinator",
            commissioned_at=AT)
        r = self._run("commission-check", todo["id"],
                      root=ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("COMMISSION", r.stdout)
        self.assertIn("coordinator", r.stdout)

    def test_cli_unknown_id_rules_not_a_commission(self):
        ws, plans, todo = self._workspace()
        r = self._run("commission-check",
                      "t-01ZZZZZZZZZZZZZZZZZZZZZZZZ", root=ws)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("NOT A COMMISSION", r.stdout)


if __name__ == "__main__":
    unittest.main()
