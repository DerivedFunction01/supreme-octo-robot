"""The unlanded class: a build a programme's own
record claimed complete, measured against main's
ancestry — the claim is the checkpoint's word, the
measure is git. Pins: the claim parser (a checkpoint
line with a completion token naming a commit), the
collector's ancestry measurement against a scratch
repo, and the row (one cadence interval, landed
clears, undeclared class stays silent)."""

import subprocess
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.services.measure import (  # noqa: E402
    continuation,
    records,
    staffing_rows,
)


def at(hour, minute=0):
    return datetime(2026, 11, 22, hour, minute, tzinfo=UTC)


class ClaimedBuildsCase(unittest.TestCase):
    def test_checkpoint_completion_line_names_its_commits(self):
        text = (
            "progress-checkpoint: 2026-11-22T02:35:00Z — builds "
            "completed and transport-pushed (sf 78ec0ef, LTW "
            "4f620b07, validate-live 73c5bbbb)."
        )
        claims = records.claimed_builds(text)
        self.assertEqual(
            [c["sha"] for c in claims], ["78ec0ef", "4f620b07", "73c5bbbb"]
        )
        self.assertEqual(claims[0]["claimed_at"], records._parse_stamp("2026-11-22T02:35:00Z"))

    def test_no_completion_token_no_claim(self):
        # A gate fire is a launch, not a completion; a
        # gate verdict claims the build it gated.
        fired = "progress-checkpoint: 2026-11-22T02:35:00Z — gate fired for 78ec0ef, polling."
        flight = "progress-checkpoint: 2026-11-22T02:35:00Z — fired 78ec0ef on sunny, in flight."
        passed = "progress-checkpoint: 2026-11-22T02:35:00Z — gate PASS for 78ec0ef in both runs."
        self.assertEqual(records.claimed_builds(fired), [])
        self.assertEqual(records.claimed_builds(flight), [])
        self.assertEqual(len(records.claimed_builds(passed)), 1)

    def test_completion_word_without_checkpoint_or_commit_claims_nothing(self):
        self.assertEqual(records.claimed_builds("the build is complete"), [])
        self.assertEqual(
            records.claimed_builds(
                "progress-checkpoint: 2026-11-22T02:35:00Z — the build is complete."
            ),
            [],
        )

    def test_digit_runs_are_not_commits(self):
        text = (
            "progress-checkpoint: 2026-11-22T02:35:00Z — gate "
            "complete, 20261122 tests over 1234567 cases."
        )
        self.assertEqual(records.claimed_builds(text), [])


class AncestryCase(unittest.TestCase):
    def _repo(self, tmp):
        def git(*args):
            subprocess.run(
                ["git", "-C", str(tmp), *args],
                check=True,
                capture_output=True,
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": str(tmp),
                    "GIT_AUTHOR_NAME": "T",
                    "GIT_AUTHOR_EMAIL": "t@t",
                    "GIT_COMMITTER_NAME": "T",
                    "GIT_COMMITTER_EMAIL": "t@t",
                },
            )

        git("init", "-b", "main")
        (tmp / "a.txt").write_text("a\n")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        git("checkout", "-b", "delta")
        (tmp / "b.txt").write_text("b\n")
        git("add", "-A")
        git("commit", "-q", "-m", "delta")
        sha = subprocess.run(
            ["git", "-C", str(tmp), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        return git, sha

    def test_branch_commit_unlanded_until_merged(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            git, sha = self._repo(tmp)
            self.assertIs(records._is_landed(str(tmp), sha), False)
            git("checkout", "main")
            git("merge", "--ff-only", "delta")
            self.assertIs(records._is_landed(str(tmp), sha), True)
            self.assertIs(records._is_landed(str(tmp), "deadbeef"), None)


class UnlandedRowsCase(unittest.TestCase):
    def _state(self, claimed, landed=False):
        return {
            "unlanded_snapshot": {
                "supreme-octo-robot": {
                    "at": claimed,
                    "claims": [
                        {
                            "sha": "78ec0ef",
                            "claimed_at": claimed.isoformat(),
                            "repo": "/repo",
                            "landed": landed,
                        }
                    ],
                }
            }
        }

    def test_row_raises_after_one_interval(self):
        now = at(4, 0)
        claimed = now - timedelta(minutes=90)
        rows = staffing_rows._unlanded_rows(self._state(claimed), now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "unlanded_build")
        self.assertEqual(rows[0]["sha"], "78ec0ef")
        self.assertEqual(rows[0]["idle_minutes"], 90)
        self.assertIn("built, unlanded", rows[0]["detail"])

    def test_row_waits_one_cadence_interval(self):
        now = at(4, 0)
        claimed = now - timedelta(minutes=10)
        self.assertEqual(staffing_rows._unlanded_rows(self._state(claimed), now), [])

    def test_landed_and_unmeasured_claims_raise_nothing(self):
        now = at(4, 0)
        claimed = now - timedelta(minutes=90)
        self.assertEqual(
            staffing_rows._unlanded_rows(self._state(claimed, landed=True), now), []
        )
        self.assertEqual(
            staffing_rows._unlanded_rows(self._state(claimed, landed=None), now), []
        )

    def test_actuation_maps_to_the_unlanded_class(self):
        self.assertEqual(continuation.SWEEP_CLASSES["unlanded_build"], ("unlanded",))
        self.assertIn("land the build", continuation._SWEEP_NEXT_ACT["unlanded_build"])


if __name__ == "__main__":
    unittest.main()
