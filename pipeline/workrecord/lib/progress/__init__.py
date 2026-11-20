"""Derived progress and its scheduler entries.

The package form of the former flat pair: the derived
progress report (cadence, checkpoints, stall verdict —
computed at read time, never stored) lives in
report.py; the scheduler-registry entry removal path
lives in schedule.py (the entry rendering is retired —
Step 6 — the tick's armed rows are the check now).
This __init__ re-exports both public surfaces so
`import lib.progress` and every current importer keep
working unchanged; entry importers name
lib.progress.schedule directly.
"""

from .report import (CHECKPOINT_PREFIX,
                     DEFAULT_CADENCE_SECONDS,
                     STALL_MISSED_CHECKS,
                     last_checkpoint,
                     measure_freshness, project_progress,
                     todo_progress)
from .schedule import (ENTRY_PREFIX,
                       REPO_ROOT, STOP_STATUSES, check_todo,
                       entry_id, is_armed,
                       jobs_dir, parse_entry_todo_id,
                       sync_all,
                       sync_todo)

__all__ = ["CHECKPOINT_PREFIX", "DEFAULT_CADENCE_SECONDS",
           "STALL_MISSED_CHECKS",
           "last_checkpoint", "measure_freshness",
           "project_progress",
           "todo_progress", "REPO_ROOT", "ENTRY_PREFIX",
           "STOP_STATUSES",
           "jobs_dir", "entry_id", "is_armed",
           "sync_todo", "sync_all",
           "parse_entry_todo_id", "check_todo"]
