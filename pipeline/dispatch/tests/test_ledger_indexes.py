"""Pins for the ledger's covering indexes (L-C2, 2026-11-16):
idx_events_kind_ts_status_job serves counts_since_grouped
index-only, and idx_events_ts_text serves stats()'s
MIN/MAX(ts) as endpoint reads. Indexes change speed, never
results — these tests pin the two properties the change
promises: the indexes exist (fresh stores and pre-existing
stores alike, picked up at Ledger construction), and the
grouped counts and stats over a seeded fixture equal a
brute-force pass over the same records. All timestamps are
fixed strings; no wall clock, no timing assertions."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dispatch.ledger import Ledger, canonical_line  # noqa: E402

UTC = timezone.utc

NEW_INDEXES = {"idx_events_kind_ts_status_job", "idx_events_ts_text"}

# The pre-L-C2 schema, verbatim: a store built with it must
# gain the new indexes — and lose or change no row — when
# the current Ledger opens it.
OLD_SCHEMA = """
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
CREATE INDEX IF NOT EXISTS idx_events_kind_ts ON events (kind, ts_epoch DESC);
"""


def index_names(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        con.close()


def seed_records():
    """Fixed-ts mix: kinds x statuses, a status-less run, a
    null job, records inside/outside any given window."""
    base = [
        ("2026-11-16T11:00:00+00:00", "run", "job-a", "ok"),
        ("2026-11-16T10:00:00+00:00", "run", "job-a", "failure"),
        ("2026-11-16T09:00:00+00:00", "run", "job-a", "timeout"),
        ("2026-11-16T08:00:00+00:00", "run", "job-a", None),
        ("2026-11-16T07:00:00+00:00", "run", "job-b", "ok"),
        ("2026-11-15T11:00:00+00:00", "run", "job-a", "failure"),
        ("2026-11-16T11:30:00+00:00", "ping_woken", "job-a", None),
        ("2026-11-16T06:00:00+00:00", "ping_woken", None, None),
        ("2026-11-10T00:00:00+00:00", "ledger_pruned", None, None),
    ]
    return [{"ts": ts, "kind": kind, "job_id": job, "status": status}
            for ts, kind, job, status in base]


def brute_grouped(records, epoch, kinds=None):
    out = {}
    for rec in records:
        ts = datetime.fromisoformat(rec["ts"]).timestamp()
        if ts < epoch or (kinds and rec["kind"] not in kinds):
            continue
        key = (rec.get("job_id"), rec["kind"], rec.get("status"))
        out[key] = out.get(key, 0) + 1
    return out


class LedgerIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lc2-indexes-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_fresh_store_carries_both_indexes(self):
        ledger = Ledger(self.tmp)
        self.assertTrue(NEW_INDEXES <= index_names(ledger.path))

    def test_existing_store_picks_up_indexes_data_unchanged(self):
        db_path = os.path.join(self.tmp, "scheduler.db")
        records = seed_records()
        con = sqlite3.connect(db_path)
        con.executescript(OLD_SCHEMA)
        for rec in records:
            epoch = datetime.fromisoformat(rec["ts"]).timestamp()
            con.execute(
                "INSERT INTO events (ts, ts_epoch, kind, job_id, status,"
                " record) VALUES (?, ?, ?, ?, ?, ?)",
                (rec["ts"], epoch, rec["kind"], rec["job_id"],
                 rec["status"], canonical_line(rec)))
        con.commit()
        con.close()
        self.assertFalse(NEW_INDEXES & index_names(db_path))

        ledger = Ledger(self.tmp)  # construction applies the schema
        self.assertTrue(NEW_INDEXES <= index_names(db_path))
        self.assertEqual(ledger.read_all(), records)
        self.assertEqual(ledger.verify(),
                         {"integrity": "ok", "events": len(records),
                          "ok": True})

    def test_grouped_counts_and_stats_match_brute_force(self):
        ledger = Ledger(self.tmp)
        records = seed_records()
        for rec in records:
            ledger._insert(rec)
        epoch = datetime(2026, 11, 15, 12, 0, tzinfo=UTC).timestamp()
        self.assertEqual(ledger.counts_since_grouped(epoch),
                         brute_grouped(records, epoch))
        self.assertEqual(
            ledger.counts_since_grouped(epoch, kinds=["run"]),
            brute_grouped(records, epoch, kinds=["run"]))
        self.assertEqual(
            ledger.count_since(epoch, kinds=["run"],
                               statuses=["failure", "timeout"]), 2)
        stats = ledger.stats()
        self.assertEqual(stats["events"], len(records))
        self.assertEqual(stats["per_kind"],
                         {"run": 6, "ping_woken": 2, "ledger_pruned": 1})
        self.assertEqual(stats["oldest"], "2026-11-10T00:00:00+00:00")
        self.assertEqual(stats["newest"], "2026-11-16T11:30:00+00:00")


if __name__ == "__main__":
    unittest.main()
