"""Rules and verbs: the shipped rule set, the action-rule
seeds, and the owner-action verb vocabulary — split
from attention.py; attention.domain.attention
re-exports this surface.
"""

from __future__ import annotations

PROGRAM_FLAGS = ("program_approved", "reversible", "in_budget", "only_blocker")


def _rule(rule_id, wait_class, scope, requires=(), priority=100):
    return {
        "id": rule_id,
        "match": {
            "wait_class": wait_class,
            "status_code": None,
            "kind": None,
            "handle": None,
        },
        "where": None,
        "action": {"type": "auto_apply"},
        "scope": scope,
        "requires": list(requires),
        "priority": priority,
        "on_scope_miss": "pending",
        "trigger": {"on": "on_enter"},
        "guards": {},
        "mode": "active",
    }


def default_rules() -> list:
    """The shipped rule set: the sweeper taxonomy as data."""
    return [
        _rule("settled-continue", "settled_continue", "always", priority=10),
        _rule("program-step", "program_step", "always", PROGRAM_FLAGS, 20),
        _rule("defect-fix", "defect_fix", "always", priority=30),
        _rule("result-preserving", "result_preserving", "always", priority=40),
        _rule("followup-worktree", "followup_worktree", "away", priority=50),
        _rule("stall-hold", "stall_hold", "away", priority=60),
        _rule("redrive", "redrive", "active", priority=70),
        _rule("ruling-propagation", "ruling_propagation", "active", priority=80),
    ]


# Owner-action verbs (§1.13; D-A5: the vocabulary is
# served domain defaults in v1, not registry data —
# verbs are semantics, not labels).
VERB_LABELS = {
    "approve_once": "Approve",
    "approve_rule": "Approve + make rule",
    "deny": "Deny",
    "pick": "Pick",
    "rule_it": "Rule it standing",
    "accept": "Accept",
    "reject": "Reject",
    "modify": "Modify",
    "push": "Push",
    "close_on_verify": "Close — verified",
    "reply": "Reply",
    "snooze": "Snooze",
    "done": "Done",
    "mute_type": "Mute type",
    "leave_it": "Leave it",
    "continue": "Continue",
    "go": "Go",
    "accept_review": "Accept review",
    "reject_incomplete": "Reject as incomplete",
    "park": "Park",
    "close": "Close",
    "status_ping": "Status ping",
    "parallelize": "Parallelize",
    "critic_pass": "Critic pass",
    "perf_pass": "Performance pass",
    "consolidation_pass": "Consolidation pass",
    "organize_pass": "Organize pass",
    "stop": "Stop",
    "resume": "Resume",
    "accept_proposal": "Accept — create the rule",
    "reject_proposal": "Reject proposal",
}
# The named exception (§1.13): bookmarks send nothing.
BOOKMARK_VERBS = ("snooze", "done", "mute_type", "leave_it")
# Verdict-shaped taps the repetition counter reads;
# reply/modify carry their judgment in the note and are
# never counted toward a rule proposal.
COUNTED_VERBS = (
    "approve_once",
    "deny",
    "pick",
    "accept",
    "reject",
    "push",
    "close_on_verify",
    "continue",
    "go",
    "accept_review",
    "reject_incomplete",
)
PROPOSAL_THRESHOLD = 3


def _action_rule(rule_id, match, verb, note):
    return {
        "id": rule_id,
        "match": match,
        "verb": verb,
        "mode": "shadow",
        "created_from": "seed",
        "note": note,
    }


def default_action_rules() -> list:
    """The §1.13 seeds R1–R6, all shadow (D-A6). R1–R3
    are evaluated now; R4–R6 are recorded with their
    triggers for the follow-on tranche."""
    return [
        _action_rule(
            "R1-defect-clears-on-terminal",
            {"kind": "defect"},
            "close_on_verify",
            "A defect item closes when its handler posts a terminal status.",
        ),
        _action_rule(
            "R2-stale-status-pings",
            {"status_code": ["WORKING", "CONTINUE"]},
            "status_ping",
            "A stale working status draws a status ping.",
        ),
        _action_rule(
            "R3-perf-clears-as-fyi",
            {"kind": "performance", "provenance": "offer"},
            "clear_fyi",
            "Result-preserving performance clears as FYI.",
        ),
        _action_rule(
            "R4-done-with-conflict-returns",
            {"status_code": ["DONE", "CLOSED"]},
            "reject_incomplete",
            "Deferred: reads the workbench derivation.",
        ),
        _action_rule(
            "R5-ui-done-draws-critic",
            {"status_code": ["DONE", "CLOSED"], "ui_surface": True},
            "critic_pass",
            "Deferred: dispatches a commission.",
        ),
        _action_rule(
            "R6-completion-proposes-consolidation",
            {"status_code": ["DONE", "CLOSED"]},
            "consolidation_proposal",
            "Deferred: reads the workbench derivation.",
        ),
    ]


def normalize_rule(rule: dict) -> dict:
    """Fill the v2 fields on a stored rule (older rules carry
    a bare string action and no priority/trigger/mode)."""
    rule = dict(rule)
    action = rule.get("action", "auto_apply")
    if isinstance(action, str):
        action = {"type": action}
    rule["action"] = action
    rule.setdefault("where", None)
    rule.setdefault("requires", [])
    rule.setdefault("priority", 100)
    rule.setdefault("on_scope_miss", "pending")
    rule.setdefault("trigger", {"on": "on_enter"})
    rule.setdefault("guards", {})
    rule.setdefault("mode", "active")
    return rule


def action_type(rule: dict) -> str:
    return normalize_rule(rule)["action"]["type"]


def ordered_rules(rules: list) -> list:
    """Evaluation order: explicit priority, then stored
    order as the tiebreak (stable)."""
    indexed = sorted(
        enumerate(rules),
        key=lambda pair: (normalize_rule(pair[1]).get("priority", 100), pair[0]),
    )
    return [rule for _, rule in indexed]
