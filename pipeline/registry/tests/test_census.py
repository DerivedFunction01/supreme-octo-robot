"""The S7 done-evidence census: the merged registry,
seeded from the S1 overlay capture (never from tracked
examples), validates every caller the captured live
registries carry — the runner thread callers, the
connector token callers, both routing tables of contract
01 (plus the restart-reconcile table), and the handler /
programme directory rows.

The capture is in-repo (docs/overlay/holding), so this
census runs anywhere the repo does.
"""

import re
import unittest
from pathlib import Path

from registry import seed
from registry.attention import directory
from registry.callers import callers, routing, tokens
from registry.store import Registry

REPO_ROOT = Path(__file__).resolve().parents[3]
HOLDING = REPO_ROOT / "docs" / "overlay" / "holding"
FIXTURES = REPO_ROOT / "contracts" / "fixtures"

# The captured thread callers (S1 capture, 2026-11-13),
# renamed to invented stand-ins — the held capture
# carries the original names as written: the review
# counted 14; the live registry had gained one from
# operator traffic by capture time — the overlay
# inventory records 15 thread callers, 3 active. The
# census validates the capture as it stands: the seed
# is renamed positionally onto these stand-ins (see
# _genericized_seed) — the capture itself is never
# cured.
THREAD_CALLERS = [
    "aldergrove-xbrl", "aldergroveforms", "aldergrove-remplan",
    "aldergrove-packaging", "aldergrove-era-attribution",
    "aldergrove-successor", "aldergrove-formation", "pinehollow-monitor",
    "brambleford-main", "brambleford-cust", "brambleford-emp",
    "workbench-viewer", "spec-starter", "owner-attention",
    "scheduler-cron",
]
ACTIVE = {"brambleford-main", "brambleford-cust", "brambleford-emp"}

TOKEN_CALLERS = {
    "home-bridge": ["bridge", "read"],
    "sweeper-venue": ["read", "send", "write-state"],
    "local-test-watch": ["send"],
    "attention-dispatch": ["send"],
}

MAIN_CHAT = "00000000-0000-4000-8000-000000000001"
SCHEDULER_CHAT = "00000000-0000-4000-8000-000000000002"


def _genericized_seed():
    """The census's seed: the capture's store data with
    its caller names renamed to the stand-ins above.

    The held capture carries the original names as
    written — curing them would falsify the copies — and
    no tracked file names them, so the correspondence
    is positional: the capture's caller list and
    THREAD_CALLERS stand in the same order, suffix for
    suffix (a desync fails the census loudly, here or at
    the set and routing assertions). Every caller-keyed
    table in the seed is renamed through the same map,
    the restart table's family prefixes through the
    family half of it. The capture files and the seed
    module's verbatim build are untouched."""
    data = seed.seed_from_capture(HOLDING)
    captured = data["thread_callers"]["callers"]
    if len(captured) != len(THREAD_CALLERS):
        raise AssertionError(
            f"capture carries {len(captured)} thread callers; "
            f"the census lists {len(THREAD_CALLERS)} stand-ins")
    rename = {}
    families = {}
    for original, standin in zip(captured, THREAD_CALLERS):
        rename[original] = standin
        if "-" in original and "-" in standin:
            head_o, tail_o = original.split("-", 1)
            head_s, tail_s = standin.split("-", 1)
            if tail_o != tail_s:
                raise AssertionError(
                    f"stand-in order desync: {original!r} "
                    f"paired with {standin!r}")
            fam_o, fam_s = head_o + "-", head_s + "-"
            if families.setdefault(fam_o, fam_s) != fam_s:
                raise AssertionError(
                    f"family rename desync at {original!r}")
    thread = data["thread_callers"]
    thread["callers"] = [rename[name] for name in thread["callers"]]
    thread["active"] = [rename[name] for name in thread["active"]]

    def renamed(table):
        if isinstance(table, dict):
            return {rename.get(key, families.get(key, key)): row
                    for key, row in table.items()}
        return table

    routing_seed = data["routing"]
    wake = routing_seed["bridge_wake_owners"]
    wake["owners"] = renamed(wake.get("owners"))
    notify = routing_seed["notify_routes"]
    notify["routes"] = renamed(notify.get("routes"))
    restart = routing_seed["restart_owners"]
    for part in ("owners", "namespaces", "prefixes"):
        restart[part] = renamed(restart.get(part))
    return data


class CensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = Registry(_genericized_seed())

    def test_every_captured_thread_caller_validates(self):
        self.assertEqual(
            callers.caller_bases(self.registry),
            set(callers.MACHINERY_CALLERS) | set(THREAD_CALLERS))
        for name in THREAD_CALLERS:
            self.assertEqual(
                callers.validate_claim(self.registry, name), name)
            self.assertEqual(
                callers.validate_claim(
                    self.registry, f"{name}:lane-1"),
                f"{name}:lane-1")

    def test_active_set_matches_capture(self):
        self.assertEqual(callers.active_bases(self.registry), ACTIVE)
        for name in ACTIVE:
            self.assertTrue(callers.is_active(self.registry, name))

    def test_connector_callers_validate_with_scopes(self):
        clean = tokens.load_token_callers(self.registry)
        self.assertEqual(sorted(clean), sorted(TOKEN_CALLERS))
        for name, scopes in TOKEN_CALLERS.items():
            self.assertEqual(
                sorted(clean[name]["scopes"]), scopes)
            self.assertRegex(clean[name]["token_sha256"],
                             r"^[0-9a-f]{64}$")

    def test_routing_tables_resolve_as_captured(self):
        reg = self.registry
        self.assertEqual(routing.wake_owner(reg, "sweeper-venue"),
                         "00000000-0000-4000-8000-000000000003")
        self.assertEqual(routing.wake_drain(reg), SCHEDULER_CHAT)
        self.assertIsNone(routing.wake_owner(reg, "aldergrove-xbrl"))
        self.assertEqual(routing.notify_route(reg, "aldergrove-xbrl"),
                         "00000000-0000-4000-8000-000000000004")
        self.assertEqual(routing.notify_route(reg, "panel"),
                         "00000000-0000-4000-8000-000000000005")
        self.assertEqual(routing.notify_route(reg, "scheduler-cron"),
                         MAIN_CHAT)
        self.assertEqual(routing.restart_owner(reg, "brambleford-main"),
                         "00000000-0000-4000-8000-000000000006")
        self.assertEqual(routing.restart_owner(reg, "brambleford-cust"),
                         "00000000-0000-4000-8000-000000000006")
        self.assertEqual(routing.restart_owner(reg, "scheduler-cron"),
                         SCHEDULER_CHAT)
        self.assertEqual(
            routing.restart_owner(reg, "aldergrove-successor:lane-3"),
            "00000000-0000-4000-8000-000000000007")
        self.assertIsNone(routing.restart_owner(reg, "pinehollow-monitor"))

    def test_directory_rows_validate_and_resolve(self):
        handlers = self.registry.handlers()
        programmes = self.registry.programmes()
        self.assertEqual(len(handlers), 10)
        self.assertEqual(len(programmes), 3)
        for row in handlers:
            self.assertEqual(directory.validate_handler_row(row),
                             [], row.get("handle"))
        for row in programmes:
            self.assertEqual(directory.validate_programme_row(row),
                             [], row.get("slug"))
            for handle in row.get("handles") or []:
                self.assertIsNotNone(
                    directory.handler_for(self.registry, handle),
                    f"{row['slug']} -> {handle}")

    def test_export_round_trips_the_forms(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            written = seed.export_forms(self.registry, tmp)
            self.assertEqual(len(written), 7)
            import json
            callers_form = json.loads(
                (Path(tmp) / "callers.json").read_text())
            self.assertEqual(callers_form["callers"], THREAD_CALLERS)
            handlers = json.loads(
                (Path(tmp) / "handlers.json").read_text())
            self.assertEqual(len(handlers), 10)
            wake = seed._read_yaml(Path(tmp) / "bridge-wake-owners.yaml")
            self.assertEqual(wake["owners"]["sweeper-venue"]["chat"],
                             "00000000-0000-4000-8000-000000000003")
            self.assertEqual(wake["drain"]["chat"], SCHEDULER_CHAT)
            restart = seed._read_yaml(
                Path(tmp) / "restart-reconcile-owners.yaml")
            self.assertEqual(
                restart["prefixes"]["brambleford-"]["chat"],
                "00000000-0000-4000-8000-000000000006")

    def test_seed_examples_build_the_fictional_form(self):
        registry = Registry(seed.seed_from_examples(FIXTURES))
        self.assertEqual(
            callers.validate_claim(registry, "alpha-thread"),
            "alpha-thread")
        self.assertEqual(len(registry.handlers()), 1)
        self.assertEqual(len(registry.programmes()), 1)
        for row in registry.handlers():
            self.assertEqual(directory.validate_handler_row(row), [])
        for row in registry.programmes():
            self.assertEqual(directory.validate_programme_row(row), [])


if __name__ == "__main__":
    unittest.main()
