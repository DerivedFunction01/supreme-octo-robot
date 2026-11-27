"""The lease panel's heavy-usage hardening (the venue
split): state reads serve stale-while-recompute so
a blocked core call never blocks a warm read; the cold
read computes once, single-flighted, off the request
path — the reader's wait is bounded by
STATE_READ_TIMEOUT_S while the build itself runs under
STATE_COMPUTE_TIMEOUT_S and lands even when slower
than the wait (the wedge cure: a build killed at its
own bound on every read could never warm a key); lease
actions keep the action bound (CORE_TIMEOUT_S); and
the venue listener admits no more than the named
handler-thread bound under parallel load.

In-process shape (test_ui_stackdump.py's pattern): the
panel module loads by location, run_core is monkeypatched
at the module seam, and routes dispatch through the real
mount — no subprocess, no real lease state.
"""

import http.client
import importlib.util
import inspect
import json
import sys
import threading
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
UI = REPO / "ui"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(UI))
server = _load("ui_server_state_reads", UI / "server.py")
bounded_server = server.bounded_server


def wait_for(predicate, timeout_s: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _panel(tmp_path, monkeypatch, refresh_after_s=None):
    """A fresh mount over a tmp var dir, watchdog off,
    state cache unbuilt (the mount builds it against the
    monkeypatched run_core)."""
    monkeypatch.setenv("VENUE_RUNNER_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("VENUE_LEASE_UI_STACKDUMP", "0")
    if refresh_after_s is not None:
        # The cadence's owning module is state_surface:
        # build_state_reads reads its global at build time.
        # server's same-named alias is an import-time snapshot
        # and patching it changes nothing (the
        # extraction seam defect).
        monkeypatch.setattr(
            server.state_surface, "STATE_REFRESH_AFTER_S",
            refresh_after_s)
    server.OUTBOX = None
    server.STATE_READS = None
    mount, _host, _port = server.build_mount()
    return mount


def _get(mount, path):
    reply = mount.dispatch(
        server.serving.Request("GET", path, {}, b""))
    return reply.status, json.loads(reply.body.decode())


def _post(mount, path, payload):
    reply = mount.dispatch(server.serving.Request(
        "POST", path, {}, json.dumps(payload).encode()))
    return reply.status, json.loads(reply.body.decode())


def test_state_read_serves_last_build_while_refresh_blocked(
        tmp_path, monkeypatch):
    mount = _panel(tmp_path, monkeypatch, refresh_after_s=0.0)
    gate = threading.Event()
    calls = []
    mode = {"blocked": False}

    def fake_run_core(*args, **kwargs):
        calls.append(args)
        if mode["blocked"]:
            gate.wait(10)
            return 0, {"marker": 2}, ""
        return 0, {"marker": 1}, ""

    monkeypatch.setattr(server, "run_core", fake_run_core)

    status, body = _get(mount, "/api/state")
    assert status == 200 and body["marker"] == 1
    assert calls == [("state",)]

    # The next read kicks a background refresh that parks
    # inside the core call; warm reads keep serving the
    # last good build, immediately, and no second refresh
    # piles up behind the parked one.
    mode["blocked"] = True
    started = time.monotonic()
    status, body = _get(mount, "/api/state")
    assert time.monotonic() - started < 5
    assert status == 200 and body["marker"] == 1
    assert wait_for(lambda: len(calls) == 2)
    status, body = _get(mount, "/api/state")
    assert status == 200 and body["marker"] == 1
    time.sleep(0.2)
    assert len(calls) == 2  # still the one parked refresh

    # When the core answers again, the refresh lands and
    # reads serve the new build.
    gate.set()
    assert wait_for(
        lambda: _get(mount, "/api/state")[1]["marker"] == 2)


def test_cold_state_reads_compute_once_single_flighted(
        tmp_path, monkeypatch):
    mount = _panel(tmp_path, monkeypatch)
    calls = []
    calls_lock = threading.Lock()

    def fake_run_core(*args, **kwargs):
        with calls_lock:
            calls.append(args)
        time.sleep(0.4)
        return 0, {"records": [{"session": "s"}]}, ""

    monkeypatch.setattr(server, "run_core", fake_run_core)

    results = []

    def read_part():
        results.append(_get(mount, "/api/state/records"))

    threads = [threading.Thread(target=read_part)
               for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert len(results) == 4
    assert all(status == 200 for status, _ in results)
    assert all(body["records"][0]["session"] == "s"
               for _, body in results)
    assert calls == [("state", "--part", "records")]


def test_cold_build_slower_than_the_wait_still_lands():
    """The wedge, pinned shut: a cold compute that takes
    longer than the reader's wait is NOT killed at the
    wait — the first read answers the failure form, the
    build runs on, lands, and the next read serves it,
    with exactly one compute throughout."""
    state_reads = server.state_reads
    calls = []

    def slow_compute(key):
        calls.append(key)
        time.sleep(0.8)
        return 0, {"marker": 1}, ""

    reads = state_reads.StateReads(
        slow_compute, refresh_after_s=5.0, cold_wait_s=0.2)
    started = time.monotonic()
    rc, result, _err = reads.read(("state",))
    assert time.monotonic() - started < 0.6
    assert result is None  # the wait expired; failure form
    # A second reader during the same flight starts no
    # second compute.
    rc, result, _err = reads.read(("state",))
    assert result is None
    assert calls == [("state",)]
    # The build lands on its own schedule and warms the
    # key; the next read serves it, still one compute.
    assert wait_for(lambda: reads._entry(("state",)) is not None)
    rc, result, _err = reads.read(("state",))
    assert result == {"marker": 1}
    assert calls == [("state",)]


def test_read_timeout_scoped_to_state_not_actions(
        tmp_path, monkeypatch):
    mount = _panel(tmp_path, monkeypatch)
    seen = []

    # The bound a caller actually gets: action routes call
    # run_core without a timeout and ride its default, so
    # the fake resolves the effective timeout from the real
    # function's default (captured before the patch) rather
    # than recording the raw kwarg — and the default itself
    # is pinned to CORE_TIMEOUT_S below, so the effective
    # action bound cannot drift silently.
    real_default = inspect.signature(
        server.run_core).parameters["timeout"].default

    def recording_run_core(*args, **kwargs):
        seen.append((args, kwargs.get("timeout", real_default)))
        if args[0] == "state":
            return 0, {"records": []}, ""
        return 0, {"action": "ungranted"}, ""

    monkeypatch.setattr(server, "run_core", recording_run_core)

    assert server.STATE_READ_TIMEOUT_S == 30
    assert server.STATE_READ_TIMEOUT_S < server.CORE_TIMEOUT_S
    assert real_default == server.CORE_TIMEOUT_S
    # The split bounds (the wedge cure): the state
    # build runs under the compute bound, far above the
    # reader's wait, and the cache's cold wait is the
    # read bound itself.
    assert server.STATE_COMPUTE_TIMEOUT_S \
        > server.STATE_READ_TIMEOUT_S
    assert server.STATE_READS._cold_wait_s \
        == server.STATE_READ_TIMEOUT_S

    status, _ = _get(mount, "/api/state")
    assert status == 200
    status, _ = _post(mount, "/api/ungrant", {"confirm": True})
    assert status == 200
    assert server.stackdump_health() is True

    state_timeouts = [t for args, t in seen if args[0] == "state"]
    action_timeouts = [t for args, t in seen if args[0] == "ungrant"]
    # The route's state read (through the cache's compute)
    # carries the compute bound — a slow build must be
    # allowed to land — while the watchdog's direct probe
    # keeps the read bound (it measures responsiveness,
    # not completion). The action's effective bound is
    # the action bound (the run_core default, pinned
    # above).
    assert state_timeouts == [server.STATE_COMPUTE_TIMEOUT_S,
                              server.STATE_READ_TIMEOUT_S]
    assert action_timeouts == [server.CORE_TIMEOUT_S]


def test_bounded_listener_caps_concurrent_handlers():
    assert bounded_server.MAX_HANDLER_THREADS == 32

    release = threading.Event()
    lock = threading.Lock()
    state = {"current": 0, "peak": 0}

    def block(request):
        with lock:
            state["current"] += 1
            state["peak"] = max(state["peak"],
                                state["current"])
        release.wait(10)
        with lock:
            state["current"] -= 1
        return 200, {"ok": True}

    router = server.serving.Router()
    router.add("GET", "/block", block)
    mount = server.serving.Mount("venue-bound-test", router)
    listener = bounded_server.build_bounded_listener(
        server.serving, mount, "127.0.0.1", 0, max_threads=3)
    port = listener.server_address[1]
    listener.start()
    try:
        statuses = []

        def client():
            conn = http.client.HTTPConnection(
                "127.0.0.1", port, timeout=15)
            conn.request("GET", "/block")
            resp = conn.getresponse()
            resp.read()
            statuses.append(resp.status)
            conn.close()

        threads = [threading.Thread(target=client)
                   for _ in range(6)]
        for thread in threads:
            thread.start()
        # Three handlers admitted; the rest queue at the
        # socket — the peak never moves past the bound.
        assert wait_for(lambda: state["peak"] == 3, 5)
        time.sleep(0.3)
        assert state["peak"] == 3
        assert statuses == []
        release.set()
        for thread in threads:
            thread.join(15)
        assert sorted(statuses) == [200] * 6
        assert state["peak"] == 3
    finally:
        release.set()
        listener.shutdown()
        listener.server_close()
