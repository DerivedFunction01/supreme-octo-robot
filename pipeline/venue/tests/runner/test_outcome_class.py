"""The launch-outcome classification (sync/runner/outcome.py)
and its stamp on the record (records._prepare).

The deaths this cures: terminal records said only "failed",
so a fire that never ran — its upload died, its lease
refused, its daemon was killed in its firing context — read
identically to a payload that ran and went red, and the
no-verdict sink (43.8% of fires, 82% of them pre-job) could
not be priced by stage. These pins drive the classifier
over the real failure shapes in the record population —
the local launch's SSH-stage texts, the lease stage's JSON
refusal dump (budget included), the sweep's write-offs, the
finalize's payload texts — and pin the writer's stamp: a
terminal record carries its class, a non-terminal record
carries none.
"""

import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

outcome = load_module("outcome_unit", REPO / "sync" / "runner" / "outcome.py")
classify = outcome.classify_outcome

STARTED = "2026-11-24T05:48:15+00:00"


def test_complete_is_ran_green():
    assert classify({"state": "complete"}) == "ran-green"
    assert classify({"state": "complete", "exit_code": 0}) == "ran-green"


def test_non_terminal_classes_none():
    for state in ("claiming", "starting", "running", "polling"):
        assert classify({"state": state}) is None


def test_local_exit_code_is_ran_red():
    # The local finalize stamps the payload's own code.
    assert classify({"state": "failed", "exit_code": 7}) == "ran-red"
    assert classify({"state": "failed", "exit_code": 1, "error": "anything"}) == "ran-red"


def test_payload_exit_texts_are_ran_red():
    assert classify({"state": "failed", "error": "job payload exited 3"}) == "ran-red"
    assert classify({"state": "failed", "error": "job exited before completing; remote log tail: boom"}) == "ran-red"
    assert classify({"state": "failed", "error": "payload exited 0 but collected none of its 2 declared outputs: a.json, b.json"}) == "ran-red"
    assert classify({
        "state": "failed",
        "launch_confirmed_at": STARTED,
        "error": "session calm-owl-42 confirmed absent after 5 consecutive poll failures; the payload died with its session — relaunch with --resume r to continue from its remote run-id",
    }) == "ran-red"


def test_local_launch_stage_texts_are_launch():
    # The specimens from the launch-path record population:
    # every stage of the local launch sequence classes launch.
    assert classify({"state": "failed", "error": "upload fv-fixtures-d1.tar.gz failed: Connection to 127.0.0.1 closed by remote host"}) == "launch"
    assert classify({"state": "failed", "error": "venue mkdir failed: kex_exchange_identification: read: Connection reset by peer"}) == "launch"
    assert classify({"state": "failed", "error": "launch failed: Connection to 127.0.0.1 closed by remote host"}) == "launch"
    assert classify({"state": "failed", "error": "script upload failed: Connection closed"}) == "launch"
    assert classify({"state": "failed", "error": "runner script upload: timed out"}) == "launch"
    assert classify({"state": "failed", "error": "manifest upload failed: cfg.json: timed out"}) == "launch"


def test_local_transport_faces_are_transport():
    assert classify({"state": "failed", "error": "venue unreachable: [Errno 2] No such file or directory: 'ssh'"}) == "transport"
    assert classify({"state": "failed", "error": "venue warmup: launch timed out on all 3 attempts; the transport was still warming and the venue was not reached — the dispatch may be retried"}) == "transport"


def test_lease_refusal_dump_is_launch_budget_included():
    assert classify({"state": "failed", "error": '{"action": "refused-budget", "reason": "monthly-budget"}'}) == "launch"
    assert classify({"state": "failed", "error": '{"action": "pin-unavailable", "session": "calm-owl-42"}'}) == "launch"


def test_manifest_defects_are_manifest():
    assert classify({"state": "failed", "error": "manifest upload missing locally: adapters/colab/snippets/jobs/env_build.sh"}) == "manifest"
    assert classify({"state": "failed", "error": "--detach requires the lease path (lease.enabled); the fallback per-job session dies with the poller"}) == "manifest"


def test_transport_stage_texts_are_transport():
    assert classify({"state": "failed", "error": "branch transport: registry: repo 'x' is not registered (have: [])"}) == "transport"
    assert classify({"state": "failed", "error": "bundle seed: snapshot build failed: boom"}) == "transport"
    assert classify({"state": "failed", "error": "bundle seed: seed did not verify: {}"}) == "transport"


def test_daemon_death_is_dispatch_blocked():
    assert classify({
        "state": "failed",
        "launch_lost": True,
        "error": "record still 'starting' with its daemon driver (pid 4242) dead and no launch begun: the daemonized launch died before the launch landed; relaunch with --resume r to retry",
    }) == "dispatch-blocked"


def test_launch_lost_write_offs_are_launch():
    assert classify({
        "state": "failed",
        "launch_lost": True,
        "error": "record still 'starting' 130 min after its freshest stamp: the launcher died before the launch landed; relaunch with --resume r to retry",
    }) == "launch"
    assert classify({
        "state": "failed",
        "launch_lost": True,
        "error": "launch never landed on calm-owl-42 (no job footprint on the confirmation read); relaunch with --resume r to retry",
    }) == "launch"


def test_orphaned_splits_on_launch_evidence():
    assert classify({"state": "orphaned"}) == "dispatch-blocked"
    assert classify({"state": "orphaned", "launch_confirmed_at": STARTED}) == "launch"
    assert classify({"state": "orphaned", "launch_at": STARTED}) == "launch"


def test_unseparated_failures_fall_by_launch_evidence():
    # It launched: a run failure, never a launch verdict.
    assert classify({"state": "failed", "launch_at": STARTED, "error": "reader gave up"}) == "ran-red"
    # Nothing separable: the stated default classes the
    # launch window, never a fabricated ran verdict.
    assert classify({"state": "failed", "error": "some raw CLI stderr"}) == "launch"
    assert classify({"state": "failed"}) == "launch"


def load_records(runs: Path):
    package = types.ModuleType("runner_outcome_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_outcome_unit"] = package
    foundation = types.ModuleType("runner_outcome_unit.foundation")
    foundation.REPO = REPO
    foundation.RUNS = runs
    foundation.VENUE = "test-venue"
    foundation.now = lambda: STARTED
    foundation.staged_write = lambda path, data: Path(path).write_bytes(data)
    sys.modules["runner_outcome_unit.foundation"] = foundation
    load_module("runner_outcome_unit.outcome", REPO / "sync" / "runner" / "outcome.py", register=True)
    return load_module("runner_outcome_unit.records", REPO / "sync" / "runner" / "records.py", register=True)


def test_writer_stamps_terminal_records_only(tmp_path):
    records = load_records(tmp_path)
    rec = {"run_id": "job-20261124T054815Z", "job": "job", "state": "failed", "exit_code": 7, "started_at": STARTED}
    records.save_record(rec)
    on_disk = json.loads((tmp_path / "job-20261124T054815Z.json").read_text())
    assert on_disk["outcome_class"] == "ran-red"

    live = {"run_id": "job-20261124T054816Z", "job": "job", "state": "running", "started_at": STARTED}
    records.save_record(live)
    on_disk = json.loads((tmp_path / "job-20261124T054816Z.json").read_text())
    assert "outcome_class" not in on_disk

    # A resume sheds the prior attempt's class with its state.
    rec.update(state="starting")
    records.save_record(rec)
    on_disk = json.loads((tmp_path / "job-20261124T054815Z.json").read_text())
    assert "outcome_class" not in on_disk
