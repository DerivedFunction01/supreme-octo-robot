"""Build the fixture feeds document for validate-live:
the shared fixture workspace (pipeline/workrecord's
tests/server/fixture_ws) assembled through the pipeline
server half, printed as JSON on stdout.

Run by scripts/validate-live.mjs with the work-record
venv's python when present. Usage: fixture_feeds.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4] / "pipeline" / "workrecord"
sys.path.insert(0, str(ROOT))

from tests.server.fixture_ws import (  # noqa: E402
    build_fixture_workspace, fixture_config)


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="wb-live-")) / "fx"
    info = build_fixture_workspace(base)
    cfg = fixture_config(base, base / "state-live")
    os.environ["WB_VIEWER_CONFIG"] = str(cfg)
    os.environ["WB_ATTENTION_ARMED_DIR"] = str(
        info["armed_dir"])
    from server import assemble
    doc = assemble.build_feeds()
    doc["_fixture"] = {
        "doing_todo": info["doing_todo"],
        "open_todo": info["open_todo"],
        "annotation_id": info["annotation_id"],
        "plan_ref": info["plan_ref"],
    }
    print(json.dumps(doc, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
