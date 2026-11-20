"""The scheduling server package.

Importing this package puts the pipeline root on
sys.path, the mega repo's path-seam pattern for
cross-pipeline loads: the dispatch substrate
(`pipeline/dispatch` — ledger, outbox, stateio, bridge,
wake, sends) is imported by the server, the CLI, and the
ops scripts as the top-level `dispatch` package.
"""

import sys
from pathlib import Path

from . import paths as _paths

_PIPELINE_ROOT = Path(_paths.PIPELINE_ROOT)
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
