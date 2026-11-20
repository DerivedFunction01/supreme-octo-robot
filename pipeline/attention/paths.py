"""Path resolver for the attention package: every root
derivation lives here (the tree's paths discipline), and
every other module names what it consumes from here.

The package sits at pipeline/attention inside the mega
repo. Its runtime home is the registry package's var
directory — the migrated store, the armed rows, and the
connector token and caller record all live there in the
consolidated tree (the surface's state stayed with the
registry package at S7; this package is its serving and
service layer).
"""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PIPELINE_ROOT = PACKAGE_ROOT.parent
REPO_ROOT = PIPELINE_ROOT.parent
ATTENTION_HOME = PIPELINE_ROOT / "registry"
PLATFORM_SERVING = PIPELINE_ROOT / "platform" / "serving.py"

# The attention state store's own apparatus (infra/
# attstore.py, re-homed from the registry package at
# commission 12): its seed data at this package's root,
# and the platform writer its saves ride — the by-path
# seam (contract 15) every store in the tree shares.
SEEDS = PACKAGE_ROOT / "attstore_seeds.json"
PLATFORM_WRITER = PIPELINE_ROOT / "platform" / "writer.py"

# The workrecord goal store (services/measure/records.py
# collects its owner-waiting declarations): it lives in
# the workrecord package's state directory, across the
# repo from this package.
WORKRECORD_GOALS = REPO_ROOT / "pipeline" / "workrecord" / "state" / "goals.json"
