"""The run ledger: one event per record — run, skip, ping
lifecycle, ack, error — stored in SQLite (state/scheduler.db,
WAL mode; stdlib sqlite3 only). The events table carries indexed
columns for the fields queries run on (ts, kind, job_id, status)
plus the full record as JSON, so exports reproduce the historical
JSONL lines byte-for-byte: JSONL is the export format, SQLite is
the store. Pruning by retention is internal to this module,
never a scheduled task."""
import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ts_epoch REAL,
    kind TEXT NOT NULL,
    job_id TEXT,
    status TEXT,
    record TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_job_ts ON events (job_id, ts_epoch DESC);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts_epoch DESC);
CREATE INDEX IF NOT EXISTS idx_events_kind_ts_status_job ON events (kind, ts_epoch, status, job_id);
CREATE INDEX IF NOT EXISTS idx_events_ts_text ON events (ts);
DROP INDEX IF EXISTS idx_events_kind_ts;
"""


def iso(inst):
    return inst.astimezone(UTC).isoformat()


def parse_iso(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def canonical_line(rec):
    return json.dumps(rec, sort_keys=True)


class Ledger:
    def __init__(self, state_dir):
        self.state_dir = state_dir
        self.path = os.path.join(state_dir, "scheduler.db")
        self._lock = threading.Lock()
        self._local = threading.local()
        os.makedirs(state_dir, exist_ok=True)
        con = self._connect()
        try:
            con.executescript(SCHEMA)
        finally:
            con.close()

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def _read_connect(self):
        """One read connection per thread, kept open. Reads
        used to pay a fresh connect + WAL pragmas + close on
        every call (~3x the query cost on this machine, and
        the list views make hundreds of calls); a cached
        per-thread connection removes that churn. Writes keep
        their own short-lived connections under the lock."""
        con = getattr(self._local, "con", None)
        if con is None:
            con = self._connect()
            self._local.con = con
        return con

    # ---------------------------------------------------------- write

    def record(self, kind, **fields):
        rec = {"ts": iso(datetime.now(UTC)), "kind": kind}
        rec.update(fields)
        self._insert(rec)
        return rec

    def _insert(self, rec):
        try:
            epoch = parse_iso(rec["ts"]).timestamp()
        except Exception:
            epoch = None
        with self._lock:
            con = self._connect()
            try:
                con.execute(
                    "INSERT INTO events (ts, ts_epoch, kind, job_id, status, record)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (rec["ts"], epoch, rec["kind"], rec.get("job_id"),
                     rec.get("status"), canonical_line(rec)),
                )
                con.commit()
            finally:
                con.close()

    # ---------------------------------------------------------- read

    def read_all(self):
        rows = self._read_connect().execute(
            "SELECT record FROM events ORDER BY id").fetchall()
        return [json.loads(row[0]) for row in rows]

    def query(self, job_id=None, kinds=None, limit=None, newest_first=True):
        sql = "SELECT record FROM events"
        clauses, params = [], []
        if job_id is not None:
            clauses.append("job_id = ?")
            params.append(job_id)
        if kinds:
            clauses.append("kind IN (%s)" % ",".join("?" * len(kinds)))
            params.extend(kinds)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id " + ("DESC" if newest_first else "ASC")
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._read_connect().execute(sql, params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def count_since(self, epoch, job_id=None, kinds=None, statuses=None):
        clauses = ["ts_epoch >= ?"]
        params = [epoch]
        if job_id is not None:
            clauses.append("job_id = ?")
            params.append(job_id)
        if kinds:
            clauses.append("kind IN (%s)" % ",".join("?" * len(kinds)))
            params.extend(kinds)
        if statuses:
            clauses.append("status IN (%s)" % ",".join("?" * len(statuses)))
            params.extend(statuses)
        row = self._read_connect().execute(
            "SELECT COUNT(*) FROM events WHERE " + " AND ".join(clauses),
            params).fetchone()
        return row[0]

    def counts_since_grouped(self, epoch, kinds=None):
        """{(job_id, kind, status): count} for events at or
        after epoch — one grouped pass over the window, for
        views that need per-job totals for every job at once
        (the per-job count_since fan-out was the list views'
        dominant cost)."""
        clauses = ["ts_epoch >= ?"]
        params = [epoch]
        if kinds:
            clauses.append("kind IN (%s)" % ",".join("?" * len(kinds)))
            params.extend(kinds)
        rows = self._read_connect().execute(
            "SELECT job_id, kind, status, COUNT(*) FROM events"
            " WHERE " + " AND ".join(clauses)
            + " GROUP BY job_id, kind, status",
            params).fetchall()
        return {(job_id, kind, status): n
                for job_id, kind, status, n in rows}

    def recent_by_job(self, kinds, per_job, job_ids=None):
        """{job_id: [records newest-first, up to per_job]} for
        the given kinds — one newest-first pass, bucketed in
        memory, instead of one query per job. When job_ids is
        given the pass stops once every listed job's bucket
        is full."""
        sql = ("SELECT job_id, record FROM events WHERE kind IN (%s)"
               " ORDER BY id DESC" % ",".join("?" * len(kinds)))
        wanted = set(job_ids) if job_ids is not None else None
        out = {}
        for job_id, raw in self._read_connect().execute(sql, list(kinds)):
            if job_id is None or (wanted is not None
                                  and job_id not in wanted):
                continue
            bucket = out.setdefault(job_id, [])
            if len(bucket) < per_job:
                bucket.append(json.loads(raw))
            if wanted is not None and all(
                    len(out.get(j, ())) >= per_job for j in wanted):
                break
        return out

    # ---------------------------------------------------------- lifecycle

    def prune(self, retention_days, now=None):
        """Drop records older than the retention window; returns the
        number dropped. A record with an unparseable ts is kept —
        pruning never guesses. VACUUMs when anything was dropped."""
        now = now or datetime.now(UTC)
        cutoff = (now - timedelta(days=retention_days)).timestamp()
        with self._lock:
            con = self._connect()
            try:
                cur = con.execute(
                    "DELETE FROM events WHERE ts_epoch IS NOT NULL AND ts_epoch < ?",
                    (cutoff,))
                dropped = cur.rowcount
                con.commit()
                if dropped:
                    con.execute("VACUUM")
            finally:
                con.close()
        return dropped

    def stats(self):
        con = self._read_connect()
        total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        per_job = dict(con.execute(
            "SELECT job_id, COUNT(*) FROM events"
            " WHERE job_id IS NOT NULL GROUP BY job_id").fetchall())
        per_kind = dict(con.execute(
            "SELECT kind, COUNT(*) FROM events GROUP BY kind").fetchall())
        oldest, newest = con.execute(
            "SELECT MIN(ts), MAX(ts) FROM events").fetchone()
        size = 0
        for suffix in ("", "-wal", "-shm"):
            try:
                size += os.path.getsize(self.path + suffix)
            except OSError:
                pass
        return {"events": total, "per_job": per_job, "per_kind": per_kind,
                "oldest": oldest, "newest": newest, "db_path": self.path,
                "db_bytes": size}

    def export_lines(self, job_id=None):
        """Canonical JSONL lines (the historical ledger format),
        oldest first — one job, or all when job_id is None."""
        return [canonical_line(rec)
                for rec in self.query(job_id=job_id, newest_first=False)]

    def export_to(self, out_path, job_id=None):
        lines = self.export_lines(job_id=job_id)
        blob = "".join(line + "\n" for line in lines).encode("utf-8")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(blob)
        return {"path": out_path, "rows": len(lines),
                "sha256": hashlib.sha256(blob).hexdigest()}

    def verify(self):
        con = self._connect()
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            con.close()
        return {"integrity": integrity, "events": total, "ok": integrity == "ok"}
