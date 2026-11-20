"""Dispatch substrate test package.

Importing this package puts the pipeline root on
sys.path (the mega repo's path-seam pattern), so test
modules import the substrate as the top-level
`dispatch` package.
"""

import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
