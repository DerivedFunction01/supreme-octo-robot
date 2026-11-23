"""Owner-set digest windows (the hardcoded-time audit's
third finding): the window times stop being a settings
constant read in the server's frame. The owner stores
their own times (window_times) and the timezone they
are wall times in (window_tz) through set_digest_prefs;
the reads in force source the times from the prefs, and
the next-window computation interprets them in the
owner's timezone. Without prefs, the settings times
read in now's own frame, exactly as before. Fixture
state only, an injected now."""

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.domain import logic  # noqa: E402
from attention.errors import Validation  # noqa: E402
from attention.services.reads import labels  # noqa: E402
from attention.services.writes import writes  # noqa: E402
from attention.settings import Settings  # noqa: E402

SETTINGS = Settings()
NY = ZoneInfo("America/New_York")
# 12:00 UTC = 07:00 EST.
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def prefs_state(times=("08:00", "13:00", "18:30"), tz="America/New_York"):
    return {
        "digest_prefs": {
            "windows": {},
            "include": {},
            "window_times": list(times),
            "window_tz": tz,
        }
    }


class TimesInForceCase(unittest.TestCase):
    def test_owner_times_replace_settings_times(self):
        self.assertEqual(
            labels.digest_window_times(prefs_state(), SETTINGS),
            ["08:00", "13:00", "18:30"],
        )

    def test_no_prefs_reads_settings_times(self):
        self.assertEqual(
            labels.digest_window_times({}, SETTINGS), list(SETTINGS.digest_windows)
        )

    def test_enablement_applies_over_owner_times(self):
        state = prefs_state()
        state["digest_prefs"]["windows"] = {"13:00": False}
        self.assertEqual(labels.digest_windows(state, SETTINGS), ["08:00", "18:30"])

    def test_tz_resolves_and_bad_name_reads_unset(self):
        self.assertEqual(labels.digest_window_tz(prefs_state()), NY)
        self.assertIsNone(labels.digest_window_tz(prefs_state(tz="Not/AZone")))
        self.assertIsNone(labels.digest_window_tz({}))


class TzInterpretationCase(unittest.TestCase):
    def test_next_window_reads_wall_times_in_the_owner_tz(self):
        # 07:00 EST: the 08:00 New York window is next, at 13:00 UTC.
        nxt = logic.next_window(NOW, ("08:00", "13:00", "18:30"), NY)
        self.assertEqual(nxt, datetime(2026, 11, 21, 13, 0, tzinfo=UTC))

    def test_without_tz_the_frame_is_now(self):
        # The settings form: 08:00 in now's (UTC) frame is tomorrow.
        nxt = logic.next_window(NOW, ("08:00", "13:00", "18:30"))
        self.assertEqual(nxt, datetime(2026, 11, 21, 13, 0, tzinfo=UTC))

    def test_window_start_in_the_owner_tz(self):
        # 07:00 EST: today's New York windows have not started;
        # the most recent is yesterday's 18:30 EST = 23:30 UTC.
        start = logic.window_start(NOW, ("08:00", "13:00", "18:30"), NY)
        self.assertEqual(start, datetime(2026, 11, 20, 23, 30, tzinfo=UTC))


class WriteCase(unittest.TestCase):
    def test_set_times_and_tz_round_trip(self):
        state = {}
        out = writes.set_digest_prefs(
            state,
            {
                "window_times": ["18:30", "08:00", "08:00"],
                "window_tz": "America/New_York",
            },
        )
        self.assertEqual(out["window_times"], ["08:00", "18:30"])
        self.assertEqual(out["window_tz"], "America/New_York")
        self.assertEqual(state["digest_prefs"]["window_times"], ["08:00", "18:30"])

    def test_renaming_a_window_prunes_its_enablement(self):
        state = prefs_state()
        state["digest_prefs"]["windows"] = {"13:00": False, "08:00": False}
        writes.set_digest_prefs(
            state, {"window_times": ["08:00", "09:00"], "window_tz": "America/New_York"}
        )
        self.assertEqual(state["digest_prefs"]["windows"], {"08:00": False})

    def test_bad_times_and_tz_are_validation_errors(self):
        for payload in (
            {"window_times": ["25:00"], "window_tz": "America/New_York"},
            {"window_times": [], "window_tz": "America/New_York"},
            {"window_times": ["08:00"], "window_tz": "Not/AZone"},
            {"window_times": ["08:00"]},
        ):
            with self.assertRaises(Validation, msg=str(payload)):
                writes.set_digest_prefs({}, payload)


if __name__ == "__main__":
    unittest.main()
