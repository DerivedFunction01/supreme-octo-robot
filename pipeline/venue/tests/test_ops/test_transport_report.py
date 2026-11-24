"""The adoption measure's counting pins (branch-transport
plan, Step 4): a launched run counts by its transport
stamp — branch only when the stamp names it, bundle
otherwise, the unstamped pre-stamp era included; a fired
run with no launch stamp is never-launched; programme is
the programme the caller registry declares for the
caller's base (read from a fixtured scratch registry, the
suite's form — the machine's local registry never leaks
in), with an undeclared caller keeping its own row and a
callerless record reading unknown."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "ops" / "transport_report.py"

START = datetime(2026, 11, 22, tzinfo=timezone.utc).timestamp()
END = datetime(2026, 11, 23, tzinfo=timezone.utc).timestamp()


def _load():
    spec = importlib.util.spec_from_file_location(
        "transport_report_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _programmes(tmp_path):
    """The declaration map under test: a scratch repo whose
    caller registry declares a shortened programme row for
    each of its fictional callers, read back through the
    lease core's own reader (the module the report binds)."""
    m = _load()
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "callers.json").write_text(json.dumps({
        "callers": ["alpha-thread", "beta-thread", "gamma-thread"],
        "programmes": {"alpha-thread": "alpha",
                        "beta-thread": "beta",
                        "gamma-thread": "gamma"},
    }))
    return m, m.callers.caller_programmes(tmp_path)


def _rec(caller, started, launch=None, transport=None):
    rec = {"caller": caller, "started_at": started}
    if launch is not None:
        rec["launch_at"] = launch
    if transport is not None:
        rec["transport"] = transport
    return rec


def test_programme_resolution(tmp_path):
    m, programmes = _programmes(tmp_path)
    assert programmes == {"alpha-thread": "alpha",
                          "beta-thread": "beta",
                          "gamma-thread": "gamma"}
    # A lane suffix reports under its base's declaration.
    assert m.programme("alpha-thread:lane-9", programmes) == "alpha"
    assert m.programme("beta-thread", programmes) == "beta"
    # An undeclared caller keeps its own name as its row.
    assert m.programme("panel", programmes) == "panel"
    assert m.programme("delta-thread:sub", programmes) == "delta-thread"
    # A callerless or malformed caller reads unknown.
    assert m.programme(None, programmes) == "unknown"
    assert m.programme("", programmes) == "unknown"
    assert m.programme(7, programmes) == "unknown"


def test_counting_over_fixture_records(tmp_path):
    m, programmes = _programmes(tmp_path)
    records = [
        # branch, stamped, with a span
        _rec("beta-thread", "2026-11-22T01:00:00+00:00",
             "2026-11-22T01:02:00+00:00",
             {"kind": "branch", "claim_to_launch_s": 120.0}),
        _rec("beta-thread", "2026-11-22T02:00:00+00:00",
             "2026-11-22T02:03:00+00:00",
             {"kind": "branch", "claim_to_launch_s": 180.0}),
        # bundle, explicitly stamped
        _rec("alpha-thread", "2026-11-22T03:00:00+00:00",
             "2026-11-22T03:10:00+00:00",
             {"kind": "bundle", "claim_to_launch_s": 600.0}),
        # launched, unstamped: the pre-stamp era counts bundle;
        # the lane suffix reports under its base's programme
        _rec("gamma-thread:followup",
             "2026-11-22T04:00:00+00:00", "2026-11-22T04:20:00+00:00"),
        # fired, never launched
        _rec("alpha-thread", "2026-11-22T05:00:00+00:00"),
        # no caller at all: unknown, and never launched
        _rec(None, "2026-11-22T06:00:00+00:00"),
        # an undeclared caller keeps its own row
        _rec("panel", "2026-11-22T07:00:00+00:00",
             "2026-11-22T07:01:00+00:00", {"kind": "bundle"}),
        # outside the window: not counted anywhere
        _rec("beta-thread", "2026-11-21T23:00:00+00:00",
             "2026-11-21T23:02:00+00:00", {"kind": "branch"}),
        # no fire stamp: tallied as skipped, never counted
        {"caller": "beta-thread", "launch_at": "2026-11-22T08:00:00+00:00"},
    ]
    out = m.summarize(records, START, END, programmes)
    p = out["programmes"]
    assert p["beta"] == {
        "fired": 2, "launched": 2, "branch": 2, "bundle": 0,
        "never_launched": 0,
        "median_claim_to_launch_s": {"branch": 150.0, "bundle": None}}
    assert p["alpha"]["fired"] == 2
    assert p["alpha"]["bundle"] == 1
    assert p["alpha"]["never_launched"] == 1
    assert p["alpha"]["median_claim_to_launch_s"]["bundle"] == 600.0
    assert p["gamma"]["launched"] == 1 and p["gamma"]["bundle"] == 1
    assert p["unknown"]["fired"] == 1 and p["unknown"]["never_launched"] == 1
    assert p["panel"]["bundle"] == 1
    assert out["totals"] == {"fired": 7, "launched": 5, "branch": 2,
                             "bundle": 3, "never_launched": 2}
    assert out["records_seen"] == 9
    assert out["records_skipped_no_start"] == 1


def test_end_to_end_over_a_sandbox_store(tmp_path):
    # The callers here are fictional and unregistered in any
    # registry, so no declaration applies and each reports
    # under its own name — the subprocess reads the store's
    # own registry, which is not this test's fixture.
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "a.json").write_text(json.dumps(_rec(
        "north-thread", "2026-11-22T01:00:00+00:00",
        "2026-11-22T01:15:00+00:00", {"kind": "bundle"})))
    (runs / "b.json").write_text(json.dumps(_rec(
        "north-thread", "2026-11-22T02:00:00+00:00")))
    (runs / "torn.json").write_text("{not json")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--day", "2026-11-22",
         "--runs-dir", str(runs)],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout)
    assert report["window"]["kind"] == "day"
    assert report["programmes"]["north-thread"]["bundle"] == 1
    assert report["programmes"]["north-thread"]["never_launched"] == 1
    assert report["records_unparseable"] == 1
