"""Unit tests for the `sched flap` state read (bin/sched).

The pure line/exit-code logic is tested with fixed clocks; the
live state file is never read here.
"""
import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_loader(
    "sched_cli", SourceFileLoader("sched_cli", os.path.join(ROOT, "bin", "sched"))
)
sched = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sched)

NOW = datetime(2026, 11, 8, 18, 0, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def state(verdict, age_secs, mechanisms=None):
    return {
        "verdict": verdict,
        "since": iso(NOW - timedelta(seconds=age_secs + 60)),
        "last_sample_at": iso(NOW - timedelta(seconds=age_secs)),
        "mechanisms": mechanisms or {},
    }


class FlapLineTests(unittest.TestCase):
    def test_no_state_is_unknown(self):
        line, code = sched.flap_line(None, NOW, 360)
        self.assertIn("unknown", line)
        self.assertEqual(code, 4)

    def test_fresh_down_exits_zero(self):
        line, code = sched.flap_line(state("down", 60), NOW, 360)
        self.assertIn("flap: down", line)
        self.assertNotIn("STALE", line)
        self.assertEqual(code, 0)

    def test_fresh_up_exits_three_and_names_denied(self):
        mechanisms = {
            "python_write_new": {"status": "denied", "detail": ""},
            "sqlite_row_write": {"status": "denied", "detail": ""},
            "unlink": {"status": "ok", "detail": ""},
        }
        line, code = sched.flap_line(state("up", 30, mechanisms), NOW, 360)
        self.assertEqual(code, 3)
        self.assertIn("python_write_new", line)
        self.assertIn("sqlite_row_write", line)
        self.assertNotIn("unlink", line.split("denied:")[1])

    def test_stale_down_reads_as_unknown_not_down(self):
        line, code = sched.flap_line(state("down", 720), NOW, 360)
        self.assertIn("STALE", line)
        self.assertEqual(code, 4)

    def test_inconclusive_exits_four_even_when_fresh(self):
        _line, code = sched.flap_line(state("inconclusive", 30), NOW, 360)
        self.assertEqual(code, 4)

    def test_unreadable_sample_time_is_unknown(self):
        bad = {"verdict": "down", "since": "x", "last_sample_at": "not-a-time"}
        line, code = sched.flap_line(bad, NOW, 360)
        self.assertIn("unreadable", line)
        self.assertEqual(code, 4)


if __name__ == "__main__":
    unittest.main()
