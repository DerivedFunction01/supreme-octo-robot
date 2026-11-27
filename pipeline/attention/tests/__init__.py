"""Test harness seeding: the supervision registry's
declaration rows are instance data in an untracked
config (services/measure/registry.py); the suite runs
against the tracked specimen declarations instead —
generic placeholder programmes mirroring the live
rows' shapes — seeded through the loader's env
override. setdefault: a runner may point the suite at
another config deliberately."""

import os
from pathlib import Path

_SPECIMEN = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "supervision-registry.specimen.json"
)
os.environ.setdefault("ATTENTION_SUPERVISION_REGISTRY", str(_SPECIMEN))
