"""Registry test package.

Importing this package puts the pipeline root on
sys.path (the mega repo's path-seam pattern), so test
modules can import the sibling packages the card
watcher spans (`pipeline/dispatch`,
`pipeline/attention`) directly, as the watcher itself
does.
"""

import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
