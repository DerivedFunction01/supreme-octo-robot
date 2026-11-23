"""Path derivation for the platform services — the ONE home.

Every platform module takes its roots from this module; no
module computes its own. Modeled on the one-spine discipline
(one paths spine owns derivation) and the ops tree's
paths.py: a packaging change touches this file and the
consumers' bootstrap lines, nothing else.

Derivation: this module lives in the platform package. The
package dir is its own location; the pipeline root and the
mega repo root are the two fixed steps up from it. The
cross-package by-path loads the platform services perform
(the dispatch ledger, the scheduling registry) resolve
here too, so no consumer re-derives a sibling's location.
"""

import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_ROOT = os.path.dirname(PACKAGE_DIR)
# The repo root in the form the platform services have
# always used it: realpath'd, then descended from — the
# by-path loads below resolve exactly as the consumers
# they replace resolved them.
REPO_ROOT = os.path.realpath(os.path.join(PACKAGE_DIR, "..", ".."))

# This package's own files.
WRITER = os.path.join(PACKAGE_DIR, "writer.py")
STATE_DIR = os.path.join(PACKAGE_DIR, "state")


def repo_module(*parts):
    """A file under the repo root, by path parts."""
    return os.path.join(REPO_ROOT, *parts)


# The by-path loads the platform services perform.
DISPATCH_LEDGER = repo_module("pipeline", "dispatch", "ledger.py")
SCHEDULING_REGISTRY = repo_module("pipeline", "scheduling", "server", "registry.py")
WORKRECORD_ROOT = repo_module("pipeline", "workrecord")

# The scheduling package: the /ops service's home. The ops
# client (ops_client.py, beside the writer) resolves the
# service endpoint from its live config and the acting
# caller's token from its token home (contract 04, §10.1:
# raw tokens live client-side only, one <caller>.token
# file; the SCHED_OPS_TOKEN_DIR env var re-points the home).
SCHEDULING_ROOT = os.path.join(PIPELINE_ROOT, "scheduling")
SCHEDULING_CONFIG = os.path.join(SCHEDULING_ROOT, "config.json")
OPS_TOKEN_DIR = os.path.join(SCHEDULING_ROOT, "ops-tokens")
