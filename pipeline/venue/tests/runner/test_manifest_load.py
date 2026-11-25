"""The manifest load (claims.load_manifest): bounded
re-reads over empty or torn observations, and a named
refusal on exhaustion.

The deaths this cures: daemon children died at the
manifest load with a raw JSONDecodeError — the file read
empty (several gate manifests were later found standing
at 0 bytes, their creating writes lost before the fire) —
and the runs read launch-lost. These pins drive claims.py
against the same stub foundation as test_claims.py: the
load rides a write landing mid-retries, a durably empty or
unparseable manifest raises ManifestUnreadable naming the
path and the face, a missing manifest raises it flagged
missing, and the daemonize parent's validation refuses
before any claim is written.
"""

import json
import sys
import types
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

STARTED = "2026-11-24T05:48:15+00:00"
VALID = {"name": "job", "uploads": []}


def load_claims(runs: Path):
    package = types.ModuleType("runner_manifest_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_manifest_unit"] = package
    foundation = types.ModuleType("runner_manifest_unit.foundation")
    foundation.REPO = REPO
    foundation.RUNS = runs
    foundation.now = lambda: STARTED
    foundation.epoch = lambda value: None
    foundation.VENUE = "test-venue"
    foundation.staged_write = lambda path, data: Path(path).write_bytes(data)
    sys.modules["runner_manifest_unit.foundation"] = foundation
    load_module("runner_manifest_unit.records", REPO / "sync" / "runner" / "records.py", register=True)
    return load_module("runner_manifest_unit.claims", REPO / "sync" / "runner" / "claims.py", register=True)


def no_sleep(claims):
    """Zero the ladder for the duration of a test: returns
    the sleep-call counter the retry loop accumulates
    (attempts = sleeps + 1)."""
    calls = []
    return mock.patch.object(claims.time, "sleep", lambda s: calls.append(s)), calls


def test_load_manifest_reads_a_standing_manifest(tmp_path):
    claims = load_claims(tmp_path / "runs")
    path = tmp_path / "job.json"
    path.write_text(json.dumps(VALID))
    assert claims.load_manifest(path) == VALID


def test_load_manifest_rides_a_landing_write(tmp_path):
    claims = load_claims(tmp_path / "runs")
    path = tmp_path / "job.json"
    path.write_text("")
    landed = []

    def landing_sleep(_seconds):
        # The write lands while the reader backs off: the
        # next read observes the complete manifest.
        path.write_text(json.dumps(VALID))
        landed.append(True)

    with mock.patch.object(claims.time, "sleep", landing_sleep):
        assert claims.load_manifest(path) == VALID
    assert landed == [True]


def test_load_manifest_durably_empty_raises_named(tmp_path):
    claims = load_claims(tmp_path / "runs")
    path = tmp_path / "job.json"
    path.write_text("")
    patcher, sleeps = no_sleep(claims)
    with patcher:
        try:
            claims.load_manifest(path)
        except claims.ManifestUnreadable as exc:
            assert not exc.missing
            assert exc.face == "empty"
            assert str(path) in str(exc)
        else:
            raise AssertionError("expected ManifestUnreadable")
    assert len(sleeps) == claims.MANIFEST_READ_ATTEMPTS - 1


def test_load_manifest_missing_raises_flagged_missing(tmp_path):
    claims = load_claims(tmp_path / "runs")
    path = tmp_path / "absent.json"
    patcher, sleeps = no_sleep(claims)
    with patcher:
        try:
            claims.load_manifest(path)
        except claims.ManifestUnreadable as exc:
            assert exc.missing
            assert str(path) in str(exc)
        else:
            raise AssertionError("expected ManifestUnreadable")
    assert len(sleeps) == claims.MANIFEST_READ_ATTEMPTS - 1


def test_load_manifest_unparseable_raises_named(tmp_path):
    claims = load_claims(tmp_path / "runs")
    path = tmp_path / "job.json"
    path.write_text("not json{")
    patcher, _sleeps = no_sleep(claims)
    with patcher:
        try:
            claims.load_manifest(path)
        except claims.ManifestUnreadable as exc:
            assert not exc.missing
            assert exc.face.startswith("unparseable")
        else:
            raise AssertionError("expected ManifestUnreadable")


def test_spawn_daemon_refuses_a_shape_invalid_manifest_before_claiming(tmp_path):
    runs = tmp_path / "runs"
    claims = load_claims(runs)
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"name": "job", "uploads": [{"path": "var/x.sh", "dest": "x.sh"}]}))
    try:
        claims.spawn_daemon("job", ["job"], path)
    except ValueError as exc:
        # The refusal names the field and the offending entry,
        # in the attached flow's own words.
        assert "manifest uploads entry is not a string" in str(exc)
        assert "'dest': 'x.sh'" in str(exc)
    else:
        raise AssertionError("expected the shape refusal")
    # As with the unreadable case: no claim, no record — the
    # refusal precedes the claim, so nothing stands to read
    # as a launched-then-lost run.
    assert not runs.exists() or list(runs.glob("*.json")) == []


def test_spawn_daemon_refuses_an_unreadable_manifest_before_claiming(tmp_path):
    runs = tmp_path / "runs"
    claims = load_claims(runs)
    path = tmp_path / "job.json"
    path.write_text("")
    patcher, _sleeps = no_sleep(claims)
    with patcher:
        try:
            claims.spawn_daemon("job", ["job"], path)
        except claims.ManifestUnreadable:
            pass
        else:
            raise AssertionError("expected ManifestUnreadable")
    # No claim was written and no child was spawned: the
    # refusal precedes the claim, so no record exists to
    # read as launch-lost.
    assert not runs.exists() or list(runs.glob("*.json")) == []
