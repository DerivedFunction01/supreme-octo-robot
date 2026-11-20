"""P2 — the deployment/release record (plan §6).

A pipeline store tying artifact <-> repo commit <-> stage.
Every deploy writes one entry — (repo, commit, artifact,
stage, time, result) plus the acting caller (contract 01
attribution) — and a drift check against the record is the
only way a deploy reads as deployed: an artifact with no
entry resolving to it reads UNDEPLOYED, never deployed.
Until this record existed, every deploy was drift-guarded
sync with no ledger (plan §6 P2); the app's deploy path
refuses to report success without its entry here (that
wiring is the deploy flow's own step — this module is the
store, its writer/reader, and the drift-check callable).

Writes ride the unified state writer (contract 15): an
append is a `write` for the first entry and a stamp-guarded
`cas-update` after that, so a record can never be torn or
silently overwritten, and every attempt is an `op` event in
the pipeline ledger when a ledger is supplied. Readers are
not parties to the writer contract — the reader below is a
plain parse of the store file.

The store file is append-only JSONL, one canonical JSON
object per line (sorted keys — the ledger's canonical-line
form), at `state/releases.jsonl` under the store home. The
writer resolves every path against the workspace root
(derived from this file's location unless passed), refusing
anything outside it.

THE HOME IS SINGLE (commission 13). The live store's home
is the canonical home — `paths.STATE_DIR`, this package's
`state/` directory — and no other. History is the reason:
two live callers once diverged (a backfill ran with
`var/release-state/` as home, a later append with the
default), the ledger split into two files, and each drift
verification read the file its own context had written, so
both verified while no single file held the history. The
constructor therefore refuses a non-canonical home
whenever the store is LIVE — its workspace root is the
repo root, the posture every service and deploy act runs
in — raising before anything is founded or written. A
store constructed under any other workspace root is a
fixture store by construction (the test suite's posture:
a scratch root, a scratch home under it); that is the one
honest escape, and it is structural — where the writer
will write — not a flag a live caller could set by habit.
"""
import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone

UTC = timezone.utc

# Contract 01 machinery nature: a code constant, never a
# registry row. The platform services act under this caller
# when no narrower caller is presented.
MACHINERY_CALLER = "platform"

# The one result value that reads as deployed. Any other
# recorded result (failed, aborted, ...) is history, not a
# deployment.
DEPLOYED = "deployed"

STORE_FILE = "releases.jsonl"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_paths = _load_module(
    "pipeline_platform_paths",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "paths.py"))


def _load_platform_writer():
    """The unified state writer lives beside this module
    (contract 15); loaded by path from the platform paths
    module, so the protocol has exactly one implementation
    and its location exactly one derivation."""
    path = _paths.WRITER
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_writer = _load_platform_writer()

# The UTC ISO format home is the dispatch ledger's `iso`
# (one owner per helper), bound by path through the
# platform paths module's derivation.
_ledger = _load_module("pipeline_dispatch_ledger",
                       _paths.DISPATCH_LEDGER)


def _repo_root():
    # The mega repo root, from the platform paths module.
    return _paths.REPO_ROOT


_iso = _ledger.iso


class ReleaseError(Exception):
    """A store write was refused or failed at the writer.
    Carries the writer's closed-table error name (contract
    15), so a caller concludes exactly what the writer
    contract allows — never a guess."""

    def __init__(self, name, detail=""):
        super().__init__(detail or name)
        self.name = name
        self.detail = detail or name


class ReleaseStore:
    """The release record over one store home.

    ledger: a pipeline Ledger (contract 05) receiving the
    writer's `op` audit events, or None (writes unaudited —
    the fixture posture, never the service posture).
    workspace_root: the root the writer resolves store
    paths against; the store home must live under it.

    Home rule (commission 13): a LIVE store — workspace
    root equal to the repo root — must sit at the
    canonical home (`paths.STATE_DIR`); any other home
    raises ValueError at construction, founding nothing.
    A store under a scratch workspace root is a fixture
    store and may sit at a scratch home; that is the test
    suite's seam, and the only one.
    """

    def __init__(self, home=None, *, ledger=None, workspace_root=None):
        if home is None:
            home = _paths.STATE_DIR
        self.home = os.path.realpath(home)
        self.path = os.path.join(self.home, STORE_FILE)
        self.ledger = ledger
        self.workspace_root = os.path.realpath(
            workspace_root) if workspace_root else _repo_root()
        canonical = os.path.realpath(_paths.STATE_DIR)
        if (self.workspace_root == os.path.realpath(_repo_root())
                and self.home != canonical):
            raise ValueError(
                f"release store home {self.home} is not the "
                f"canonical home {canonical}: the live "
                "release record has exactly one home "
                "(paths.STATE_DIR), and a second home "
                "splits the ledger — construct with the "
                "default home; a scratch home belongs to a "
                "fixture store under a scratch workspace "
                "root")

    # ------------------------------------------------------ write

    def record(self, *, repo, commit, artifact, stage, result,
               caller, at=None):
        """Append one deploy entry through the unified
        writer and return it. Every field is required and
        non-empty; the entry is history the moment it lands
        (append-only — a later deploy is a new entry, never
        an edit of this one)."""
        fields = {"repo": repo, "commit": commit,
                  "artifact": artifact, "stage": stage,
                  "result": result, "caller": caller}
        for name, value in fields.items():
            if not isinstance(value, str) or not value:
                raise ReleaseError(
                    "bad_request", f"{name} must be a non-empty string")
        entry = dict(fields)
        entry["time"] = _iso(at or datetime.now(UTC))
        line = json.dumps(entry, sort_keys=True) + "\n"
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as fh:
                current = fh.read()
            stamp = hashlib.sha256(
                current.encode("utf-8")).hexdigest()
            req = {"caller": caller, "op": "cas-update",
                   "path": self.path, "expected_stamp": stamp,
                   "content": current + line}
        else:
            req = {"caller": caller, "op": "write",
                   "path": self.path, "content": line}
        status, payload = _writer.perform(
            self.ledger, {"workspace_root": self.workspace_root}, req)
        if status != 200:
            raise ReleaseError(payload.get("error", "io_error"),
                               payload.get("detail", ""))
        return entry

    # ------------------------------------------------------ read

    def entries(self):
        """Every entry, oldest first. A missing store reads
        as empty — no deploys recorded yet."""
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def resolve(self, artifact, stage=None):
        """The entry a drift check trusts: the newest entry
        for the artifact (and stage, when given) whose
        result is `deployed`. None when no deploy ever
        landed for it."""
        for entry in reversed(self.entries()):
            if entry.get("artifact") != artifact:
                continue
            if stage is not None and entry.get("stage") != stage:
                continue
            if entry.get("result") == DEPLOYED:
                return entry
        return None

    def drift_check(self, artifact, stage=None):
        """The drift-check callable. A recorded deploy
        resolves to its exact commit; anything else —
        never recorded, or recorded only as failed —
        reads as undeployed."""
        hit = self.resolve(artifact, stage)
        if hit is None:
            return {"artifact": artifact, "stage": stage,
                    "status": "undeployed", "commit": None,
                    "repo": None, "time": None, "entry": None}
        return {"artifact": artifact, "stage": stage,
                "status": DEPLOYED, "commit": hit["commit"],
                "repo": hit["repo"], "time": hit["time"],
                "entry": hit}
