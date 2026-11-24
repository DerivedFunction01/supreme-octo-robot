import unittest
from datetime import datetime, timedelta, timezone

from server.firing import schedule

UTC = timezone.utc
NY = "America/New_York"


def z(year, month, day, hh=0, mm=0):
    return datetime(year, month, day, hh, mm, tzinfo=UTC)


class ScheduleTests(unittest.TestCase):
    def test_parse_every(self):
        self.assertEqual(schedule.parse_every("5m"), timedelta(minutes=5))
        self.assertEqual(schedule.parse_every("168h"), timedelta(hours=168))
        with self.assertRaises(ValueError):
            schedule.parse_every("5d")

    def test_interval_advance_collapses(self):
        cad = {"type": "interval", "every": "5m"}
        latest, collapsed, new_due = schedule.advance(cad, NY, z(2026, 10, 31, 12, 0), z(2026, 10, 31, 12, 26))
        self.assertEqual(collapsed, 6)  # 12:00, 05, 10, 15, 20, 25
        self.assertEqual(latest, z(2026, 10, 31, 12, 25))
        self.assertEqual(new_due, z(2026, 10, 31, 12, 30))

    def test_daily_next_point(self):
        cad = {"type": "daily", "at": "06:00"}
        # After 07:00 EDT on Oct 31, the next 06:00 is Nov 1 EST = 11:00Z.
        point = schedule.first_point_after(cad, NY, z(2026, 10, 31, 11, 0))
        self.assertEqual(point, z(2026, 11, 1, 11, 0))

    def test_ec2_spring_forward_gap(self):
        cad = {"type": "daily", "at": "02:30"}
        # On the spring-forward date, 02:30 does not exist in
        # New York; it fires at the first valid instant after
        # the gap, 03:00 EDT = 07:00Z.
        point = schedule.first_point_at_or_after(cad, NY, z(2026, 3, 8, 0, 0))
        self.assertEqual(point, z(2026, 3, 8, 7, 0))

    def test_ec3_fall_back_repeated_hour_fires_once(self):
        cad = {"type": "daily", "at": "01:30"}
        # On the fall-back date, 01:30 happens twice; the grid
        # yields the first occurrence, 01:30 EDT = 05:30Z,
        # exactly once.
        point = schedule.first_point_at_or_after(cad, NY, z(2026, 11, 1, 0, 0))
        self.assertEqual(point, z(2026, 11, 1, 5, 30))
        latest, collapsed, new_due = schedule.advance(cad, NY, point, z(2026, 11, 1, 8, 0))
        self.assertEqual(collapsed, 1)
        self.assertEqual(latest, point)
        self.assertEqual(new_due, z(2026, 11, 2, 6, 30))  # Nov 2 01:30 EST

    def test_weekly_point(self):
        cad = {"type": "weekly", "dow": ["Wed"], "at": "19:00"}
        # From the Friday specimen at 12:00Z, next is Wed 19:00 EST.
        point = schedule.first_point_after(cad, NY, z(2026, 10, 30, 12, 0))
        self.assertEqual(point, z(2026, 11, 5, 0, 0))


if __name__ == "__main__":
    unittest.main()
