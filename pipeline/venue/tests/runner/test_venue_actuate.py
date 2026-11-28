"""Venue-state actuators (sync/runner/venue_actuate.py): the
reap decisions, the process-table match, the saturation and
share legs.

Dummy-first, as the plan rules for the kill path: every pin
runs over hand-built process tables and state dicts — no
live venue, no SSH, no real process is ever signalled. The
battery leads with the safety cases: a tree whose root is
dead while descendants survive reparented to init (the
root-pid read sees nothing; the run-dir name match is the
only leg that finds them), a process naming another run's
dir (never a subject), the caller's own chain (never a
subject), and a reap that leaves a survivor (never a
settle). The payload pins are textual: the command names
its run and root, and its output parses back into the
verdict the settle consumes.
"""

import sys
import types
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402


def _load_actuate():
    package = types.ModuleType("runner_va_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_va_unit"] = package
    foundation = types.ModuleType("runner_va_unit.foundation")

    def _epoch(value):
        # The production foundation's epoch, mirrored.
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except (TypeError, ValueError):
            return None

    foundation.epoch = _epoch
    sys.modules["runner_va_unit.foundation"] = foundation
    return load_module(
        "runner_va_unit.venue_actuate",
        REPO / "sync" / "runner" / "venue_actuate.py",
        register=True,
    )


va = _load_actuate()

RUN_DIR = "venue-runs/job-20261126T200000Z"
OTHER_DIR = "venue-runs/other-20261126T200000Z"
NOW = 1_800_000_000.0


def _proc(ppid, pgid, cmdline="", cwd=""):
    return {"ppid": ppid, "pgid": pgid, "cmdline": cmdline, "cwd": cwd}


# --- the match: safety cases first ---


def test_dead_root_reparented_descendants_match_by_run_dir_name():
    # The specimen shape: the root is gone, a shard and its
    # child survive reparented to init, outside the root's
    # process group, still naming the run dir. The name and
    # cwd legs are the only ones that can find them.
    procs = {
        1: _proc(0, 1, "/sbin/init"),
        900: _proc(1, 900, f"python shard.py --out {RUN_DIR}/part", "/root"),
        901: _proc(1, 900, "python next-server.py", RUN_DIR),
        950: _proc(
            1, 950, "python shard.py --out venue-runs/other-x/part", "/root"
        ),
    }
    matched = va.matching_pids(procs, 4242, RUN_DIR)
    assert matched == [900, 901]


def test_live_tree_matches_descendants_and_group_members():
    procs = {
        1: _proc(0, 1, "/sbin/init"),
        4242: _proc(1, 4242, f"bash {RUN_DIR}/run.sh", RUN_DIR),
        4243: _proc(4242, 4242, "python worker.py", "/tmp"),
        4244: _proc(4243, 4242, "python helper.py", "/tmp"),
        4245: _proc(1, 4242, "setsid-less sibling", "/var"),
        700: _proc(1, 700, "unrelated", "/var"),
    }
    matched = va.matching_pids(procs, 4242, RUN_DIR)
    assert matched == [4242, 4243, 4244, 4245]


def test_another_runs_process_is_never_a_subject():
    procs = {
        1: _proc(0, 1, "/sbin/init"),
        4242: _proc(1, 4242, f"bash {RUN_DIR}/run.sh", RUN_DIR),
        950: _proc(1, 950, f"bash {OTHER_DIR}/run.sh", OTHER_DIR),
        951: _proc(950, 950, "python worker.py", OTHER_DIR),
    }
    matched = va.matching_pids(procs, 4242, RUN_DIR)
    assert matched == [4242]


def test_self_chain_and_init_are_never_subjects():
    # The payload process and its ancestors: even standing
    # in the run dir (the checker exec's own cwd), the chain
    # that runs the reap is excluded absolutely, as is pid 1.
    procs = {
        1: _proc(0, 1, f"/sbin/init --cwd {RUN_DIR}"),
        4242: _proc(1, 4242, f"bash {RUN_DIR}/run.sh", RUN_DIR),
        800: _proc(1, 800, "sshd: agent", "/root"),
        801: _proc(800, 801, "bash -c python3 -", RUN_DIR),
        802: _proc(801, 801, "python3 -", RUN_DIR),
    }
    matched = va.matching_pids(procs, 4242, RUN_DIR, exclude={800, 801, 802})
    assert matched == [4242]


def test_survivors_after_partial_kill_still_match_by_name_and_group():
    # Post-kill table: root gone, one group member and one
    # reparented name-match remain. The settle's verify reads
    # them through the captured pgid and the name leg.
    procs = {
        1: _proc(0, 1, "/sbin/init"),
        4245: _proc(1, 4242, "surviving sibling", "/var"),
        900: _proc(1, 900, f"python shard.py --out {RUN_DIR}/part", "/root"),
    }
    left = va.survivors(procs, 4242, RUN_DIR, pgid=4242)
    assert left == [900, 4245]


def test_no_survivors_on_a_clean_table():
    procs = {1: _proc(0, 1, "/sbin/init"), 700: _proc(1, 700, "unrelated", "/var")}
    assert va.survivors(procs, 4242, RUN_DIR, pgid=4242) == []


# --- the settle licence ---


def test_settle_only_on_a_verified_empty_table():
    clean = {"verified_gone": True, "survivors": [], "exit_code": 143}
    assert va.settle_action(clean) == ("settle", 143)
    # The job finished on its own during the reap: its own
    # standing exit code settles it, not the reap's 143.
    own = {"verified_gone": True, "survivors": [], "exit_code": 0}
    assert va.settle_action(own) == ("settle", 0)


def test_a_reap_leaving_a_survivor_never_settles():
    left = {"verified_gone": False, "survivors": [900], "exit_code": None}
    assert va.settle_action(left) == ("hold", [900])
    unverified = {"verified_gone": False, "survivors": [], "exit_code": None}
    assert va.settle_action(unverified)[0] == "hold"
    assert va.settle_action(None)[0] == "hold"
    assert va.settle_action({})[0] == "hold"


# --- the payload ---


def test_reap_command_names_run_and_root_and_parses_back():
    cmd = va.build_reap_command("job-20261126T200000Z", 4242)
    assert "job-20261126T200000Z" in cmd
    assert "VENUE_REAP_EOF" in cmd
    out = 'noise line\nREAPJ {"run_id": "job-20261126T200000Z", "verified_gone": true, "survivors": [], "exit_code": 143, "exit_written": true}\n'
    parsed = va.parse_reap_output(out)
    assert parsed["verified_gone"] is True
    assert va.parse_reap_output("no verdict here") is None
    assert va.parse_reap_output("") is None


# --- reap decisions ---


def _state(jobs, state="wedged"):
    return {
        "venue": "test-venue",
        "state": state,
        "sampled_at": "2026-11-26T20:10:00+00:00",
        "pids_current": 40,
        "pids_capacity": 1024,
        "jobs": jobs,
    }


def _job(run_id, verdict, alive=True, pid=4242, cpu=120.0, delta=0.0):
    return {
        "run_id": run_id,
        "caller": "lane-a",
        "root_pid": pid,
        "tree_alive": alive,
        "cpu_s": cpu,
        "cpu_delta_s": delta,
        "verdict": verdict,
    }


def test_wedged_job_decides_a_reap_with_its_samples_as_evidence():
    state = _state([_job("run-w", "wedged")])
    recs = {
        "run-w": {
            "state": "running",
            "caller": "lane-a",
            "started_at": "2026-11-26T19:00:00+00:00",
            "timeout_s": 18000,
        }
    }
    decisions = va.reap_decisions(state, recs, now_epoch=NOW)
    assert len(decisions) == 1
    d = decisions[0]
    assert d["run_id"] == "run-w" and d["reason"] == "wedged" and d["root_pid"] == 4242
    assert d["evidence"]["cpu_s"] == 120.0 and d["evidence"]["cpu_delta_s"] == 0.0


def test_unreachable_held_job_decides_no_reap_on_either_leg():
    # A job held at "unreachable" (its venue is dark) is
    # never reaped: not on the wedged leg, and not on the
    # timeout leg even with its record long past timeout —
    # the actuator cannot verify a tree it cannot see, and
    # no timeout accrues across a dark window.
    state = _state(
        [_job("run-u", "unreachable"), _job("run-w", "wedged", pid=4343)],
        state="unreachable",
    )
    recs = {
        "run-u": {
            "state": "running",
            "caller": "lane-a",
            "started_at": "2026-11-26T19:00:00+00:00",
            "timeout_s": 60,
        },
        "run-w": {
            "state": "running",
            "caller": "lane-a",
            "started_at": "2026-11-26T19:00:00+00:00",
            "timeout_s": 18000,
        },
    }
    decisions = va.reap_decisions(state, recs, now_epoch=NOW)
    assert [d["run_id"] for d in decisions] == ["run-w"]


def test_advancing_past_timeout_decides_a_timeout_reap():
    # The classifier verdicts this tree "advancing" (its CPU
    # still grows); the timeout reap keys off the record.
    state = _state(
        [_job("run-t", "advancing", cpu=900.0, delta=5.0)], state="advancing"
    )
    started = va.epoch("2026-11-26T19:00:00+00:00")
    recs = {
        "run-t": {
            "state": "running",
            "started_at": "2026-11-26T19:00:00+00:00",
            "timeout_s": 600,
        }
    }
    decisions = va.reap_decisions(state, recs, now_epoch=started + 900)
    assert len(decisions) == 1
    assert decisions[0]["reason"] == "timeout"


def test_stalled_gone_and_terminal_decide_nothing():
    from datetime import datetime, timezone

    recent = datetime.fromtimestamp(NOW - 300, tz=timezone.utc).isoformat()
    state = _state(
        [
            _job("run-s", "stalled"),
            _job("run-g", "gone", alive=False),
            _job("run-done", "wedged", pid=5555),
        ]
    )
    recs = {
        "run-s": {"state": "running", "started_at": recent, "timeout_s": 18000},
        "run-done": {"state": "failed", "started_at": recent, "timeout_s": 18000},
    }
    assert va.reap_decisions(state, recs, now_epoch=NOW) == []


# --- saturation refusal ---


def _saturated(at_epoch):
    from datetime import datetime, timezone

    stamp = datetime.fromtimestamp(at_epoch, tz=timezone.utc).isoformat()
    return {
        "venue": "test-venue",
        "state": "saturated",
        "sampled_at": stamp,
        "pids_current": 1000,
        "pids_capacity": 1024,
        "jobs": [],
    }


def test_saturation_refusal_names_the_state_when_fresh():
    refusal = va.saturation_refusal(_saturated(NOW), now_epoch=NOW)
    assert refusal is not None
    assert "saturated" in refusal and "1000/1024" in refusal


def test_saturation_refusal_ignores_stale_advancing_and_absent():
    assert va.saturation_refusal(_saturated(NOW - 7200), now_epoch=NOW) is None
    advancing = _saturated(NOW)
    advancing["state"] = "advancing"
    assert va.saturation_refusal(advancing, now_epoch=NOW) is None
    unreachable = _saturated(NOW)
    unreachable["state"] = "unreachable"
    assert va.saturation_refusal(unreachable, now_epoch=NOW) is None
    assert va.saturation_refusal(None, now_epoch=NOW) is None


# --- share sizing ---


def _share_state(current, capacity=1024, at_epoch=NOW):
    from datetime import datetime, timezone

    stamp = datetime.fromtimestamp(at_epoch, tz=timezone.utc).isoformat()
    return {
        "venue": "test-venue",
        "state": "advancing",
        "sampled_at": stamp,
        "pids_current": current,
        "pids_capacity": capacity,
        "jobs": [],
    }


def test_share_scales_declared_cores_by_the_free_fraction():
    share = va.share_for(_share_state(0), 8, now_epoch=NOW)
    assert share == {"workers": 8, "free_fraction": 1.0, "basis": "state"}
    share = va.share_for(_share_state(512), 8, now_epoch=NOW)
    assert share["workers"] == 4 and share["free_fraction"] == 0.5
    share = va.share_for(_share_state(1023), 8, now_epoch=NOW)
    assert share["workers"] == 1


def test_share_without_a_fresh_state_is_unscaled_and_named():
    share = va.share_for(None, 8, now_epoch=NOW)
    assert share["workers"] == 8 and share["basis"] == "no-state"
    share = va.share_for(_share_state(0, at_epoch=NOW - 7200), 8, now_epoch=NOW)
    assert share["workers"] == 8 and share["basis"] == "stale-state"
    share = va.share_for(_share_state(0), None, now_epoch=NOW)
    assert share["workers"] is None and share["basis"] == "no-cores-declared"
