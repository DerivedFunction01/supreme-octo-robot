"""The store seam: services depend on this interface only.

State is one JSON-shaped dict — the product's local-durable
store (§1.4): handlers, items, presence, waits, rules, log.

The file-backed store is this package's migrated
AttentionStateStore (contract 01's annex; re-homed here
from the registry package at commission 12): the pinned
store's load/save protocol, seed backfill, and datetime
decode carried whole at S7, with saves riding the unified
writer (contract 15). This module keeps the pinned seam's
names (Store, MemoryStore, JsonFileStore, empty_state,
backfill) over that store, so the services and the shell
speak exactly the vocabulary they were written against.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Protocol

from attention.infra.attstore import AttentionStateStore
from attention.infra.attstore import backfill as _backfill
from attention.infra.attstore import empty_state as _empty_state


def empty_state() -> dict:
    return _empty_state()


def backfill(state: dict) -> dict:
    return _backfill(state)


class Store(Protocol):
    def load_state(self) -> dict: ...

    def save_state(self, state: dict) -> None: ...


class MemoryStore:
    """In-memory store for demos and tests."""

    def __init__(self, state: dict | None = None) -> None:
        self._state = copy.deepcopy(state) if state is not None else empty_state()

    def load_state(self) -> dict:
        return copy.deepcopy(self._state)

    def save_state(self, state: dict) -> None:
        self._state = copy.deepcopy(state)


class JsonFileStore:
    """The migrated file store at one explicit path."""

    def __init__(self, path: Path) -> None:
        self._store = AttentionStateStore(Path(path))

    def load_state(self) -> dict:
        return self._store.load_state()

    def save_state(self, state: dict) -> None:
        self._store.save_state(state)
