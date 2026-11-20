"""The work-record service's server half: the read-side
feed builders the workbench app consumes, landed at step
S8 from the pinned workbench-viewer server (pin b0b9cc5)
in the target's shape.

The pinned tree kept these as flat modules beside an
HTTP shell (server.py) that inserted its own paths. The
target shape: a package inside the work-record service.
Importing this package installs the mega repo's path
seams — the work-record root (for `lib`), the pipeline
root (for `evaluation`, `dispatch`, `registry`) — the
same pattern pipeline/evaluation's __init__ uses in the
other direction. The HTTP shell landed at S11
(serving.py, on the platform serving core); everything
it serves is a function here.

Modules:
- config: the one settings seam (WB_VIEWER_* env >
  config.json > defaults), as pinned.
- common: sweep/fingerprint caches, degraded containment,
  ApiError — the seam every feed stands on.
- feedcache: the keyed stale-while-revalidate cache.
- feeds: the entry, entries, todos, plans, board,
  worktrees, diff and home builders — pure reads
  over lib/.
- repos_feed: the repo census, status, and dataset feeds
  (derivations in pipeline/evaluation).
- messages_api: the message-store read/write surface
  over the dispatch substrate's store (plan §4.5/S6),
  plus the annotation anchor-context join (lib/
  annotations, landed with this step).
- armed: the contract 03 armed-rows feed (the rows the
  harness's writers land in the armed directory).
- goals: the contract 11 goal-records feed — the
  goal-record store's projection (lib/goals owns the
  store and its writer; this module only serves it).
- assemble: the route-keyed feeds document the app's
  live adapter consumes — every payload above, assembled
  once, in the pinned routes' shapes.
- shapestore: the assembled shapes' database store —
  the feeds document's and the census's cross-restart
  persistence, one row per shape (payload, assembly
  instant, source fingerprint).
- actions: the mutation endpoints (entries, todos, plan
  resolves) — thin callers over lib/ mutations.
- stackdump: the wedge stack-dump watchdog
  (stackdump-contract: v1).
- serving: the HTTP shell on the platform serving core —
  the single-instance lock, the route table, bind-before-
  warm, and the message-maintenance workers.
"""

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "workrecord_server_paths",
    Path(__file__).resolve().parent / "paths.py")
_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paths)

_WORKRECORD_ROOT = _paths.WORKRECORD_ROOT
if str(_WORKRECORD_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKRECORD_ROOT))

_PIPELINE_ROOT = _paths.PIPELINE_ROOT
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
