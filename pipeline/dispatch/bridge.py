"""The connector bridge queue (contract 05, SCH8).

One JSON record per bridged call under the bridge
directory. A bridged call is one the hosting server
cannot perform in-process (chat and pending-permission
access are runtime agent tools): the call records a
request here, a home-side agent holding the runtime
tools fulfills it, and the requester polls for the
result. Attribution is preserved end to end; bridged
tools are asynchronous by contract.

Envelope idempotency: a record may carry an
`envelope_id` (1–128 chars of [A-Za-z0-9._-]); a second
enqueue with the same (caller, envelope_id) returns the
existing record instead of queueing a twin — a
transport-level retry of one performed call can never
double-queue (a duplicated chat_send would double-send).

Records are written through the pipeline platform
writer's staged-write protocol (contract 15), loaded by
path from this file's location — the mega repo's
standing seam — so a write denial or crash can never
tear a record.

Extracted at S6 from the pinned scheduler's connector
module, which keeps the tool surface (auth, scopes,
direct tools) and calls this queue.
"""
import importlib.util
import json
import os
import threading
import uuid
from datetime import datetime, timezone

UTC = timezone.utc

_lock = threading.Lock()

_ENVELOPE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_paths = _load_module(
    "pipeline_dispatch_paths",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "paths.py"))


def _load_platform_writer():
    """The staged-write protocol core lives in the
    pipeline platform home (contract 15); loaded by path
    from the dispatch paths module, so the protocol has
    exactly one implementation."""
    path = _paths.PLATFORM_WRITER
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_writer = _load_platform_writer()


def valid_envelope_id(value):
    return isinstance(value, str) and 1 <= len(value) <= 128 \
        and all(c in _ENVELOPE_CHARS for c in value)


def request_path(bridge_dir, request_id):
    return os.path.join(bridge_dir, f"{request_id}.json")


def write_record(bridge_dir, record):
    os.makedirs(bridge_dir, exist_ok=True)
    _writer.staged_write(
        request_path(bridge_dir, record["id"]),
        (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def new_record(caller, tool, args, envelope_id=None):
    record = {
        "id": uuid.uuid4().hex[:16], "tool": tool, "args": args,
        "caller": caller, "ts": datetime.now(UTC).isoformat(),
        "status": "queued",
    }
    if envelope_id is not None:
        record["envelope_id"] = envelope_id
    return record


def enqueue(bridge_dir, caller, tool, args, envelope_id=None):
    record = new_record(caller, tool, args, envelope_id)
    with _lock:
        write_record(bridge_dir, record)
    return record


def read_request(bridge_dir, request_id):
    path = request_path(bridge_dir, request_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def find_by_envelope(bridge_dir, caller, envelope_id):
    if not os.path.isdir(bridge_dir):
        return None
    for name in sorted(os.listdir(bridge_dir)):
        if not name.endswith(".json"):
            continue
        record = read_request(bridge_dir, name[:-5])
        if record and record.get("caller") == caller \
                and record.get("envelope_id") == envelope_id:
            return record
    return None


def enqueue_idempotent(bridge_dir, caller, tool, args, envelope_id):
    """Find-or-enqueue under one lock hold: a retry of an
    already-seen (caller, envelope_id) returns the
    existing record, whatever its current status, and
    queues nothing. Returns (record, deduped)."""
    with _lock:
        existing = find_by_envelope(bridge_dir, caller, envelope_id)
        if existing is not None:
            return existing, True
        record = new_record(caller, tool, args, envelope_id)
        write_record(bridge_dir, record)
        return record, False


def poll_queued(bridge_dir):
    """Every record still queued, in filename order."""
    pending = []
    if os.path.isdir(bridge_dir):
        for name in sorted(os.listdir(bridge_dir)):
            if not name.endswith(".json"):
                continue
            record = read_request(bridge_dir, name[:-5])
            if record and record.get("status") == "queued":
                pending.append(record)
    return pending


def fulfill(bridge_dir, request_id, caller, ok, result=None, error=None):
    """Record a fulfillment. Returns the updated record,
    or None when no such request exists; raises
    ValueError when the record already left `queued`
    (a terminal record is never fulfilled twice)."""
    record = read_request(bridge_dir, request_id) \
        if isinstance(request_id, str) else None
    if record is None:
        return None
    if record.get("status") != "queued":
        raise ValueError(f"request already {record.get('status')}")
    record["status"] = "done" if ok else "failed"
    record["fulfilled_by"] = caller
    record["fulfilled_at"] = datetime.now(UTC).isoformat()
    if ok:
        record["result"] = result
    else:
        record["error"] = str(error or "fulfillment failed")
    with _lock:
        write_record(bridge_dir, record)
    return record
