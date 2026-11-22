"""Shared path derivation for the ops tree — the ONE home.

Every ops script takes its roots from this module (the shell
scripts from its counterpart, ops/paths.sh); no script computes
its own root. Modeled on the one-spine discipline: one paths
module owns path derivation, so a packaging change (like the
ops regroup into clusters) touches this file and the scripts'
bootstrap line, nothing else.

Derivation: this module lives at the ops root. The scheduling
root is found by walking up from here to the directory holding
jobs/ + server/ — depth-independent. The workspace root is
found by a second walk: up from the scheduling root to the
mega-repo root (the ancestor holding pipeline/ + apps/), whose
parent is the workspace. A tree with no mega-repo ancestor (a
fixture copy of this module standing alone with a script)
falls back to the original one-level-up derivations, which is
what a standalone copy's script always resolved.
"""
import os

OPS_DIR = os.path.dirname(os.path.abspath(__file__))


def _walk_root(start):
    d = start
    while not (os.path.isdir(os.path.join(d, "jobs"))
               and os.path.isdir(os.path.join(d, "server"))):
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.dirname(start)
        d = parent
    return d


REPO_ROOT = _walk_root(OPS_DIR)


def _walk_mega_root(start):
    d = os.path.dirname(start)
    while True:
        if os.path.isdir(os.path.join(d, "pipeline")) and os.path.isdir(
            os.path.join(d, "apps")
        ):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


_MEGA_ROOT = _walk_mega_root(REPO_ROOT)
if _MEGA_ROOT is not None:
    WORKSPACE_ROOT = os.path.dirname(_MEGA_ROOT)
else:
    WORKSPACE_ROOT = os.path.dirname(REPO_ROOT)
# The server's exported workspace anchor wins when present.
WORKSPACE_ROOT = os.environ.get("SCHEDULER_WORKSPACE", WORKSPACE_ROOT)
USER_HOME_DIR = os.path.dirname(WORKSPACE_ROOT)

STATE_DIR = os.path.join(REPO_ROOT, "state")
REGISTRY_DIR = os.path.join(REPO_ROOT, "registry")
FILE_REGISTRY_MANIFEST = os.path.join(REGISTRY_DIR, "file-registry.yaml")
JOBS_DIR = os.path.join(REPO_ROOT, "jobs")
BODIES_DIR = os.path.join(REPO_ROOT, "bodies")

# The pipeline platform's unified writer (contract 15),
# derived from the pipeline dir (the scheduling root's parent).
# In a standalone copy of the ops tree the file is absent and
# consumers perform the same protocol inline — the
# liveness entry's standing pattern.
PLATFORM_WRITER = os.path.join(
    os.path.dirname(REPO_ROOT), "platform", "writer.py")


class _Spine:
    """This module as the ops tree's paths spine, for its
    own writer seam: _load_writer below is a seam over
    this spine (spine and seam share the module), and it
    consumes the spine's PLATFORM_WRITER through the
    spine object — the standing seam form, in which a
    seam reads its spine's constant as an attribute —
    rather than as a bare module global."""

    PLATFORM_WRITER = PLATFORM_WRITER


def _load_writer():
    """The pipeline's unified writer (contract 15), loaded
    by path from PLATFORM_WRITER — the file_registry seam's
    pattern. None when the ops tree runs standalone,
    outside the mega repo."""
    if not os.path.isfile(_Spine.PLATFORM_WRITER):
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", _Spine.PLATFORM_WRITER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def staged_write(path, data):
    """Write bytes through the unified writer's protocol
    (stage to a fresh sibling, fsync, read-back compare,
    rename over — contract 15), so a denied or torn write
    leaves the standing file byte-identical. Standalone
    (no pipeline), the same protocol is performed inline:
    the protocol, not the module, is the invariant. This
    module is the ops tree's one staged-write home — ops
    scripts call it instead of staging by hand."""
    writer = _load_writer()
    if writer is not None:
        writer.staged_write(path, data)
        return
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp-ops"
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        with open(tmp, "rb") as fh:
            if fh.read() != data:
                raise OSError(
                    "read-back mismatch on staged write")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    dir_fd = os.open(directory or ".", os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def save_json(path, obj):
    """A state file's write in the ops tree's standing
    serialization (indent=1, sort_keys=True), through
    staged_write."""
    import json
    staged_write(
        path,
        json.dumps(obj, indent=1, sort_keys=True).encode("utf-8"))


def script_dir(file):
    """A consuming script's own directory (its cluster dir) —
    for sibling pointers and own-dir sys.path entries."""
    return os.path.dirname(os.path.abspath(file))


def cluster_dir(name):
    """An ops cluster dir by name (e.g. the bridge cluster the
    local-test watcher imports its connector client from)."""
    return os.path.join(OPS_DIR, name)


BRIDGE_DIR = cluster_dir("bridge")
