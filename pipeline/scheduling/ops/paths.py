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


def script_dir(file):
    """A consuming script's own directory (its cluster dir) —
    for sibling pointers and own-dir sys.path entries."""
    return os.path.dirname(os.path.abspath(file))


def cluster_dir(name):
    """An ops cluster dir by name (e.g. the bridge cluster the
    local-test watcher imports its connector client from)."""
    return os.path.join(OPS_DIR, name)


BRIDGE_DIR = cluster_dir("bridge")
