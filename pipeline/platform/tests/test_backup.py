"""P3 gate tests: state-store backup and the restore drill.

Proves (plan §6 P3 done-evidence, fixture form): for each
pipeline store class that exists now — scheduling registry,
ledger (both runtime stores over the dispatch Ledger
class), work-record store — a snapshot records every
file's SHA-256 in its manifest, a restore lands the files
hash-verified, and the restored store loads through its
own package's loader with counts identical to the
manifest's. A tampered snapshot is refused, never
restored. All stores are fixture copies seeded through
their own packages' APIs under a temp root; no live store
is touched.
"""

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
REPO_ROOT = PLATFORM.parents[1]
sys.path.insert(0, str(PLATFORM))

import backup  # noqa: E402

FIXTURES = REPO_ROOT / "contracts" / "fixtures"


def _load_ledger_class():
    path = REPO_ROOT / "pipeline" / "dispatch" / "ledger.py"
    spec = importlib.util.spec_from_file_location(
        "pipeline_dispatch_ledger", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Ledger


# The retired migration field family (contract 14,
# amendment 3): the S0 specimens carry it because they
# record the pinned format; the target registry refuses
# it as unknown-field, so the fixture transform strips
# exactly that family and nothing else.
RETIRED_FIELDS = {"migrated", "migrated_at", "proof_pending",
                  "migration_note"}


def seed_registry(root):
    """A scheduling-registry fixture: the contract
    specimens in target format, named by their entry
    ids, plus the body file the agent entry names."""
    jobs = Path(root) / "jobs"
    jobs.mkdir(parents=True)
    for entry_id in ("bridge-wake", "bridge-drain"):
        lines = (FIXTURES / f"scheduler-entry-{entry_id}.yaml"
                 ).read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines
                if line.split(":")[0].strip()
                not in RETIRED_FIELDS]
        (jobs / f"{entry_id}.yaml").write_text(
            "\n".join(kept) + "\n", encoding="utf-8")
    bodies = Path(root) / "bodies"
    bodies.mkdir()
    (bodies / "bridge-drain.md").write_text(
        "Fixture body for the bridge-drain agent entry.\n",
        encoding="utf-8")
    return root


def seed_ledger(root, extra_kinds=("run", "ping_created")):
    """A ledger fixture: the S0 specimen lines inserted
    through the Ledger's row path, plus a few records
    written through its record() path."""
    Ledger = _load_ledger_class()
    ledger = Ledger(str(root))
    specimen = (FIXTURES / "ledger-events.jsonl").read_text(
        encoding="utf-8")
    for line in specimen.splitlines():
        if line.strip():
            ledger._insert(json.loads(line))
    for kind in extra_kinds:
        ledger.record(kind, job_id="fixture-job", status="ok")
    return root


def seed_workrecord(root):
    """A work-record fixture, seeded through the package's
    own registry API (the same calls its tests use)."""
    wr = str(REPO_ROOT / "pipeline" / "workrecord")
    if wr not in sys.path:
        sys.path.insert(0, wr)
    from lib import registry as reg
    base = Path(root) / "workbench"
    db = base / "registry.db"
    layout = (base / "entries", base / "archive")
    reg.init_registry(db)
    reg.add_entry(db, layout, "alpha-entry")
    reg.add_entry(db, layout, "beta-entry")
    reg.add_todo(db, "t-alpha", "Alpha todo")
    reg.add_todo(db, "t-beta", "Beta todo")
    return root


class Drill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def drill(self, store, source):
        snap = backup.snapshot(
            store, source, self.root / "backups",
            workspace_root=self.root)
        restored = self.root / f"restored-{store.name}"
        counts = backup.restore(store, snap["dir"], restored)
        self.assertEqual(counts, snap["manifest"]["counts"])
        self.assertEqual(counts, store.count(str(source)))
        return snap

    def test_scheduling_registry(self):
        source = seed_registry(self.root / "src-registry")
        snap = self.drill(
            backup.SchedulingRegistryStore(), source)
        counts = snap["manifest"]["counts"]
        self.assertEqual(counts["entries"], 2)
        self.assertEqual(counts["errors"], 0)

    def test_dispatch_ledger(self):
        source = seed_ledger(self.root / "src-ledger")
        snap = self.drill(backup.LedgerStore("dispatch-ledger"),
                           source)
        counts = snap["manifest"]["counts"]
        self.assertEqual(counts["events"], 4)
        self.assertEqual(counts["integrity"], "ok")

    def test_scheduling_ledger(self):
        source = seed_ledger(self.root / "src-sched-ledger",
                              extra_kinds=("run",))
        snap = self.drill(
            backup.LedgerStore("scheduling-ledger"), source)
        self.assertEqual(snap["manifest"]["counts"]["events"], 3)

    def test_workrecord(self):
        source = seed_workrecord(self.root / "src-workrecord")
        snap = self.drill(backup.WorkrecordStore(), source)
        counts = snap["manifest"]["counts"]
        self.assertEqual(counts, {"entries": 2, "todos": 2})

    def test_manifest_records_every_file_hash(self):
        source = seed_ledger(self.root / "src-ledger2")
        snap = backup.snapshot(
            backup.LedgerStore("dispatch-ledger"), source,
            self.root / "backups", workspace_root=self.root)
        manifest = json.loads(Path(
            snap["dir"], "manifest.json").read_text("utf-8"))
        self.assertTrue(manifest["files"])
        for item in manifest["files"]:
            data = Path(snap["dir"], item["path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(data).hexdigest(), item["sha256"])
            self.assertEqual(len(data), item["bytes"])

    def test_tampered_snapshot_refused(self):
        source = seed_ledger(self.root / "src-ledger3")
        store = backup.LedgerStore("dispatch-ledger")
        snap = backup.snapshot(store, source,
                               self.root / "backups",
                               workspace_root=self.root)
        victim = Path(snap["dir"],
                      snap["manifest"]["files"][0]["path"])
        data = bytearray(victim.read_bytes())
        data[0] ^= 0xFF
        victim.write_bytes(bytes(data))
        with self.assertRaises(backup.BackupError):
            backup.restore(store, snap["dir"],
                           self.root / "restored-tampered")


if __name__ == "__main__":
    unittest.main()
