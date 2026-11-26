"""Lane records (lane-records plan, Steps 1 and 3):
the lane declaration as a record in the existing
record form — declare, ping, renew, terminate on
evidence only — and the staffing measure reading
lane records as its primary source, reconciled
against the contract's staffable queue and
cross-checked against venue run records and
worktree activity.

The specimens are the plan's Step 5 backend list:
full staffing clears the row; one lane short, the
commission names the unstaffed item; an
authoring-side (venue=none) lane counts toward
expected and actual; a stale record is flagged and
not counted as actual; an overrun unrenewed lane
escalates; termination by silence does not close a
lane; a lane in gap-wait with a live ping counts
as actual.
"""

import copy
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.infra import sample_data  # noqa: E402
from attention.services.measure import lanes, registry  # noqa: E402
from attention.services.measure import staffing_venue  # noqa: E402
from attention.services.reads import digest as digest_mod  # noqa: E402
from attention.settings import Settings  # noqa: E402

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
CALM = "calm-lake-11-r1"
SCARLET = "scarlet-ridge-9-r1"


def iso(stamp: datetime) -> str:
    return stamp.isoformat()


def block(lane: str, **fields) -> str:
    lines = ["<!-- lane-record"]
    lines.append(f"lane: {lane}")
    for field, value in fields.items():
        lines.append(f"{field}: {value}")
    lines.append("-->")
    return "\n".join(lines) + "\n"


def programme(slug: str, locations: list) -> dict:
    return {
        "slug": slug,
        "label": f"Programme {slug}",
        "handles": ["@x"],
        "cadence_minutes": 15,
        "record_locations": locations,
        "worktree_roots": [],
        "retired": False,
    }


def write_record(path: Path, text: str, mtime: datetime) -> None:
    path.write_text(text, encoding="utf-8")
    stamp = mtime.timestamp()
    os.utime(path, (stamp, stamp))


class SeedDeclaration(unittest.TestCase):
    def test_edgar_seed_carries_the_declaration(self):
        count, entries = registry.lane_declarations_for("edgar-greenfield")
        self.assertEqual(count, 11)
        self.assertEqual(len(entries), 11)
        self.assertEqual(len({e["key"] for e in entries}), 11)
        for entry in entries:
            # The venue field is always present.
            self.assertTrue(entry["venue"], entry["key"])
            self.assertTrue(entry["termination_condition"], entry["key"])
        # The current declaration states no per-lane
        # estimates: every entry's estimate is unstated.
        unstated = {
            e["key"] for e in entries if e["estimate_minutes"] is None
        }
        self.assertEqual(unstated, {e["key"] for e in entries})


class RecordGrammar(unittest.TestCase):
    def test_blocks_header_and_checkpoint_attribution(self):
        text = (
            "<!-- lane-declaration: expected_count=2 -->\n\n"
            + block(
                "lane-a",
                label="Lane A",
                venue="storm-mosaic-17",
                state="running",
                declared_at=iso(NOW - timedelta(minutes=30)),
                estimate_minutes=120,
                termination_condition="Register delivered",
            )
            + f"\nprogress-checkpoint: {iso(NOW - timedelta(minutes=5))}\n"
            + block(
                "lane-b",
                label="Lane B",
                venue="none",
                declared_at=iso(NOW - timedelta(minutes=30)),
                estimate_minutes=60,
                termination_condition="Plan adopted",
            )
        )
        declared, blocks, refused = lanes.parse_record_text(text)
        self.assertEqual(declared, 2)
        self.assertEqual(refused, [])
        self.assertEqual([b["lane"] for b in blocks], ["lane-a", "lane-b"])
        self.assertEqual(len(blocks[0]["_checkpoints"]), 1)
        self.assertEqual(blocks[1]["_checkpoints"], [])

    def test_block_without_venue_is_refused(self):
        text = block("lane-x", label="Lane X", state="running")
        declared, blocks, refused = lanes.parse_record_text(text)
        self.assertEqual(blocks, [])
        self.assertEqual(len(refused), 1)
        self.assertIn("lane-x", refused[0])
        self.assertIn("venue", refused[0])

    def test_renewal_merge_keeps_the_first_declaration(self):
        first = block(
            "lane-a",
            venue="storm-mosaic-17",
            declared_at=iso(NOW - timedelta(minutes=180)),
            estimate_minutes=60,
            termination_condition="Register delivered",
        )
        renewal = block(
            "lane-a",
            venue="storm-mosaic-17",
            declared_at=iso(NOW - timedelta(minutes=180)),
            renewed_at=iso(NOW - timedelta(minutes=50)),
            estimate_minutes=90,
            renewals=1,
            termination_condition="Register delivered",
        )
        _d, blocks, _r = lanes.parse_record_text(first + renewal)
        merged = lanes._merge_blocks(blocks)
        self.assertEqual(merged["declared_at"], iso(NOW - timedelta(minutes=180)))
        self.assertEqual(merged["estimate_minutes"], "90")
        self.assertEqual(merged["renewals"], 1)


class CollectorLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def collect(self, files: dict, now=NOW) -> dict:
        locations = []
        for name, (text, mtime) in files.items():
            path = self.root / name
            write_record(path, text, mtime)
            locations.append(str(path))
        state = {"programmes": [programme("prog-x", locations)]}
        lanes.collect(state, now)
        return state

    def lane(self, state, key):
        entry = state["lane_snapshot"]["prog-x"]
        return [lane for lane in entry["lanes"] if lane["key"] == key][0]

    def rows(self, state, kind, key=None):
        found = [
            r for r in lanes._lane_rows(state, NOW) if r["kind"] == kind
        ]
        if key is not None:
            found = [r for r in found if r["extra"].get("lane") == key]
        return found

    def test_stale_record_flagged_and_not_counted(self):
        fresh = block(
            "lane-a",
            venue="storm-mosaic-17",
            state="running",
            declared_at=iso(NOW - timedelta(minutes=30)),
            estimate_minutes=240,
            termination_condition="Register delivered",
        ) + f"progress-checkpoint: {iso(NOW - timedelta(minutes=5))}\n"
        stale = block(
            "lane-b",
            venue="storm-mosaic-17",
            state="running",
            declared_at=iso(NOW - timedelta(minutes=30)),
            estimate_minutes=240,
            termination_condition="Register delivered",
        )
        state = self.collect(
            {
                "a.md": (fresh, NOW),
                "b.md": (stale, NOW - timedelta(minutes=40)),
            }
        )
        self.assertFalse(self.lane(state, "lane-a")["stale"])
        self.assertTrue(self.lane(state, "lane-b")["stale"])
        facts = lanes.record_facts(state, "prog-x")
        self.assertEqual(facts["actual"], 1)
        self.assertEqual(len(self.rows(state, "lane_stale", "lane-b")), 1)
        self.assertEqual(self.rows(state, "lane_stale", "lane-a"), [])

    def test_authoring_side_lane_counts(self):
        text = block(
            "lane-plan",
            venue="none",
            state="running",
            declared_at=iso(NOW - timedelta(minutes=20)),
            estimate_minutes=120,
            termination_condition="Plan adopted",
        ) + f"progress-checkpoint: {iso(NOW - timedelta(minutes=2))}\n"
        state = self.collect({"plan.md": (text, NOW)})
        facts = lanes.record_facts(state, "prog-x")
        self.assertEqual(facts["actual"], 1)
        self.assertEqual(self.rows(state, "lane_unposted"), [])
        self.assertEqual(self.rows(state, "lane_unwitnessed"), [])

    def test_overrun_unrenewed_escalates_and_stays_open(self):
        silent = block(
            "lane-c",
            venue="storm-mosaic-17",
            state="running",
            declared_at=iso(NOW - timedelta(hours=3)),
            estimate_minutes=60,
            termination_condition="Register delivered",
        )
        state = self.collect({"c.md": (silent, NOW - timedelta(minutes=40))})
        lane = self.lane(state, "lane-c")
        self.assertTrue(lane["overrun"])
        self.assertFalse(lane["terminated"])
        escalated = self.rows(state, "lane_escalated", "lane-c")
        self.assertEqual(len(escalated), 1)
        self.assertEqual(escalated[0]["escalation"], "main")
        self.assertEqual(lanes.record_facts(state, "prog-x")["actual"], 0)

    def test_overrun_still_pinging_is_overrun_not_escalated(self):
        text = block(
            "lane-d",
            venue="storm-mosaic-17",
            state="running",
            declared_at=iso(NOW - timedelta(hours=3)),
            estimate_minutes=60,
            termination_condition="Register delivered",
        ) + f"progress-checkpoint: {iso(NOW - timedelta(minutes=3))}\n"
        state = self.collect({"d.md": (text, NOW)})
        self.assertEqual(len(self.rows(state, "lane_overrun", "lane-d")), 1)
        self.assertEqual(self.rows(state, "lane_escalated", "lane-d"), [])
        self.assertEqual(lanes.record_facts(state, "prog-x")["actual"], 1)

    def test_termination_by_silence_does_not_close(self):
        # No termination block at all: the lane simply
        # goes quiet past its estimate. Silence is not
        # a termination condition.
        text = block(
            "lane-e",
            venue="storm-mosaic-17",
            state="running",
            declared_at=iso(NOW - timedelta(hours=5)),
            estimate_minutes=60,
            termination_condition="Register delivered",
        )
        state = self.collect({"e.md": (text, NOW - timedelta(hours=2))})
        self.assertFalse(self.lane(state, "lane-e")["terminated"])
        self.assertEqual(len(self.rows(state, "lane_escalated", "lane-e")), 1)

    def test_termination_requires_checkable_evidence(self):
        delivered = str(self.root / "register-lane-f.md")
        (self.root / "register-lane-f.md").write_text("verdict", encoding="utf-8")
        base = dict(
            venue="storm-mosaic-17",
            declared_at=iso(NOW - timedelta(hours=3)),
            estimate_minutes=60,
            termination_condition="Register delivered",
        )
        proven = block("lane-f", state="running", **base) + block(
            "lane-f",
            state="terminated",
            termination_evidence=f"Register delivered at {delivered}",
            **base,
        )
        unproven = block("lane-g", state="running", **base) + block(
            "lane-g",
            state="terminated",
            termination_evidence="Register delivered at /nonexistent/register.md",
            **base,
        )
        state = self.collect(
            {"f.md": (proven, NOW), "g.md": (unproven, NOW)}
        )
        self.assertTrue(self.lane(state, "lane-f")["terminated"])
        self.assertFalse(self.lane(state, "lane-g")["terminated"])
        self.assertEqual(lanes.record_facts(state, "prog-x")["actual"], 1)

    def test_gap_wait_with_live_ping_counts(self):
        text = block(
            "lane-h",
            venue="storm-mosaic-17",
            state="gap-wait",
            gap_waits_on="packet plant on storm-mosaic-17",
            declared_at=iso(NOW - timedelta(minutes=45)),
            estimate_minutes=240,
            termination_condition="Hand-back at a named SHA",
        ) + f"progress-checkpoint: {iso(NOW - timedelta(minutes=4))}\n"
        state = self.collect({"h.md": (text, NOW)})
        self.assertEqual(lanes.record_facts(state, "prog-x")["actual"], 1)
        self.assertEqual(self.rows(state, "lane_unwitnessed", "lane-h"), [])
        self.assertEqual(self.rows(state, "lane_stale", "lane-h"), [])

    def test_record_block_supersedes_the_seed(self):
        text = block(
            "restructuring",
            venue="storm-mosaic-17",
            state="running",
            declared_at=iso(NOW - timedelta(minutes=30)),
            estimate_minutes=60,
            termination_condition="Register delivered",
        ) + f"progress-checkpoint: {iso(NOW - timedelta(minutes=1))}\n"
        path = self.root / "ci.md"
        write_record(path, text, NOW)
        state = {
            "programmes": [
                programme("edgar-greenfield", [str(path)])
            ]
        }
        lanes.collect(state, NOW)
        entry = state["lane_snapshot"]["edgar-greenfield"]
        self.assertEqual(entry["declared"], 11)
        lane = [
            lane for lane in entry["lanes"]
            if lane["key"] == "restructuring"
        ][0]
        self.assertEqual(lane["source"], "record")
        self.assertEqual(lane["state"], "running")
        self.assertFalse(lane["stale"])


def queue_state(families: dict) -> tuple:
    """A synthetic venue snapshot for the edgar
    programme, in the served shape (the venue
    measure specimens' form)."""
    state = {
        "armed_rows": [
            {
                "project": "edgar-sec",
                "todo": "ci-corefin-coci-build",
                "row": {"project": "edgar-sec", "programme": "edgar-sec"},
            }
        ],
        "venue_snapshot": {
            "edgar-greenfield": {
                "at": NOW,
                "jobs": 4,
                "families": {
                    name: {"sessions": sessions, "runs": 1, "child_runs": 0}
                    for name, sessions in families.items()
                },
                "workers": len(families),
                "child_workers": 0,
                "coordinator_caller": "edgar-specimen",
            }
        },
    }
    idle = {SCARLET: NOW - timedelta(minutes=52)}
    return state, [CALM, SCARLET], idle


def lane_snapshot_entry(lanes_facts: list) -> dict:
    return {
        "edgar-greenfield": {
            "at": NOW,
            "declared": 20,
            "lanes": lanes_facts,
            "refused": [],
            "worktrees": {},
        }
    }


def counted_lane(key: str, family: str) -> dict:
    return {
        "key": key,
        "label": key,
        "family": family,
        "queue_item": None,
        "venue": "storm-mosaic-17",
        "state": "running",
        "stale": False,
        "overrun": False,
        "terminated": False,
    }


_REAL_CONTRACT_FOR = registry.staffing_contract_for


# The recorded specimen queue entry: the Round 4
# instrument build as it stood in the queue before
# its discharge pruned it from the live contract.
# The fixture rebuilds the specimen contract —
# live queue plus this entry — so the
# reconciliation pins exercise the gated-item form
# without the live queue carrying discharged work.
_SPECIMEN_WORK_ITEM = {
    "key": "round4-instrument-build",
    "label": "Round 4 instrument build",
    "family": "round4",
    "staffable_when": "segment-packet-landing",
}


def packet_landed(slug):
    contract = _REAL_CONTRACT_FOR(slug)
    if contract:
        contract["staffable_queue"].append(dict(_SPECIMEN_WORK_ITEM))
        for entry in contract["staffable_queue"]:
            if entry["key"] == "segment-packet-landing":
                entry["landed"] = True
    return contract


# Filler families carrying a fixture's venue
# snapshot up to the cured floor (8 distinct
# register families in active work), stacked on
# the two sessions so no one-deep condition fires:
# the lane premises below isolate the queue and
# lane-record conditions from the count condition.
FILLER_FAMILIES = {
    "fam-c": [CALM],
    "fam-d": [CALM],
    "fam-e": [CALM],
    "fam-f": [SCARLET],
    "fam-g": [SCARLET],
    "fam-h": [SCARLET],
}


class MeasureReconciliation(unittest.TestCase):
    def test_full_staffing_clears_the_row(self):
        state, live, idle = queue_state(
            {"cocisep": [CALM], "corefin-coci": [SCARLET], **FILLER_FAMILIES}
        )
        with mock.patch.object(registry, "staffing_contract_for", packet_landed):
            rows = staffing_venue._family_rows(state, NOW, live, idle)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            [e["key"] for e in rows[0]["queue_unstaffed"]],
            ["round4-instrument-build"],
        )
        # The counted lane covering the due item's
        # family staffs it: the row clears.
        state["lane_snapshot"] = lane_snapshot_entry(
            [counted_lane("round4-lane", "round4")]
        )
        with mock.patch.object(registry, "staffing_contract_for", packet_landed):
            rows = staffing_venue._family_rows(state, NOW, live, idle)
        self.assertEqual(rows, [])

    def test_one_lane_short_names_the_unstaffed_item(self):
        queue = [
            {
                "key": "fam-a-build",
                "label": "Fam A build",
                "family": "fama",
                "staffable_when": None,
            },
            {
                "key": "fam-b-build",
                "label": "Fam B build",
                "family": "famb",
                "staffable_when": None,
            },
        ]

        def two_item_contract(slug):
            contract = _REAL_CONTRACT_FOR(slug)
            if contract is not None:
                contract["staffable_queue"] = queue
            return contract

        state, live, idle = queue_state(
            {"cocisep": [CALM], "corefin-coci": [SCARLET]}
        )
        state["lane_snapshot"] = lane_snapshot_entry(
            [counted_lane("fama-lane", "fama")]
        )
        with mock.patch.object(
            registry, "staffing_contract_for", two_item_contract
        ):
            rows = staffing_venue._family_rows(state, NOW, live, idle)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("lane_shortfall", row["conditions"])
        self.assertIn("prerequisite_due_family_unstaffed", row["conditions"])
        # The shortfall the commission consumes names
        # the unstaffed item, in the landed form.
        self.assertEqual(
            [e["key"] for e in row["queue_unstaffed"]], ["fam-b-build"]
        )
        self.assertEqual(row["lane_records"]["expected"], 2)
        self.assertEqual(row["lane_records"]["actual"], 1)
        self.assertEqual(row["lane_records"]["declared"], 20)

    def test_no_lane_snapshot_keeps_the_venue_derivation(self):
        state, live, idle = queue_state(
            {"cocisep": [CALM], "corefin-coci": [SCARLET]}
        )
        with mock.patch.object(registry, "staffing_contract_for", packet_landed):
            rows = staffing_venue._family_rows(state, NOW, live, idle)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("lane_records", rows[0])
        self.assertNotIn("lane_shortfall", rows[0]["conditions"])
        self.assertEqual(lanes._lane_rows(state, NOW), [])
        self.assertIsNone(lanes.record_facts(state, "edgar-greenfield"))


TWO_ITEM_QUEUE = [
    {
        "key": "fam-a-build",
        "label": "Fam A build",
        "family": "fama",
        "staffable_when": None,
    },
    {
        "key": "fam-b-build",
        "label": "Fam B build",
        "family": "famb",
        "staffable_when": None,
    },
]


def two_item_contract(slug):
    contract = _REAL_CONTRACT_FOR(slug)
    if contract is not None:
        contract["staffable_queue"] = copy.deepcopy(TWO_ITEM_QUEUE)
    return contract


def stale_lane(key: str, family: str) -> dict:
    lane = counted_lane(key, family)
    lane["stale"] = True
    return lane


class LaneServeShape(unittest.TestCase):
    """The serve-shape cure: one unconditional lane
    block per programme whose contract names a
    staffable queue — served at full staffing as at
    a shortfall, absent where no queue is named —
    while the serial_staffing row's firing and
    clearing behaviour stands unchanged."""

    def test_full_staffing_serves_the_block_the_row_clears(self):
        state, live, idle = queue_state(
            {"cocisep": [CALM], "corefin-coci": [SCARLET], **FILLER_FAMILIES}
        )
        state["lane_snapshot"] = lane_snapshot_entry(
            [counted_lane("fama-lane", "fama"), counted_lane("famb-lane", "famb")]
        )
        with mock.patch.object(registry, "staffing_contract_for", two_item_contract):
            blocks = staffing_venue.lane_blocks(state)
            rows = staffing_venue._family_rows(state, NOW, live, idle)
        # The defect row clears at full staffing; the
        # block the standing row renders from stands.
        self.assertEqual(rows, [])
        block = blocks["edgar-greenfield"]
        self.assertEqual(block["slug"], "edgar-greenfield")
        self.assertEqual(block["label"], "edgar — greenfield extractor")
        self.assertEqual(block["declared"], 20)
        self.assertEqual(block["expected"], 2)
        self.assertEqual(block["actual"], 2)
        self.assertGreaterEqual(block["actual"], block["expected"])
        self.assertEqual(block["queue_unstaffed"], [])
        self.assertEqual(
            [lane["key"] for lane in block["lanes"]], ["fama-lane", "famb-lane"]
        )

    def test_no_named_queue_serves_no_block(self):
        state, _live, _idle = queue_state({"cocisep": [CALM]})
        blocks = staffing_venue.lane_blocks(state)
        # Only the edgar programme's contract names a
        # queue; every other programme is absent.
        self.assertEqual(sorted(blocks), ["edgar-greenfield"])

        def no_queue_contract(slug):
            contract = _REAL_CONTRACT_FOR(slug)
            if contract is not None:
                del contract["staffable_queue"]
            return contract

        with mock.patch.object(registry, "staffing_contract_for", no_queue_contract):
            self.assertEqual(staffing_venue.lane_blocks(state), {})

    def test_one_lane_short_block_names_the_unstaffed_item(self):
        state, live, idle = queue_state(
            {"cocisep": [CALM], "corefin-coci": [SCARLET], **FILLER_FAMILIES}
        )
        state["lane_snapshot"] = lane_snapshot_entry(
            [counted_lane("fama-lane", "fama")]
        )
        with mock.patch.object(registry, "staffing_contract_for", two_item_contract):
            blocks = staffing_venue.lane_blocks(state)
            rows = staffing_venue._family_rows(state, NOW, live, idle)
        block = blocks["edgar-greenfield"]
        self.assertEqual(block["expected"], 2)
        self.assertEqual(block["actual"], 1)
        self.assertEqual(
            [e["key"] for e in block["queue_unstaffed"]], ["fam-b-build"]
        )
        # The row fires exactly as before the cure,
        # from the same assembly: its evidence and
        # the block's fields are one payload.
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            row["conditions"],
            ["lane_shortfall", "prerequisite_due_family_unstaffed"],
        )
        self.assertEqual(row["queue_unstaffed"], block["queue_unstaffed"])
        self.assertEqual(row["lane_records"]["declared"], block["declared"])
        self.assertEqual(row["lane_records"]["expected"], block["expected"])
        self.assertEqual(row["lane_records"]["actual"], block["actual"])
        self.assertEqual(row["lane_records"]["lanes"], block["lanes"])

    def test_stale_lane_served_stale_and_excluded_from_actual(self):
        state, _live, _idle = queue_state(
            {"cocisep": [CALM], "corefin-coci": [SCARLET]}
        )
        state["lane_snapshot"] = lane_snapshot_entry(
            [stale_lane("fama-lane", "fama"), counted_lane("famb-lane", "famb")]
        )
        with mock.patch.object(registry, "staffing_contract_for", two_item_contract):
            blocks = staffing_venue.lane_blocks(state)
        block = blocks["edgar-greenfield"]
        by_key = {lane["key"]: lane for lane in block["lanes"]}
        self.assertEqual(sorted(by_key), ["fama-lane", "famb-lane"])
        self.assertTrue(by_key["fama-lane"]["stale"])
        self.assertFalse(by_key["famb-lane"]["stale"])
        # The stale lane is served, not counted: only
        # the fresh lane reads into actual, and the
        # stale lane's item stands unstaffed.
        self.assertEqual(block["actual"], 1)
        self.assertEqual(
            [e["key"] for e in block["queue_unstaffed"]], ["fam-a-build"]
        )

    def test_digest_programmes_carry_the_block(self):
        state = sample_data.sample_state(NOW)
        state["programmes"] = registry.declarations()
        state["digest_wb_snapshot"] = {
            "at": NOW.isoformat(),
            "parked": {
                "available": True,
                "reason": None,
                "skipped_projects": [],
                "plans": [],
            },
            "parked_counts": {},
            "modified": {},
            "wb_topics": {},
        }
        venue_state, _live, _idle = queue_state(
            {"cocisep": [CALM], "corefin-coci": [SCARLET]}
        )
        state["venue_snapshot"] = venue_state["venue_snapshot"]
        state["lane_snapshot"] = lane_snapshot_entry(
            [counted_lane("fama-lane", "fama"), counted_lane("famb-lane", "famb")]
        )
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(run_records_dir=Path(tmp) / "records")
            with mock.patch.object(
                registry, "staffing_contract_for", two_item_contract
            ):
                payload = digest_mod.build_digest(state, settings, NOW)
        entries = {p["slug"]: p for p in payload["programmes"]}
        block = entries["edgar-greenfield"]["lane_block"]
        self.assertEqual(block["actual"], 2)
        self.assertEqual(block["expected"], 2)
        self.assertEqual(block["queue_unstaffed"], [])
        # A programme with no queue named carries no
        # block key at all — honest absence.
        self.assertNotIn("lane_block", entries["steampowernj"])
        self.assertNotIn("lane_block", entries["supreme-octo-robot"])


if __name__ == "__main__":
    unittest.main()
