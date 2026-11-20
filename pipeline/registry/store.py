"""The merged registry store (contract 01).

One live JSON file holds every section of the caller +
routing registry:

  version          the store form's version (1)
  thread_callers   {callers: [ids], active: [ids]} — the
                   runner file form, operator-written only
  token_callers    {name: {token_sha256, scopes}} — the
                   connector form; hashes only, ever
  routing          the caller→chat tables (see routing.py)
  handlers         attention handler rows (§9.1)
  programmes       attention programme rows (§9.1)

Machinery callers are code constants (callers.py) and are
never listed in this file. The file itself is untracked
live state under contract 04's seed/example pattern:
seeded from the tracked fictional examples on a fresh
deployment, and for this consolidation seeded from the S1
overlay capture (seed.py) — never the reverse.

Load discipline, carried from both pinned registries: a
missing or malformed store yields an empty registry —
fail-closed per nature (thread claims fall back to the
machinery set alone; token authentication refuses every
call) and never a crash.
"""

from __future__ import annotations

import importlib.util
import json
import os

from . import paths as _paths

STORE_VERSION = 1

_SECTIONS = ("thread_callers", "token_callers", "routing",
             "handlers", "programmes")


def _load_platform_writer():
    """The staged-write protocol core lives in the pipeline
    platform home (contract 15); loaded by path from the
    registry paths module, so the protocol has exactly one
    implementation."""
    path = _paths.PLATFORM_WRITER
    spec = importlib.util.spec_from_file_location(
        "pipeline_platform_writer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_writer = _load_platform_writer()


def empty_data() -> dict:
    """The empty registry: every section present, every
    section empty. Machinery callers still resolve — they
    are constants, not data."""
    return {
        "version": STORE_VERSION,
        "thread_callers": {"callers": [], "active": []},
        "token_callers": {},
        "routing": {
            "bridge_wake_owners": {"version": 1, "owners": {}},
            "notify_routes": {"main": None, "routes": {}},
            "restart_owners": {"owners": {}, "namespaces": {},
                               "prefixes": {}},
        },
        "handlers": [],
        "programmes": [],
    }


def _clean(data) -> dict:
    """Shape the loaded mapping onto the store form:
    sections of the wrong type fall back to their empty
    form rather than poisoning a nature's validation."""
    out = empty_data()
    if not isinstance(data, dict):
        return out
    if isinstance(data.get("version"), int):
        out["version"] = data["version"]
    thread = data.get("thread_callers")
    if isinstance(thread, dict):
        out["thread_callers"] = {
            "callers": thread.get("callers")
            if isinstance(thread.get("callers"), list) else [],
            "active": thread.get("active")
            if isinstance(thread.get("active"), list) else [],
        }
    tokens = data.get("token_callers")
    if isinstance(tokens, dict):
        out["token_callers"] = tokens
    routing = data.get("routing")
    if isinstance(routing, dict):
        for table, form in empty_data()["routing"].items():
            if isinstance(routing.get(table), dict):
                merged = dict(form)
                merged.update(routing[table])
                out["routing"][table] = merged
    for section in ("handlers", "programmes"):
        if isinstance(data.get(section), list):
            out[section] = data[section]
    return out


class Registry:
    """The one registry store, loaded. Consumers resolve
    every nature through the sibling modules (callers,
    tokens, routing, directory); this class is the data
    and its persistence."""

    def __init__(self, data=None) -> None:
        self.data = _clean(data if data is not None else {})

    @classmethod
    def empty(cls) -> "Registry":
        return cls(empty_data())

    @classmethod
    def load(cls, path) -> "Registry":
        """Load the store at path. A missing or malformed
        file yields the empty registry — the pinned
        fail-closed discipline, never a crash."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return cls(json.load(fh))
        except (OSError, ValueError):
            return cls.empty()

    def save(self, path) -> None:
        """Persist through the unified writer (contract
        15): staged sibling, read-back compare, rename
        over — a denial at any stage leaves the previous
        store byte-identical."""
        payload = json.dumps(self.data, indent=2,
                             sort_keys=True).encode("utf-8")
        _writer.staged_write(os.fspath(path), payload)

    # -- section accessors ------------------------------------

    def thread_callers(self) -> dict:
        return self.data["thread_callers"]

    def token_callers(self) -> dict:
        return self.data["token_callers"]

    def routing(self) -> dict:
        return self.data["routing"]

    def handlers(self) -> list:
        return self.data["handlers"]

    def programmes(self) -> list:
        return self.data["programmes"]
