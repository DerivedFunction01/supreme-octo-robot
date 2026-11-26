"""Supervision registry pins (the superapp supervision
plan, Step 1): every live programme's seeded row loads
and validates, a missing or invalid field refuses
loudly naming the field, the edgar row reproduces the
family-concurrency staffing contract
verbatim as data, the sweep's measure classes are
seeded per programme, the coordinator routes are
wb-sent, and the drain tail carries the standing
defaults plus each programme's baked-in extras.
Fixture data only — the module's own seed, no live
store or workspace reads.
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.services.measure import registry  # noqa: E402

# The edgar staffing contract as ruled in its
# cured form (owner order, in the
# programme GOAL.md's class 2: the numeric floor of
# at least 8 distinct register families in active
# work at all times; the measure work-denominated —
# the expected count set by the register's staffable
# families, sessions capacity and never the
# denominator; one-deep-per-session while families
# wait a class-2 instance by definition): written
# out here from the ruling, so the seed is checked
# against the source, not against itself.
EXPECTED_EDGAR_CONTRACT = {
    "unit": "table_family",
    "evidence_window_minutes": 30,
    "min_families_in_flight": 8,
    "defect_conditions": [
        "fewer_than_min_families_in_flight",
        "one_deep_per_session_while_staffable_families_wait",
        "prerequisite_due_family_unstaffed",
    ],
    "delegate_counts_toward_concurrency": False,
    "no_parallel_work_claim": "void_unless_verified_family_by_family",
    "clearing": "later_measure_only",
    "non_response_after_consecutive_runs": 2,
    "reminder_cadence_minutes": 30,
    # The staffable queue, from the staffing-
    # commission amendment as commissioned and
    # amended since: the CI-gold trace pricing and
    # the caption-channel reader pricing were
    # staffed on the owner's direct order and left
    # the queue as staffed work, so what remains is
    # the two precondition markers and the Round 4
    # instrument build gated on the segment
    # packet's landing. The packet has since
    # landed and its marker stands flipped landed
    # by amendment, so the Round 4 build is
    # staffable now. Family keys are the venue
    # measure's workstream stems.
    "staffable_queue": [
        {
            "key": "segment-register-close",
            "label": "Segment register close",
            "marker": True,
            "landed": False,
        },
        {
            "key": "segment-packet-landing",
            "label": "Segment packet landing (composed tree settles)",
            "marker": True,
            "landed": True,
        },
        {
            "key": "round4-instrument-build",
            "label": "Round 4 instrument build",
            "family": "round4",
            "staffable_when": "segment-packet-landing",
        },
    ],
}

EXPECTED_SLUGS = {
    "edgar-greenfield",
    "edgar-sec",
    "steampowernj",
    "supreme-octo-robot",
}


class SeedLoads(unittest.TestCase):
    def test_every_live_programme_row_loads(self):
        rows = registry.declarations()
        self.assertEqual({r["slug"] for r in rows}, EXPECTED_SLUGS)
        for row in rows:
            self.assertIs(registry.validate_declaration(row), row)

    def test_active_declarations_exclude_the_retired_row(self):
        active = {r["slug"] for r in registry.active_declarations()}
        self.assertEqual(
            active, {"edgar-greenfield", "steampowernj", "supreme-octo-robot"}
        )

    def test_returned_rows_are_copies(self):
        row = registry.for_slug("edgar-greenfield")
        row["cadence_minutes"] = 999
        row["measure_classes"].append("register_seam")
        fresh = registry.for_slug("edgar-greenfield")
        self.assertEqual(fresh["cadence_minutes"], 15)
        self.assertNotIn("register_seam", fresh["measure_classes"])


class LoudRefusal(unittest.TestCase):
    def _row(self):
        return copy.deepcopy(registry.for_slug("supreme-octo-robot"))

    def test_each_missing_field_refuses_loudly(self):
        for field in registry.REQUIRED_FIELDS:
            row = self._row()
            del row[field]
            with self.assertRaises(registry.RegistryError) as caught:
                registry.validate_declaration(row)
            self.assertIn(field, str(caught.exception))

    def test_invalid_values_refuse(self):
        bad = {
            "venue": "moon",
            "cadence_minutes": 0,
            "escalation_hours": -1,
            "staffing_band": {"min": 12, "max": 10},
            "measure_classes": ["idle", "bogus"],
            "drain_tail": [],
            "retired": "no",
        }
        for field, value in bad.items():
            row = self._row()
            row[field] = value
            with self.assertRaises(registry.RegistryError) as caught:
                registry.validate_declaration(row)
            self.assertIn(field, str(caught.exception))

    def test_route_must_be_wb_sent(self):
        row = self._row()
        row["coordinator_route"] = {
            "sender": "cron",
            "kind": "chat",
            "handle": "@workhorse",
        }
        with self.assertRaises(registry.RegistryError) as caught:
            registry.validate_declaration(row)
        self.assertIn("coordinator_route", str(caught.exception))

    def test_chat_route_requires_a_handle(self):
        row = self._row()
        row["coordinator_route"] = {"sender": "wb", "kind": "chat"}
        with self.assertRaises(registry.RegistryError):
            registry.validate_declaration(row)

    def test_todo_route_requires_a_bundle(self):
        row = self._row()
        row["coordinator_route"] = {"sender": "wb", "kind": "todo"}
        with self.assertRaises(registry.RegistryError):
            registry.validate_declaration(row)
        row["coordinator_route"] = {
            "sender": "wb",
            "kind": "todo",
            "bundle": "2026-11-19-superapp-supervision-reminders",
        }
        self.assertIs(registry.validate_declaration(row), row)


class EdgarContract(unittest.TestCase):
    def test_edgar_row_reproduces_the_cured_contract_verbatim(self):
        contract = registry.staffing_contract_for("edgar-greenfield")
        self.assertEqual(contract, EXPECTED_EDGAR_CONTRACT)

    def test_no_other_programme_carries_a_staffing_contract(self):
        for slug in ("edgar-sec", "steampowernj", "supreme-octo-robot"):
            self.assertIsNone(registry.staffing_contract_for(slug))


class StaffableQueue(unittest.TestCase):
    def _row(self):
        return copy.deepcopy(registry.for_slug("edgar-greenfield"))

    def _queue(self, row):
        return row["staffing_contract"]["staffable_queue"]

    def test_seeded_queue_loads_in_order(self):
        contract = registry.staffing_contract_for("edgar-greenfield")
        queue = contract["staffable_queue"]
        # The queue as discharged: the Round 4
        # instrument build stood discharged by its
        # deliverable of record and is pruned; the
        # two markers remain.
        self.assertEqual(
            [entry["key"] for entry in queue],
            [
                "segment-register-close",
                "segment-packet-landing",
            ],
        )
        markers = {e["key"]: e["landed"] for e in queue if e.get("marker")}
        self.assertEqual(
            markers,
            {"segment-register-close": False, "segment-packet-landing": True},
        )

    def test_valid_queue_amendments_load(self):
        row = self._row()
        queue = self._queue(row)
        queue[1]["landed"] = True
        del queue[0]
        self.assertIs(registry.validate_declaration(row), row)

    def test_duplicate_keys_refuse(self):
        row = self._row()
        self._queue(row).append(dict(self._queue(row)[0]))
        with self.assertRaises(registry.RegistryError) as caught:
            registry.validate_declaration(row)
        self.assertIn("staffable_queue", str(caught.exception))

    def test_gate_naming_an_unknown_key_refuses(self):
        row = self._row()
        self._queue(row)[2]["staffable_when"] = "no-such-key"
        with self.assertRaises(registry.RegistryError) as caught:
            registry.validate_declaration(row)
        self.assertIn("staffable_queue", str(caught.exception))
        self.assertIn("no-such-key", str(caught.exception))

    def test_work_item_without_a_family_refuses(self):
        row = self._row()
        del self._queue(row)[2]["family"]
        with self.assertRaises(registry.RegistryError) as caught:
            registry.validate_declaration(row)
        self.assertIn("staffable_queue", str(caught.exception))

    def test_marker_carrying_a_family_refuses(self):
        row = self._row()
        self._queue(row)[1]["family"] = "segform"
        with self.assertRaises(registry.RegistryError) as caught:
            registry.validate_declaration(row)
        self.assertIn("staffable_queue", str(caught.exception))

    def test_marker_carrying_a_gate_refuses(self):
        row = self._row()
        self._queue(row)[1]["staffable_when"] = None
        with self.assertRaises(registry.RegistryError) as caught:
            registry.validate_declaration(row)
        self.assertIn("staffable_queue", str(caught.exception))

    def test_marker_without_a_landed_flag_refuses(self):
        row = self._row()
        del self._queue(row)[1]["landed"]
        with self.assertRaises(registry.RegistryError) as caught:
            registry.validate_declaration(row)
        self.assertIn("staffable_queue", str(caught.exception))

    def test_queue_is_optional(self):
        row = self._row()
        del row["staffing_contract"]["staffable_queue"]
        self.assertIs(registry.validate_declaration(row), row)


class SweepClassesAndRoutes(unittest.TestCase):
    def test_sweep_measure_classes_seeded_per_programme(self):
        for slug in EXPECTED_SLUGS:
            classes = registry.measure_classes_for(slug)
            for core in ("idle", "serial", "stall", "orphan"):
                self.assertIn(core, classes, f"{slug} missing {core}")

    def test_terminal_class_is_enabled_for_every_active_programme(self):
        # The terminal-unconsumed class:
        # every active programme declares it; the
        # retired row does not gain it retroactively.
        for row in registry.active_declarations():
            self.assertIn(
                "terminal",
                registry.measure_classes_for(row["slug"]),
                f"{row['slug']} missing terminal",
            )
        self.assertNotIn("terminal", registry.measure_classes_for("edgar-sec"))

    def test_unlanded_class_is_enabled_for_every_active_programme(self):
        # The unlanded class: seeded with
        # the terminal declarers — every active
        # programme declares it; the retired row does
        # not gain it retroactively.
        for row in registry.active_declarations():
            self.assertIn(
                "unlanded",
                registry.measure_classes_for(row["slug"]),
                f"{row['slug']} missing unlanded",
            )
        self.assertNotIn("unlanded", registry.measure_classes_for("edgar-sec"))

    def test_caller_stems_are_declared_where_the_caller_is_not_the_slug(self):
        self.assertEqual(
            registry.for_slug("steampowernj").get("caller_stems"), ["steampower"]
        )
        self.assertEqual(
            registry.for_slug("supreme-octo-robot").get("caller_stems"),
            ["workhorse"],
        )
        bad = registry.for_slug("steampowernj")
        bad["caller_stems"] = "steampower"
        with self.assertRaises(registry.RegistryError):
            registry.validate_declaration(bad)

    def test_register_seam_is_steam_powers_alone(self):
        self.assertIn("register_seam", registry.measure_classes_for("steampowernj"))
        for slug in ("edgar-greenfield", "edgar-sec", "supreme-octo-robot"):
            self.assertNotIn("register_seam", registry.measure_classes_for(slug))

    def test_coordinator_routes_are_wb_sent_chat_routes(self):
        for row in registry.declarations():
            route = registry.coordinator_route_for(row["slug"])
            self.assertEqual(route["sender"], "wb")
            self.assertEqual(route["kind"], "chat")
            self.assertIn(route["handle"], row["handles"])


class DrainTail(unittest.TestCase):
    def test_standing_defaults_seed_every_programme(self):
        default_keys = {item["key"] for item in registry.DEFAULT_DRAIN_TAIL}
        self.assertEqual(default_keys, {"consolidation", "doc-updates", "performance"})
        for slug in EXPECTED_SLUGS:
            keys = {item["key"] for item in registry.drain_tail_for(slug)}
            self.assertTrue(default_keys <= keys, slug)

    def test_steam_powers_baked_in_extra_is_declared(self):
        keys = {item["key"] for item in registry.drain_tail_for("steampowernj")}
        self.assertIn("tech-debt-paydown", keys)
        for slug in ("edgar-greenfield", "edgar-sec", "supreme-octo-robot"):
            keys = {item["key"] for item in registry.drain_tail_for(slug)}
            self.assertNotIn("tech-debt-paydown", keys)


class Accessors(unittest.TestCase):
    def test_for_handle_prefers_the_active_programme(self):
        self.assertEqual(registry.for_handle("@xbrl")["slug"], "edgar-greenfield")
        self.assertEqual(
            registry.for_handle("@workhorse")["slug"], "supreme-octo-robot"
        )
        self.assertIsNone(registry.for_handle("@nobody"))
        self.assertIsNone(registry.for_handle(None))

    def test_cadence_and_escalation_fall_back_to_the_default(self):
        self.assertEqual(registry.cadence_for("@workhorse", 99), 15)
        self.assertEqual(registry.cadence_for("@nobody", 99), 99)
        self.assertEqual(registry.escalation_for("@steampower", 7), 1)
        self.assertEqual(registry.escalation_for(None, 7), 7)

    def test_wb_projects_linkage(self):
        row = registry.for_slug("edgar-greenfield")
        self.assertEqual(registry.wb_projects_for(row), ["edgar-sec"])
        # An undeclared list falls back to the slug, the
        # harness's own keying (programmes.wb_projects).
        row = registry.for_slug("edgar-sec")
        self.assertEqual(registry.wb_projects_for(row), ["edgar-sec"])

    def test_workhorse_wb_projects_name_both_surfaces(self):
        # The supervision programme's workbench surface
        # answers to two names, one per surface: the wb
        # server serves the bundle under
        # "workbench-viewer" (its --project slug) while
        # the armed-row file drop keys its rows
        # "workrecord". Both are declared, so the
        # frontier attribution and the armed match read
        # the same programme.
        row = registry.for_slug("supreme-octo-robot")
        self.assertEqual(
            registry.wb_projects_for(row),
            ["workbench-viewer", "workrecord"],
        )


if __name__ == "__main__":
    unittest.main()
