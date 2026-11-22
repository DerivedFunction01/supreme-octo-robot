"""The S7 done-evidence census: the merged registry,
seeded from an S1-shaped overlay capture (never from
tracked examples), validates every caller the captured
registries carry — the runner thread callers, the
connector token callers, both routing tables of contract
01 (plus the restart-reconcile table), and the handler /
programme directory rows.

The capture the census consumes is a fixture this suite
builds in its own scratch (see _write_fixture_capture):
the live holding (docs/overlay/holding) is untracked
operator state and exists only where an operator captured
it, so a suite that read it failed in every clean clone.
The fixture carries the capture's exact directory layout
and file forms with invented names and values, sized and
shaped so every assertion below keeps its meaning; the
production seed-capture path still reads the live holding
through the seed CLI — it is not a test input.
"""

import json
import tempfile
import unittest
from pathlib import Path

from registry import seed
from registry.attention import directory
from registry.callers import callers, routing, tokens
from registry.store import Registry

REPO_ROOT = Path(__file__).resolve().parents[3]
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

# The fixture capture's thread callers, in the capture's
# own invented names: positionally paired with
# THREAD_CALLERS, suffix for suffix, family head for
# family head, exactly as the held capture paired with
# the stand-ins when the census was written against it.
CAPTURED_CALLERS = [
    "cap-xbrl", "capforms", "cap-remplan", "cap-packaging",
    "cap-era-attribution", "cap-successor", "cap-formation",
    "pine-monitor", "bram-main", "bram-cust", "bram-emp",
    "wb-viewer", "ss-starter", "oa-attention", "sc-cron",
]
CAPTURED_ACTIVE = ["bram-main", "bram-cust", "bram-emp"]

WAKE_CHAT = "00000000-0000-4000-8000-000000000003"
NOTIFY_XBRL_CHAT = "00000000-0000-4000-8000-000000000004"
NOTIFY_PANEL_CHAT = "00000000-0000-4000-8000-000000000005"
RESTART_FAMILY_CHAT = "00000000-0000-4000-8000-000000000006"
RESTART_NAMESPACE_CHAT = "00000000-0000-4000-8000-000000000007"


def _write_fixture_capture(holding):
    """Build the S1 capture's directory shape in scratch:
    every file seed_from_capture reads, in its held form,
    with invented values carrying the census's assertions.

    - colab-runner/config/callers.json: the 15 thread
      callers above, the brambleford three active.
    - scheduler/config.json: the connector token callers
      of TOKEN_CALLERS, hashes only (invented digests).
    - scheduler/bodies/bridge-wake-owners.yaml: the
      sweeper-venue wake owner and the drain chat; no
      entry for the xbrl caller (unresolved by design).
    - colab-runner/config/notify-routes.json: routes for
      the xbrl caller, the panel, and the scheduler
      caller, with MAIN_CHAT as the table's main.
    - scheduler/bodies/restart-reconcile-owners.yaml:
      the scheduler caller as an exact owner, the
      successor caller as a namespace, the brambleford
      family as a prefix; the monitor caller in none.
    - owner-attention/var/data/state.json: 10 handler
      rows and 3 programme rows, programme handles
      resolving against the handlers.
    """
    holding = Path(holding)

    def put(rel, text):
        path = holding / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def put_json(rel, data):
        put(rel, json.dumps(data, indent=2) + "\n")

    put_json("colab-runner/config/callers.json", {
        "callers": CAPTURED_CALLERS,
        "active": CAPTURED_ACTIVE,
    })
    put_json("scheduler/config.json", {
        "connector": {"callers": {
            "home-bridge": {
                "token_sha256": "a" * 64,
                "scopes": ["bridge", "read"]},
            "sweeper-venue": {
                "token_sha256": "b" * 64,
                "scopes": ["read", "send", "write-state"]},
            "local-test-watch": {
                "token_sha256": "c" * 64,
                "scopes": ["send"]},
            "attention-dispatch": {
                "token_sha256": "d" * 64,
                "scopes": ["send"]},
        }},
    })
    put("scheduler/bodies/bridge-wake-owners.yaml",
        "version: 1\n"
        "owners:\n"
        "  sweeper-venue:\n"
        f'    chat: "{WAKE_CHAT}"\n'
        "drain:\n"
        f'  chat: "{SCHEDULER_CHAT}"\n')
    put_json("colab-runner/config/notify-routes.json", {
        "main": MAIN_CHAT,
        "routes": {
            "cap-xbrl": NOTIFY_XBRL_CHAT,
            "panel": NOTIFY_PANEL_CHAT,
            "sc-cron": MAIN_CHAT,
        },
    })
    put("scheduler/bodies/restart-reconcile-owners.yaml",
        "owners:\n"
        "  sc-cron:\n"
        f'    chat: "{SCHEDULER_CHAT}"\n'
        "namespaces:\n"
        "  cap-successor:\n"
        f'    chat: "{RESTART_NAMESPACE_CHAT}"\n'
        "prefixes:\n"
        "  bram-:\n"
        f'    chat: "{RESTART_FAMILY_CHAT}"\n')
    handlers = [{
        "handle": f"fixture-handler-{n:02d}",
        "label": f"Fixture handler {n:02d}",
    } for n in range(1, 11)]
    programmes = [{
        "slug": f"fixture-programme-{part}",
        "label": f"Fixture programme {part}",
        "handles": handles,
        "venue": "none",
    } for part, handles in (
        ("a", ["fixture-handler-01", "fixture-handler-02"]),
        ("b", ["fixture-handler-03"]),
        ("c", []),
    )]
    put_json("owner-attention/var/data/state.json", {
        "handlers": handlers,
        "programmes": programmes,
    })
    return holding


def _genericized_seed(holding):
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
    data = seed.seed_from_capture(holding)
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
        cls._holding = tempfile.TemporaryDirectory()
        cls.registry = Registry(_genericized_seed(
            _write_fixture_capture(cls._holding.name)))

    @classmethod
    def tearDownClass(cls):
        cls._holding.cleanup()

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
