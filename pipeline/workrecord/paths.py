"""Path derivation for the work-record package — the ONE
home.

Every work-record module takes its roots from this module
(the lib, server, and wbcli areas through their own
resolver modules, which derive from this foundation); no
module computes its own. Modeled on programme-a's discipline
(one paths spine owns derivation): a packaging change
touches this file, nothing else.

Derivation: this module lives at the package root. The
package dir is its own location; the pipeline root, the
mega repo root, and the workspace root are the fixed steps
up from it. Cross-package values (the platform writer, the
scheduling registry and its jobs dir) resolve here too.

This module also carries the tree's one cwd derivation:
project_root_from_cwd, wb's project selection walk (see
its docstring). The standing rule — cwd acts as root in
exactly one runtime place — holds here by construction:
no other module in the tree reads the cwd as a root.
"""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = PACKAGE_DIR.parent
REPO_ROOT = PIPELINE_ROOT.parent
WORKSPACE_ROOT = REPO_ROOT.parent

# Cross-package values.
PLATFORM_WRITER = PIPELINE_ROOT / "platform" / "writer.py"
SCHEDULING_REGISTRY = (
    PIPELINE_ROOT / "scheduling" / "server" / "registry.py")
SCHEDULING_JOBS_DIR = PIPELINE_ROOT / "scheduling" / "jobs"
WORKTREE_TRIM_SCRIPT = (
    PIPELINE_ROOT / "scheduling" / "ops" / "worktree_trim.sh")

MANIFEST_NAME = "workbench.yaml"


def project_root_from_cwd(start=None):
    """The nearest directory at or above the cwd holding
    the project manifest, or None.

    wb's operating model is the git model: the CLI runs
    inside the project it operates on, and project
    selection (after --db / --root / --project) walks up
    from the cwd for workbench.yaml. This walk is the
    tree's single cwd site; both wb contexts consume it.
    """
    here = Path(start) if start is not None else Path.cwd()
    for candidate in (here, *here.parents):
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    return None
