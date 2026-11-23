"""Same-second parallel launches of one job must not collide.

The specimen: two detached launches
of the same job inside one second minted the
identical run_id — the second run's record saves silently
absorbed the first's, and one shard's results were lost with
no error at either launch. The first save now claims the id
exclusively and suffixes past an occupied one.

This pin occupies the smoke job's base id for every second in
a wide window around the launch with terminal marker records,
so the launch cannot land on a free base by timing luck: it
must come back with the -2 suffix, live its whole life under
that id, and leave every marker byte-identical.
"""

import json
import re
import time
from datetime import datetime, timedelta, timezone

from runner_harness import _detach_smoke, run_verb, runner_env, runs_dir  # noqa: F401


def test_launch_suffixes_past_an_occupied_base_id(tmp_path):
    env = runner_env(tmp_path)
    runs = runs_dir(env)
    runs.mkdir(parents=True, exist_ok=True)
    markers = {}
    start = datetime.now(timezone.utc) - timedelta(seconds=10)
    for offset in range(260):
        ts = (start + timedelta(seconds=offset)).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"smoke-{ts}"
        body = json.dumps(
            {
                "run_id": run_id,
                "job": "smoke",
                "state": "complete",
                "started_at": "2026-01-01T00:00:00+00:00",
                "marker": "occupied",
            }
        )
        (runs / f"{run_id}.json").write_text(body)
        markers[run_id] = body

    out = _detach_smoke(env)
    run_id = out["run_id"]
    assert re.fullmatch(r"smoke-\d{8}T\d{6}Z-2", run_id), f"launch did not suffix past the occupied base: {run_id}"
    assert (runs / f"{run_id}.json").exists()

    rc = 3
    deadline = time.time() + 180
    while rc == 3 and time.time() < deadline:
        rc = run_verb(env, "--poll", run_id).returncode
    assert rc == 0, "the suffixed run never reconciled to completion"
    rec = json.loads((runs / f"{run_id}.json").read_text())
    assert rec["state"] == "complete"
    assert rec["run_id"] == run_id

    for occupied_id, body in markers.items():
        assert (runs / f"{occupied_id}.json").read_text() == body, f"occupied record {occupied_id} was overwritten"
