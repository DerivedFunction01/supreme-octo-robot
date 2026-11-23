"""Path derivation for the venue package — the ONE home.

Every venue module takes its roots from this module; no
module computes its own. Modeled on the same discipline
(one paths spine owns derivation): a packaging change
touches this file, nothing else.

Derivation: this module lives at the venue package root.
Two root forms are carried, because the tree's consumers
divide by contract:

- REPO — the package root as loaded (abspath form, never
  resolved). The runner foundation's contract: the test
  fixtures symlink the checkout's sync/ tree into a scratch
  repo whose copied bin/ keeps the root in the fixture, and
  a resolved root would follow that symlink back to the
  checkout, out of the fixture.
- REPO_RESOLVED — the same root resolved: the form the bin
  entries, the sync funnels, and the ops scripts have
  always derived, and the safe form for code loads out of
  the symlinked trees and for cross-package values.
"""
import os
from pathlib import Path

PACKAGE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
REPO = PACKAGE_DIR
REPO_RESOLVED = Path(os.path.realpath(PACKAGE_DIR))

# The package's own dirs, as loaded (the runner foundation's
# form): its runs store and the adapter's job manifests.
BIN_DIR = REPO / "bin"
RUNS_DIR = REPO / "results" / "runs"
ADAPTER_JOBS_DIR = REPO / "adapters" / "colab" / "jobs"

# Resolved forms: the transient registry the ops mirror
# binds (the var/ and results/ data roots stay joins off
# REPO at their consumers — one consumer re-roots them
# wholesale under the COLAB_RUNNER_HOME override).
TRANSIENT_REGISTRY = REPO_RESOLVED / "config" / "transient.json"

# Code loads out of the sync tree (resolved, as the loaders
# have always resolved them).
NAMING = REPO_RESOLVED / "sync" / "naming.py"
LIVENESS_ENTRY = REPO_RESOLVED / "sync" / "liveness_entry.py"
EXTEND_GUARD = REPO_RESOLVED / "sync" / "extend_guard.py"
LEASE_FOUNDATION = (
    REPO_RESOLVED / "sync" / "lease" / "core" / "foundation.py")

# Cross-package values, through the resolved root: the
# pipeline root, and the platform writer the record
# writers delegate to (contract 15) with the platform
# /ops client beside it — the seam's writes are performed
# by the scheduler service through that client. (The
# liveness entries' scheduling dir is deliberately not a
# spine value: it is a function of the liveness module's
# own root — a patchable seam — and is composed from that
# root at the consumer.)
PIPELINE_ROOT = REPO_RESOLVED.parent
PLATFORM_WRITER = PIPELINE_ROOT / "platform" / "writer.py"
PLATFORM_OPS_CLIENT = PIPELINE_ROOT / "platform" / "ops_client.py"
