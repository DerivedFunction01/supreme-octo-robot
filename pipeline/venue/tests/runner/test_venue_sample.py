"""The venue-state sampler leaf (sync/runner/venue_sample.py):
the probe payload's parser, the /proc stat reader, the tree
CPU sum, and the JSON-lines sample store.

Dummy-first by construction: every fixture below is recorded
probe output in the payload's exact line format, and the tree
walk is pinned through the pure sum_tree_cpu helper over
hand-built stat maps — no /proc, no venue, no network.
"""

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

vs = load_module("venue_sample_unit", REPO / "sync" / "runner" / "venue_sample.py")

AT = "2026-01-01T00:00:00+00:00"

FIXTURE_ADVANCING = """\
PIDS 812 1024
JOB gate-a-20260101T000000Z 4101 1 50213
JOB gate-b-20260101T000000Z 4207 1 918
"""

FIXTURE_VANISHED = """\
PIDS 7 1024
JOB gate-a-20260101T000000Z 4101 0 0
"""

FIXTURE_UNLIMITED = """\
PIDS 7 max
"""

FIXTURE_DISK = """\
PIDS 812 1024
DISK root 52428800
DISK workspace 1048576
JOB gate-a-20260101T000000Z 4101 1 50213
"""

FIXTURE_DISK_PARTIAL = """\
PIDS 812 1024
DISK root notakb
DISK cellar 1048576
"""

FIXTURE_MALFORMED = """\
PIDS 812 1024
this line is not a probe line
JOB only-three 4101 1
JOB gate-x notapid 1 500
JOB gate-y 4102 maybe 500
JOB gate-z 4103 1 noticks
ERR pids cgroup files unreadable

JOB gate-a-20260101T000000Z 4101 1 50213
"""


def test_parse_two_advancing_jobs():
    sample = vs.parse_sample(FIXTURE_ADVANCING, "msi-hx18", AT)
    assert sample["venue"] == "msi-hx18"
    assert sample["at"] == AT
    assert sample["pids_current"] == 812
    assert sample["pids_max"] == 1024
    assert sample["errors"] == []
    assert sample["jobs"] == [
        {
            "run_id": "gate-a-20260101T000000Z",
            "root_pid": 4101,
            "tree_alive": True,
            "cpu_ticks": 50213,
        },
        {
            "run_id": "gate-b-20260101T000000Z",
            "root_pid": 4207,
            "tree_alive": True,
            "cpu_ticks": 918,
        },
    ]


def test_parse_vanished_tree_reads_dead_with_zero_ticks():
    sample = vs.parse_sample(FIXTURE_VANISHED, "hp-envy", AT)
    assert sample["pids_current"] == 7
    assert sample["jobs"] == [
        {
            "run_id": "gate-a-20260101T000000Z",
            "root_pid": 4101,
            "tree_alive": False,
            "cpu_ticks": 0,
        }
    ]


def test_parse_unlimited_pids_max_is_none():
    sample = vs.parse_sample(FIXTURE_UNLIMITED, "msi-hx18", AT)
    assert sample["pids_current"] == 7
    assert sample["pids_max"] is None
    assert sample["jobs"] == []


def test_parse_malformed_lines_ignored_not_fatal():
    sample = vs.parse_sample(FIXTURE_MALFORMED, "msi-hx18", AT)
    assert sample["pids_current"] == 812
    assert sample["pids_max"] == 1024
    assert sample["errors"] == ["pids cgroup files unreadable"]
    assert [job["run_id"] for job in sample["jobs"]] == ["gate-a-20260101T000000Z"]


def test_parse_empty_output_is_an_empty_sample():
    sample = vs.parse_sample("", "msi-hx18", AT)
    assert sample["pids_current"] is None
    assert sample["pids_max"] is None
    assert sample["jobs"] == []
    assert sample["errors"] == []


def test_parse_disk_lines_land_as_used_kb():
    sample = vs.parse_sample(FIXTURE_DISK, "msi-hx18", AT)
    assert sample["disk_root_used_kb"] == 52428800
    assert sample["disk_workspace_used_kb"] == 1048576


def test_parse_absent_disk_lines_stay_none():
    sample = vs.parse_sample(FIXTURE_ADVANCING, "msi-hx18", AT)
    assert sample["disk_root_used_kb"] is None
    assert sample["disk_workspace_used_kb"] is None


def test_parse_malformed_disk_lines_ignored_not_fatal():
    sample = vs.parse_sample(FIXTURE_DISK_PARTIAL, "msi-hx18", AT)
    assert sample["disk_root_used_kb"] is None
    assert sample["disk_workspace_used_kb"] is None


# Synthetic budgets for the disk-block pins: the figures
# are the test's own, never an instance's real budget.
BUDGET = {"warn_gb": 10, "stop_gb": 12}
GB_KB = 1048576


def _disk_sample(root_kb, workspace_kb=None):
    return {"disk_root_used_kb": root_kb, "disk_workspace_used_kb": workspace_kb}


def test_disk_block_ok_below_warn():
    block = vs.disk_block(_disk_sample(9 * GB_KB, 2 * GB_KB), BUDGET)
    assert block == {
        "root_used_gb": 9.0,
        "workspace_used_gb": 2.0,
        "warn_gb": 10,
        "stop_gb": 12,
        "state": "ok",
    }


def test_disk_block_warn_at_the_warn_figure():
    block = vs.disk_block(_disk_sample(10 * GB_KB), BUDGET)
    assert block["state"] == "warn"
    assert block["root_used_gb"] == 10.0
    assert block["workspace_used_gb"] is None


def test_disk_block_warn_below_stop():
    block = vs.disk_block(_disk_sample(int(11.9 * GB_KB)), BUDGET)
    assert block["state"] == "warn"


def test_disk_block_stop_at_the_stop_figure():
    block = vs.disk_block(_disk_sample(12 * GB_KB), BUDGET)
    assert block["state"] == "stop"


def test_disk_block_stop_above_the_stop_figure():
    block = vs.disk_block(_disk_sample(40 * GB_KB), BUDGET)
    assert block["state"] == "stop"


def test_disk_block_no_budget_no_block():
    assert vs.disk_block(_disk_sample(40 * GB_KB), None) is None
    assert vs.disk_block(_disk_sample(40 * GB_KB), {}) is None


def test_disk_block_no_root_reading_no_block():
    assert vs.disk_block(_disk_sample(None, 2 * GB_KB), BUDGET) is None


def test_load_disk_thresholds_reads_the_seed(tmp_path):
    (tmp_path / "disk-thresholds.json").write_text(
        json.dumps(
            {
                "venue-a": {"warn_gb": 10, "stop_gb": 12},
                "venue-b": {"warn_gb": 20.5, "stop_gb": 24},
                "venue-c": {"warn_gb": "soon"},
                "venue-d": "unmeasured",
            }
        )
    )
    assert vs.load_disk_thresholds(tmp_path) == {
        "venue-a": {"warn_gb": 10, "stop_gb": 12},
        "venue-b": {"warn_gb": 20.5, "stop_gb": 24},
    }


def test_load_disk_thresholds_absent_or_malformed_seed_is_empty(tmp_path):
    assert vs.load_disk_thresholds(tmp_path) == {}
    (tmp_path / "disk-thresholds.json").write_text("not json")
    assert vs.load_disk_thresholds(tmp_path) == {}
    (tmp_path / "disk-thresholds.json").write_text(json.dumps([1, 2]))
    assert vs.load_disk_thresholds(tmp_path) == {}


def test_carried_disk_block_rides_with_the_samples_stamp():
    block = {
        "root_used_gb": 11.0,
        "workspace_used_gb": 1.0,
        "warn_gb": 10,
        "stop_gb": 12,
        "state": "warn",
    }
    prev = {"venue": "venue-a", "state": "advancing", "sampled_at": AT, "disk": block}
    carried = vs.carried_disk_block(prev)
    assert carried == {**block, "disk_sampled_at": AT}


def test_carried_disk_block_keeps_the_original_stamp_when_carried_twice():
    block = {
        "root_used_gb": 11.0,
        "workspace_used_gb": None,
        "warn_gb": 10,
        "stop_gb": 12,
        "state": "warn",
        "disk_sampled_at": AT,
    }
    dark = {
        "venue": "venue-a",
        "state": "unreachable",
        "sampled_at": "2026-01-01T01:00:00+00:00",
        "disk": block,
    }
    assert vs.carried_disk_block(dark)["disk_sampled_at"] == AT


def test_carried_disk_block_absent_is_none():
    assert vs.carried_disk_block({"venue": "venue-a", "sampled_at": AT}) is None
    assert vs.carried_disk_block(None) is None
    assert vs.carried_disk_block({"disk": "not-a-block"}) is None


def _stat_line(pid, comm, ppid, utime, stime):
    # Fields after the comm: state(3) then ppid(4), nine more
    # fixed fields (5..13), utime(14), stime(15).
    tail = ["S", str(ppid)] + ["0"] * 9 + [str(utime), str(stime)]
    return f"{pid} ({comm}) " + " ".join(tail)


def test_parse_stat_plain():
    parsed = vs.parse_stat(_stat_line(4101, "python3", 1, 300, 25))
    assert parsed == (4101, (1, 300, 25))


def test_parse_stat_comm_with_spaces_and_parens():
    parsed = vs.parse_stat(_stat_line(4102, "worker (x) y", 4101, 111, 222))
    assert parsed == (4102, (4101, 111, 222))


def test_parse_stat_malformed_is_none():
    assert vs.parse_stat("not a stat line") is None
    assert vs.parse_stat("4101 (python3) S 1 0") is None
    assert vs.parse_stat("") is None


def test_sum_tree_cpu_default_roots():
    stat_by_pid = {
        1: (0, 10, 5),
        2: (1, 20, 0),
        3: (1, 1, 1),
        4: (2, 100, 100),
        9: (0, 7, 3),
    }
    assert vs.sum_tree_cpu(stat_by_pid) == {1: 237, 9: 10}


def test_sum_tree_cpu_explicit_roots():
    stat_by_pid = {
        1: (0, 10, 5),
        2: (1, 20, 0),
        4: (2, 100, 100),
    }
    assert vs.sum_tree_cpu(stat_by_pid, roots=[2]) == {2: 220}
    assert vs.sum_tree_cpu(stat_by_pid, roots=[999]) == {999: 0}


def test_sum_tree_cpu_cycle_terminates():
    stat_by_pid = {1: (2, 5, 5), 2: (1, 7, 7)}
    assert vs.sum_tree_cpu(stat_by_pid, roots=[1]) == {1: 24}


def test_capacity_live_value_wins_over_declared():
    sample = {"pids_max": 2048}
    assert vs.effective_pids_capacity(sample, "local") == 2048


def test_capacity_declared_fallback_when_live_unreadable():
    assert vs.effective_pids_capacity({"pids_max": None}, "local") == 1024
    assert vs.effective_pids_capacity({"pids_max": None}, "local-hp") == 1024
    assert vs.effective_pids_capacity({"pids_max": None}, "unknown-shape") is None
    assert vs.effective_pids_capacity({"pids_max": None}) is None


def test_probe_command_shape():
    command = vs.build_probe_command()
    assert isinstance(command, str)
    assert "pids.current" in command
    assert "pids.max" in command
    assert "root.pid" in command
    assert "PIDS" in command and "JOB" in command and "ERR" in command
    assert "DISK" in command and "statvfs" in command


def _stub_writer(path, data):
    """The test's own staged writer (stage + replace), passed
    to SampleStore as writer= — the by-path load has no package
    context for the foundation seam."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def test_store_append_and_last_two(tmp_path):
    store = vs.SampleStore(root=tmp_path, writer=_stub_writer)
    first = vs.parse_sample(FIXTURE_ADVANCING, "msi-hx18", AT)
    second = vs.parse_sample(FIXTURE_VANISHED, "msi-hx18", AT)
    third = vs.parse_sample(FIXTURE_UNLIMITED, "msi-hx18", AT)
    path = store.append(first)
    assert path == tmp_path / "venue-samples-msi-hx18.jsonl"
    store.append(second)
    assert store.last_two("msi-hx18") == [first, second]
    store.append(third)
    assert store.last_two("msi-hx18") == [second, third]
    lines = path.read_text().splitlines()
    assert [json.loads(line)["venue"] for line in lines] == ["msi-hx18"] * 3


def _big_sample(venue, marker, size):
    sample = vs.parse_sample(FIXTURE_VANISHED, venue, AT)
    sample["pad"] = marker * size
    return sample


def test_store_append_bounds_oversized_history(tmp_path):
    store = vs.SampleStore(root=tmp_path, writer=_stub_writer)
    path = store.path_for("msi-hx18")
    chunk = vs.MAX_STORE_BYTES // 4
    seeded = [_big_sample("msi-hx18", "a", chunk) for _ in range(6)]
    for sample in seeded:
        store.append(sample)
        assert path.stat().st_size <= vs.MAX_STORE_BYTES
    newest = _big_sample("msi-hx18", "b", chunk)
    store.append(newest)
    assert path.stat().st_size <= vs.MAX_STORE_BYTES
    assert store.last_two("msi-hx18") == [seeded[-1], newest]


def test_store_append_keeps_a_single_oversized_sample(tmp_path):
    store = vs.SampleStore(root=tmp_path, writer=_stub_writer)
    big = _big_sample("hp-envy", "x", vs.MAX_STORE_BYTES * 2)
    store.append(big)
    assert store.last_two("hp-envy") == [big]
    newer = vs.parse_sample(FIXTURE_ADVANCING, "hp-envy", AT)
    store.append(newer)
    assert store.last_two("hp-envy") == [big, newer]


def test_store_append_small_history_grows_line_by_line(tmp_path):
    store = vs.SampleStore(root=tmp_path, writer=_stub_writer)
    path = store.path_for("msi-hx18")
    for _ in range(3):
        before = len(path.read_text().splitlines()) if path.exists() else 0
        store.append(vs.parse_sample(FIXTURE_VANISHED, "msi-hx18", AT))
        assert len(path.read_text().splitlines()) == before + 1


def test_store_last_two_missing_and_single(tmp_path):
    store = vs.SampleStore(root=tmp_path, writer=_stub_writer)
    assert store.last_two("hp-envy") == []
    only = vs.parse_sample(FIXTURE_VANISHED, "hp-envy", AT)
    store.append(only)
    assert store.last_two("hp-envy") == [only]


def test_store_files_are_per_venue(tmp_path):
    store = vs.SampleStore(root=tmp_path, writer=_stub_writer)
    store.append(vs.parse_sample(FIXTURE_ADVANCING, "msi-hx18", AT))
    store.append(vs.parse_sample(FIXTURE_VANISHED, "hp-envy", AT))
    assert store.last_two("msi-hx18")[0]["pids_current"] == 812
    assert store.last_two("hp-envy")[0]["pids_current"] == 7
