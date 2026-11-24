"""The panel's shape store: the SQLite persistence for
the assembled shapes the panel serves — the state-read
cache's last good builds and the outbox's stored shape —
so a panel restart serves the current shape at once
while the refresh disciplines recompute behind it
(owner ruling: workbench and venue state
persists in a database, or the surfaces load slowly /
not at all across restarts).

The store is a materialisation, never a source of
truth. The state builds it holds are the core's own
assembled documents, recomposed by the core on every
refresh from the lease records and the segment journal;
the outbox shape it holds is keyed by the JSONL file's
stat signature, so it can only ever prime a shape the
file itself would parse to. Nothing here computes a
served figure.

Containment is the contract: every operation degrades
to absent / no-op on any failure (missing directory,
corrupt database, locked store, bad payload). The
panel's cold behaviour without a store is today's
behaviour, so a broken store must be indistinguishable
from no store — never a failed read, never a failed
append. Connections are short-lived per operation; the
writers are the panel process's own threads, and
SQLite's busy timeout serialises them.
"""

import sqlite3
import time
from contextlib import closing
from pathlib import Path

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS state_shapes ("
    " key TEXT PRIMARY KEY,"
    " payload TEXT NOT NULL,"
    " stored_wall REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS outbox_shape ("
    " id INTEGER PRIMARY KEY CHECK (id = 1),"
    " sig_size INTEGER NOT NULL,"
    " sig_mtime_ns INTEGER NOT NULL,"
    " payload TEXT NOT NULL,"
    " seq INTEGER NOT NULL)",
)


class ShapeStore:
    """One SQLite file holding the panel's persisted
    shapes. Payloads are opaque JSON text owned by the
    callers; the store keeps the text and its stamps,
    nothing more."""

    def __init__(self, path: Path):
        self._path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=5.0)
        for statement in _SCHEMA:
            conn.execute(statement)
        return conn

    # -- state builds -------------------------------------------------

    def load_all_states(self) -> dict:
        """{key_text: payload_text} for every persisted
        state build; {} when the store cannot be read."""
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT key, payload FROM state_shapes"
                ).fetchall()
        except Exception:
            return {}
        return {key: payload for key, payload in rows}

    def save_state(self, key_text: str, payload_text: str) -> None:
        """Persist one state build under its key. A
        failure is a silent no-op: the in-memory cache
        already holds the build, and the next landing
        retries the store."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO state_shapes"
                    " (key, payload, stored_wall)"
                    " VALUES (?, ?, ?)",
                    (key_text, payload_text, time.time()))
                conn.commit()
        except Exception:
            pass

    # -- the outbox shape ---------------------------------------------

    def load_outbox(self):
        """((size, mtime_ns), payload_text, seq) for the
        persisted outbox shape, or None when the store
        holds none or cannot be read."""
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT sig_size, sig_mtime_ns, payload,"
                    " seq FROM outbox_shape WHERE id = 1"
                ).fetchone()
        except Exception:
            return None
        if row is None:
            return None
        return (row[0], row[1]), row[2], row[3]

    def save_outbox(self, signature, payload_text: str,
                    seq: int) -> None:
        """Persist the outbox shape under the stat
        signature it was built from. A failure is a
        silent no-op: the JSONL file remains the durable
        record, and the next refresh point retries."""
        if signature is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO outbox_shape"
                    " (id, sig_size, sig_mtime_ns, payload,"
                    " seq) VALUES (1, ?, ?, ?, ?)",
                    (signature[0], signature[1],
                     payload_text, seq))
                conn.commit()
        except Exception:
            pass
