"""Register E5 — session/lease state has ONE shared writer.

The defect class: several component processes hand-rolling
their own staging onto shared state files — the lease core's
stamps, the funnel's binding heals, the liveness writers —
each a private tmp+replace away from tearing a file another
process reads (the 2026-11-13 binding loss: a sessions file
recreated empty under concurrent recovery writers). The cure
pinned here: every one of those writes rides the lease
foundation's seam onto the platform writer (contract 15),
and two writers interleaved at the rename seam can never
leave a torn or empty target — a reader at any point sees
one writer's complete payload or the other's.

Determinism: the interleave is driven by threading events
at the rename seam, never by clocks or sleeps; the event
waits carry hang-guard timeouts only, and no assertion
depends on elapsed time. All fixtures are generic.
"""

import importlib
import importlib.util
import json
import os
import stat
import threading
import types
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from unit_harness import lease, repo  # noqa: F401

foundation = importlib.import_module("lease.core.foundation")
identity = importlib.import_module("lease.sessions.identity")
listeners = importlib.import_module("lease.state.listeners")
provisioning = importlib.import_module("lease.sessions.provisioning")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_ROOT = REPO_ROOT.parent

STAMP_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _load(name, path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _RecordingWriter:
    """A writer-module double: records every staged_write and
    performs it plainly, so file assertions still hold."""

    def __init__(self):
        self.calls = []

    def staged_write(self, path, data, mode=None):
        self.calls.append((path, data, mode))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)
        if mode is not None:
            os.chmod(path, mode)


def test_seam_delegates_to_the_platform_writer():
    """In this tree the venue seam's writer IS the platform
    writer module — the delegation the consolidation rests
    on, proven rather than assumed."""
    assert foundation.WRITER is not None
    assert Path(foundation.WRITER.__file__).resolve() == (
        PIPELINE_ROOT / "platform" / "writer.py").resolve()


def test_stamp_writers_ride_the_seam(repo, monkeypatch):
    """The per-session stamp writers that used to hand-roll
    tmp+replace — absence stamps, listener census, identity,
    provisioning — all call the one seam."""
    calls = []
    monkeypatch.setattr(
        foundation, "staged_write",
        lambda path, data, mode=None: calls.append((Path(path), data)))
    foundation.stamp_absent(repo, "sess-a", STAMP_AT, STAMP_AT)
    listeners._save_stamp(repo, "sess-a", {"kind": "census"})
    identity._write_stamp(repo, "sess-a", {"kind": "identity"})
    provisioning._write_stamp(repo, "sess-a", {"kind": "provision"})
    var = foundation.var_dir(repo)
    assert [p for p, _ in calls] == [
        var / "absent-sess-a.json",
        var / "listener-census-sess-a.json",
        var / "identity-sess-a.json",
        var / "provision-sess-a.json",
    ]
    assert json.loads(calls[0][1])["first_absent_at"] == STAMP_AT.isoformat()
    assert json.loads(calls[1][1]) == {"kind": "census"}
    assert json.loads(calls[2][1]) == {"kind": "identity"}
    assert json.loads(calls[3][1]) == {"kind": "provision"}


def test_interleaved_writers_never_tear(tmp_path, monkeypatch):
    """Two writers, one target, interleaved deterministically
    at the rename seam: writer A stages and is held just
    before its rename while writer B writes whole. A reader
    at every held point sees a complete payload — the
    original, then B's, then A's — never torn, never empty,
    and no staging litter survives."""
    target = tmp_path / "shared.json"
    original = b'{"seat": "original", "seq": 0}'
    payload_a = b'{"seat": "first", "seq": 1}'
    payload_b = b'{"seat": "second", "seq": 2}'
    target.write_bytes(original)

    real_replace = os.replace
    a_ident = []
    a_holding = threading.Event()
    release_a = threading.Event()

    def gated_replace(src, dst):
        if str(dst) == str(target) and a_ident and threading.get_ident() == a_ident[0]:
            a_holding.set()
            release_a.wait(60)  # hang guard only; no assertion reads a clock
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", gated_replace)

    def write_a():
        a_ident.append(threading.get_ident())
        foundation.staged_write(target, payload_a)

    thread_a = threading.Thread(target=write_a)
    thread_a.start()
    assert a_holding.wait(60)
    # A has staged but not renamed: the complete original stands.
    assert target.read_bytes() == original
    assert json.loads(target.read_bytes())["seat"] == "original"

    thread_b = threading.Thread(
        target=lambda: foundation.staged_write(target, payload_b))
    thread_b.start()
    thread_b.join(60)
    assert not thread_b.is_alive()
    # B renamed whole: a reader sees B complete.
    assert target.read_bytes() == payload_b
    assert json.loads(target.read_bytes())["seat"] == "second"

    release_a.set()
    thread_a.join(60)
    assert not thread_a.is_alive()
    # A renamed last, whole: the final state is A's complete payload.
    assert target.read_bytes() == payload_a
    assert json.loads(target.read_bytes())["seat"] == "first"
    assert [p.name for p in tmp_path.iterdir()] == ["shared.json"]


def test_mode_discipline_through_the_seam(tmp_path):
    """The seam's mode contract: an explicit mode is stamped
    (a recreated credential-class file is never left at the
    umask default); without one, the target's mode carries."""
    fresh = tmp_path / "fresh.json"
    foundation.staged_write(fresh, b"{}", mode=0o600)
    assert stat.S_IMODE(os.stat(fresh).st_mode) == 0o600

    carried = tmp_path / "carried.json"
    carried.write_bytes(b"{}")
    os.chmod(carried, 0o640)
    foundation.staged_write(carried, b'{"v": 1}')
    assert stat.S_IMODE(os.stat(carried).st_mode) == 0o640

    foundation.staged_write(carried, b'{"v": 2}', mode=0o600)
    assert stat.S_IMODE(os.stat(carried).st_mode) == 0o600
    assert json.loads(carried.read_bytes()) == {"v": 2}


def test_funnel_heals_ride_the_writer(tmp_path, monkeypatch):
    """The CLI funnel's recovery writers — the binding
    restore, the pruned-entry merge, the token restore —
    write through the writer seam at 0600, never a private
    staging (the concurrent-recovery-writer class)."""
    cli = _load("e5_cli", REPO_ROOT / "sync" / "cli.py")
    fake = _RecordingWriter()
    monkeypatch.setattr(cli, "_WRITER", fake)
    sessions = tmp_path / "sessions.json"
    token = tmp_path / "token.json"
    monkeypatch.setattr(cli, "SESSIONS", sessions)
    monkeypatch.setattr(cli, "TOKEN", token)

    sessions.write_bytes(b"torn{")
    snapshot = b'{"sess-a": {"endpoint": "https://example.invalid/a"}}'
    cli._restore_binding(snapshot)
    assert fake.calls == [(str(sessions), snapshot, 0o600)]
    assert sessions.read_bytes() == snapshot

    fake.calls.clear()
    cli._atomic_write_token(b'{"refresh_token": "generic-fixture-token-value"}')
    assert fake.calls == [
        (str(token), b'{"refresh_token": "generic-fixture-token-value"}', 0o600)]

    # The merge: a pruned entry whose lease record lives goes
    # back, merged into the current map, through the seam.
    fake.calls.clear()
    var = tmp_path / "var"
    var.mkdir()
    (var / "lease-sess-a.json").write_text(
        json.dumps({"deadline": "2999-01-01T00:00:00+00:00"}))
    monkeypatch.setattr(cli, "_var_dir", lambda: var)
    sessions.write_text(json.dumps({"sess-b": {"endpoint": "https://example.invalid/b"}}))
    before = json.dumps({
        "sess-a": {"endpoint": "https://example.invalid/a"},
        "sess-b": {"endpoint": "https://example.invalid/b"},
    }).encode()
    cli._restore_pruned_entries(before)
    assert len(fake.calls) == 1
    path, data, mode = fake.calls[0]
    assert (path, mode) == (str(sessions), 0o600)
    merged = json.loads(data)
    assert set(merged) == {"sess-a", "sess-b"}
    assert merged["sess-a"] == {"endpoint": "https://example.invalid/a"}


def test_sh_liveness_cache_rides_the_writer(tmp_path, monkeypatch):
    """bin/colab-sh's two writes onto shared liveness state —
    the cache merge into the checker's file and the mirror
    freshness stamp — ride the lease seam, not a private
    staging."""
    sh_state = _load("e5_sh_state", REPO_ROOT / "bin" / "_sh_state.py")
    monkeypatch.setenv("COLAB_RUNNER_VAR", str(tmp_path))
    calls = []

    def record(path, data, mode=None):
        calls.append((Path(path), data))
        Path(path).write_bytes(data)

    fake_foundation = types.SimpleNamespace(staged_write=record)
    monkeypatch.setattr(
        sh_state, "_lease_module",
        lambda: types.SimpleNamespace(foundation=fake_foundation))

    liveness = tmp_path / "liveness-sess-a.json"
    liveness.write_text(json.dumps({"state": "unknown"}))
    sh_state._liveness_cache_write("sess-a")
    assert [p for p, _ in calls] == [liveness]
    merged = json.loads(calls[0][1])
    assert merged["state"] == "unknown"  # the checker's keys survive the merge
    assert merged[sh_state._CACHE_KEY]["state"] == "alive"

    calls.clear()
    monkeypatch.setattr(sh_state, "_mirror_fresh", lambda: False)
    monkeypatch.setattr(
        sh_state.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0))
    sh_state.restore_transient()
    assert [p.name for p, _ in calls] == ["mirror-restore.stamp"]


def test_liveness_entry_write_state_round_trip(tmp_path):
    """The checker's state write face: whole-content replace
    through the seam, parseable at every step."""
    entry = _load("e5_liveness_entry", REPO_ROOT / "sync" / "liveness_entry.py")
    path = tmp_path / "liveness-sess-a.json"
    entry.write_state(path, {"session": "sess-a", "open": {}})
    assert json.loads(path.read_text()) == {"session": "sess-a", "open": {}}
    entry.write_state(path, {"session": "sess-a", "open": {"x": {"since": "t"}}})
    assert json.loads(path.read_text())["open"] == {"x": {"since": "t"}}
    assert [p.name for p in tmp_path.iterdir()] == ["liveness-sess-a.json"]
