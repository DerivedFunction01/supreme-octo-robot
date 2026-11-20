#!/usr/bin/env python3
"""The work-record server's standalone entry: inserts
this service's root on sys.path (for the `server`
package and `lib`) and runs the serving shell's main.

The mega app's one process is the repo-root run.py,
which mounts this same surface on the platform serving
core beside the other three; this entry stands the
surface alone, in the shape the pinned viewer's run.py
always had."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.serving import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
