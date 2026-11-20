"""Path derivation for the scheduling package — the ONE home.

Every scheduling module outside ops/ takes its roots from
this module (the server and cli areas through their own
resolver modules, server/paths.py and cli/paths.py, which
derive from this foundation); no module computes its own.
Modeled on the one-spine discipline (one paths spine owns
derivation) and the ops tree's paths.py: a packaging change
touches this file and the consumers' bootstrap lines,
nothing else. The ops tree keeps its own paths module
(ops/paths.py) — its scripts carry to venues the server
tree never reaches.

Derivation: this module lives at the scheduling package
root. The package root is its own location; the pipeline
root and the mega repo root are the two fixed steps up
from it. The package's data dirs (jobs, bodies, state,
examples) and its cross-package loads (the platform
writer, the gate portability component) resolve here.
"""
import os

PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
PIPELINE_ROOT = os.path.dirname(PACKAGE_ROOT)
REPO_ROOT = os.path.dirname(PIPELINE_ROOT)

# The package's own dirs and files.
JOBS_DIR = os.path.join(PACKAGE_ROOT, "jobs")
BODIES_DIR = os.path.join(PACKAGE_ROOT, "bodies")
STATE_DIR = os.path.join(PACKAGE_ROOT, "state")
REGISTRY_DIR = os.path.join(PACKAGE_ROOT, "registry")
EXAMPLES_DIR = os.path.join(PACKAGE_ROOT, "examples", "registry")
CONFIG_PATH = os.path.join(PACKAGE_ROOT, "config.json")
CONFIG_EXAMPLE_PATH = os.path.join(PACKAGE_ROOT, "config.example.json")
# The client-side ops token home (contract 04, §10.1): raw
# tokens live client-side only, one untracked file per caller
# (`<caller>.token`); the server stores hashes alone. The
# SCHED_OPS_TOKEN_DIR env var re-points the home (tests,
# staged installs); the default is this directory.
OPS_TOKEN_DIR = os.path.join(PACKAGE_ROOT, "ops-tokens")
SERVER_DIR = os.path.join(PACKAGE_ROOT, "server")
CLI_DIR = os.path.join(PACKAGE_ROOT, "cli")
BIN_DIR = os.path.join(PACKAGE_ROOT, "bin")
TOOLS_DIR = os.path.join(PACKAGE_ROOT, "tools")
OPS_DIR = os.path.join(PACKAGE_ROOT, "ops")

# The by-path loads the scheduling tree performs.
PLATFORM_WRITER = os.path.join(PIPELINE_ROOT, "platform", "writer.py")
PLATFORM_SERVING = os.path.join(PIPELINE_ROOT, "platform", "serving.py")
GATE_PORTABILITY = os.path.join(PIPELINE_ROOT, "gate", "portability.py")
