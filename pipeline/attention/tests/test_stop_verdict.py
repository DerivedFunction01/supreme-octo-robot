"""Stop-verdict contract pins (the stopped-lane plan,
Step 3): the wait-class register carries the
stop-enumeration fields; the classifier verdicts every
row per its class; hard-stop namings refuse before any
class match; near-miss state strings read
unrecognized; owner-block claims verdict only through
the verification read (default false — uncited,
miscited, or lane-evidenced claims are void); flagged
reasons validate their reference both ways; the
residue forms produce no verdict; and the attstore
load path carries the new fields onto live rows
without overwriting. Fixture state only — in-memory
registers, injected readers, no live store or
workspace reads.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from attention.domain import attention as dom  # noqa: E402
from attention.domain import stop_verdict as sv  # noqa: E402
from attention.infra import attstore  # noqa: E402

SINCE = "2026-11-27T15:00:00+00:00"
OWNER_CHAT = "chat-owner"
OWNER_AT = "2026-11-27T14:00:00+00:00"


def record(state, reason=None, ref=None, citation=None, cause=None):
    """A status record's text + its parsed stop line."""
    payload = {"reason": reason, "since": SINCE, "ref": ref, "citation": citation}
    text = f"STATUS: {state}\nstop: {json.dumps(payload)}"
    return text, sv.parse_stop_line(text)


def approval_reader(kind, ref_id):
    return {
        ("plan", "plan-approved"): True,
        ("goal", "goal-approved"): True,
        ("plan", "plan-unapproved"): False,
    }.get((kind, ref_id))


def owner_reader(probe):
    if "chat" in probe:
        return probe == {"chat": OWNER_CHAT, "at": OWNER_AT}
    return probe.get("act") == "permission_card"


def verdict_for(state, reason=None, ref=None, citation=None, cause=None, **readers):
    _, stop = record(state, reason, ref, citation)
    readers.setdefault("approval_state", approval_reader)
    readers.setdefault("owner_traffic", owner_reader)
    return sv.verdict(state, stop, cause=cause, **readers)


class RegisterShapeTests(unittest.TestCase):
    def test_rows_carry_the_stop_fields(self):
        for entry in dom.default_wait_classes():
            for field in ("disposition", "evidence", "proof", "admitted_by"):
                self.assertIn(field, entry, entry["name"])
            self.assertTrue(entry["disposition"], entry["name"])
            self.assertTrue(entry["proof"], entry["name"])
            self.assertTrue(entry["admitted_by"], entry["name"])
            if entry["name"] == "form_submit":
                self.assertIsNone(entry["evidence"])
            else:
                self.assertTrue(entry["evidence"], entry["name"])

    def test_row_set_and_marks(self):
        rows = {c["name"]: c for c in dom.default_wait_classes()}
        self.assertEqual(set(rows), set(dom.RULED_CLASSES) | set(dom.HARD_STOP_CLASSES))
        self.assertEqual(len(rows), 17)
        for name in dom.HARD_STOP_CLASSES:
            self.assertTrue(rows[name]["hard_stop"], name)
        for name in dom.RULED_CLASSES:
            self.assertFalse(rows[name]["hard_stop"], name)
        self.assertEqual(
            rows["execution_risk_flag"]["disposition"], "reroute_and_continue"
        )
        self.assertEqual(
            rows["execution_risk_flag"]["admitted_by"],
            "stopped-lane actuation commission",
        )

    def test_candidates_and_residue_are_not_rows(self):
        names = {c["name"] for c in dom.default_wait_classes()}
        for candidate in dom.STOP_REASON_CANDIDATES:
            self.assertNotIn(candidate, names)
        self.assertEqual(
            dom.STOP_REASON_CANDIDATES, ("venue_governance", "external_platform_cap")
        )
        self.assertEqual(
            dom.STOP_RESIDUE_FORMS, ("unreasoned_stop", "unenumerated_reason")
        )

    def test_flag_fields_only_where_the_ref_rides_the_stop_line(self):
        rows = {c["name"]: c for c in dom.default_wait_classes()}
        self.assertEqual(rows["scope_expansion"].get("requires_plan"), True)
        self.assertEqual(rows["external_send"].get("requires_goal"), True)
        self.assertEqual(rows["schedule_change"].get("requires_plan"), True)
        for name in ("permission_card", "purchase", "login", "form_submit"):
            for field in ("requires_plan", "requires_goal", "requires_todo"):
                self.assertNotIn(field, rows[name], name)

    def test_floor_reads_as_before_over_old_and_new_shapes(self):
        old_shape = [
            {"name": "login", "hard_stop": True},
            {"name": "program_step", "hard_stop": False},
        ]
        self.assertTrue(dom.class_is_hard_stop("login", old_shape))
        self.assertFalse(dom.class_is_hard_stop("program_step", old_shape))
        self.assertTrue(dom.class_is_hard_stop("login", dom.default_wait_classes()))
        self.assertFalse(dom.class_is_hard_stop("execution_risk_flag", None))
        rule = {
            "match": {"wait_class": "login"},
            "action": {"type": "auto_apply"},
        }
        self.assertFalse(dom.rule_is_legal(rule, dom.default_wait_classes()))
        self.assertFalse(dom.rule_is_legal(rule, old_shape))
        clear = {
            "match": {"wait_class": "execution_risk_flag"},
            "action": {"type": "auto_apply"},
        }
        self.assertTrue(dom.rule_is_legal(clear, dom.default_wait_classes()))


class RowVerdictTests(unittest.TestCase):
    def test_every_row_verdicts_per_its_class(self):
        for row in dom.default_wait_classes():
            name = row["name"]
            required = [k for k in sv.REF_KINDS if row.get(f"requires_{k}")]
            if required:
                ref = {"kind": required[0], "id": f"{required[0]}-approved"}
                got = verdict_for("PARKED", name, ref=ref)
                self.assertEqual(got["verdict"], sv.ACTUATE, name)
                self.assertEqual(got["disposition"], row["disposition"], name)
            elif row["hard_stop"]:
                got = verdict_for("PARKED", name)
                self.assertEqual(got["verdict"], sv.OWNER_ITEM, name)
            else:
                got = verdict_for("PARKED", name)
                self.assertEqual(got["verdict"], sv.ACTUATE, name)
                self.assertEqual(got["disposition"], row["disposition"], name)

    def test_flag_validation_both_ways(self):
        ref_ok = {"kind": "plan", "id": "plan-approved"}
        ref_bad = {"kind": "plan", "id": "plan-unapproved"}
        ref_unknown = {"kind": "plan", "id": "plan-unrecorded"}
        self.assertEqual(
            verdict_for("PARKED", "scope_expansion", ref=ref_ok)["verdict"], sv.ACTUATE
        )
        for ref in (ref_bad, ref_unknown, None):
            got = verdict_for("PARKED", "scope_expansion", ref=ref)
            self.assertEqual(got["verdict"], sv.STANDING, ref)
        wrong_kind = {"kind": "todo", "id": "plan-approved"}
        self.assertEqual(
            verdict_for("PARKED", "scope_expansion", ref=wrong_kind)["verdict"],
            sv.STANDING,
        )
        goal_ref = {"kind": "goal", "id": "goal-approved"}
        self.assertEqual(
            verdict_for("PARKED", "external_send", ref=goal_ref)["verdict"], sv.ACTUATE
        )


class RefusalTests(unittest.TestCase):
    def test_cause_naming_a_hard_stop_class_refuses(self):
        got = verdict_for(
            "PARKED", "program_step", cause="held on a permission card tap"
        )
        self.assertEqual(got["verdict"], sv.REFUSED)

    def test_cause_naming_both_a_ruled_class_and_a_hard_stop_refuses(self):
        got = verdict_for(
            "WORKING",
            "program_step",
            cause="program step queued; a login is also outstanding",
        )
        self.assertEqual(got["verdict"], sv.REFUSED)

    def test_cause_naming_its_own_hard_stop_reason_does_not_refuse(self):
        got = verdict_for("PARKED", "login", cause="login required at the portal")
        self.assertEqual(got["verdict"], sv.OWNER_ITEM)

    def test_cron_change_alias_refuses(self):
        got = verdict_for("PARKED", "redrive", cause="waiting on a cron change")
        self.assertEqual(got["verdict"], sv.REFUSED)


class StateParsingTests(unittest.TestCase):
    def test_near_miss_state_strings_read_unrecognized(self):
        near_misses = (
            "Block owner",
            "BLOCKED_OWNER",
            "blocked-owner",
            "BO",
            "Blocked — owner",
        )
        for state in near_misses:
            got = verdict_for(state, "execution_risk_flag")
            self.assertEqual(got["verdict"], sv.UNRECOGNIZED, state)

    def test_canonical_states_parse(self):
        got = verdict_for("BLOCKED-HARD", "login")
        self.assertEqual(got["verdict"], sv.OWNER_ITEM)


class OwnerBlockTests(unittest.TestCase):
    def test_verified_citation_stands_as_owner_item(self):
        citation = {"chat": OWNER_CHAT, "at": OWNER_AT}
        got = verdict_for("BLOCKED-OWNER", "execution_risk_flag", citation=citation)
        self.assertEqual(got["verdict"], sv.OWNER_ITEM)

    def test_uncited_claim_is_void(self):
        got = verdict_for("BLOCKED-OWNER", "execution_risk_flag")
        self.assertEqual(got["verdict"], sv.VOID)

    def test_miscited_claim_is_void(self):
        citation = {"chat": "chat-lane", "at": OWNER_AT}
        got = verdict_for("BLOCKED-OWNER", "execution_risk_flag", citation=citation)
        self.assertEqual(got["verdict"], sv.VOID)

    def test_lane_evidenced_claim_is_void(self):
        # The only evidence offered is a citation into
        # the claiming lane's own thread: owner traffic
        # holds no such owner message, so the claim
        # cannot verify — a record never verifies itself.
        citation = {"chat": "chat-lane-itself", "at": OWNER_AT}
        got = verdict_for("BLOCKED-HARD", "program_step", citation=citation)
        self.assertEqual(got["verdict"], sv.VOID)

    def test_named_hard_stop_act_that_exists_stands(self):
        got = verdict_for(
            "BLOCKED-OWNER",
            "execution_risk_flag",
            cause="held on the permission card the owner raised",
        )
        self.assertEqual(got["verdict"], sv.OWNER_ITEM)

    def test_named_hard_stop_act_that_does_not_exist_is_void(self):
        got = verdict_for(
            "BLOCKED-OWNER",
            "execution_risk_flag",
            cause="held on a login the owner demanded",
        )
        self.assertEqual(got["verdict"], sv.VOID)

    def test_hard_stop_reason_needs_no_citation(self):
        got = verdict_for("BLOCKED-OWNER", "login", owner_traffic=None)
        self.assertEqual(got["verdict"], sv.OWNER_ITEM)

    def test_unreasoned_owner_block_claim_is_void(self):
        got = verdict_for("BLOCKED-OWNER", None)
        self.assertEqual(got["verdict"], sv.VOID)


class ResidueAndMalformedTests(unittest.TestCase):
    def test_no_stop_line_is_residue(self):
        stop = sv.parse_stop_line("STATUS: WORKING\nall quiet")
        self.assertIsNone(stop)
        got = sv.verdict("WORKING", stop)
        self.assertEqual(got["verdict"], sv.RESIDUE)

    def test_unreasoned_stop_is_residue(self):
        got = verdict_for("PARKED", None)
        self.assertEqual(got["verdict"], sv.RESIDUE)

    def test_unenumerated_reason_is_residue(self):
        for reason in ("venue_governance", "external_platform_cap", "not_a_reason"):
            got = verdict_for("PARKED", reason)
            self.assertEqual(got["verdict"], sv.RESIDUE, reason)

    def test_malformed_stop_lines_read_unrecognized(self):
        def line(**overrides):
            payload = {
                "reason": "login",
                "since": SINCE,
                "ref": None,
                "citation": None,
            }
            payload.update(overrides)
            return "stop: " + json.dumps(payload)

        bad_lines = [
            "stop: {not json",
            line(since="yesterday"),
            line(ref={"kind": "card", "id": "c1"}),
            line(citation={"chat": "c1"}),
            line(extra=1),
            line() + "\n" + line(),
        ]
        for text in bad_lines:
            stop = sv.parse_stop_line(text)
            self.assertIs(stop, sv.MALFORMED, text)
            got = sv.verdict("PARKED", stop)
            self.assertEqual(got["verdict"], sv.UNRECOGNIZED, text)

    def test_well_formed_line_parses_to_the_normalized_stop(self):
        text, stop = record(
            "PARKED", "scope_expansion", ref={"kind": "plan", "id": "plan-approved"}
        )
        self.assertEqual(
            stop,
            {
                "reason": "scope_expansion",
                "since": SINCE,
                "ref": {"kind": "plan", "id": "plan-approved"},
                "citation": None,
            },
        )


class BackfillTests(unittest.TestCase):
    def test_live_rows_gain_the_fields_on_load(self):
        state = {
            "wait_classes": [
                {
                    "name": "program_step",
                    "hard_stop": False,
                    "stale_after_hours": 48,
                    "on_stale": "expire",
                },
                {"name": "scope_expansion", "hard_stop": True},
            ]
        }
        attstore.backfill(state)
        program_step, scope_expansion = state["wait_classes"]
        self.assertEqual(program_step["disposition"], "commission_next_step")
        self.assertEqual(program_step["admitted_by"], "incumbent wait-class register")
        self.assertNotIn("requires_plan", program_step)
        self.assertEqual(scope_expansion["requires_plan"], True)

    def test_present_fields_are_never_overwritten(self):
        state = {
            "wait_classes": [
                {
                    "name": "program_step",
                    "hard_stop": False,
                    "disposition": "owner-edited",
                }
            ]
        }
        attstore.backfill(state)
        self.assertEqual(state["wait_classes"][0]["disposition"], "owner-edited")

    def test_unregistered_entry_gains_honest_absence(self):
        state = {"wait_classes": [{"name": "in_app_class", "hard_stop": False}]}
        attstore.backfill(state)
        entry = state["wait_classes"][0]
        self.assertIsNone(entry["disposition"])
        self.assertIsNone(entry["evidence"])
        self.assertNotIn("requires_plan", entry)

    def test_backfill_does_not_append_rows(self):
        # A stored register is operator data: the field
        # carry rides the load path, rows do not — they
        # resolve against the catalog defaults at read
        # time, and the S1 census count stands.
        state = {"wait_classes": [{"name": "program_step", "hard_stop": False}]}
        attstore.backfill(state)
        self.assertEqual([e["name"] for e in state["wait_classes"]], ["program_step"])

    def test_empty_state_rows_carry_the_fields(self):
        rows = {c["name"]: c for c in attstore.empty_state()["wait_classes"]}
        self.assertIn("execution_risk_flag", rows)
        for entry in rows.values():
            self.assertIn("disposition", entry, entry["name"])
        self.assertEqual(rows["scope_expansion"].get("requires_plan"), True)


if __name__ == "__main__":
    unittest.main()
