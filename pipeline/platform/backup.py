"""P3 — state-store backup (plan §6).

Scheduled, integrity-verified snapshots of the pipeline
stores, restored by drill. The plan names the classes: a
ledger goes by its own export + SHA-256; the rest are file
snapshots with manifests. This module carries the general
act both classes share:

  snapshot(store, source_root, backup_root)
      Copy every file of the store into
      <backup_root>/<store>/<timestamp>/, hash each file
      (SHA-256 recorded), count the store through its own
      package's loader, and write a manifest.json naming
      the files, their hashes, and the counts. Binary
      payloads ride the unified writer's staged-write
      protocol core (contract 15); the manifest — a state
      record — is written through the writer's attributed
      `perform`, so the act itself is an `op` event in the
      pipeline ledger when a ledger is supplied.
  restore(store, snapshot_dir, dest_root)
      Refuse unless every snapshotted file still hashes
      to its manifest value; write the files into the
      destination through the same protocol; then load
      the restored store through its own package's
      loader and require the counts to equal the
      manifest's. A restored store whose counts differ
      is a failed drill, never a quiet pass.

The adapters below are the stores that exist now. Each
knows exactly two things: its name, and how its own
package counts the store. Everything else — files,
hashes, manifests — is the shared act above.

Store roots here are fixture copies under the caller's
scratch: the live stores are read-only to this service's
build, and the drill proves on copies. A snapshot of a
live SQLite store must be taken at a quiesce point (the
scheduling service's scheduling concern, §6 P3); the
adapters count through normal opens, exactly as their
packages do.
"""
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone

UTC = timezone.utc

# Contract 01 machinery nature: a code constant, shared
# with releases.py — the platform services' caller.
MACHINERY_CALLER = "platform"

MANIFEST_FILE = "manifest.json"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_paths = _load_module(
    "pipeline_platform_paths",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "paths.py"))
_HERE = _paths.PACKAGE_DIR
_REPO_ROOT = _paths.REPO_ROOT

_writer = _load_module("pipeline_platform_writer", _paths.WRITER)
_ledger_mod = _load_module(
    "pipeline_dispatch_ledger", _paths.DISPATCH_LEDGER)
_sched_registry = _load_module(
    "pipeline_scheduling_registry", _paths.SCHEDULING_REGISTRY)


def _workrecord_registry():
    """The work-record package's registry, via the repo's
    standing sys.path seam (its importers do the same)."""
    root = _paths.WORKRECORD_ROOT
    if root not in sys.path:
        sys.path.insert(0, root)
    from lib import registry as reg
    return reg


class BackupError(Exception):
    """A snapshot or restore refused or failed integrity.
    The message names the store, the file or counts at
    fault — a drill concludes from evidence, not vibes."""


# ---------------------------------------------------------- stores

class StoreAdapter:
    """A pipeline store class: a name, and its own
    package's count of the store at a root. The file set
    is every file under the root (the shared act walks
    it); subclasses never enumerate files themselves."""

    name = "?"

    def count(self, root):
        raise NotImplementedError


class SchedulingRegistryStore(StoreAdapter):
    """The scheduling registry: the registry home — the
    root holds jobs/*.yaml plus the bodies/ the agent
    entries reference — counted by the scheduling
    package's own loader (registry.load_dir: parsed and
    validated entries, plus quarantined-file errors)."""

    name = "scheduling-registry"

    def count(self, root):
        entries, errors = _sched_registry.load_dir(
            os.path.join(root, "jobs"), home=root)
        return {"entries": len(entries), "errors": len(errors),
                "ids": sorted(entries)}


class LedgerStore(StoreAdapter):
    """A ledger store: the dispatch Ledger class over a
    state dir (scheduler.db). One class, two runtime
    stores — the scheduling server's ledger and the
    dispatch ledger are distinct state dirs over it —
    so the adapter takes its store name at construction.
    Counted by the Ledger's own stats + integrity check."""

    def __init__(self, name):
        self.name = name

    def count(self, root):
        ledger = _ledger_mod.Ledger(root)
        stats = ledger.stats()
        check = ledger.verify()
        return {"events": stats["events"],
                "per_kind": stats["per_kind"],
                "integrity": check["integrity"]}


class WorkrecordStore(StoreAdapter):
    """The work-record store: a registry DB plus its
    entry files under <root>/workbench/, counted by the
    work-record package's own registry API."""

    name = "workrecord"

    def count(self, root):
        reg = _workrecord_registry()
        db = os.path.join(root, "workbench", "registry.db")
        entries = reg.list_entries(db)
        todos = reg.list_todos(db)
        return {"entries": len(entries), "todos": len(todos)}


# ---------------------------------------------------------- the act

def _store_files(root):
    """Every file constituting the store, as sorted
    root-relative paths. Interpreter caches and the
    writer's own staging temps are never store content."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if ".sched-tmp-" in name:
                continue
            out.append(os.path.relpath(
                os.path.join(dirpath, name), root))
    return sorted(out)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _stamp(at):
    return at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def snapshot(store, source_root, backup_root, *, caller=MACHINERY_CALLER,
             ledger=None, workspace_root=None, at=None):
    """Take one integrity-verified snapshot. Returns
    {"dir": snapshot_dir, "manifest": manifest}. Any hash
    mismatch between a source file and its copy raises
    BackupError and the partial snapshot is left in place
    as evidence — never silently completed."""
    at = at or datetime.now(UTC)
    source_root = os.path.realpath(source_root)
    if not os.path.isdir(source_root):
        raise BackupError(f"{store.name}: no such store root: "
                          f"{source_root}")
    base = os.path.join(os.path.realpath(backup_root),
                        store.name, _stamp(at))
    snap_dir, n = base, 2
    while os.path.exists(snap_dir):
        snap_dir = f"{base}-{n}"
        n += 1
    files = []
    for rel in _store_files(source_root):
        with open(os.path.join(source_root, rel), "rb") as fh:
            data = fh.read()
        digest = _sha256(data)
        _writer.staged_write(os.path.join(snap_dir, rel), data)
        with open(os.path.join(snap_dir, rel), "rb") as fh:
            if _sha256(fh.read()) != digest:
                raise BackupError(
                    f"{store.name}: copy of {rel} failed its "
                    f"hash check during snapshot")
        files.append({"path": rel, "sha256": digest,
                      "bytes": len(data)})
    manifest = {
        "store": store.name,
        "at": at.astimezone(UTC).isoformat(),
        "source_root_name": os.path.basename(source_root),
        "files": files,
        "counts": store.count(source_root),
        "caller": caller,
    }
    root = os.path.realpath(workspace_root) if workspace_root \
        else _REPO_ROOT
    status, payload = _writer.perform(
        ledger, {"workspace_root": root},
        {"caller": caller, "op": "write",
         "path": os.path.join(snap_dir, MANIFEST_FILE),
         "content": json.dumps(manifest, indent=2,
                                sort_keys=True) + "\n"})
    if status != 200:
        raise BackupError(
            f"{store.name}: manifest write refused: "
            f"{payload.get('error')}: {payload.get('detail')}")
    return {"dir": snap_dir, "manifest": manifest}


def restore(store, snapshot_dir, dest_root):
    """Restore one snapshot into a destination root and
    prove it: every file hash-checked against the
    manifest before it lands, and the restored store
    loaded through its own package's loader with counts
    equal to the manifest's. Returns the restored
    counts. A mismatch anywhere raises BackupError."""
    snapshot_dir = os.path.realpath(snapshot_dir)
    manifest_path = os.path.join(snapshot_dir, MANIFEST_FILE)
    if not os.path.exists(manifest_path):
        raise BackupError(f"no manifest at {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    if manifest.get("store") != store.name:
        raise BackupError(
            f"manifest is for {manifest.get('store')!r}, "
            f"not {store.name!r}")
    dest_root = os.path.realpath(dest_root)
    for item in manifest["files"]:
        rel = item["path"]
        with open(os.path.join(snapshot_dir, rel), "rb") as fh:
            data = fh.read()
        if _sha256(data) != item["sha256"]:
            raise BackupError(
                f"{store.name}: snapshot file {rel} no longer "
                f"matches its manifest hash — refusing restore")
        _writer.staged_write(os.path.join(dest_root, rel), data)
    counts = store.count(dest_root)
    if counts != manifest["counts"]:
        raise BackupError(
            f"{store.name}: restored counts {counts} differ "
            f"from manifest counts {manifest['counts']}")
    return counts
