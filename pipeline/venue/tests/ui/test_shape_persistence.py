"""Panel shape persistence: the assembled
shapes the panel serves — the state-read cache's builds
and the outbox's stored shape — persist in the venue
var dir's SQLite shape store, so a panel restart serves
the current shape at once while the refresh disciplines
recompute behind it.

The pins, from the plan: a primed state build serves
byte-identical to the build that landed pre-restart,
with zero compute calls before the first refresh lands,
and primed builds are born refresh-eligible; a primed
outbox shape serves without a file parse exactly when
its stored signature still equals the file's; absent,
corrupt, or failing stores degrade to today's cold
behaviour everywhere — cold compute on first read, the
parse on construction, an append the store cannot
break.
"""

import importlib.util
import json
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
UI = REPO / "ui"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_loader(
        name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(UI))
server = _load("ui_server_shape_persistence", UI / "server.py")
shape_store_mod = server.state_surface.shape_store
state_reads_mod = server.state_reads
StateReads = state_reads_mod.StateReads
ShapeStore = shape_store_mod.ShapeStore


def wait_for(predicate, timeout_s: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


# -- the store itself ---------------------------------------------------


def test_store_round_trips_both_shapes(tmp_path):
    store = ShapeStore(tmp_path / "shapes.db")
    assert store.load_all_states() == {}
    assert store.load_outbox() is None
    store.save_state('["state"]', '{"rc": 0}')
    store.save_state('["state", "--part", "x"]', '{"rc": 1}')
    assert store.load_all_states() == {
        '["state"]': '{"rc": 0}',
        '["state", "--part", "x"]': '{"rc": 1}',
    }
    store.save_outbox((123, 456), '[{"seq": 1}]', 1)
    assert store.load_outbox() == ((123, 456), '[{"seq": 1}]', 1)
    # A second instance over the same file sees the same
    # shapes: the persistence is the file's, not the
    # object's.
    again = ShapeStore(tmp_path / "shapes.db")
    assert again.load_all_states() == store.load_all_states()
    assert again.load_outbox() == store.load_outbox()


def test_store_corrupt_file_reads_absent_writes_noop(tmp_path):
    path = tmp_path / "shapes.db"
    path.write_bytes(b"this is not a sqlite database" * 64)
    store = ShapeStore(path)
    assert store.load_all_states() == {}
    assert store.load_outbox() is None
    store.save_state('["state"]', '{}')
    store.save_outbox((1, 2), '[]', 0)
    assert store.load_all_states() == {}
    assert store.load_outbox() is None


# -- state builds ---------------------------------------------------------


class CountingCompute:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def __call__(self, key):
        self.calls += 1
        return 0, self.result, ""


def test_state_build_persists_and_primes_byte_identical(tmp_path):
    store = ShapeStore(tmp_path / "shapes.db")
    build = {"leases": [{"session": "s-1", "cu": 1.5}],
             "binding": {"damaged": False}}
    compute1 = CountingCompute(build)
    reads1 = server.state_surface.build_state_reads(
        compute1, store=store)
    rc, result, err = reads1.read(("state",))
    assert (rc, err) == (0, "")
    assert result == build
    served_before = json.dumps(result)

    # A fresh cache over the same store (the restart):
    # the first read serves the persisted build with the
    # compute untouched at return time, byte-identical.
    compute2 = CountingCompute({"leases": []})
    reads2 = server.state_surface.build_state_reads(
        compute2, store=store)
    rc, result, err = reads2.read(("state",))
    assert (rc, err) == (0, "")
    assert json.dumps(result) == served_before
    # The primed build was born refresh-eligible: the
    # read kicked the recompute, whose landing replaces
    # it under the existing discipline.
    assert wait_for(lambda: compute2.calls >= 1)
    assert wait_for(
        lambda: reads2.read(("state",))[1] == {"leases": []})


def test_state_prime_with_corrupt_store_is_cold_behaviour(tmp_path):
    path = tmp_path / "shapes.db"
    path.write_bytes(b"garbage" * 128)
    store = ShapeStore(path)
    compute = CountingCompute({"fresh": True})
    reads = server.state_surface.build_state_reads(
        compute, store=store)
    rc, result, err = reads.read(("state",))
    assert (rc, result, err) == (0, {"fresh": True}, "")
    assert compute.calls == 1


def test_persister_skips_undecodable_records(tmp_path):
    store = ShapeStore(tmp_path / "shapes.db")
    store.save_state('["state"]', "not json at all")
    store.save_state("not a json key", '{"rc": 0,'
                       ' "result": {}, "err": ""}')
    store.save_state('["state", "--part", "p"]',
                     '{"rc": 0, "result": [1, 2],'
                     ' "err": ""}')
    persister = server.state_surface.StateShapePersister(store)
    assert persister.load_all() == {}


def test_state_reads_without_persister_is_unchanged():
    compute = CountingCompute({"a": 1})
    reads = StateReads(compute, refresh_after_s=5.0)
    assert reads.read(("state",)) == (0, {"a": 1}, "")
    assert compute.calls == 1


# -- the outbox shape -----------------------------------------------------


class CountingOutbox(server.Outbox):
    def __init__(self, *args, **kwargs):
        self.parse_calls = 0
        super().__init__(*args, **kwargs)

    def _read_all(self):
        self.parse_calls += 1
        return super()._read_all()


def _write_events(path: Path, count: int) -> None:
    lines = []
    for seq in range(1, count + 1):
        lines.append(json.dumps(
            {"seq": seq, "ts": "2026-11-17T00:00:00+00:00",
             "kind": "note", "detail": {"n": seq}}))
    path.write_text("\n".join(lines) + "\n")


def test_outbox_primes_on_signature_match_without_parse(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    _write_events(path, 3)
    store = ShapeStore(tmp_path / "shapes.db")
    first = CountingOutbox(path, store=store)
    assert first.parse_calls == 1
    assert first.seq == 3

    second = CountingOutbox(path, store=store)
    assert second.parse_calls == 0
    assert second.seq == 3
    events, last = second.after(0)
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert last == 3


def test_outbox_signature_mismatch_parses_as_today(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    _write_events(path, 2)
    store = ShapeStore(tmp_path / "shapes.db")
    CountingOutbox(path, store=store)
    # An external append (the runner core's direct write)
    # moves the file past the stored signature.
    with path.open("a") as fh:
        fh.write(json.dumps(
            {"seq": 3, "ts": "2026-11-17T00:01:00+00:00",
             "kind": "note", "detail": {"n": 3}}) + "\n")
    third = CountingOutbox(path, store=store)
    assert third.parse_calls == 1
    events, _last = third.after(0)
    assert [e["seq"] for e in events] == [1, 2, 3]


def test_outbox_append_persists_the_extended_shape(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    _write_events(path, 1)
    store = ShapeStore(tmp_path / "shapes.db")
    outbox = CountingOutbox(path, store=store)
    outbox.append("lease-note", {"n": 2})
    primed = CountingOutbox(path, store=store)
    assert primed.parse_calls == 0
    events, last = primed.after(0)
    assert [e["seq"] for e in events] == [1, 2]
    assert last == 2


class ExplodingStore:
    def load_outbox(self):
        raise RuntimeError("store is down")

    def save_outbox(self, signature, payload, seq):
        raise RuntimeError("store is down")


def test_outbox_store_failure_never_breaks_append(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    _write_events(path, 1)
    outbox = server.Outbox(path, store=ExplodingStore())
    event = outbox.append("lease-note", {"n": 2})
    assert event["seq"] == 2
    events, last = outbox.after(0)
    assert [e["seq"] for e in events] == [1, 2]
    assert last == 2
    # The file is the truth the next process parses.
    reread = server.Outbox(path)
    events, _last = reread.after(0)
    assert [e["seq"] for e in events] == [1, 2]
