"""Retire the status-code transport (supervision plan,
Step 5): a thread that posts nothing still measures
correctly from records alone — armed entries,
checkpoint stamps, blocked todos, the goal store, run
records, and worktree presence. No handler_status is
seeded anywhere in this file; the transport itself is
asserted gone at the end."""

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention import cli as cli_mod  # noqa: E402
from attention import client  # noqa: E402
from attention.services.measure import continuation, staffing  # noqa: E402
from attention.services.writes import ingest  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 19, 18, 0, tzinfo=UTC)

PROGRAMME = {
    "slug": "edgar-specimen",
    "label": "Specimen — field extractor",
    "handles": ["@specimen-field"],
    "cadence_minutes": 15,
    "wb_projects": ["specimen-repo"],
    "retired": False,
}


def _armed(todo, minutes_ago=5, status="doing"):
    return {
        "project": "specimen-repo",
        "todo": todo,
        "row": {
            "project": "specimen-repo",
            "programme": "specimen-repo",
            "handle": todo,
            "todo": todo,
            "bundle": "2026-11-17-greenfield-continuous-improvement",
            "status": status,
            "armed_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
            "cadence_minutes": 15,
        },
        "ingested_at": NOW - timedelta(minutes=minutes_ago),
    }


def _state(now=NOW, armed=(), **overrides):
    state = {
        "handlers": [],
        "handler_status": {},
        "items": [],
        "sends": [],
        "dispatch_failures": [],
        "verifications": [],
        "programmes": [dict(PROGRAMME)],
        "armed_rows": list(armed),
        "capacity_error": None,
        "capacity_snapshot": {
            "at": now,
            "sessions": [{"session": "oak-reef-65"}, {"session": "sunny-ridge-19"}],
            "session_runs": {"oak-reef-65": 1, "sunny-ridge-19": 0},
            "idle_since": {"sunny-ridge-19": now - timedelta(minutes=30)},
            "specs": [],
        },
        "stamp_snapshot": {},
        "blocked_snapshot": {},
        "goal_snapshot": {},
        "worktree_snapshot": {},
        "record_snapshot": {},
    }
    state.update(overrides)
    return state


def _runs(tmp, records):
    root = Path(tmp) / "records"
    root.mkdir()
    for i, record in enumerate(records):
        stamp = (NOW - timedelta(minutes=record.pop("_age_minutes", 10))).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        (root / f"{stamp}-{i}.json").write_text(
            json.dumps(record), encoding="utf-8"
        )
    return root


def _settings(tmp, **overrides):
    values = {"run_records_dir": Path(tmp) / "records"}
    values.update(overrides)
    return Settings(**values)


def _kinds(view):
    return [r["kind"] for r in view["rows"]]


class NonPostingThreadTests(unittest.TestCase):
    def test_understaffed_from_armed_entries_and_runs(self):
        # One child worker on one of two live sessions,
        # armed and checkpointing — no post anywhere.
        with tempfile.TemporaryDirectory() as tmp:
            _runs(
                tmp,
                [
                    {
                        "id": "run-1",
                        "caller": "edgar-specimen",
                        "session": "oak-reef-65",
                        "state": "running",
                        "started_at": (NOW - timedelta(minutes=10)).isoformat(),
                        "finished_at": None,
                    }
                ],
            )
            state = _state(
                armed=[_armed("ci-corefin-coci-build")],
                stamp_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "stamps": {"ci-corefin-coci-build": NOW.isoformat()},
                    }
                },
            )
            view = staffing.build_staffing(state, _settings(tmp), NOW)
            rows = [r for r in view["rows"] if r["kind"] == "understaffed"]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["topic"], "edgar-specimen")
            self.assertEqual(row["workers"], 1)
            self.assertEqual(row["sessions_used"], 1)
            self.assertEqual(row["sessions_live"], 2)

    def test_record_gap_from_checkpoint_not_post(self):
        # Work is moving (a finished run 10m ago) but the
        # newest checkpoint is 60m old: a record gap.
        with tempfile.TemporaryDirectory() as tmp:
            _runs(
                tmp,
                [
                    {
                        "id": "run-1",
                        "caller": "edgar-specimen",
                        "session": "oak-reef-65",
                        "state": "finished",
                        "started_at": (NOW - timedelta(minutes=20)).isoformat(),
                        "finished_at": (NOW - timedelta(minutes=10)).isoformat(),
                    }
                ],
            )
            state = _state(
                armed=[_armed("ci-corefin-coci-build")],
                stamp_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "stamps": {
                            "ci-corefin-coci-build": (
                                NOW - timedelta(minutes=60)
                            ).isoformat()
                        },
                    }
                },
            )
            view = staffing.build_staffing(
                state, _settings(tmp, stall_after_hours=0.5), NOW
            )
            rows = [r for r in view["rows"] if r["kind"] == "record_gap"]
            self.assertEqual(len(rows), 1)
            self.assertIn("newest checkpoint is 60 minutes old", rows[0]["detail"])
            self.assertEqual(rows[0]["checkpoint_gap_minutes"], 60)

    def test_record_gap_falls_back_to_arming_time(self):
        # No checkpoint yet: the record's age is the
        # arming time, read from the armed row — not a
        # zero stamp that would read as infinitely stale.
        with tempfile.TemporaryDirectory() as tmp:
            _runs(
                tmp,
                [
                    {
                        "id": "run-1",
                        "caller": "edgar-specimen",
                        "session": "oak-reef-65",
                        "state": "finished",
                        "started_at": (NOW - timedelta(minutes=20)).isoformat(),
                        "finished_at": (NOW - timedelta(minutes=10)).isoformat(),
                    }
                ],
            )
            state = _state(armed=[_armed("ci-corefin-coci-build", minutes_ago=60)])
            view = staffing.build_staffing(
                state, _settings(tmp, stall_after_hours=0.5), NOW
            )
            rows = [r for r in view["rows"] if r["kind"] == "record_gap"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["checkpoint_gap_minutes"], 60)

    def test_armed_with_no_checkpoint_is_unreported(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "records").mkdir()
            state = _state(armed=[_armed("ci-corefin-coci-build", minutes_ago=60)])
            view = staffing.build_staffing(state, _settings(tmp), NOW)
            rows = [r for r in view["rows"] if r["kind"] == "armed_unreported"]
            self.assertEqual(len(rows), 1)
            self.assertIn("no checkpoint", rows[0]["detail"])

    def test_phantom_from_blocked_todo_body(self):
        # An uncited owner-order claim in a blocked todo's
        # body is a phantom stop, priced from the body's
        # latest checkpoint.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "records").mkdir()
            state = _state(
                blocked_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "blocked": [
                            {
                                "todo": "ci-corefin-coci-build",
                                "project": "specimen-repo",
                                "title": "Build",
                                "body": (
                                    "progress-checkpoint: "
                                    "2026-11-19T16:30:00Z — working\n"
                                    "The owner said stop the draw until "
                                    "he reviews it."
                                ),
                                "checkpoint_at": "2026-11-19T16:30:00+00:00",
                            }
                        ],
                    }
                },
            )
            view = staffing.build_staffing(state, _settings(tmp), NOW)
            rows = [r for r in view["rows"] if r["kind"] == "phantom_stop"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["idle_minutes"], 90)
            self.assertEqual(rows[0]["escalation"], "main")

    def test_blocked_cited_but_unverified(self):
        # A cited basis main has not stamped past one
        # check cycle is a blocked row.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "records").mkdir()
            state = _state(
                blocked_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "blocked": [
                            {
                                "todo": "ci-corefin-coci-build",
                                "project": "specimen-repo",
                                "title": "Build",
                                "body": (
                                    "Blocked on the owner's call — thread "
                                    "main-chat 2026-11-19T16:30:00Z, "
                                    "waiting on his go."
                                ),
                                "checkpoint_at": "2026-11-19T16:30:00+00:00",
                            }
                        ],
                    }
                },
            )
            view = staffing.build_staffing(state, _settings(tmp), NOW)
            self.assertEqual(
                [r["kind"] for r in view["rows"] if "blocked" in r["kind"]],
                ["blocked_unverified"],
            )

    def test_blocked_with_no_basis(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "records").mkdir()
            state = _state(
                blocked_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "blocked": [
                            {
                                "todo": "ci-corefin-coci-build",
                                "project": "specimen-repo",
                                "title": "Build",
                                "body": "",
                                "checkpoint_at": None,
                            }
                        ],
                    }
                },
            )
            view = staffing.build_staffing(state, _settings(tmp), NOW)
            self.assertEqual(
                [r["kind"] for r in view["rows"] if "blocked" in r["kind"]],
                ["blocked_uncited"],
            )

    def test_owner_waiting_from_goal_store(self):
        # A goal-store declaration, two hours old, no
        # lane record since, no workers measured.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "records").mkdir()
            state = _state(
                goal_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "owner_waiting": [
                            {
                                "goal": "edgar-specimen",
                                "label": "Greenfield verdict",
                                "commissioned_at": (
                                    NOW - timedelta(hours=2)
                                ).isoformat(),
                                "declared_at": (
                                    NOW - timedelta(hours=2)
                                ).isoformat(),
                            }
                        ],
                    }
                },
            )
            view = staffing.build_staffing(state, _settings(tmp), NOW)
            rows = [r for r in view["rows"] if r["kind"] == "owner_waiting"]
            self.assertEqual(len(rows), 1)
            self.assertIn("waited 120 minutes", rows[0]["detail"])
            self.assertEqual(rows[0]["escalation"], "main")

    def test_worktree_done_reads_from_records(self):
        # Work done in the workbench, trees unlanded: the
        # claim is reported against the tree, not taken.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "records").mkdir()
            state = _state(
                worktree_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "trees": [
                            {
                                "name": "form/x",
                                "tip": "abc",
                                "dirty": False,
                                "landed": False,
                            }
                        ],
                    }
                },
            )
            view = staffing.build_staffing(
                state,
                _settings(tmp),
                NOW,
                wb_topics={
                    "edgar-specimen": {
                        "todos_total": 2,
                        "todos_done": 2,
                        "plan_modified": None,
                    }
                },
            )
            self.assertIn("unlanded_claim", _kinds(view))

    def test_worktree_standing_unarmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "records").mkdir()
            state = _state(
                worktree_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "trees": [
                            {
                                "name": "form/x",
                                "tip": "abc",
                                "dirty": False,
                                "landed": False,
                            }
                        ],
                    }
                },
            )
            view = staffing.build_staffing(state, _settings(tmp), NOW)
            self.assertIn("unarmed_work", _kinds(view))


class ContinuationFromRecordsTests(unittest.TestCase):
    def test_complete_reads_armed_and_trees(self):
        programme = dict(PROGRAMME)
        state = _state()
        self.assertTrue(continuation._is_complete(state, programme))
        state = _state(armed=[_armed("ci-corefin-coci-build")])
        self.assertFalse(continuation._is_complete(state, programme))
        state = _state(
            worktree_snapshot={
                "edgar-specimen": {
                    "at": NOW,
                    "trees": [{"name": "form/x", "landed": False}],
                }
            },
        )
        self.assertFalse(continuation._is_complete(state, programme))

    def test_signature_moves_on_stamp_not_post(self):
        programme = dict(PROGRAMME)
        before = continuation._signature(_state(), programme)
        after = continuation._signature(
            _state(
                armed=[_armed("ci-corefin-coci-build")],
                stamp_snapshot={
                    "edgar-specimen": {
                        "at": NOW,
                        "stamps": {"ci-corefin-coci-build": NOW.isoformat()},
                    }
                },
            ),
            programme,
        )
        self.assertNotEqual(before, after)


class TransportGoneTests(unittest.TestCase):
    def test_no_post_status_anywhere(self):
        self.assertFalse(hasattr(ingest, "post_status"))
        self.assertFalse(hasattr(client, "post_status"))
        with self.assertRaises(SystemExit):
            cli_mod.build_parser().parse_args(
                ["post", "status", "--code", "DONE", "--summary", "Done"]
            )


if __name__ == "__main__":
    unittest.main()
