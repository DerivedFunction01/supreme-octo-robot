"""The writer seam's service route (the 2026-11-22 cure).

The defect class: the seam executed the platform writer
in the caller's own process, so the write-denial flap —
which denies short-lived processes in waves — killed
callers at their first write (the lease reaper's exit-120
deaths). The cure pinned here: where the platform tree
exists, foundation.staged_write performs through the
platform /ops client under the venue machinery caller,
and a service failure raises the seam's WriterError with
the target byte-identical — there is no local fallback.

These pins double the client binding (the suite's
loopback service double in tests/conftest.py covers the
end-to-end route); the in-process writer is rigged to
explode, so any local write attempt fails the pin.
"""

import importlib
import types

import pytest
from unit_harness import lease, repo  # noqa: F401

foundation = importlib.import_module("lease.core.foundation")


class _ClientError(Exception):
    """The double's own WriterError stand-in: a distinct
    class from the seam's, as the client's loaded writer
    module is a distinct instance in production."""

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
    monkeypatch.setattr(foundation, "OPS_CLIENT", fake)
    return calls


def _exploding_writer(monkeypatch):
    def denied(*a, **k):
        raise AssertionError("the seam attempted a local write")

    monkeypatch.setattr(foundation.WRITER, "staged_write", denied)


def test_seam_performs_through_the_client(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    landed = {}

    def perform(caller, path, data, mode):
        landed[path] = (data, mode)

    calls = _fake_client(monkeypatch, perform)
    _exploding_writer(monkeypatch)
    foundation.staged_write(target, b'{"v": 1}', mode=0o600)
    assert calls == [("venue", str(target), b'{"v": 1}', 0o600)]
    assert landed == {str(target): (b'{"v": 1}', 0o600)}


def test_service_failure_raises_the_seams_writer_error(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_bytes(b"standing")

    def fail(caller, path, data, mode):
        raise _ClientError("io_error", "ops server unreachable")

    _fake_client(monkeypatch, fail)
    _exploding_writer(monkeypatch)
    with pytest.raises(foundation.WRITER.WriterError) as caught:
        foundation.staged_write(target, b"new")
    # Normalized onto the seam's own WriterError class,
    # with the endpoint's error name carried whole.
    assert caught.value.name == "io_error"
    assert "unreachable" in caught.value.detail
    assert target.read_bytes() == b"standing"


def test_refusal_names_survive_the_route(tmp_path, monkeypatch):
    def refuse(caller, path, data, mode):
        raise _ClientError("outside_scope", "outside the workspace")

    _fake_client(monkeypatch, refuse)
    with pytest.raises(foundation.WRITER.WriterError) as caught:
        foundation.staged_write(tmp_path / "x.json", b"x")
    assert caught.value.name == "outside_scope"
