"""The assembled shapes' database store (the owner's
persistence ruling, 2026-11-17: the assembled read
shapes belong in a database, so they persist).

Two shapes persist here: the assembled feeds document
(server/assemble) and the repo census
(server/repos_feed) — the two read shapes whose cold
assembly / cold walk a restart used to pay on its
first reads. Each stands as ONE row: the payload
bytes, the instant the shape was assembled, and a
fingerprint of the source it was assembled from. A
persist replaces the row — no history accumulates
here; history is the registry's and the ledger's
business, not the read shapes'.

The store is deliberately small (the dispatch
ledger's idiom: stdlib sqlite3, WAL, short-lived
connections, a lock around writes). Its file lives
in the state dir through the config seam
(shapes_store_file), beside the message store.

Failure discipline: the store never sinks a serve. A
file that is not a database is discarded and rebuilt
empty at open; a schema-version mismatch discards
the table and rebuilds it; an absent shape reads as
None. Callers contain the rest — the persist logs
and moves on, the prime falls back to the cold path.
"""

import sqlite3
import threading
from pathlib import Path

from . import config as cfgmod  # noqa: E402

SCHEMA_VERSION = 1

FEEDS_DOCUMENT = "feeds_document"
CENSUS = "census"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shapes (
    name TEXT PRIMARY KEY,
    payload BLOB NOT NULL,
    assembled_at TEXT NOT NULL,
    fingerprint TEXT,
    stored_at TEXT NOT NULL
);
"""


class ShapeStore:
    """One shapes database file. Construction readies
    the schema (discarding on a version mismatch or a
    non-database file, per the module note); put, get,
    and payload_size are the whole surface."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._ready()
        except sqlite3.DatabaseError:
            # Not a database — a truncated or foreign
            # file at the path. Discard it and rebuild
            # empty: the cold path stands, exactly as
            # it does for a missing store.
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(f"{self.path}{suffix}").unlink()
                except OSError:
                    pass
            self._ready()

    def _connect(self):
        con = sqlite3.connect(str(self.path), timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def _ready(self) -> None:
        con = self._connect()
        try:
            version = con.execute(
                "PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                # A store from another schema era: its
                # rows are the old shape's, and shapes
                # are regenerable by definition — the
                # next assembly / walk rebuilds them.
                con.execute("DROP TABLE IF EXISTS shapes")
            con.executescript(_SCHEMA)
            if version != SCHEMA_VERSION:
                con.execute(
                    f"PRAGMA user_version = {SCHEMA_VERSION}")
            con.commit()
        finally:
            con.close()

    def put(self, name, payload: bytes, *, assembled_at,
            fingerprint, stored_at) -> None:
        """Replace the shape's one row: the payload
        bytes, the instant the shape was assembled,
        the fingerprint of its source, and the instant
        it was stored (the two instants are one act's,
        kept apart because they answer different
        questions — how old is this shape, and when
        did the store last move)."""
        with self._lock:
            con = self._connect()
            try:
                con.execute(
                    "INSERT INTO shapes (name, payload,"
                    " assembled_at, fingerprint, stored_at)"
                    " VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(name) DO UPDATE SET"
                    " payload = excluded.payload,"
                    " assembled_at = excluded.assembled_at,"
                    " fingerprint = excluded.fingerprint,"
                    " stored_at = excluded.stored_at",
                    (name, payload, assembled_at,
                     fingerprint, stored_at))
                con.commit()
            finally:
                con.close()

    def get(self, name):
        """{payload, assembled_at, fingerprint} for the
        shape, or None when the store holds no row for
        it."""
        con = self._connect()
        try:
            row = con.execute(
                "SELECT payload, assembled_at, fingerprint"
                " FROM shapes WHERE name = ?",
                (name,)).fetchone()
        finally:
            con.close()
        if row is None:
            return None
        return {"payload": bytes(row[0]),
                "assembled_at": row[1],
                "fingerprint": row[2]}

    def payload_size(self, name):
        """The stored payload's byte length, without
        loading it (the prime guard's stat, one level
        down), or None when no row stands."""
        con = self._connect()
        try:
            row = con.execute(
                "SELECT length(payload) FROM shapes"
                " WHERE name = ?", (name,)).fetchone()
        finally:
            con.close()
        return None if row is None else row[0]


def open_store(cfg) -> ShapeStore:
    """The store for a loaded server config (the path
    resolves through the config seam, like every state
    file). Construction is cheap — a connect and a
    version check — so callers open per act rather
    than holding a connection for the process's
    life."""
    return ShapeStore(cfgmod.shapes_store_path(cfg))
