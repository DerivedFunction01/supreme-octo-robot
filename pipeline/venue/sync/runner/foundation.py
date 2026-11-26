#!/usr/bin/env python3
"""Runner foundation: repo roots, the module handles, the funnel.

Every runner leaf builds on these: REPO/RUNS (derived from this
file's location, one level deeper than bin/ was for the
monolith — the root it lands on is the same), the sync/cli.py funnel
binding, the lease / repo-registry / transfer handles loaded
through bin/_load.py (the one bin loader), and the two helpers
with no seam of their own (now, mirror).
"""

import importlib.util as _ilu
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The paths spine (paths.py at the package root) owns the
# root derivation. It is loaded by path from this file's
# own location, and its root is the path as loaded, never
# resolved: the test fixtures symlink the checkout's sync/
# tree into a scratch repo whose copied bin/ keeps the
# root in the fixture (repo_fixture.cli_repo's contract),
# and resolving here would follow that symlink back to
# the checkout — the subprocess would read the checkout's
# (absent) operator config and the session gate would fail
# closed against the fixture's authored policy.
_paths_spec = _ilu.spec_from_file_location(
    "venue_paths", Path(__file__).parent.parent.parent / "paths.py")
_paths = _ilu.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(_paths)

REPO = _paths.REPO
PLATFORM_ARGV = _paths.PLATFORM_ARGV
RUNS = _paths.RUNS_DIR
# The venue adapter's job manifests (plan §7 V3): adapter
# material under adapters/<venue>/jobs, never core tree.
JOBS = _paths.ADAPTER_JOBS_DIR

sys.path.insert(0, str(REPO / "bin"))
import _load

cli = _load.sync("cli")
lease = _load.sync("lease")

# Venue identity + the unified-writer seam, single-sourced in
# the lease core's foundation (S5, plan §7 V1 / §4.15): run
# records stamp the same venue the lease records stamp, and
# their writes ride the same writer protocol.
VENUE = lease.foundation.VENUE
staged_write = lease.foundation.staged_write
repo_registry = _load.sync("repo_registry")
transfer = _load.sync("transfer")
git_identity = _load.sync("git_identity")

# The funnel, re-exported under the names this module's consumers
# (bin/colab-lease & friends historically, the test suites) use.
colab = cli.colab
colab_bin = cli.colab_bin
colab_env = cli.colab_env
json_object_from_output = cli.json_object_from_output
TOKEN = cli.TOKEN


def mirror(op: str) -> None:
    subprocess.run([sys.executable, str(REPO / "ops" / "mirror_transient.py"), op], capture_output=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def epoch(value) -> "float | None":
    """A served stamp → epoch seconds, else None (a
    missing or malformed stamp is an honest unknown)."""
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None
