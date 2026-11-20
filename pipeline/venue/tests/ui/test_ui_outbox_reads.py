"""The outbox's stored-shape read path (2026-11-16):
/api/outbox used to re-read and re-parse the whole
ui-outbox.jsonl on every poll — the profiled payload
(747,589 B) cost 200.5 ms per request at N=1 growing
to 2,019.8 ms at N=8 while the venue's state parts,
served from their stored shapes, sat at 2.7–14.2 ms.

The cure keeps the parsed events as the shape reads
serve, in the state parts' discipline: append() extends
the shape with the event it wrote; the runner core's
run-terminal appends write the file directly, so a read
stats the file first and rebuilds the shape whenever
the file changed. These pins hold the three properties
the cure stands on:

  - result preservation: after() equals the old
    read-the-file-every-time algorithm over the same
    bytes, for every cursor;
  - no stale reads: an external append, a replacement,
    or a shrink is visible on the very next read;
  - no per-request recompute: an unchanged file is
    parsed once, however many reads follow.

Deterministic throughout: histories are seeded with
fixed timestamp strings, file writes are synchronous,
and nothing sleeps, polls, or asserts on a clock.
"""

import json
import random
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
UI = REPO / "ui"

sys.path.insert(0, str(UI))


def _load(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = _load("ui_server_outbox_reads", UI / "server.py")

TS = "2026-11-16T00:00:00+00:00"


def write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events))


def file_truth(path: Path, seq: int):
    """The pre-cure read algorithm, verbatim: parse the
    whole file, filter by seq, echo the cursor when no
    event passes."""
    events = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    events = [e for e in events if int(e.get("seq", 0)) > seq]
    last = max([seq] + [int(e.get("seq", 0)) for e in events])
    return events, last


def external_append(path: Path, kind: str, detail: dict) -> dict:
    """The runner core's write shape (emit_terminal_event):
    derive the next seq from the file's tail and append
    directly, with no contact with the server's Outbox."""
    seq = 0
    lines = path.read_text().splitlines()
    for line in reversed(lines):
        if line.strip():
            seq = int(json.loads(line).get("seq", 0))
            break
    event = {"seq": seq + 1, "ts": TS, "kind": kind, "detail": detail}
    with path.open("a") as fh:
        fh.write(json.dumps(event) + "\n")
    return event


class CountingOutbox(server.Outbox):
    """Counts full-file parses: the stored shape may be
    built once per file change, never once per read."""

    def __init__(self, path):
        self.reads = 0
        super().__init__(path)

    def _read_all(self):
        self.reads += 1
        return super()._read_all()


def seeded_history() -> list[dict]:
    rng = random.Random(20261116)
    events = []
    for i in range(1, 301):
        events.append({
            "seq": i,
            "ts": TS,
            "kind": rng.choice(["lease-started", "lease-extended",
                                "run-terminal", "grant-ended"]),
            "detail": {"n": i, "pad": "x" * rng.randrange(0, 40)},
        })
    # The two-writer race shape: one duplicated seq.
    events.append({"seq": 300, "ts": TS, "kind": "run-terminal",
                   "detail": {"n": 301}})
    # An event with no seq counts as 0, exactly as before.
    events.append({"ts": TS, "kind": "lease-started", "detail": {}})
    return events


def test_after_matches_file_truth_for_a_seeded_history(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    events = seeded_history()
    raw = "".join(json.dumps(e) + "\n" for e in events)
    # Unparseable and blank lines ride the file, skipped
    # by both readers identically.
    raw = raw.replace("\n", "\nnot json\n\n", 1)
    path.write_text(raw)
    outbox = server.Outbox(path)
    for cursor in (0, 1, 7, 150, 299, 300, 301, 10_000):
        assert outbox.after(cursor) == file_truth(path, cursor)


def test_unchanged_file_is_parsed_once(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    write_events(path, seeded_history())
    outbox = CountingOutbox(path)
    assert outbox.reads == 1
    for _ in range(3):
        outbox.after(0)
        outbox.after(150)
    assert outbox.reads == 1
    # The server's own append extends the shape; the next
    # read still needs no rebuild.
    outbox.append("lease-extended", {"session": "s"})
    assert outbox.reads == 1
    outbox.after(0)
    assert outbox.reads == 1
    # An external append forces exactly one rebuild, on
    # the first read that follows it.
    external_append(path, "run-terminal", {"run_id": "r"})
    outbox.after(0)
    assert outbox.reads == 2
    outbox.after(0)
    assert outbox.reads == 2


def test_external_append_is_visible_on_the_next_read(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    write_events(path, [
        {"seq": 1, "ts": TS, "kind": "lease-started", "detail": {}},
        {"seq": 2, "ts": TS, "kind": "lease-extended", "detail": {}},
    ])
    outbox = server.Outbox(path)
    assert outbox.after(0)[1] == 2
    event = external_append(path, "run-terminal", {"run_id": "r-1"})
    events, last = outbox.after(0)
    assert events[-1] == event and last == 3
    assert outbox.after(2) == ([event], 3)
    assert outbox.after(3) == ([], 3)


def test_external_replacement_and_removal_are_visible(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    write_events(path, seeded_history())
    outbox = server.Outbox(path)
    # 301 events carry seq > 0; the seq-less one counts 0.
    assert len(outbox.after(0)[0]) == 301
    # A prune/rotation replaces the file with a shorter
    # one; the shape follows the file, never its memory.
    write_events(path, [
        {"seq": 1, "ts": TS, "kind": "lease-started", "detail": {}},
    ])
    assert outbox.after(0) == file_truth(path, 0)
    path.unlink()
    assert outbox.after(0) == ([], 0)
    assert outbox.after(5) == ([], 5)


def test_own_append_keeps_file_format_and_seq(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    outbox = server.Outbox(path)
    first = outbox.append("lease-started", {"session": "a"})
    second = outbox.append("lease-stopped", {"session": "a"})
    assert (first["seq"], second["seq"]) == (1, 2)
    lines = path.read_text().splitlines()
    assert [json.loads(line) for line in lines] == [first, second]
    # The served dicts are the file's own parsed lines.
    events, last = outbox.after(0)
    assert events == [json.loads(line) for line in lines]
    assert last == 2
    assert outbox.after(1) == ([second], 2)


def test_served_events_equal_a_fresh_parse_after_mixed_writes(tmp_path):
    path = tmp_path / "ui-outbox.jsonl"
    write_events(path, seeded_history()[:10])
    outbox = server.Outbox(path)
    outbox.append("budget-caps-changed", {"caps": {}})
    external_append(path, "run-terminal", {"run_id": "r-2"})
    outbox.append("grant-ended", {"result": {}})
    events, _last = outbox.after(0)
    parsed = [json.loads(line) for line in
              path.read_text().splitlines() if line.strip()]
    assert events == parsed


def test_wire_read_sees_an_external_append_while_the_server_runs(tmp_path):
    """Through the real server (the ui harness's boot): a
    run-terminal line appended directly to the served
    var dir's outbox appears in the very next poll."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ui_harness import UiServer

    var = tmp_path / "var"
    var.mkdir(parents=True)
    seeded = [
        {"seq": 1, "ts": TS, "kind": "lease-started", "detail": {}},
        {"seq": 2, "ts": TS, "kind": "lease-extended", "detail": {}},
    ]
    write_events(var / "ui-outbox.jsonl", seeded)
    ui = UiServer(tmp_path)
    try:
        page = ui.get_json("/api/outbox?after=0")
        assert page["events"] == seeded and page["last_seq"] == 2
        event = external_append(var / "ui-outbox.jsonl",
                                "run-terminal", {"run_id": "r-3"})
        page = ui.get_json("/api/outbox?after=2")
        assert page["events"] == [event] and page["last_seq"] == 3
    finally:
        ui.close()
