"""The armed-rows feed (contract 03, ARM2 + ATT9).

The harness's writers land one JSON row per armed todo
in the armed directory (lib/progress/attention.py); the
evaluator and the workbench app read them back. This is
the read side: every row file in the directory, parsed,
in (project, todo) order. A file that does not parse, or
a row missing its join keys (project, todo), is skipped
and counted — ATT9's consumer rule: such rows never
supervise, and they never break the feed either.
"""

import json

from lib.progress import attention as attention_mod
from lib.util import now_iso

ROW_PREFIX = attention_mod.ROW_PREFIX


def armed_feed(directory=None) -> dict:
    """{"rows": [...], "skipped": n, "captured_at": ...}
    over the armed directory (the writer's own directory
    unless one is named)."""
    directory = directory or attention_mod.armed_dir()
    rows = []
    skipped = 0
    if directory.is_dir():
        for path in sorted(directory.glob(f"{ROW_PREFIX}*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                skipped += 1
                continue
            if not isinstance(row, dict) \
                    or not row.get("project") \
                    or not row.get("todo"):
                skipped += 1
                continue
            rows.append(row)
    rows.sort(key=lambda r: (r["project"], r["todo"]))
    return {"rows": rows, "skipped": skipped,
            "captured_at": now_iso()}
