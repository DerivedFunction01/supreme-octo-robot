"""land-record writer pins: a landing record prices
its phases from the gate run records it names, counts
fires and venue-minutes onto the record, and refuses
a landing whose gate runs carry no green verdict.
Run records are seeded in a temp results dir — no
live record is ever an input.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[2] / "bin" / "land-record"


def _run_record(state="complete", exit_code=0, started=None, finished=None, **extra):
    record = {
        "run_id": "r",
        "state": state,
        "exit_code": exit_code,
        "started_at": started,
        "finished_at": finished,
    }
    record.update(extra)
    return record


class LandRecord(unittest.TestCase):
    def _results(self, tmp, runs):
        results = Path(tmp) / "results"
        (results / "runs").mkdir(parents=True)
        for run_id, record in runs.items():
            (results / "runs" / f"{run_id}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
        return results

    def _invoke(self, results, *argv):
        return subprocess.run(
            [
                sys.executable,
                str(BIN),
                "--results-dir",
                str(results),
                "--now",
                "2026-11-26T17:00:00+00:00",
                *argv,
            ],
            capture_output=True,
            text=True,
        )

    def test_record_prices_phases_and_counts_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self._results(
                tmp,
                {
                    "gate-a": _run_record(
                        started="2026-11-26T16:00:00+00:00",
                        finished="2026-11-26T16:10:00+00:00",
                    ),
                    "gate-b": _run_record(
                        started="2026-11-26T16:20:00+00:00",
                        finished="2026-11-26T16:35:00+00:00",
                        constituents=[{"branch": "x"}, {"branch": "y"}],
                    ),
                },
            )
            proc = self._invoke(
                results,
                "--sha",
                "b" * 40,
                "--gate-run",
                "gate-a",
                "--gate-run",
                "gate-b",
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            written = list((results / "landings").glob("*.json"))
            self.assertEqual(1, len(written))
            record = json.loads(written[0].read_text(encoding="utf-8"))
        self.assertEqual(2, record["fires"])
        self.assertEqual(25.0, record["venue_minutes"])
        self.assertEqual(2, record["constituent_count"])
        # Formation opens at the first fire; the verdict
        # is the last green run's finish (16:35).
        self.assertEqual(35.0, record["phases_minutes"]["formation_to_gate"])
        self.assertEqual(25.0, record["phases_minutes"]["gate_to_landed"])
        self.assertEqual(60.0, record["phases_minutes"]["formation_to_landed"])

    def test_no_green_verdict_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self._results(
                tmp,
                {
                    "gate-red": _run_record(
                        exit_code=1,
                        started="2026-11-26T16:00:00+00:00",
                        finished="2026-11-26T16:10:00+00:00",
                    )
                },
            )
            proc = self._invoke(
                results, "--sha", "b" * 40, "--gate-run", "gate-red"
            )
            self.assertEqual(2, proc.returncode)
            self.assertIn("no gate run completed green", proc.stderr)
            self.assertFalse((results / "landings").exists())

    def test_missing_run_record_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self._results(tmp, {})
            proc = self._invoke(
                results, "--sha", "b" * 40, "--gate-run", "gate-ghost"
            )
            self.assertEqual(2, proc.returncode)
            self.assertIn("no run record gate-ghost", proc.stderr)


if __name__ == "__main__":
    unittest.main()
