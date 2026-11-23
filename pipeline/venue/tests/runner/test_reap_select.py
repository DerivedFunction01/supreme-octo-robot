"""The job-end process reap's selection (2026-11-23): the
launch stamp wrapper reaps a run's leaked processes at job
end, scoped to the run's own directories — a process is
the run's when its working directory or an open file sits
under the Step 5 upload dir or the run's out dir, and
nothing else is ever signalled. The selection is a pure
function over a process-table snapshot, shipped as source
(REAP_SELECT_SOURCE) because the wrapper carries it
verbatim onto the session; these pins exec that same
source over synthetic snapshots — no live process is ever
a test subject (the determinism ruling) — and pin the
wrapper's construction on its source: payload first, reap
second, exit stamp last, so a terminal read implies the
reap already ran.
"""

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

SCOPE = ["/vm/runs/R1", "/vm/job-out-R1"]
GROUP = 500


def load_launch():
    package = types.ModuleType("runner_reap_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_reap_unit"] = package
    foundation = types.ModuleType("runner_reap_unit.foundation")
    foundation.REPO = REPO
    foundation.colab = None
    foundation.json_object_from_output = None
    foundation.lease = None
    foundation.transfer = None
    sys.modules["runner_reap_unit.foundation"] = foundation
    return load_module("runner_reap_unit.launch", REPO / "sync" / "runner" / "launch.py", register=True)


def _select(launch):
    ns: dict = {}
    exec(launch.REAP_SELECT_SOURCE, ns)
    return ns["_reap_select"]


def _proc(pid, cwd=None, fds=None, pgid=None):
    return {"pid": pid, "cwd": cwd, "fds": fds, "pgid": pgid}


def test_cwd_under_the_upload_dir_is_reaped():
    select = _select(load_launch())
    reaped, left = select([_proc(10, cwd="/vm/runs/R1/sub", fds=[], pgid=GROUP)], SCOPE, own_pid=99, group_pid=GROUP)
    assert reaped == [10] and left == []


def test_open_file_under_the_out_dir_is_reaped():
    select = _select(load_launch())
    procs = [_proc(11, cwd="/vm", fds=["/vm/job-out-R1/server.log"], pgid=GROUP)]
    reaped, left = select(procs, SCOPE, own_pid=99, group_pid=GROUP)
    assert reaped == [11] and left == []


def test_deleted_open_file_under_scope_still_scopes():
    select = _select(load_launch())
    procs = [_proc(12, cwd="/vm", fds=["/vm/runs/R1/payload.py (deleted)"], pgid=GROUP)]
    reaped, _ = select(procs, SCOPE, own_pid=99, group_pid=GROUP)
    assert reaped == [12]


def test_sibling_run_dir_does_not_scope():
    """Scope is the run's own dirs, exact-segment: another
    run's upload dir (runs/R2) is not this run's scope."""
    select = _select(load_launch())
    procs = [_proc(13, cwd="/vm/runs/R2", fds=["/vm/runs/R2/x"], pgid=999)]
    reaped, left = select(procs, SCOPE, own_pid=99, group_pid=GROUP)
    assert reaped == [] and left == []


def test_group_member_outside_scope_is_left_and_reported():
    """The job's own process the dir test cannot scope — the
    payload's server started at the session root with no run
    files open — is left alive and named unscoped, never
    signalled on a guess."""
    select = _select(load_launch())
    procs = [_proc(14, cwd="/vm", fds=["/vm/shared.log"], pgid=GROUP)]
    reaped, left = select(procs, SCOPE, own_pid=99, group_pid=GROUP)
    assert reaped == [] and left == [14]


def test_uninspectable_group_member_is_left_and_reported():
    """Scope that cannot be established (cwd and fd table
    unreadable) is no evidence: left alone, and stamped."""
    select = _select(load_launch())
    procs = [_proc(15, cwd=None, fds=None, pgid=GROUP)]
    reaped, left = select(procs, SCOPE, own_pid=99, group_pid=GROUP)
    assert reaped == [] and left == [15]


def test_own_pid_is_never_a_candidate():
    """The wrapper itself, though it shares the group and
    may hold run files open, is neither reaped nor left."""
    select = _select(load_launch())
    procs = [_proc(99, cwd="/vm/runs/R1", fds=["/vm/job-out-R1/x"], pgid=GROUP)]
    reaped, left = select(procs, SCOPE, own_pid=99, group_pid=GROUP)
    assert reaped == [] and left == []


def test_foreign_process_is_neither_reaped_nor_reported():
    select = _select(load_launch())
    procs = [_proc(16, cwd="/vm", fds=[], pgid=999)]
    reaped, left = select(procs, SCOPE, own_pid=99, group_pid=GROUP)
    assert reaped == [] and left == []


def test_stamp_runs_payload_then_reaps_then_stamps_the_exit_code():
    launch = load_launch()
    stamp = launch.build_launch_stamp("runs/R1/payload.py", "job-out-R1", ",'--flag'", "R1")
    # The shipped selection is the tested selection, verbatim.
    assert launch.REAP_SELECT_SOURCE in stamp
    run_line = "subprocess.run([sys.executable, 'runs/R1/payload.py', '--out', 'job-out-R1','--flag'])"
    assert run_line in stamp
    reap_call = stamp.index("try:\n    _reap_driver()")
    assert stamp.index(run_line) < reap_call
    assert reap_call < stamp.index("open('job-out-R1.exit-code', 'w')")
    # The reap's own stamp lands in the job's output.
    assert "reap.json" in stamp


def test_main_builds_its_stamp_through_the_builder():
    text = (REPO / "sync" / "runner" / "main.py").read_text()
    assert "build_launch_stamp(remote_script, remote_out, job_args, run_id)" in text
