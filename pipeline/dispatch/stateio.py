"""Durable state I/O: JSON written temp-file-plus-rename (spec EC-10),
so a crash mid-write leaves the previous good file. Reads raise
StateError on anything unreadable or malformed — the engine treats
that as fail-safe state_error and stops firing.

Consolidation (step S9/P4, plan §4.15 / contract 15): the staging
half of write_json is the unified state writer's protocol now —
this module keeps the JSON serialization and the exception
surface its callers were written against, and delegates the
stage → fsync → read-back → rename act to
`pipeline/platform/writer.py`, the protocol's one implementation.
The hand-rolled mkstemp staging that stood here since the pin is
the per-app atomic-write helper §12 folds into the wrapper."""
import json
import os


class StateError(Exception):
    pass


def _load_platform_writer():
    """The staged-write protocol core lives in the pipeline
    platform home (contract 15); loaded by path from the
    dispatch paths module — the ops service's standing
    pattern — so the protocol has exactly one implementation."""
    import importlib.util
    paths_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "paths.py")
    spec = importlib.util.spec_from_file_location(
        "pipeline_dispatch_paths", paths_path)
    paths = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paths)
    path = paths.PLATFORM_WRITER
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_writer = _load_platform_writer()


def write_json(path, data):
    blob = (json.dumps(data, indent=1, sort_keys=True)
            + "\n").encode("utf-8")
    try:
        _writer.staged_write(path, blob)
    except _writer.WriterError as exc:
        # This module's standing exception surface is OSError
        # (its callers — the engine, the outbox — were written
        # against the staging discipline this replaces, whose
        # failures were OSError); the writer's error names map
        # onto it here, at the seam, nowhere else.
        raise OSError(exc.detail) from exc


def read_json(path, default):
    """Return the stored JSON, or `default` when the file simply does
    not exist yet. A file that exists but cannot be parsed is a
    StateError, never a silent default (EC-10)."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise StateError(f"state file {path} is unreadable: {exc}") from exc
