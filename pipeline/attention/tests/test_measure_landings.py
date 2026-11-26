"""Landing-record aggregates (wall-clock plan, step
5): the measure's `landings` section — gates-per-
landing and phase wall clock — read from landing
records the tests seed themselves in a temp dir.
No live record is ever an input.
"""

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.services.measure import landings  # noqa: E402

NOW = datetime(2026, 11, 26, 17, 0, tzinfo=UTC)


def _record(landed_at, fires, venue_minutes, constituents, phases):
    return {
        "landed_sha": "a" * 40,
        "change": "seeded",
        "landed_at": landed_at.isoformat(),
        "formation_opened_at": landed_at.isoformat(),
        "gate_green_at": landed_at.isoformat(),
        "gate_runs": ["r"] * fires,
        "fires": fires,
        "venue_minutes": venue_minutes,
        "constituent_count": constituents,
        "phases_minutes": phases,
    }


class Summarize(unittest.TestCase):
    def _seed(self, tmp, records):
        home = Path(tmp)
        for i, record in enumerate(records):
            (home / f"landing-{i}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
        return home

    def test_aggregates_over_the_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self._seed(
                tmp,
                [
                    _record(
                        NOW - timedelta(hours=1),
                        2,
                        20.0,
                        1,
                        {
                            "formation_to_gate": 30.0,
                            "gate_to_landed": 5.0,
                            "formation_to_landed": 35.0,
                        },
                    ),
                    _record(
                        NOW - timedelta(hours=2),
                        1,
                        10.0,
                        2,
                        {
                            "formation_to_gate": 10.0,
                            "gate_to_landed": 15.0,
                            "formation_to_landed": 25.0,
                        },
                    ),
                    # Outside the 7-day window: excluded.
                    _record(
                        NOW - timedelta(days=9),
                        9,
                        99.0,
                        9,
                        {
                            "formation_to_gate": 99.0,
                            "gate_to_landed": 99.0,
                            "formation_to_landed": 99.0,
                        },
                    ),
                ],
            )
            summary = landings.summarize(home, NOW)
        self.assertEqual(2, summary["landings"])
        self.assertEqual(1.5, summary["fires_per_landing"])
        self.assertEqual(15.0, summary["venue_minutes_per_landing"])
        self.assertEqual(1.5, summary["constituents_per_landing"])
        self.assertEqual(
            20.0, summary["phase_median_minutes"]["formation_to_gate"]
        )
        self.assertEqual(
            10.0, summary["phase_median_minutes"]["gate_to_landed"]
        )
        self.assertEqual(
            30.0, summary["phase_median_minutes"]["formation_to_landed"]
        )

    def test_no_records_is_honest_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = landings.summarize(Path(tmp), NOW)
        self.assertEqual(0, summary["landings"])
        self.assertIsNone(summary["fires_per_landing"])
        self.assertIsNone(summary["venue_minutes_per_landing"])
        self.assertIsNone(
            summary["phase_median_minutes"]["formation_to_gate"]
        )

    def test_missing_dir_is_honest_absence(self):
        summary = landings.summarize(Path("/nonexistent-landings"), NOW)
        self.assertEqual(0, summary["landings"])


if __name__ == "__main__":
    unittest.main()
