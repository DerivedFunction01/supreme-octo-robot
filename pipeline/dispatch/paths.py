"""Path derivation for the dispatch substrate — the ONE home.

Every dispatch module takes its roots from this module; no
module computes its own. Modeled on the one-spine discipline
(one paths spine owns derivation): a packaging change
touches this file, nothing else.

Derivation: this module lives in the dispatch package. The
package dir is its own location; the pipeline root and the
mega repo root are the two fixed steps up from it. The one
cross-package load the substrate performs (the platform
writer, contract 15) resolves here too.
"""
import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_ROOT = os.path.dirname(PACKAGE_DIR)
REPO_ROOT = os.path.dirname(PIPELINE_ROOT)

# The by-path load the substrate performs.
PLATFORM_WRITER = os.path.join(PIPELINE_ROOT, "platform", "writer.py")
