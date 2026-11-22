"""Presence lapse pins (the hardcoded-time audit's first
finding): a declared presence window that has passed
lapses as a whole. An away/focus mode reads back as
active (the long-standing behaviour), and an "active
until T" declaration past T serves the default presence
— no stale expiry, none of the expectation the window
carried. A declaration still inside its window serves
verbatim. Fixture state only, an injected now."""

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.services.reads import labels  # noqa: E402

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
PAST = "2026-11-16T22:00:00+00:00"
FUTURE = "2026-11-22T22:00:00+00:00"


def state(mode, expires_at, expectation=""):
    return {
        "presence": {
            "mode": mode,
            "expires_at": expires_at,
            "expectation": expectation,
        }
    }


class PresenceLapseCase(unittest.TestCase):
    def test_expired_active_declaration_serves_the_default(self):
        view = labels.presence_view(state("active", PAST, "Keep things moving forward."), NOW)
        self.assertEqual(view["mode"], "active")
        self.assertIsNone(view["expires_at"])
        self.assertEqual(view["expectation"], "")

    def test_expired_away_declaration_serves_the_default(self):
        view = labels.presence_view(state("away", PAST, "Back Monday."), NOW)
        self.assertEqual(view["mode"], "active")
        self.assertIsNone(view["expires_at"])
        self.assertEqual(view["expectation"], "")

    def test_live_declaration_serves_verbatim(self):
        view = labels.presence_view(state("focus", FUTURE, "Deep work."), NOW)
        self.assertEqual(view["mode"], "focus")
        self.assertEqual(view["expires_at"], FUTURE)
        self.assertEqual(view["expectation"], "Deep work.")

    def test_unbounded_declaration_serves_verbatim(self):
        view = labels.presence_view(state("away", None, "Out."), NOW)
        self.assertEqual(view["mode"], "away")
        self.assertIsNone(view["expires_at"])
        self.assertEqual(view["expectation"], "Out.")

    def test_effective_mode_lapses_only_non_active_modes(self):
        self.assertEqual(labels.effective_mode(state("away", PAST), NOW), "active")
        self.assertEqual(labels.effective_mode(state("focus", FUTURE), NOW), "focus")
        self.assertEqual(labels.effective_mode(state("active", PAST), NOW), "active")


if __name__ == "__main__":
    unittest.main()
