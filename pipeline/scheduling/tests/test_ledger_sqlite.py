import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from dispatch.ledger import Ledger, canonical_line

UTC = timezone.utc


class LedgerSqliteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ledger = Ledger(self.tmp)

    def test_record_read_all_round_trip(self):
        self.ledger.record("run", job_id="job-a", status="ok", exit_code=0)
        self.ledger.record("ping_created", job_id="job-a", ping_id="p1")
        recs = self.ledger.read_all()
        self.assertEqual([r["kind"] for r in recs], ["run", "ping_created"])
        self.assertEqual(recs[0]["exit_code"], 0)
        self.assertIn("ts", recs[0])

    def test_query_filters_and_order(self):
        for i in range(3):
            self.ledger.record("run", job_id="job-a", status="ok")
        self.ledger.record("run", job_id="job-b", status="failure")
        newest = self.ledger.query(limit=2)
        self.assertEqual(len(newest), 2)
        self.assertEqual(newest[0]["job_id"], "job-b")  # newest first
        only_a = self.ledger.query(job_id="job-a", kinds=["run"])
        self.assertEqual(len(only_a), 3)

    def test_prune_drops_old_keeps_unparseable(self):
        old = datetime.now(UTC) - timedelta(days=200)
        self.ledger._insert({"ts": old.isoformat(), "kind": "run",
                             "job_id": "job-a", "status": "ok"})
        self.ledger._insert({"ts": "not-a-date", "kind": "run",
                             "job_id": "job-a", "status": "ok"})
        self.ledger.record("run", job_id="job-a", status="ok")
        dropped = self.ledger.prune(90)
        self.assertEqual(dropped, 1)
        remaining = self.ledger.read_all()
        self.assertEqual(len(remaining), 2)  # unparseable kept, fresh kept

    def test_export_hash_matches_canonical_source(self):
        source = os.path.join(self.tmp, "source.jsonl")
        recs = [{"ts": "2026-10-31T00:00:00+00:00", "kind": "run",
                 "job_id": "job-a", "status": "ok"},
                {"ts": "2026-10-31T01:00:00+00:00", "kind": "run",
                 "job_id": "job-a", "status": "failure", "exit_code": 3}]
        with open(source, "w", encoding="utf-8") as fh:
            for rec in recs:
                fh.write(json.dumps(rec) + "\n")  # NOT canonical order
        other = Ledger(os.path.join(self.tmp, "fresh"))
        imported, source_hash = other.import_jsonl(source)
        self.assertEqual(imported, 2)
        canonical = "".join(canonical_line(r) + "\n" for r in recs).encode()
        self.assertEqual(source_hash, hashlib.sha256(canonical).hexdigest())
        out = other.export_to(os.path.join(self.tmp, "out.jsonl"))
        self.assertEqual(out["rows"], 2)
        self.assertEqual(out["sha256"], source_hash)
        one = other.export_to(os.path.join(self.tmp, "one.jsonl"),
                              job_id="job-b")
        self.assertEqual(one["rows"], 0)

    def test_import_refuses_non_empty(self):
        self.ledger.record("run", job_id="job-a", status="ok")
        source = os.path.join(self.tmp, "s.jsonl")
        with open(source, "w", encoding="utf-8") as fh:
            fh.write('{"ts": "2026-01-01T00:00:00+00:00", "kind": "run"}\n')
        with self.assertRaises(ValueError):
            self.ledger.import_jsonl(source)

    def test_verify_and_stats(self):
        self.ledger.record("run", job_id="job-a", status="ok")
        result = self.ledger.verify()
        self.assertTrue(result["ok"])
        stats = self.ledger.stats()
        self.assertEqual(stats["events"], 1)
        self.assertEqual(stats["per_job"], {"job-a": 1})
        self.assertGreater(stats["db_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
