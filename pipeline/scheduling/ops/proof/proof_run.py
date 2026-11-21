#!/usr/bin/env python3
"""Proof run for one registry entry, in whatever context invokes
this script (Step 5 runs it under a transient systemd unit with
the server service's own WorkingDirectory and Environment, so a
pass here is a pass in the server's real context — an agent-shell
success proves nothing).

Usage: proof_run.py <job-id>
Writes state/proof-<job-id>.txt and exits with the run's status
mapped to 0 (ok) / 1 (anything else).
"""
import os
import sys
from datetime import datetime, timezone

import importlib.util as _importlib_util

_here = os.path.dirname(os.path.abspath(__file__))
_paths_spec = _importlib_util.spec_from_file_location(
    "ops_paths",
    next(_p for _p in (os.path.join(os.path.dirname(_here), "paths.py"),
                       os.path.join(_here, "paths.py"))
         if os.path.isfile(_p)))
paths = _importlib_util.module_from_spec(_paths_spec)
_paths_spec.loader.exec_module(paths)

sys.path.insert(0, paths.REPO_ROOT)

from server import registry  # noqa: E402
from server.firing import executor  # noqa: E402

ROOT = paths.REPO_ROOT


def main(argv):
    if len(argv) != 2:
        print("usage: proof_run.py <job-id>", file=sys.stderr)
        return 2
    job_id = argv[1]
    entries, errors = registry.load_dir(
        paths.JOBS_DIR, ROOT, anchors=registry.derive_anchors(ROOT)
    )
    if errors:
        print(f"registry errors: {errors}", file=sys.stderr)
        return 2
    if job_id not in entries:
        print(f"no such entry: {job_id}", file=sys.stderr)
        return 2
    result = executor.run_entry(entries[job_id], datetime.now(timezone.utc), 65536)
    out_path = os.path.join(paths.STATE_DIR, f"proof-{job_id}.txt")
    text = (f"status={result.status} exit={result.exit_code}\n"
            + (result.stdout_tail or "")[-2000:]
            + (result.stderr_tail or "")[-1000:])
    paths.staged_write(out_path, text.encode("utf-8"))
    print(f"proof {job_id}: status={result.status} exit={result.exit_code}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
