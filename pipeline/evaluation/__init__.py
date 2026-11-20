"""Pipeline evaluation: the doctor and the derivation
set (repos, datasets, diffs), landed at step S4 from the
workbench pin — the classification feed and the
supervision evaluator join at S10 (contract 03).

The doctor and the derivations read work-record data
through the work-record service's package (`lib` in
pipeline/workrecord): importing this package puts that
root on sys.path, the mega repo's path-seam pattern for
cross-pipeline loads (the same derivation the ops
service uses to load the platform writer). It also
puts the pipeline root on sys.path: the doctor posts
its digest through the dispatch substrate's message
store (`dispatch.messages`, plan §4.5/S6)."""

import sys

from . import paths as _paths

_WORKRECORD_ROOT = _paths.WORKRECORD_ROOT
if str(_WORKRECORD_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKRECORD_ROOT))

_PIPELINE_ROOT = _paths.PIPELINE_ROOT
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
