"""Live-store census for the unified writer (contract 15,
§4.15; AC-14 invariant (b), live-store half).

The gate's writer-uniqueness leg (gate.writeruniqueness)
is the invariant's static half: it scans a package's own
sources for write patterns that bypass the writer. This
census is the other half, over the live store set: every
store's configured writer seam must resolve to the ONE
platform writer — pipeline/platform/writer.py, its
staged_write / perform entries — so a store cannot drift
onto a private writer while its package's leg is green.

A seam, in the tree's standing form, is a module that
loads the writer by path from its package paths spine's
PLATFORM_WRITER constant (the platform package's own
stores use its spine's WRITER) under the module name
"pipeline_platform_writer", and calls staged_write or
perform on the loaded module. The census:

- loads every spine by path (spines are derivation-only
  modules; loading one is the consumers' own pattern)
  and asserts its constant realpaths to writer.py;
- AST-checks every seam module for the seam's shape —
  the spine constant referenced, the by-path load under
  the writer's module name, a staged_write / perform
  call — without importing seam modules (server modules
  are not import-safe in a suite);
- sweeps the tree so the census is a census: every
  non-test module that loads "pipeline_platform_writer"
  by path is a counted seam, and every paths spine that
  assigns PLATFORM_WRITER is a counted spine. A seam or
  spine the table does not name fails the census by
  name; a seam that cannot be resolved fails loudly
  naming it. Nothing here skips.

Since the writer-service route, a write reaches the
one writer two ways: in-process through a seam above,
or through the /ops service, whose endpoint performs
it server-side with the same writer. The platform ops
client is the second way's transport face: it loads
the writer by path for its error contract (WriterError)
only — it calls neither staged_write nor perform on
the loaded module and stages nothing itself (the gate's
writer-uniqueness leg is the static half that keeps
exactly one staged-write implementation in the tree).
The sweep's net catches the client by its load, so the
census counts it in TRANSPORTS below, a category of
one shape: a by-path loader that never calls the
writer. A loader in neither table fails the census by
name; a transport that starts calling the writer
fails its own pin and must re-register as a seam.
"""

import ast
import importlib.util
import os
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent.parent
PIPELINE = PLATFORM.parent
REPO_ROOT = PLATFORM.parents[1]
WRITER = PLATFORM / "writer.py"
WRITER_NAME = "pipeline_platform_writer"

# (store, seam module, paths spine, spine constant) —
# repo-relative. The re-pointed set: scheduling ops (S3),
# workrecord (S4), venue (S5), attention state (S7; the
# store re-homed from the registry package into the
# attention package at commission 12, its seam now riding
# the attention spine), the registry's
# own stores, dispatch's state seams, the platform
# package's own two stores, and the platform cutover's
# config provisioning (commission 14's cure of the gate
# leg's provision_config finding). The scheduler-keeper
# durable-write cure added two more scheduling seams —
# the ops spine's own staged-write home and the ops
# client's token store — both counted by the census.
SEAMS = (
    ("platform release store",
     "pipeline/platform/releases.py",
     "pipeline/platform/paths.py", "WRITER"),
    ("platform backup",
     "pipeline/platform/backup.py",
     "pipeline/platform/paths.py", "WRITER"),
    ("platform cutover config provisioning",
     "pipeline/platform/ops/cutover/provision_config.py",
     "pipeline/platform/paths.py", "WRITER"),
    ("registry store",
     "pipeline/registry/store.py",
     "pipeline/registry/paths.py", "PLATFORM_WRITER"),
    ("registry seed",
     "pipeline/registry/seed.py",
     "pipeline/registry/paths.py", "PLATFORM_WRITER"),
    ("attention state store (S7)",
     "pipeline/attention/infra/attstore.py",
     "pipeline/attention/paths.py", "PLATFORM_WRITER"),
    ("scheduling ops service (S3)",
     "pipeline/scheduling/server/serving/ops.py",
     "pipeline/scheduling/server/paths.py", "PLATFORM_WRITER"),
    ("scheduling config blocks",
     "pipeline/scheduling/server/entries/configblocks.py",
     "pipeline/scheduling/server/paths.py", "PLATFORM_WRITER"),
    ("scheduling file registry watch",
     "pipeline/scheduling/ops/watches/file_registry.py",
     "pipeline/scheduling/ops/paths.py", "PLATFORM_WRITER"),
    ("scheduling ops staged-write home",
     "pipeline/scheduling/ops/paths.py",
     "pipeline/scheduling/ops/paths.py", "PLATFORM_WRITER"),
    ("scheduling connector token",
     "pipeline/scheduling/cli/connector_token.py",
     "pipeline/scheduling/cli/paths.py", "PLATFORM_WRITER"),
    ("scheduling ops client token store",
     "pipeline/scheduling/cli/ops_client.py",
     "pipeline/scheduling/cli/paths.py", "PLATFORM_WRITER"),
    ("venue lease foundation (S5)",
     "pipeline/venue/sync/lease/core/foundation.py",
     "pipeline/venue/paths.py", "PLATFORM_WRITER"),
    ("venue writer route",
     "pipeline/venue/sync/writer_route.py",
     "pipeline/venue/paths.py", "PLATFORM_WRITER"),
    ("dispatch stateio",
     "pipeline/dispatch/stateio.py",
     "pipeline/dispatch/paths.py", "PLATFORM_WRITER"),
    ("dispatch bridge",
     "pipeline/dispatch/bridge.py",
     "pipeline/dispatch/paths.py", "PLATFORM_WRITER"),
    ("workrecord (S4)",
     "pipeline/workrecord/lib/util.py",
     "pipeline/workrecord/lib/paths.py", "PLATFORM_WRITER"),
)

# By-path loaders of the writer that are NOT seams:
# (module, what it takes from the writer). A transport
# loads the writer for its WriterError contract and
# performs writes through the /ops service instead of
# calling the loaded module — the writer-service
# route's client face. It is not a store's seam (no
# spine constant, no staged_write / perform call on
# the loaded module) and not a second implementation
# (it stages nothing; the server performs the one
# writer's protocol). The census counts it here so
# the sweep's partition stays exact: every by-path
# loader in the tree is a seam or a named transport.
TRANSPORTS = (
    ("pipeline/platform/ops_client.py",
     "the /ops client: WriterError only; writes are "
     "performed by the server-side writer over HTTP"),
)

# Every spine whose writer constant the census resolves:
# the seams' own spines plus the foundation spines the
# chained ones re-export (scheduling's and workrecord's
# package spines).
SPINES = tuple(sorted(
    {(spine, constant) for _s, _m, spine, constant in SEAMS}
    | {("pipeline/scheduling/paths.py", "PLATFORM_WRITER"),
       ("pipeline/workrecord/paths.py", "PLATFORM_WRITER")}
))


def _load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse(relpath):
    with open(REPO_ROOT / relpath, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _calls(tree):
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)]


def _loads_writer_by_path(tree):
    """The seam's load shape: a spec_from_file_location
    call, with the writer's module name carried as a
    call argument (directly, or through the seam's own
    loader helper, the backup form)."""
    has_loader = any(
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "spec_from_file_location"
        or isinstance(call.func, ast.Name)
        and call.func.id == "spec_from_file_location"
        for call in _calls(tree))
    has_name = any(
        isinstance(arg, ast.Constant) and arg.value == WRITER_NAME
        for call in _calls(tree)
        for arg in list(call.args)
        + [kw.value for kw in call.keywords])
    return has_loader and has_name


def _is_seam_source(relpath):
    """A non-test Python source under pipeline/, for the
    completeness sweeps."""
    parts = relpath.split("/")
    if "__pycache__" in parts or "tests" in parts:
        return False
    return not parts[-1].startswith("test_")


def _sweep_seams():
    found = set()
    for dirpath, dirnames, filenames in os.walk(PIPELINE):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            full = Path(dirpath) / filename
            relpath = full.relative_to(REPO_ROOT).as_posix()
            if not _is_seam_source(relpath):
                continue
            if _loads_writer_by_path(_parse(relpath)):
                found.add(relpath)
    return found


def _sweep_spines():
    found = set()
    for dirpath, dirnames, filenames in os.walk(PIPELINE):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        if "paths.py" not in filenames:
            continue
        full = Path(dirpath) / "paths.py"
        relpath = full.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(_parse(relpath)):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            if any(isinstance(target, ast.Name)
                   and target.id == "PLATFORM_WRITER"
                   for target in targets):
                found.add(relpath)
    return found


class WriterCensusTests(unittest.TestCase):
    def test_writer_entry_points_exist(self):
        module = _load_by_path("census_platform_writer", WRITER)
        for entry in ("staged_write", "perform"):
            self.assertTrue(
                callable(getattr(module, entry, None)),
                f"the unified writer at {WRITER} has no "
                f"callable {entry} entry")

    def test_every_spine_resolves_to_the_one_writer(self):
        for index, (spine, constant) in enumerate(SPINES):
            with self.subTest(spine=spine, constant=constant):
                try:
                    module = _load_by_path(
                        f"census_spine_{index}", REPO_ROOT / spine)
                except Exception as exc:  # noqa: BLE001 - named
                    self.fail(
                        f"spine {spine} cannot be loaded by "
                        f"path, so its {constant} cannot "
                        f"resolve: {exc}")
                value = getattr(module, constant, None)
                self.assertIsNotNone(
                    value,
                    f"spine {spine} declares no {constant}; "
                    f"the seams under it cannot resolve to "
                    f"the unified writer")
                resolved = os.path.realpath(os.fspath(value))
                self.assertEqual(
                    resolved, os.path.realpath(WRITER),
                    f"spine {spine}'s {constant} resolves to "
                    f"{resolved}, not the one unified writer "
                    f"at {os.path.realpath(WRITER)}")

    def test_every_seam_loads_the_writer_from_its_spine(self):
        for store, seam, spine, constant in SEAMS:
            with self.subTest(store=store, seam=seam):
                tree = _parse(seam)
                self.assertTrue(
                    any(isinstance(node, ast.Attribute)
                        and node.attr == constant
                        for node in ast.walk(tree)),
                    f"{store}: seam {seam} never references "
                    f"its spine's {constant} ({spine}); its "
                    f"writer does not resolve through the "
                    f"spine")
                self.assertTrue(
                    _loads_writer_by_path(tree),
                    f"{store}: seam {seam} does not load "
                    f"{WRITER_NAME} by path; it is not the "
                    f"standing seam form")
                self.assertTrue(
                    any(isinstance(call.func, ast.Attribute)
                        and call.func.attr in ("staged_write",
                                               "perform")
                        for call in _calls(tree)),
                    f"{store}: seam {seam} never calls "
                    f"staged_write or perform; its writes do "
                    f"not ride the unified writer")

    def test_census_counts_every_seam_in_the_tree(self):
        counted = {seam for _s, seam, _p, _c in SEAMS}
        transports = {module for module, _r in TRANSPORTS}
        self.assertFalse(
            counted & transports,
            "writer census tables overlap: "
            f"{sorted(counted & transports)} counted as "
            "both a seam and a transport — a by-path "
            "loader is exactly one of the two")
        found = _sweep_seams()
        self.assertEqual(
            found, counted | transports,
            "writer seam census drift: uncounted seam(s) "
            f"{sorted(found - counted - transports)}, "
            "counted seam(s) no longer loading the writer "
            f"by path {sorted(counted - found)} — a "
            "store's seam must be added to SEAMS or "
            "removed from it, never left uncounted; a "
            "by-path loader that never calls the writer "
            "belongs in TRANSPORTS, with its reason")

    def test_transports_never_call_the_writer(self):
        for module, _role in TRANSPORTS:
            with self.subTest(transport=module):
                tree = _parse(module)
                self.assertTrue(
                    _loads_writer_by_path(tree),
                    f"transport {module} no longer loads "
                    f"{WRITER_NAME} by path; it does not "
                    "belong in TRANSPORTS")
                self.assertFalse(
                    any(isinstance(call.func, ast.Attribute)
                        and call.func.attr in ("staged_write",
                                               "perform")
                        for call in _calls(tree)),
                    f"transport {module} calls staged_write "
                    "or perform on a loaded module; a "
                    "transport performs through the /ops "
                    "service only — a module that calls "
                    "the writer is a seam and must be "
                    "counted in SEAMS, through its spine")

    def test_census_counts_every_spine_in_the_tree(self):
        counted = {spine for spine, constant in SPINES
                   if constant == "PLATFORM_WRITER"}
        found = _sweep_spines()
        self.assertEqual(
            found, counted,
            "writer spine census drift: uncounted spine(s) "
            f"{sorted(found - counted)}, counted spine(s) "
            f"no longer assigning PLATFORM_WRITER "
            f"{sorted(counted - found)}")
        tree = _parse("pipeline/platform/paths.py")
        self.assertTrue(
            any(isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name)
                        and target.id == "WRITER"
                        for target in node.targets)
                for node in ast.walk(tree)),
            "the platform spine no longer assigns WRITER; "
            "its own stores' seam constant is gone")


if __name__ == "__main__":
    unittest.main()
