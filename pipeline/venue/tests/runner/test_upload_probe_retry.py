"""upload_one's verify probe: bounded attempts against an
episodic exec-channel stall.

The specimen: the probe was one-shot, and the channel
stalls in episodes of minutes — probe-fail rates of 9/60 and
10/79 on two sessions in one evening, successes interleaved
seconds apart — so one stall killed the launch, including a
solo launch on a quiet session (combo-price2 …T203542Z, probe
dead at its full 300 s). The chunked transfer's legs already
rode attempt retries; the probe now does too. These pins drive
upload_one against a stub foundation whose colab is scripted:
a stall signature (timeout, unreadable output) retries, a size
mismatch is information and returns at once, and the journal
keeps one entry per upload_one call — the final outcome.

The probe also verifies the landed SHA-256 — a
same-size foreign file in the shared slot is a mismatch that
returns at once with the foreign-bytes error.
"""

import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
from module_loader import load_module  # noqa: E402

DEST = "wrap.py"
SIZE = 2788


def _json_object_from_output(text):
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON object in output")


class ScriptedColab:
    """Uploads always land; exec outcomes follow the script.

    Each script entry is ("timeout",), ("stdout", text),
    ("size", n), or ("hash", hex) — the size entry renders the
    probe's own output for a remote file of n bytes of the
    source's own content (b"x" * n, matching make_src); the
    hash entry renders the probe output for a same-size file
    carrying the given SHA-256 instead.
    """

    def __init__(self, script):
        self.script = list(script)
        self.exec_calls = 0
        self.upload_calls = 0

    def __call__(self, *argv, timeout=None):
        if argv[0] == "upload":
            self.upload_calls += 1
            return subprocess.CompletedProcess(argv, 0, "", "")
        assert argv[0] == "exec", argv
        self.exec_calls += 1
        outcome = self.script.pop(0)
        if outcome[0] == "timeout":
            raise subprocess.TimeoutExpired(argv, timeout)
        if outcome[0] == "stdout":
            return subprocess.CompletedProcess(argv, 0, outcome[1], "")
        if outcome[0] == "size":
            body = json.dumps({"size": outcome[1],
                               "sha256": hashlib.sha256(b"x" * outcome[1]).hexdigest()})
            return subprocess.CompletedProcess(argv, 0, body + "\n", "")
        if outcome[0] == "hash":
            body = json.dumps({"size": SIZE, "sha256": outcome[1]})
            return subprocess.CompletedProcess(argv, 0, body + "\n", "")
        raise AssertionError(outcome)


def load_launch(tmp_path, colab):
    package = types.ModuleType("runner_probe_unit")
    package.__path__ = [str(REPO / "sync" / "runner")]
    sys.modules["runner_probe_unit"] = package
    foundation = types.ModuleType("runner_probe_unit.foundation")
    foundation.REPO = tmp_path
    foundation.PLATFORM_ARGV = tmp_path / "argv.py"
    foundation.colab = colab
    foundation.json_object_from_output = _json_object_from_output
    journal = []
    foundation.lease = types.SimpleNamespace(
        append_launch_outcome=lambda repo, session, stage, ok, detail="": journal.append(
            {"stage": stage, "ok": ok, "detail": detail}))
    foundation.transfer = types.SimpleNamespace(
        chunked_upload=lambda *a, **k: {"ok": True})
    sys.modules["runner_probe_unit.foundation"] = foundation
    launch = load_module(
        "runner_probe_unit.launch", REPO / "sync" / "runner" / "launch.py", register=True)
    return launch, journal


@pytest.fixture(autouse=True)
def fast_probe(monkeypatch):
    monkeypatch.setenv("VENUE_RUN_PROBE_ATTEMPTS", "3")
    monkeypatch.setenv("VENUE_RUN_PROBE_BACKOFF_S", "0")


def make_src(tmp_path):
    src = tmp_path / "wrap.py"
    src.write_bytes(b"x" * SIZE)
    return src


def test_first_try_success_is_one_probe(tmp_path):
    colab = ScriptedColab([("size", SIZE)])
    launch, journal = load_launch(tmp_path, colab)
    assert launch.upload_one("sess", make_src(tmp_path), DEST, "tag") is None
    assert colab.exec_calls == 1
    assert journal == [{"stage": "probe", "ok": True, "detail": DEST}]


def test_timeout_then_success_retries(tmp_path):
    colab = ScriptedColab([("timeout",), ("size", SIZE)])
    launch, journal = load_launch(tmp_path, colab)
    assert launch.upload_one("sess", make_src(tmp_path), DEST, "tag") is None
    assert colab.exec_calls == 2
    assert journal == [{"stage": "probe", "ok": True, "detail": DEST}]


def test_unreadable_then_success_retries(tmp_path):
    colab = ScriptedColab([("stdout", "garbled channel output"), ("size", SIZE)])
    launch, journal = load_launch(tmp_path, colab)
    assert launch.upload_one("sess", make_src(tmp_path), DEST, "tag") is None
    assert colab.exec_calls == 2
    assert journal == [{"stage": "probe", "ok": True, "detail": DEST}]


def test_mismatch_returns_at_once_without_retry(tmp_path):
    colab = ScriptedColab([("size", 1069), ("size", SIZE)])
    launch, journal = load_launch(tmp_path, colab)
    err = launch.upload_one("sess", make_src(tmp_path), DEST, "tag")
    assert err == f"upload verify: {DEST} landed at 1069 bytes, expected {SIZE}"
    assert colab.exec_calls == 1
    assert journal == [{"stage": "probe", "ok": False, "detail": DEST}]


def test_all_attempts_timing_out_fails_with_the_timeout_error(tmp_path):
    colab = ScriptedColab([("timeout",), ("timeout",), ("timeout",)])
    launch, journal = load_launch(tmp_path, colab)
    err = launch.upload_one("sess", make_src(tmp_path), DEST, "tag")
    assert err == f"upload verify timed out for {DEST}"
    assert colab.exec_calls == 3
    assert journal == [{"stage": "probe", "ok": False,
                        "detail": f"{DEST}: verify probe timed out"}]


def test_all_attempts_unreadable_fails_with_the_unreadable_error(tmp_path):
    colab = ScriptedColab([("stdout", "junk")] * 3)
    launch, journal = load_launch(tmp_path, colab)
    err = launch.upload_one("sess", make_src(tmp_path), DEST, "tag")
    assert err.startswith(f"upload verify unreadable for {DEST}:")
    assert colab.exec_calls == 3
    assert journal == [{"stage": "probe", "ok": False, "detail": DEST}]


def test_same_size_foreign_bytes_fail_at_once_on_the_hash(tmp_path):
    foreign = hashlib.sha256(b"y" * SIZE).hexdigest()
    colab = ScriptedColab([("hash", foreign), ("size", SIZE)])
    launch, journal = load_launch(tmp_path, colab)
    err = launch.upload_one("sess", make_src(tmp_path), DEST, "tag")
    expected = hashlib.sha256(b"x" * SIZE).hexdigest()
    assert err == (f"upload verify: {DEST} landed with sha256 {foreign}, "
                   f"expected {expected} — the slot holds foreign bytes")
    assert colab.exec_calls == 1
    assert journal == [{"stage": "probe", "ok": False, "detail": DEST}]
