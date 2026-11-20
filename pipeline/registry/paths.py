"""Path derivation for the pipeline registry — the ONE home.

Every registry module takes its roots from this module; no
module computes its own. Modeled on the one-spine discipline
(one paths spine owns derivation): a packaging change
touches this file, nothing else.

Derivation: this module lives in the registry package. The
package dir is its own location; the pipeline root and the
mega repo root are the two fixed steps up from it. The
cross-package by-path loads the registry performs (the
platform writer, the scheduling registry's YAML parser)
resolve here too.
"""
import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_ROOT = os.path.dirname(PACKAGE_DIR)
REPO_ROOT = os.path.dirname(PIPELINE_ROOT)

# This package's own files: the config contract's
# live/example pair. (The attention store's seeds left
# with the store at its re-home to the attention package,
# commission 12.)
CONFIG_LIVE = os.path.join(PACKAGE_DIR, "config.json")
VAR_DIR = os.path.join(PACKAGE_DIR, "var")

# The by-path loads the registry performs.
PLATFORM_WRITER = os.path.join(PIPELINE_ROOT, "platform", "writer.py")
SCHEDULING_REGISTRY = os.path.join(
    PIPELINE_ROOT, "scheduling", "server", "registry.py")
