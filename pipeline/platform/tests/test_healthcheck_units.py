"""The health probe's per-unit form (the survival
build, 2026-11-15): --unit probes only the surfaces the
named systemd unit serves, and its verdict carries the
unit name, so a per-unit watchdog ladder confirms
against its own unit's surfaces — never through another
unit's. The whole-fleet form (no argument) keeps the
original conjunctive verdict and shape.

The probe's transport is stubbed at the module's own
_get seam with fixture payloads in each surface's served
shape, so the pin is the mapping and the verdict form —
no live server, no timing.
"""

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parents[1] / "ops"


def _load_healthcheck():
    spec = importlib.util.spec_from_file_location(
        "workhorse_healthcheck", OPS_DIR / "healthcheck.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Fixture payloads, one per surface, in the served
# shapes the probe's health predicates read.
FIXTURES = {
    "8796": (200, {"status": "ok", "state_error": None}),
    "8792": (200, {"ok": True}),
    "8797": (200, {"status": "ok"}),
    "8793": (200, {"events": []}),
}


def _fixture_get(fixtures):
    def _get(url):
        for port, payload in fixtures.items():
            if f":{port}/" in url:
                return payload
        raise AssertionError(f"unfixtured url: {url}")
    return _get


def _run(module, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main(argv)
    return code, json.loads(out.getvalue())


class PerUnitMappingTests(unittest.TestCase):
    def setUp(self):
        self.healthcheck = _load_healthcheck()
        self.healthcheck._get = _fixture_get(FIXTURES)

    def test_workhorse_probes_the_coupled_pair(self):
        code, verdict = _run(
            self.healthcheck, ["--unit", "workhorse"])
        self.assertEqual(code, 0)
        self.assertEqual(verdict["unit"], "workhorse")
        self.assertTrue(verdict["ok"])
        self.assertEqual(
            [v["surface"] for v in verdict["surfaces"]],
            ["scheduling", "attention"])

    def test_workbench_probes_only_the_workbench(self):
        code, verdict = _run(
            self.healthcheck, ["--unit", "workbench"])
        self.assertEqual(code, 0)
        self.assertEqual(verdict["unit"], "workbench")
        self.assertEqual(
            [v["surface"] for v in verdict["surfaces"]],
            ["workbench"])

    def test_venue_probes_only_the_lease_panel(self):
        code, verdict = _run(
            self.healthcheck, ["--unit", "venue"])
        self.assertEqual(code, 0)
        self.assertEqual(verdict["unit"], "venue")
        self.assertEqual(
            [v["surface"] for v in verdict["surfaces"]],
            ["lease-panel"])

    def test_whole_fleet_form_is_unchanged(self):
        code, verdict = _run(self.healthcheck, [])
        self.assertEqual(code, 0)
        self.assertNotIn("unit", verdict)
        self.assertEqual(
            [v["surface"] for v in verdict["surfaces"]],
            ["scheduling", "workbench", "attention",
             "lease-panel"])


class PerUnitVerdictTests(unittest.TestCase):
    def setUp(self):
        self.healthcheck = _load_healthcheck()

    def test_a_unit_verdict_ignores_other_units(self):
        # Scheduling is down; the venue ladder's verdict
        # must not read through it.
        fixtures = dict(FIXTURES)
        fixtures["8796"] = (200, {"status": "down",
                                   "state_error": "boom"})
        self.healthcheck._get = _fixture_get(fixtures)
        code, verdict = _run(
            self.healthcheck, ["--unit", "venue"])
        self.assertEqual(code, 0)
        self.assertTrue(verdict["ok"])
        code, verdict = _run(
            self.healthcheck, ["--unit", "workhorse"])
        self.assertEqual(code, 1)
        self.assertFalse(verdict["ok"])

    def test_unhealthy_payload_fails_its_unit(self):
        fixtures = dict(FIXTURES)
        fixtures["8792"] = (200, {"ok": False})
        self.healthcheck._get = _fixture_get(fixtures)
        code, verdict = _run(
            self.healthcheck, ["--unit", "workbench"])
        self.assertEqual(code, 1)
        self.assertFalse(verdict["surfaces"][0]["ok"])

    def test_a_refused_probe_names_the_surface(self):
        def _get(url):
            raise ConnectionError("refused")
        self.healthcheck._get = _get
        code, verdict = _run(
            self.healthcheck, ["--unit", "workbench"])
        self.assertEqual(code, 1)
        surface = verdict["surfaces"][0]
        self.assertEqual(surface["surface"], "workbench")
        self.assertFalse(surface["ok"])
        self.assertIn("ConnectionError", surface["error"])


if __name__ == "__main__":
    unittest.main()
