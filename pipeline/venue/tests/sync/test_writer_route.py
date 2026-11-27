"""The funnel writer route (sync/writer_route.py): the one
home for the sync package's non-lease writes.

The defect class: the funnel (sync/cli.py) and the liveness
entries (sync/liveness_entry.py) each carried a private copy
of the writer seam that called the platform writer
IN-PROCESS — the denied class under the write-denial flap,
whose waves deny Python open('w') and fsync in short-lived
processes. A restore denied in the same wave that truncated
the credential it was healing left the fleet blind. The cure
pinned here: the route performs through the /ops service
first (the shared writer, server-side), falls back to the
local staged protocol under bounded denial retry only on a
transport failure, and treats every well-formed server
answer — above all a refusal — as final.

The client and writer seams are doubled, in the lease-unit
suite's manner: the client's WriterError is a distinct
class from the route's, as the client's loaded writer
module is a distinct instance in production.
"""

import errno
import importlib.util
import os
import stat
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


route = load("writer_route_under_test", "sync/writer_route.py")

REAL_WRITER = route.WRITER


class _ClientError(Exception):
    """The client double's WriterError stand-in (a distinct
    class from the route's, as in production)."""

    def __init__(self, name, detail=""):
        super().__init__(detail or name)
        self.name = name
        self.detail = detail or name


def _fake_client(monkeypatch, behaviour):
    calls = []

    def staged_write(caller, path, data, mode=None):
        calls.append((caller, path, data, mode))
        behaviour(caller, path, data, mode)

    fake = types.SimpleNamespace(WriterError=_ClientError, staged_write=staged_write)
    monkeypatch.setattr(route, "OPS_CLIENT", fake)
    return calls


def _exploding_writer(monkeypatch):
    def denied(*a, **k):
        raise AssertionError("the route attempted a local write")

    monkeypatch.setattr(route, "WRITER", types.SimpleNamespace(
        WriterError=route.WriterError, staged_write=denied))


def _unreachable(caller, path, data, mode):
    raise _ClientError(
        "io_error", "ops server unreachable — nothing was performed")


def _denial_error():
    """A denial as the platform writer surfaces it: its
    io_error WriterError raised `from` the denied OSError,
    so the errno rides the cause chain."""
    try:
        raise OSError(errno.EPERM, "Operation not permitted")
    except OSError as exc:
        err = route.WriterError("io_error", str(exc))
        err.__cause__ = exc
        return err


def test_server_route_performs_the_write(tmp_path, monkeypatch):
    target = tmp_path / "token.json"
    landed = {}

    def perform(caller, path, data, mode):
        landed[path] = (data, mode)

    calls = _fake_client(monkeypatch, perform)
    _exploding_writer(monkeypatch)
    route.staged_write(target, b'{"v": 1}', mode=0o600)
    assert calls == [("workhorse", str(target), b'{"v": 1}', 0o600)]
    assert landed == {str(target): (b'{"v": 1}', 0o600)}
    assert not target.exists()  # the double performed it, not the disk


def test_server_unreachable_falls_back_and_lands(tmp_path, monkeypatch):
    target = tmp_path / "token.json"
    _fake_client(monkeypatch, _unreachable)
    route.staged_write(target, b'{"v": 2}', mode=0o600)
    assert target.read_bytes() == b'{"v": 2}'
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_server_lost_response_falls_back_and_lands(tmp_path, monkeypatch):
    target = tmp_path / "sessions.json"

    def lost(caller, path, data, mode):
        raise _ClientError(
            "io_error",
            "ops request sent but its response was lost — the "
            "outcome is unknown and the op may have performed; "
            "verify before repeating")

    _fake_client(monkeypatch, lost)
    route.staged_write(target, b"{}", mode=0o600)
    assert target.read_bytes() == b"{}"


def test_server_refusal_is_final_and_the_target_untouched(tmp_path, monkeypatch):
    target = tmp_path / "token.json"
    target.write_bytes(b"standing")

    def refuse(caller, path, data, mode):
        raise _ClientError("outside_scope", "resolves outside the workspace")

    _fake_client(monkeypatch, refuse)
    _exploding_writer(monkeypatch)
    with pytest.raises(route.WriterError) as caught:
        route.staged_write(target, b"new", mode=0o600)
    # Normalized onto the route's own WriterError class,
    # with the endpoint's error name carried whole.
    assert caught.value.name == "outside_scope"
    assert target.read_bytes() == b"standing"


def test_fallback_retries_a_transient_denial_then_lands(tmp_path, monkeypatch):
    target = tmp_path / "token.json"
    _fake_client(monkeypatch, _unreachable)
    monkeypatch.setenv("VENUE_WRITER_ATTEMPTS", "4")
    monkeypatch.setenv("VENUE_WRITER_BACKOFF_S", "0,0,0")
    attempts = []

    def flaky(path, data, mode=None):
        attempts.append(path)
        if len(attempts) < 3:
            raise _denial_error()
        REAL_WRITER.staged_write(path, data, mode=mode)

    monkeypatch.setattr(route, "WRITER", types.SimpleNamespace(
        WriterError=route.WriterError, staged_write=flaky))
    route.staged_write(target, b'{"v": 3}', mode=0o600)
    assert len(attempts) == 3
    assert target.read_bytes() == b'{"v": 3}'
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_fallback_exhaustion_leaves_the_target_byte_identical(tmp_path, monkeypatch):
    target = tmp_path / "token.json"
    target.write_bytes(b"standing")
    _fake_client(monkeypatch, _unreachable)
    monkeypatch.setenv("VENUE_WRITER_ATTEMPTS", "3")
    monkeypatch.setenv("VENUE_WRITER_BACKOFF_S", "0,0")

    def always_denied(path, data, mode=None):
        raise _denial_error()

    monkeypatch.setattr(route, "WRITER", types.SimpleNamespace(
        WriterError=route.WriterError, staged_write=always_denied))
    with pytest.raises(route.WriterError) as caught:
        route.staged_write(target, b"new", mode=0o600)
    assert caught.value.name == "io_error"
    assert target.read_bytes() == b"standing"
    # No staging litter survives an exhausted retry.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["token.json"]


def test_a_non_denial_local_failure_is_not_retried(tmp_path, monkeypatch):
    target = tmp_path / "token.json"
    _fake_client(monkeypatch, _unreachable)
    monkeypatch.setenv("VENUE_WRITER_ATTEMPTS", "4")
    monkeypatch.setenv("VENUE_WRITER_BACKOFF_S", "0,0,0")
    attempts = []

    def mismatch(path, data, mode=None):
        attempts.append(path)
        raise route.WriterError("verify_failed", "read-back mismatch")

    monkeypatch.setattr(route, "WRITER", types.SimpleNamespace(
        WriterError=route.WriterError, staged_write=mismatch))
    with pytest.raises(route.WriterError) as caught:
        route.staged_write(target, b"new")
    assert caught.value.name == "verify_failed"
    assert len(attempts) == 1


def test_no_platform_tree_uses_the_inline_protocol(tmp_path, monkeypatch):
    target = tmp_path / "auth-required.json"
    monkeypatch.setattr(route, "OPS_CLIENT", None)
    monkeypatch.setattr(route, "WRITER", None)
    route.staged_write(target, b'{"noted_at": "x"}', mode=0o600)
    assert target.read_bytes() == b'{"noted_at": "x"}'
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["auth-required.json"]
