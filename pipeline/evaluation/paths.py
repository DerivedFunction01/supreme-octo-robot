"""Path derivation for pipeline evaluation — the ONE home.

Every evaluation module takes its roots from this module;
no module computes its own. Modeled on the one-spine
discipline (one paths spine owns derivation): a packaging
change touches this file, nothing else.

Derivation: this module lives in the evaluation package.
The package dir is its own location; the pipeline root is
the one fixed step up from it, and the work-record root —
the root this package puts on sys.path for its data — is
the pipeline root's workrecord child.
"""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = PACKAGE_DIR.parent
WORKRECORD_ROOT = PIPELINE_ROOT / "workrecord"
